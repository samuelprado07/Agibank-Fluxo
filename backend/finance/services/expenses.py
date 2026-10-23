from calendar import monthrange
from datetime import date, timedelta

from django.db import transaction

from finance.forms import ExpenseForm
from finance.models import ExpenseHistory, ExpenseSeries, ExpenseSeriesExclusion, ExpenseSeriesRevision, Movement, Occurrence
from .recurrences import effective_values, ensure_occurrences, month_of


def validate_expense(payload, instance=None):
    errors = {}
    allowed = set(ExpenseForm.Meta.fields) | ({"scope", "due_day"} if instance else {"recurring", "end_date"})
    for key in payload.keys() - allowed:
        errors[key] = ["Campo não permitido nesta operação."]
    for key in ("description", "amount", "category", "due_date"):
        if key in payload and not isinstance(payload[key], str):
            errors[key] = ["Informe um texto. Valores monetários devem ser enviados como texto decimal."]
    if "essential" in payload and type(payload["essential"]) is not bool:
        errors["essential"] = ["Informe verdadeiro ou falso."]
    if "is_estimate" in payload and type(payload["is_estimate"]) is not bool:
        errors["is_estimate"] = ["Informe verdadeiro ou falso."]
    if "essential" not in payload and instance is None:
        errors["essential"] = ["Informe se a despesa é essencial."]
    if "recurring" in payload and type(payload["recurring"]) is not bool:
        errors["recurring"] = ["Informe verdadeiro ou falso."]
    if "end_date" in payload and payload["end_date"] is not None and not isinstance(payload["end_date"], str):
        errors["end_date"] = ["Informe uma data em texto ou deixe o término em branco."]
    if payload.get("scope", "this") not in ("this", "following"):
        errors["scope"] = ["Escolha somente esta ocorrência ou esta e as próximas."]
    if instance and payload.get("scope") == "following" and not instance.series_id:
        errors["scope"] = ["Esta despesa não pertence a uma série mensal."]
    if "due_day" in payload and (type(payload["due_day"]) is not int or not 1 <= payload["due_day"] <= 31 or payload.get("scope") != "following"):
        errors["due_day"] = ["Informe um dia de 1 a 31 somente para edição da série."]
    if errors:
        return None, errors
    values = {**snapshot(instance), **payload} if instance else payload
    form = ExpenseForm(values)
    if not form.is_valid():
        return None, {key: list(value) for key, value in form.errors.items()}
    if instance is None and payload.get("end_date"):
        try:
            end = date.fromisoformat(payload["end_date"])
            if end < form.cleaned_data["due_date"]:
                errors["end_date"] = ["O término não pode ser anterior ao primeiro vencimento."]
            if not payload.get("recurring"):
                errors["end_date"] = ["O término só se aplica a despesas mensais."]
        except (TypeError, ValueError):
            errors["end_date"] = ["Informe uma data de término válida."]
    if instance and payload.get("scope") == "following" and month_of(form.cleaned_data["due_date"]) != instance.competence:
        errors["due_date"] = ["Para editar a série, mantenha o mês de competência e ajuste apenas o dia. Para mover só esta conta, escolha somente esta ocorrência."]
    if "due_day" in payload:
        form.cleaned_data["due_day"] = payload["due_day"]
    return (None, errors) if errors else (form, {})


@transaction.atomic
def create_expense(scenario, form, payload=None):
    payload = payload or {}
    if payload.get("recurring"):
        series = ExpenseSeries.objects.create(scenario=scenario, description=form.cleaned_data["description"], amount=form.cleaned_data["amount"], category=form.cleaned_data["category"], essential=form.cleaned_data["essential"], is_estimate=form.cleaned_data["is_estimate"], start_date=form.cleaned_data["due_date"], due_day=form.cleaned_data["due_date"].day, end_date=date.fromisoformat(payload["end_date"]) if payload.get("end_date") else None)
        ensure_occurrences(scenario, max(series.start_date, scenario.reference_date + timedelta(days=59)))
        return series.occurrences.order_by("competence").first()
    expense = form.save(commit=False)
    expense.scenario = scenario
    expense.direction = Occurrence.Direction.EXPENSE
    expense.status = Occurrence.Status.PENDING
    expense.full_clean()
    expense.save()
    return expense


def snapshot(expense):
    return {"description": expense.description, "amount": str(expense.amount), "category": expense.category, "due_date": expense.due_date.isoformat(), "essential": expense.essential, "is_estimate": expense.is_estimate, "status": expense.status, "is_exception": expense.is_exception}


