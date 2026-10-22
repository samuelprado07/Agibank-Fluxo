from calendar import monthrange
from datetime import date

from django.db import transaction

from finance.models import Occurrence


def month_of(value):
    return value.replace(day=1)


def series_values(series):
    return {"description": series.description, "amount": str(series.amount), "category": series.category, "essential": series.essential, "day": series.due_day}


def effective_values(series, competence):
    values = series_values(series)
    for revision in series.revisions.order_by("pk"):
        if revision.effective_from <= competence:
            values = revision.values
    return values


@transaction.atomic
def ensure_occurrences(scenario, horizon):
    """Persist missing months only; never overwrite exceptions, payments or exclusions."""
    for series in scenario.expense_series.select_for_update().all():
        existing = set(series.occurrences.values_list("competence", flat=True))
        excluded = set(series.exclusions.values_list("competence", flat=True))
        # Last edit wins among applicable revisions, including edits made
        # later to an earlier month. All revisions remain available for audit.
        revisions = list(series.revisions.order_by("pk"))
        month = month_of(series.start_date)
        pending = []
        while month <= month_of(horizon):
            values = series_values(series)
            for revision in revisions:
                if revision.effective_from <= month:
                    values = revision.values
            due_date = date(month.year, month.month, min(values["day"], monthrange(month.year, month.month)[1]))
            if month not in existing and month not in excluded and series.start_date <= due_date <= horizon and (series.end_date is None or due_date <= series.end_date) and (series.cancelled_from is None or due_date < series.cancelled_from):
                pending.append(Occurrence(scenario=scenario, series=series, competence=month, description=values["description"], amount=values["amount"], category=values["category"], essential=values["essential"], due_date=due_date, direction="expense", status="pending"))
            if month.month == 12:
                if month.year == 9999:
                    break
                month = date(month.year + 1, 1, 1)
            else:
                month = date(month.year, month.month + 1, 1)
        Occurrence.objects.bulk_create(pending, ignore_conflicts=True)
