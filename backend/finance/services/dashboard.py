from datetime import timedelta
from decimal import Decimal

from .projection import project
from .recurrences import ensure_occurrences

ZERO = Decimal("0.00")


def build_dashboard(scenario):
    reference = scenario.reference_date
    if scenario.opening_date > reference:
        raise ValueError("A data de abertura não pode ser posterior à referência.")
    ensure_occurrences(scenario, reference + timedelta(days=59))
    warnings = []
    movements = list(scenario.movements.select_related("occurrence").filter(is_voided=False))
    occurrences = list(scenario.occurrences.all())
    linked = {}
    balance = scenario.opening_balance
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

    pending = []
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
            warnings.append(f"Recebimento atrasado não incluído na projeção: {occurrence.description}.")
            continue
        pending.append(occurrence)

    limit = reference + timedelta(days=59)
    future_income = sorted((o for o in pending if o.direction == "income" and reference <= o.due_date <= limit), key=lambda o: (o.due_date, o.pk))
    next_income = future_income[0] if future_income else None
    end = max(reference + timedelta(days=14), next_income.due_date) if next_income else limit
    if not next_income:
        warnings.append("Próximo recebimento não informado neste horizonte. Análise limitada a 60 dias, incluindo a referência.")
    if not scenario.variable_expenses_included:
        warnings.append("Gastos variáveis não estão integralmente representados; despesas ausentes podem alterar os resultados.")

    events = []
    essentials = []
    for occurrence in pending:
        if occurrence.due_date > end:
            continue
        effective = max(reference, occurrence.due_date)
        if occurrence.direction == "expense" and occurrence.due_date < reference:
            warnings.append(f"Despesa vencida considerada imediata: {occurrence.description} ({occurrence.due_date.isoformat()}).")
        event = {"id": occurrence.pk, "description": occurrence.description, "amount": occurrence.amount, "date": effective, "due_date": occurrence.due_date, "direction": occurrence.direction, "essential": occurrence.essential}
        events.append(event)
        if occurrence.direction == "expense" and occurrence.essential:
            essentials.append(event)

    committed = sum((e["amount"] for e in essentials if e["due_date"] <= next_income.due_date), ZERO) if next_income else None
    days, alerts = project(balance, reference, end, events)
    income_data = lambda o: {"description": o.description, "amount": o.amount, "date": o.due_date, "status": "estimated"}
    for alert in alerts:
        relevant = next((o for o in future_income if o.due_date >= alert["date"]), None)
        alert["next_income"] = income_data(relevant) if relevant else None
    return {
        "scenario": {"name": scenario.name, "opening_date": scenario.opening_date},
        "reference_date": reference,
        "period": {"start": reference, "end": end, "chart_end": reference + timedelta(days=14), "maximum_days": 60},
        "next_income": income_data(next_income) if next_income else None,
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
            "Cada mês tem sua própria ocorrência; dias inexistentes usam o último dia do mês, sem ajuste por feriados ou finais de semana.",
            "Saldo negativo representa necessidade estimada de recursos, sem autorização de pagamento.",
        ],
    }
