from django.http import JsonResponse
from django.views.decorators.http import require_safe

from .models import Scenario
from .services.dashboard import build_dashboard


@require_safe
def dashboard(request):
    scenario = Scenario.objects.order_by("pk").first()
    if scenario is None:
        return JsonResponse({"code": "no_scenario", "message": "Nenhum cenário demonstrativo carregado."}, status=404)
    try:
        data = build_dashboard(scenario)
    except ValueError as error:
        return JsonResponse({"code": "invalid_scenario", "message": str(error)}, status=422)
    return JsonResponse(data)
