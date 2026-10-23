from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from .expense_views import read_payload
from .income_views import income_errors
from .services.assistant import respond
from .services.projection_context import AssistantError, capture_context, metadata
from .services.simulations import SimulationError
from .services.expenses import ExpenseConflict


@ensure_csrf_cookie
@require_http_methods(['GET', 'HEAD', 'POST'])
@income_errors
def assistant(request, action):
    if (action == 'context') != (request.method in ('GET', 'HEAD')):
        return JsonResponse({'message': 'Método não permitido.'}, status=405)
    try:
        if action == 'context':
            return JsonResponse(metadata(capture_context()))
        payload, error = read_payload(request)
        if error is not None:
            return error
        return JsonResponse(respond(payload))
    except AssistantError as error:
        return JsonResponse({'message': str(error), 'code': error.code}, status=error.status)
    except (SimulationError, ExpenseConflict) as error:
        return JsonResponse({'message': str(error), 'code': 'invalid_context'}, status=getattr(error, 'status', 409))
    except ValueError:
        return JsonResponse({'message': 'Não há dados válidos suficientes para orientar sobre este planejamento.', 'code': 'invalid_context'}, status=422)
