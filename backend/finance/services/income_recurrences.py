from calendar import monthrange
from datetime import date

from django.db import transaction

from finance.models import Occurrence
from .recurrences import month_of


def series_values(series, competence):
    values = {"description": series.description, "amount": str(series.amount), "day": series.due_day}
    for revision in series.revisions.order_by("pk"):
        if revision.effective_from <= competence:
            values = revision.values
    return values


def monthly_date(competence, day):
    return date(competence.year, competence.month, min(day, monthrange(competence.year, competence.month)[1]))


@transaction.atomic
def ensure_income_occurrences(scenario, horizon):
    for series in scenario.income_series.select_for_update().all():
        existing = set(series.occurrences.values_list("competence", flat=True))
        revisions = list(series.revisions.order_by("pk"))
        month = month_of(series.start_date)
        pending = []
        while month <= month_of(horizon):
            values = {"description": series.description, "amount": str(series.amount), "day": series.due_day}
            for revision in revisions:
                if revision.effective_from <= month:
                    values = revision.values
            expected = monthly_date(month, values["day"])
            if month not in existing and series.start_date <= expected <= horizon and (series.end_date is None or expected <= series.end_date) and (series.cancelled_from is None or expected < series.cancelled_from):
                pending.append(Occurrence(scenario=scenario, income_series=series, competence=month, description=values["description"], amount=values["amount"], due_date=expected, direction="income"))
            if month.year == 9999 and month.month == 12:
                break
            month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        Occurrence.objects.bulk_create(pending, ignore_conflicts=True)
