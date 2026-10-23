from datetime import timedelta
from decimal import Decimal

from django.db import transaction

from finance.models import Occurrence, Scenario
from .projection import ASSUMPTION_DETAILS, project
from .recurrences import ensure_occurrences, missing_occurrences
from .income_recurrences import ensure_income_occurrences, missing_income_occurrences
from .alerts import attach_relevant_incomes
from .projection_version import projection_version

ZERO = Decimal("0.00")


@transaction.atomic
def capture_projection(scenario_id, *, materialize=True):
    # SQLite IMMEDIATE protects generation and all inputs from competing writes.
    scenario = Scenario.objects.get(pk=scenario_id)
    reference = scenario.reference_date
    if scenario.opening_date > reference:
        raise ValueError("A data de abertura não pode ser posterior à referência.")
    horizon = reference + timedelta(days=59)
    if materialize:
        ensure_occurrences(scenario, horizon)
        ensure_income_occurrences(scenario, horizon)
    movements = list(scenario.movements.select_related("occurrence").filter(is_voided=False))
    occurrences = list(scenario.occurrences.all())
    if not materialize:
        virtual = missing_occurrences(scenario, horizon) + missing_income_occurrences(scenario, horizon)
        # Virtual IDs follow all persisted IDs and the same generation order.
        # They are only calculation identities, never accepted as edit targets.
        highest = Occurrence.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
        for offset, occurrence in enumerate(virtual, 1):
            occurrence.pk = highest + offset
            occurrence.amount = Decimal(occurrence.amount)
        occurrences.extend(virtual)
    return scenario, movements, occurrences


def build_dashboard(scenario):
    scenario, movements, occurrences = capture_projection(scenario.pk)
    return build_from_snapshot(scenario, movements, occurrences)


