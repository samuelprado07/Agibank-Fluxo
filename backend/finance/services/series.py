from calendar import monthrange
from datetime import date
from decimal import Decimal

from django import forms
from django.db import transaction

from finance.models import ExpenseSeries, ExpenseSeriesHistory, ExpenseSeriesRevision
from .expenses import is_paid_or_linked, record_change, snapshot
from .recurrences import effective_values, month_of


class SeriesForm(forms.Form):
    description = forms.CharField(max_length=150)
    amount = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    category = forms.CharField(max_length=60, required=False)
    essential = forms.BooleanField(required=False)
    due_day = forms.IntegerField(min_value=1, max_value=31)
    end_date = forms.DateField(required=False)


def series_snapshot(series):
    return {"start_date": series.start_date.isoformat(), "end_date": series.end_date.isoformat() if series.end_date else None, "cancelled_from": series.cancelled_from.isoformat() if series.cancelled_from else None}


def serialize_series(series, reference):
    values = effective_values(series, month_of(max(reference, series.start_date)))
    state = "active"
    if series.cancelled_from:
        state = "stopped" if series.cancelled_from <= reference else "scheduled_stop"
    elif series.end_date and series.end_date < reference:
        state = "ended"
    next_occurrence = series.occurrences.filter(status="pending", due_date__gte=reference).order_by("due_date", "pk").first()
    next_change = None
    for future_month in sorted(set(series.revisions.filter(effective_from__gt=month_of(reference)).values_list("effective_from", flat=True))):
        future = effective_values(series, future_month)
        if future != values:
            next_change = {"date": future_month, "amount": f'{Decimal(future["amount"]):.2f}', "due_day": future["day"]}
            break
    return {"id": series.pk, "description": values["description"], "amount": f'{Decimal(values["amount"]):.2f}', "category": values["category"], "essential": values["essential"], "due_day": values["day"], "start_date": series.start_date, "end_date": series.end_date, "cancelled_from": series.cancelled_from, "generation_status": state, "pending_count": series.occurrences.filter(status="pending").count(), "next_due_date": next_occurrence.due_date if next_occurrence else None, "next_change": next_change}


def validate_series(series, payload, reference):
    errors = {}
    allowed = set(SeriesForm.base_fields) | {"effective_from"}
    for key in payload.keys() - allowed:
        errors[key] = ["Campo não permitido. O início da série é preservado."]
    for key in ("description", "amount", "category"):
        if key in payload and not isinstance(payload[key], str):
            errors[key] = ["Informe um texto; valores monetários usam texto decimal."]
    if "essential" in payload and type(payload["essential"]) is not bool:
        errors["essential"] = ["Informe verdadeiro ou falso."]
    if "due_day" in payload and type(payload["due_day"]) is not int:
        errors["due_day"] = ["Informe um dia inteiro entre 1 e 31."]
    if "end_date" in payload and payload["end_date"] is not None and not isinstance(payload["end_date"], str):
        errors["end_date"] = ["Informe uma data em texto ou deixe o término em branco."]
    try:
        effective = date.fromisoformat(payload.get("effective_from", month_of(max(reference, series.start_date)).isoformat()))
        if effective.day != 1 or effective < month_of(series.start_date):
            raise ValueError
    except (TypeError, ValueError):
        errors["effective_from"] = ["Informe o primeiro dia de uma competência a partir do início da série."]
        effective = month_of(series.start_date)
    if errors:
        return None, effective, errors
    values = effective_values(series, effective)
    initial = {**values, "due_day": values["day"], "end_date": series.end_date}
    form = SeriesForm({**initial, **payload})
    if not form.is_valid():
        errors.update({key: list(value) for key, value in form.errors.items()})
    elif form.cleaned_data["end_date"] and form.cleaned_data["end_date"] < series.start_date:
        errors["end_date"] = ["O término não pode ser anterior ao primeiro vencimento."]
    return form, effective, errors


@transaction.atomic
def update_series(series, form, effective):
    series = ExpenseSeries.objects.select_for_update().get(pk=series.pk)
    before = {**series_snapshot(series), "values": effective_values(series, effective), "effective_from": effective.isoformat()}
    data = form.cleaned_data
    values = {key: str(data[key]) if key == "amount" else data[key] for key in ("description", "amount", "category", "essential")}
    values["day"] = data["due_day"]
    if values != effective_values(series, effective):
        ExpenseSeriesRevision.objects.create(series=series, effective_from=effective, values=values)
        for occurrence in series.occurrences.select_for_update().filter(competence__gte=effective, status="pending", is_exception=False):
            if is_paid_or_linked(occurrence):
                continue
            old = snapshot(occurrence)
            for key in ("description", "amount", "category", "essential"):
                setattr(occurrence, key, data[key])
            occurrence.due_date = date(occurrence.competence.year, occurrence.competence.month, min(data["due_day"], monthrange(occurrence.competence.year, occurrence.competence.month)[1]))
            occurrence.full_clean()
            occurrence.save()
            record_change(occurrence, "edit", old)
    series.end_date = data["end_date"]
    series.save(update_fields=["end_date"])
    after = {**series_snapshot(series), "values": values, "effective_from": effective.isoformat()}
    if before != after:
        ExpenseSeriesHistory.objects.create(series=series, action="edit", before=before, after=after)
    return series


@transaction.atomic
def stop_series(series, from_date, cancel_pending):
    series = ExpenseSeries.objects.select_for_update().get(pk=series.pk)
    before = series_snapshot(series)
    series.cancelled_from = min(series.cancelled_from, from_date) if series.cancelled_from else from_date
    series.save(update_fields=["cancelled_from"])
    cancelled = 0
    if cancel_pending:
        for occurrence in series.occurrences.select_for_update().filter(status="pending", due_date__gte=from_date):
            if is_paid_or_linked(occurrence):
                continue
            old = snapshot(occurrence)
            occurrence.status = "cancelled"
            occurrence.is_exception = True
            occurrence.save(update_fields=["status", "is_exception"])
            record_change(occurrence, "cancel", old)
            cancelled += 1
    ExpenseSeriesHistory.objects.create(series=series, action="stop", before=before, after={**series_snapshot(series), "cancel_pending": cancel_pending, "pending_from": from_date.isoformat(), "cancelled_count": cancelled})
    return series
