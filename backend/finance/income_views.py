from datetime import timedelta
from functools import wraps

from django.db import OperationalError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .expense_views import _active_scenario, _missing_scenario, read_payload
from .models import IncomeSeries, Occurrence, ReceiptHistory
from .services.income_recurrences import ensure_income_occurrences
from .services.incomes import IncomeError, cancel_income, create_income, edit_income, serialize_income, stop_income_series
from .services.payments import PaymentError
from .services.receipts import change_receipt


def income_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except (IncomeError, PaymentError) as error:
            return JsonResponse({"message": str(error), "errors": error.errors}, status=error.status)
        except OperationalError as error:
            if not any(word in str(error).lower() for word in ("locked", "busy")):
                raise
            response = JsonResponse({"message": "O planejamento está ocupado. Tente novamente com a mesma operação."}, status=503)
            response["Retry-After"] = "1"
            return response
    return wrapped


@ensure_csrf_cookie
@require_http_methods(["GET", "HEAD", "POST"])
@income_errors
def income_collection(request):
    scenario = _active_scenario()
    if scenario is None:
        return _missing_scenario()
    if request.method in ("GET", "HEAD"):
        ensure_income_occurrences(scenario, scenario.reference_date + timedelta(days=59))
        rows = scenario.occurrences.filter(direction="income").select_related("income_series").order_by("due_date", "pk")
        return JsonResponse({"reference_date": scenario.reference_date, "opening_date": scenario.opening_date, "incomes": [serialize_income(row, scenario.reference_date) for row in rows]})
    payload, error = read_payload(request)
    if error is not None:
        return error
    income = create_income(scenario, payload)
    return JsonResponse(serialize_income(income, scenario.reference_date), status=201)


@require_http_methods(["GET", "HEAD", "PATCH", "POST"])
@income_errors
@transaction.atomic
def income_detail(request, income_id, cancel=False):
    scenario = _active_scenario()
    if scenario is None:
        return _missing_scenario()
    income = scenario.occurrences.select_for_update().filter(pk=income_id, direction="income").first()
    if income is None:
        return JsonResponse({"message": "Renda não encontrada."}, status=404)
    if cancel and request.method != "POST" or not cancel and request.method == "POST":
        return JsonResponse({"message": "Método não permitido."}, status=405)
    if request.method in ("PATCH", "POST"):
        payload, error = read_payload(request)
        if error is not None:
            return error
        if cancel:
            if payload:
                raise IncomeError("O cancelamento individual não recebe campos adicionais.", 400)
            cancel_income(income)
        else:
            edit_income(income, payload)
    result = serialize_income(income, scenario.reference_date)
    result["history"] = [{"id": item.pk, "action": item.action, "before": item.before, "after": item.after, "created_at": item.created_at} for item in income.income_history.order_by("pk")]
    result["receipt_history"] = [{"id": item.pk, "action": item.action, "reason": item.reason, "before": item.before, "after": item.after, "created_at": item.created_at} for item in ReceiptHistory.objects.filter(movement__occurrence=income).order_by("pk")]
    return JsonResponse(result)


@require_http_methods(["POST", "PATCH"])
@income_errors
def income_receipt(request, income_id, undo=False):
    if undo and request.method != "POST":
        return JsonResponse({"message": "Use POST para desfazer."}, status=405)
    payload, error = read_payload(request)
    if error is not None:
        return error
    return JsonResponse(change_receipt(income_id, "undo" if undo else "correct" if request.method == "PATCH" else "confirm", payload))


@require_http_methods(["POST"])
@income_errors
@transaction.atomic
def income_series_cancel(request, series_id):
    series = IncomeSeries.objects.select_for_update().filter(pk=series_id, scenario=_active_scenario()).first()
    if series is None:
        return JsonResponse({"message": "Renda mensal não encontrada."}, status=404)
    payload, error = read_payload(request)
    if error is not None:
        return error
    stop_income_series(series, payload)
    return JsonResponse({"id": series.pk, "cancelled_from": series.cancelled_from})