def build_from_snapshot(scenario, movements, occurrences, *, fixed_end=None):
    reference = scenario.reference_date
    warnings = []
    linked = {}
    balance = scenario.opening_balance
    realized_income = realized_expenses = ZERO
    for movement in movements:
        if movement.amount <= 0 or movement.direction not in ("income", "expense"):
            warnings.append(f"Movimentação inválida excluída: {movement.description}.")
            continue
        if movement.occurrence_id and (movement.occurrence.scenario_id != scenario.pk or movement.direction != movement.occurrence.direction):
            warnings.append(f"Vínculo inconsistente excluído: {movement.description}.")
            continue
        if movement.date > reference:
            warnings.append(f"Movimentação realizada com data futura excluída: {movement.description}.")
            continue
        if movement.occurrence_id:
            linked[movement.occurrence_id] = movement
        if movement.date >= scenario.opening_date:
            balance += movement.amount if movement.direction == "income" else -movement.amount
            if movement.direction == "income":
                realized_income += movement.amount
            else:
                realized_expenses += movement.amount

    pending = []
    overdue_incomes = []
    for occurrence in occurrences:
        if occurrence.pk in linked:
            if occurrence.status != "settled":
                warnings.append(f"Revise a situação de {occurrence.description}: já possui movimentação vinculada; previsão não repetida.")
            continue
        if occurrence.status == "settled":
            warnings.append(f"Lançamento pago ou recebido sem movimentação: {occurrence.description}.")
            continue
        if occurrence.status == "cancelled":
            continue
        if occurrence.status != "pending" or occurrence.direction not in ("income", "expense") or occurrence.amount <= 0:
            warnings.append(f"Lançamento inválido excluído: {occurrence.description}.")
            continue
        if occurrence.direction == "income" and occurrence.due_date < reference:
            overdue_incomes.append({"id": occurrence.pk, "description": occurrence.description, "amount": occurrence.amount, "date": occurrence.due_date})
            warnings.append(f"Recebimento atrasado não incluído na projeção: {occurrence.description}.")
            continue
        pending.append(occurrence)

    limit = reference + timedelta(days=59)
    future_income = sorted((o for o in pending if o.direction == "income" and reference <= o.due_date <= limit), key=lambda o: (o.due_date, o.pk))
    next_income = future_income[0] if future_income else None
    end = fixed_end or (max(reference + timedelta(days=14), next_income.due_date) if next_income else limit)
    if not reference + timedelta(days=14) <= end <= limit:
        raise ValueError("O horizonte deve conter de 15 a 60 dias, incluindo a referência.")
    if not next_income:
        warnings.append(f"Próximo recebimento não informado na busca de 60 dias. Análise limitada a {(end - reference).days + 1} dias, incluindo a referência.")
    elif next_income.due_date > end:
        warnings.append("O próximo recebimento está após o período fixado da comparação. Comprometimento até essa renda e saldo próprio restante não são informados neste intervalo.")
    warnings.append("Gastos ausentes da simulação podem alterar os resultados, mesmo quando há estimativas cadastradas.")

    events = []
    essentials = []
    for occurrence in pending:
        if occurrence.due_date > end:
            continue
        effective = max(reference, occurrence.due_date)
        if occurrence.direction == "expense" and occurrence.due_date < reference:
            warnings.append(f"Despesa vencida considerada imediata: {occurrence.description} ({occurrence.due_date.isoformat()}).")
        event = {"id": occurrence.pk, "description": occurrence.description, "amount": occurrence.amount, "date": effective, "due_date": occurrence.due_date, "direction": occurrence.direction, "essential": occurrence.essential, "is_estimate": occurrence.is_estimate}
        event.update({"is_recurring": bool(occurrence.series_id or occurrence.income_series_id), "series_id": occurrence.series_id or occurrence.income_series_id,
                      "series_type": "expense" if occurrence.series_id else "income" if occurrence.income_series_id else None, "competence": occurrence.competence})
        events.append(event)
        if occurrence.direction == "expense" and occurrence.essential:
            essentials.append(event)

    committed = sum((e["amount"] for e in events if e["direction"] == "expense" and e["due_date"] <= next_income.due_date), ZERO) if next_income and next_income.due_date <= end else None
    days, alerts = project(balance, reference, end, events)
    income_data = lambda o: {"id": o.pk, "description": o.description, "amount": o.amount, "date": o.due_date, "status": "estimated", "outside_analysis": o.due_date > end}
    attach_relevant_incomes(alerts, [income_data(item) for item in future_income], days, end)
    result = {
        "scenario": {"name": scenario.name, "opening_date": scenario.opening_date},
        "reference_date": reference,
        "period": {"start": reference, "end": end, "chart_start": reference, "chart_end": reference + timedelta(days=14), "chart_days": 15, "analysis_days": (end - reference).days + 1, "maximum_days": 60},
        "current_balance_basis": {"opening_date": scenario.opening_date, "opening_balance": scenario.opening_balance,
                                  "reference_date": reference, "includes_reference_day": True, "realized_income": realized_income,
                                  "realized_expenses": realized_expenses, "current_balance": balance},
        "projection_policy": {"same_day_order": "expenses_then_income_then_id", "overdue_expenses": "immediate_at_reference",
                              "overdue_income": "excluded_until_confirmation_or_rescheduling", "reference_opening": "current_balance_after_realized",
                              "horizon": "at_least_15_days_through_next_income_or_60_days", "inclusive_dates": True},
        "assumption_details": dict(ASSUMPTION_DETAILS),
        "alert_policy": {"interval": "continuous_negative_steps", "zero_exit": "deficit_closed_without_margin", "same_day_zero_and_deficit": "separate_observations",
                         "expense_scope": "context_of_episode_dates", "income_dependency": "estimated_entries_reducing_the_observed_deficit"},
        "next_income": income_data(next_income) if next_income else None,
        "next_incomes": [income_data(item) for item in future_income if next_income and item.due_date == next_income.due_date],
        "overdue_incomes": overdue_incomes,
        "indicators": {
            "current_balance": balance,
            "pending_essential": sum((e["amount"] for e in essentials), ZERO),
            "committed": committed,
            "own_remaining": balance - committed if committed is not None else None,
            "projected_final": days[-1]["closing_balance"],
        },
        "days": days,
        "chart_days": days[:15],
        "alerts": alerts,
        "warnings": list(dict.fromkeys(warnings)),
        "assumptions": [
            "Projeção calculada a partir dos lançamentos cadastrados e da data de referência exibida.",
            "Saldo atual inclui apenas realizados desde o início da abertura até a referência, inclusive.",
            "Saídas previstas são consideradas antes de entradas previstas no mesmo dia; horários bancários não são simulados.",
            "Recebimentos futuros são estimados. A cobertura dos compromissos depende de sua ocorrência nas datas informadas.",
            "Valor comprometido é planejamento: não bloqueia dinheiro. Limites de crédito não compõem recursos próprios.",
            "Valor comprometido inclui todas as despesas pendentes até a próxima renda, inclusive nessa data, essenciais ou não e incluindo estimativas.",
            "Estimativas têm valor e data informados e não representam pagamentos realizados. Cada cadastro é um gasto adicional; ajuste ou cancele lançamentos sobrepostos.",
            "Cada mês tem sua própria ocorrência; dias inexistentes usam o último dia do mês, sem ajuste por feriados ou finais de semana.",
            "Saldo negativo representa necessidade estimada de recursos, sem autorização de pagamento.",
        ],
    }
    result['projection_version'] = projection_version(result)
    return result
