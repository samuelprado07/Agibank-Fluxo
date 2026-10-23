from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.db import transaction

from finance.models import IncomeHistory, IncomeSeries, IncomeSeriesHistory, IncomeSeriesRevision, Movement, Occurrence
from .income_recurrences import ensure_income_occurrences, monthly_date, series_values
from .recurrences import month_of


class IncomeError(Exception):
    def __init__(self, message, status=409, errors=None):
        super().__init__(message)
        self.status = status
        self.errors = errors or {}


class IncomeForm(forms.Form):
    description = forms.CharField(max_length=150)
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    expected_date = forms.DateField(input_formats=["%Y-%m-%d"])


def snapshot(income):
    return {"description": income.description, "amount": str(income.amount), "expected_date": income.due_date.isoformat(), "status": income.status, "is_exception": income.is_exception}


def validate_income(payload, income=None):
    allowed = {"description", "amount", "expected_date"} | ({"scope", "due_day"} if income else {"frequency", "end_date"})
    errors = {key: ["Campo não permitido nesta operação."] for key in payload.keys() - allowed}
    for key in ("description", "amount", "expected_date"):
        if key in payload and not isinstance(payload[key], str):
            errors[key] = ["Informe texto; valores monetários devem usar texto decimal."]
    if not income and payload.get("frequency") not in ("single", "monthly"):
        errors["frequency"] = ["Escolha única ou mensal."]
    scope = payload.get("scope", "this")
    if scope not in ("this", "following") or (scope == "following" and not (income and income.income_series_id)):
        errors["scope"] = ["Escolha um alcance válido para esta renda."]
    if "due_day" in payload and (type(payload["due_day"]) is not int or not 1 <= payload["due_day"] <= 31 or scope != "following"):
        errors["due_day"] = ["Use um dia de 1 a 31 para alterar esta e as próximas."]
    if errors:
        raise IncomeError("Confira os campos da renda.", 400, errors)
    form = IncomeForm({**(snapshot(income) if income else {}), **payload})
    if not form.is_valid():
        raise IncomeError("Confira os campos da renda.", 400, {key: list(value) for key, value in form.errors.items()})
    values = form.cleaned_data
    if income and scope == "following" and month_of(values["expected_date"]) != income.competence:
        raise IncomeError("Para reagendar para outro mês, edite somente esta ocorrência.", 400)
    if not income:
        end = payload.get("end_date")
        if end is not None:
            try:
                if payload["frequency"] != "monthly" or not isinstance(end, str):
                    raise ValueError
                end = date.fromisoformat(end)
                if end < values["expected_date"]:
                    raise ValueError
            except ValueError:
                raise IncomeError("Informe um término válido, a partir da primeira data esperada, apenas para renda mensal.", 400)
        values["end_date"] = end
    return values


def require_pending(income):
    if income.status != "pending" or Movement.objects.filter(occurrence=income, is_voided=False).exists():
        raise IncomeError("Somente previsões pendentes podem ser alteradas. Use a correção para recebimentos confirmados.")


@transaction.atomic
def create_income(scenario, payload):
    values = validate_income(payload)
    if payload["frequency"] == "monthly":
        series = IncomeSeries.objects.create(scenario=scenario, description=values["description"], amount=values["amount"], due_day=values["expected_date"].day, start_date=values["expected_date"], end_date=values["end_date"])
        ensure_income_occurrences(scenario, max(series.start_date, scenario.reference_date + timedelta(days=59)))
        return series.occurrences.order_by("competence").first()
    return Occurrence.objects.create(scenario=scenario, description=values["description"], amount=values["amount"], due_date=values["expected_date"], direction="income")


def record_change(income, action, before):
    after = snapshot(income)
    if before != after:
        IncomeHistory.objects.create(occurrence=income, action=action, before=before, after=after)


