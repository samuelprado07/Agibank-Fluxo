import json
from datetime import timedelta

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .models import Occurrence, Scenario, PaymentHistory
from .services.expenses import ExpenseConflict, cancel_expense, create_expense, delete_expense, edit_expense, require_editable, serialize_expense, validate_expense
from .services.recurrences import ensure_occurrences


def _active_scenario(request):
    return request.scenario


def _missing_scenario():
    return JsonResponse({"code": "no_scenario", "message": "Nenhum planejamento financeiro cadastrado."}, status=404)


def read_payload(request):
    if request.content_type != "application/json":
        return None, JsonResponse({"message": "Envie os dados em JSON."}, status=415)
    try:
        payload = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return None, JsonResponse({"message": "JSON inválido.", "errors": {"__all__": ["Não foi possível ler os dados enviados."]}}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"message": "Envie um objeto JSON.", "errors": {"__all__": ["Formato inválido."]}}, status=400)
    return payload, None


@ensure_csrf_cookie
@require_http_methods(["GET", "HEAD", "POST"])
def expense_collection(request):
    scenario = _active_scenario(request)
    if scenario is None:
        return _missing_scenario()
    if request.method in ("GET", "HEAD"):
        ensure_occurrences(scenario, scenario.reference_date + timedelta(days=59))
        expenses = scenario.occurrences.select_related("series").filter(direction=Occurrence.Direction.EXPENSE).order_by("due_date", "pk")
        return JsonResponse({"reference_date": scenario.reference_date, "opening_date": scenario.opening_date, "expenses": [serialize_expense(expense) for expense in expenses]})
    payload, error = read_payload(request)
    if error is not None:
        return error
    form, errors = validate_expense(payload)
    if errors:
        return JsonResponse({"message": "Confira os campos informados.", "errors": errors}, status=400)
    expense = create_expense(scenario, form, payload)
    return JsonResponse(serialize_expense(expense), status=201)


@require_http_methods(["GET", "HEAD", "PATCH", "DELETE"])
@transaction.atomic
def expense_detail(request, expense_id):
    scenario = _active_scenario(request)
    if scenario is None:
        return _missing_scenario()
    expense = scenario.occurrences.select_for_update().filter(pk=expense_id, direction=Occurrence.Direction.EXPENSE).first()
    if expense is None:
        return JsonResponse({"message": "Despesa não encontrada."}, status=404)
    try:
        if request.method == "DELETE":
            delete_expense(expense)
            return JsonResponse({}, status=204)
        if request.method == "PATCH":
            require_editable(expense)
            payload, error = read_payload(request)
            if error is not None:
                return error
            form, errors = validate_expense(payload, expense)
            if errors:
                return JsonResponse({"message": "Confira os campos informados.", "errors": errors}, status=400)
            edit_expense(expense, form, payload.get("scope", "this"))
        result = serialize_expense(expense)
        result["history"] = [{"id": h.pk, "action": h.action, "before": h.before, "after": h.after, "created_at": h.created_at} for h in expense.history.order_by("created_at", "pk")]
        result["payment_history"] = [{"id": h.pk, "action": h.action, "reason": h.reason, "before": h.before, "after": h.after, "created_at": h.created_at} for h in PaymentHistory.objects.filter(movement__occurrence=expense).order_by("created_at", "pk")]
        return JsonResponse(result)
    except ExpenseConflict as error:
        return JsonResponse({"message": str(error)}, status=409)


@require_http_methods(["POST"])
@transaction.atomic
def expense_cancel(request, expense_id):
    scenario = _active_scenario(request)
    if scenario is None:
        return _missing_scenario()
    expense = scenario.occurrences.select_for_update().filter(pk=expense_id, direction="expense").first()
    if expense is None:
        return JsonResponse({"message": "Despesa não encontrada."}, status=404)
    try:
        require_editable(expense)
        payload, error = read_payload(request)
        if error is not None:
            return error
        if set(payload) - {"scope"} or payload.get("scope", "this") not in ("this", "following"):
            return JsonResponse({"message": "Informe apenas um alcance válido para o cancelamento."}, status=400)
        cancel_expense(expense, payload.get("scope", "this"))
        return JsonResponse(serialize_expense(expense))
    except ExpenseConflict as error:
        return JsonResponse({"message": str(error)}, status=409)
