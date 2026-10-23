from django.http import JsonResponse
from django.db import OperationalError
from django.views.decorators.http import require_safe

from .models import Scenario
from .services.dashboard import build_dashboard


@require_safe
def dashboard(request):
    try:
        scenario = Scenario.objects.order_by("pk").first()
        if scenario is None:
            return JsonResponse({"code": "no_scenario", "message": "Nenhum planejamento financeiro cadastrado."}, status=404)
        data = build_dashboard(scenario)
    except Scenario.DoesNotExist:
        return JsonResponse({"code": "no_scenario", "message": "Planejamento não encontrado. Atualize a consulta."}, status=404)
    except OperationalError as error:
        if not any(word in str(error).lower() for word in ("locked", "busy")):
            raise
        response = JsonResponse({"code": "projection_busy", "message": "O planejamento está sendo atualizado. Tente consultar novamente em instantes."}, status=503)
        response["Retry-After"] = "1"
        return response
    except ValueError as error:
        return JsonResponse({"code": "invalid_scenario", "message": str(error)}, status=422)
    return JsonResponse(data)
