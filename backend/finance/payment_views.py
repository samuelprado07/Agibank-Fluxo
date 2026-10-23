from django.db import OperationalError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .expense_views import read_payload
from .services.payments import PaymentError, change_payment


@require_http_methods(["POST", "PATCH"])
def payment(request, expense_id, undo=False):
    if undo and request.method != "POST":
        return JsonResponse({"message": "Use POST para desfazer."}, status=405)
    payload, error = read_payload(request)
    if error is not None:
        return error
    action = "undo" if undo else "correct" if request.method == "PATCH" else "confirm"
    try:
        return JsonResponse(change_payment(expense_id, action, payload, scenario=request.scenario))
    except PaymentError as error:
        return JsonResponse({"message": str(error), "errors": error.errors}, status=error.status)
    except OperationalError as error:
        if "locked" not in str(error).lower() and "busy" not in str(error).lower():
            raise
        response = JsonResponse({"message": "O planejamento está ocupado. Tente novamente com a mesma operação."}, status=503)
        response["Retry-After"] = "1"
        return response
