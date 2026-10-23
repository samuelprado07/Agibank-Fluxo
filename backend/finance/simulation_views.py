from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .expense_views import read_payload
from .income_views import income_errors
from .services.expenses import ExpenseConflict
from .services.simulations import SimulationError, apply_preview, context, preview


@ensure_csrf_cookie
@require_http_methods(["GET", "HEAD", "POST"])
@income_errors
def simulation(request, action):
    if (action == "context") != (request.method in ("GET", "HEAD")):
        return JsonResponse({"message": "Método não permitido."}, status=405)
    try:
        if action == "context":
            return JsonResponse(context(scenario=request.scenario))
        payload, error = read_payload(request)
        if error is not None:
            return error
        return JsonResponse((preview if action == "preview" else apply_preview)(payload, scenario=request.scenario))
    except SimulationError as error:
        return JsonResponse({"message": str(error), "errors": error.errors}, status=error.status)
    except ExpenseConflict as error:
        return JsonResponse({"message": str(error)}, status=409)