def is_paid_or_linked(expense):
    return expense.status == "settled" or Movement.objects.filter(occurrence=expense, is_voided=False).exists()


class ExpenseConflict(Exception):
    pass


def require_editable(expense):
    if is_paid_or_linked(expense):
        raise ExpenseConflict("Despesa com pagamento associado está protegida. Alterações exigem o fluxo de correção do pagamento.")
    if expense.status != "pending":
        raise ExpenseConflict("Somente despesas pendentes podem ser alteradas ou canceladas.")


def record_change(expense, action, before):
    after = snapshot(expense)
    if before != after:
        ExpenseHistory.objects.create(occurrence=expense, action=action, before=before, after=after)


@transaction.atomic
def edit_expense(expense, form, scope):
    require_editable(expense)
    values = form.cleaned_data
    targets = [expense]
    if scope == "following":
        series = ExpenseSeries.objects.select_for_update().get(pk=expense.series_id)
        revision = {key: str(values[key]) if key == "amount" else values[key] for key in ("description", "amount", "category", "essential", "is_estimate")}
        revision["day"] = values.get("due_day", effective_values(series, expense.competence)["day"] if values["due_date"] == expense.due_date else values["due_date"].day)
        ExpenseSeriesRevision.objects.create(series=series, effective_from=expense.competence, values=revision)
        targets = list(series.occurrences.select_for_update().filter(competence__gte=expense.competence, status="pending").order_by("competence"))
    for target in targets:
        if is_paid_or_linked(target) or (scope == "following" and target.is_exception and target.pk != expense.pk):
            continue
        before = snapshot(target)
        for key in ("description", "amount", "category", "essential", "is_estimate"):
            setattr(target, key, values[key])
        target.due_date = date(target.competence.year, target.competence.month, min(revision["day"], monthrange(target.competence.year, target.competence.month)[1])) if scope == "following" else values["due_date"]
        if scope == "this" and target.series_id:
            target.is_exception = True
        target.full_clean()
        target.save()
        record_change(target, "edit", before)
    expense.refresh_from_db()
    return expense


@transaction.atomic
def cancel_expense(expense, scope):
    require_editable(expense)
    if scope == "following" and not expense.series_id:
        raise ExpenseConflict("Esta despesa não pertence a uma série mensal.")
    targets = [expense]
    if scope == "following":
        series = ExpenseSeries.objects.select_for_update().get(pk=expense.series_id)
        series.cancelled_from = min(series.cancelled_from, expense.competence) if series.cancelled_from else expense.competence
        series.save(update_fields=["cancelled_from"])
        targets = series.occurrences.select_for_update().filter(competence__gte=expense.competence, status="pending")
    for target in targets:
        if is_paid_or_linked(target):
            continue
        before = snapshot(target)
        target.status = "cancelled"
        target.is_exception = bool(target.series_id)
        target.save(update_fields=["status", "is_exception"])
        record_change(target, "cancel", before)
    expense.refresh_from_db()
    return expense


@transaction.atomic
def delete_expense(expense):
    if Movement.objects.filter(occurrence=expense).exists() or is_paid_or_linked(expense) or expense.status == "cancelled" or expense.history.exists():
        raise ExpenseConflict("Despesa com histórico de pagamento, edição ou cancelamento não pode ser excluída.")
    if expense.series_id:
        # Remember a removed month so consultation cannot recreate it.
        ExpenseSeriesExclusion.objects.get_or_create(series_id=expense.series_id, competence=expense.competence)
    expense.delete()


def serialize_expense(expense):
    linked = Movement.objects.filter(occurrence=expense).first()
    active = linked is not None and not linked.is_voided
    return {
        "id": expense.pk,
        "description": expense.description,
        "amount": expense.amount,
        "category": expense.category,
        "due_date": expense.due_date,
        "essential": expense.essential,
        "is_estimate": expense.is_estimate,
        "status": expense.status,
        "recurring": bool(expense.series_id),
        "series_id": expense.series_id,
        "series_day": effective_values(expense.series, expense.competence)["day"] if expense.series_id else None,
        "competence": expense.competence,
        "is_exception": expense.is_exception,
        "end_date": expense.series.end_date if expense.series_id else None,
        "can_edit": expense.status == "pending" and not active,
        "can_pay": expense.status == "pending" and not active,
        "can_correct_payment": expense.status == "settled" and active,
        "payment_version": linked.version if linked else 0,
        "can_delete": expense.status == "pending" and linked is None and not expense.history.exists(),
        "payment": {"amount": linked.amount, "date": linked.date} if active else None,
    }
