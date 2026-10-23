from datetime import date, timedelta

from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_safe

from .expense_views import _active_scenario, _missing_scenario, read_payload
from .services.recurrences import ensure_occurrences
from .services.series import serialize_series, stop_series, update_series, validate_series


@ensure_csrf_cookie
@require_safe
def series_collection(request):
    scenario = _active_scenario(request)
    if scenario is None:
        return _missing_scenario()
    ensure_occurrences(scenario, scenario.reference_date + timedelta(days=59))
    return JsonResponse({"reference_date": scenario.reference_date, "recurrences": [serialize_series(series, scenario.reference_date) for series in scenario.expense_series.order_by("pk")]})


@require_http_methods(["GET", "HEAD", "PATCH", "POST"])
def series_detail(request, series_id, cancel=False):
    scenario = _active_scenario(request)
    if scenario is None:
        return _missing_scenario()
    series = scenario.expense_series.filter(pk=series_id).first()
    if series is None:
        return JsonResponse({"message": "Recorrência não encontrada."}, status=404)
    if (cancel and request.method != "POST") or (not cancel and request.method == "POST"):
        return JsonResponse({"message": "Método não permitido."}, status=405)
    if request.method in ("PATCH", "POST"):
        payload, error = read_payload(request)
        if error is not None:
            return error
        if cancel:
            try:
                from_date = date.fromisoformat(payload.get("from_date", ""))
                if from_date < scenario.reference_date or type(payload.get("cancel_pending")) is not bool or set(payload) - {"from_date", "cancel_pending"}:
                    raise ValueError
            except (TypeError, ValueError):
                return JsonResponse({"message": "Informe uma data a partir da referência e escolha se deseja cancelar as pendências."}, status=400)
            series = stop_series(series, from_date, payload["cancel_pending"])
        else:
            form, effective, errors = validate_series(series, payload, scenario.reference_date)
            if errors:
                return JsonResponse({"message": "Confira os campos informados.", "errors": errors}, status=400)
            series = update_series(series, form, effective)
    result = serialize_series(series, scenario.reference_date)
    result["history"] = [{"action": event.action, "before": event.before, "after": event.after, "created_at": event.created_at} for event in series.history.order_by("pk")]
    return JsonResponse(result)