@transaction.atomic
def edit_income(income, payload):
    require_pending(income)
    values = validate_income(payload, income)
    scope = payload.get("scope", "this")
    targets = [income]
    if scope == "following":
        series = IncomeSeries.objects.select_for_update().get(pk=income.income_series_id)
        before = series_values(series, income.competence)
        day = payload.get("due_day", before["day"] if values["expected_date"] == income.due_date else values["expected_date"].day)
        revision = {"description": values["description"], "amount": str(values["amount"]), "day": day}
        IncomeSeriesRevision.objects.create(series=series, effective_from=income.competence, values=revision)
        IncomeSeriesHistory.objects.create(series=series, action="edit", before=before, after={**revision, "effective_from": income.competence.isoformat()})
        targets = series.occurrences.select_for_update().filter(competence__gte=income.competence, status="pending")
    for target in targets:
        if Movement.objects.filter(occurrence=target, is_voided=False).exists() or (scope == "following" and target.is_exception and target.pk != income.pk):
            continue
        old = snapshot(target)
        target.description = values["description"]
        target.amount = values["amount"]
        target.due_date = monthly_date(target.competence, day) if scope == "following" else values["expected_date"]
        if scope == "following" and (target.due_date < series.start_date or (series.end_date and target.due_date > series.end_date)):
            raise IncomeError("O novo dia moveria uma ocorrência para fora da vigência da renda mensal. Ajuste somente essa ocorrência para criar uma exceção.", 400)
        if scope == "this" and target.income_series_id:
            target.is_exception = True
        target.save()
        record_change(target, "edit", old)
    income.refresh_from_db()


@transaction.atomic
def cancel_income(income):
    require_pending(income)
    before = snapshot(income)
    income.status = "cancelled"
    income.is_exception = bool(income.income_series_id)
    income.save(update_fields=["status", "is_exception"])
    record_change(income, "cancel", before)


@transaction.atomic
def stop_income_series(series, payload):
    if payload.keys() - {"from_date", "cancel_pending"} or type(payload.get("cancel_pending")) is not bool:
        raise IncomeError("Informe a data de encerramento e se deseja cancelar previsões pendentes.", 400)
    try:
        cutoff = date.fromisoformat(payload.get("from_date", ""))
    except (ValueError, TypeError):
        raise IncomeError("Informe uma data válida para o encerramento.", 400)
    if cutoff < series.start_date:
        raise IncomeError("O encerramento não pode ser anterior ao início da renda mensal.", 400)
    before = {"cancelled_from": series.cancelled_from.isoformat() if series.cancelled_from else None}
    series.cancelled_from = min(series.cancelled_from, cutoff) if series.cancelled_from else cutoff
    series.save(update_fields=["cancelled_from"])
    if payload["cancel_pending"]:
        for income in series.occurrences.select_for_update().filter(status="pending", due_date__gte=cutoff):
            if not Movement.objects.filter(occurrence=income, is_voided=False).exists():
                cancel_income(income)
    IncomeSeriesHistory.objects.create(series=series, action="stop", before=before, after={"cancelled_from": series.cancelled_from.isoformat(), "from_date": cutoff.isoformat(), "cancel_pending": payload["cancel_pending"]})


def serialize_income(income, reference):
    movement = Movement.objects.filter(occurrence=income).first()
    active = movement is not None and not movement.is_voided
    series = income.income_series
    return {"id": income.pk, **snapshot(income), "overdue": income.status == "pending" and not active and income.due_date < reference,
            "frequency": "monthly" if series else "single", "series_id": income.income_series_id, "competence": income.competence,
            "series_day": series_values(series, income.competence)["day"] if series else None,
            "series_start": series.start_date if series else None, "series_end": series.end_date if series else None,
            "series_cancelled_from": series.cancelled_from if series else None,
            "can_edit": income.status == "pending" and not active, "can_receive": income.status == "pending" and not active,
            "can_correct_receipt": income.status == "settled" and active, "receipt_version": movement.version if movement else 0,
            "receipt": {"amount": movement.amount, "date": movement.date} if active else None}
