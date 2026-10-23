from django.urls import path
from .auth_views import me, register, sign_in, sign_out

from .views import health

urlpatterns = [
    path('auth/me/', me, name='auth-me'),
    path('auth/register/', register, name='auth-register'),
    path('auth/login/', sign_in, name='auth-login'),
    path('auth/logout/', sign_out, name='auth-logout'),
    path('health/', health, name='health'),
]
