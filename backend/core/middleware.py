from django.http import JsonResponse
from finance.models import Scenario


class FinancialSessionMiddleware:
    """All financial endpoints resolve their scenario from the authenticated owner."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/') and not request.path.startswith('/api/auth/') and request.path != '/api/health/':
            if not request.user.is_authenticated:
                return JsonResponse({'code': 'authentication_required', 'message': 'Entre na sua conta para acessar o planejamento.'}, status=401)
            request.scenario = Scenario.objects.filter(owner=request.user).first()
        response = self.get_response(request)
        if hasattr(request, 'scenario'):
            response['Cache-Control'] = 'no-store'
        return response
