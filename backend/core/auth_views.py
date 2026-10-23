from django import forms
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError, OperationalError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.cache import never_cache
from finance.models import Scenario
from finance.expense_views import read_payload


class RegistrationForm(forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField(max_length=150)
    password = forms.CharField(strip=False, max_length=128)
    password_confirmation = forms.CharField(strip=False, max_length=128)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if get_user_model().objects.filter(username=email).exists() or get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Este e-mail já está cadastrado.')
        return email

    def clean(self):
        values = super().clean()
        password = values.get('password')
        if password and values.get('password_confirmation') != password:
            self.add_error('password_confirmation', 'As senhas não coincidem.')
        if password:
            user = get_user_model()(username=values.get('email', ''), email=values.get('email', ''), first_name=values.get('name', ''))
            try:
                validate_password(password, user)
            except ValidationError as error:
                self.add_error('password', error)
        return values


def user_data(user):
    return {'id': user.pk, 'name': user.first_name, 'email': user.email}


@ensure_csrf_cookie
@never_cache
@require_http_methods(['GET', 'HEAD'])
def me(request):
    return JsonResponse({'user': user_data(request.user) if request.user.is_authenticated else None})


@require_POST
@never_cache
def register(request):
    if request.user.is_authenticated:
        return JsonResponse({'message': 'Saia da conta atual antes de cadastrar outra.'}, status=409)
    payload, error = read_payload(request)
    if error is not None:
        return error
    if set(payload) - {'name', 'email', 'password', 'password_confirmation'}:
        return JsonResponse({'message': 'Campos adicionais não são permitidos.'}, status=400)
    if any(not isinstance(value, str) for value in payload.values()):
        return JsonResponse({'message': 'Preencha os campos com valores de texto.'}, status=400)
    # Validate passwords before acquiring SQLite's writer lock.
    form = RegistrationForm(payload)
    if not form.is_valid():
        return JsonResponse({'message': 'Confira os dados do cadastro.', 'errors': dict(form.errors)}, status=400)
    User = get_user_model()
    user = User(username=form.cleaned_data['email'], email=form.cleaned_data['email'], first_name=form.cleaned_data['name'])
    user.set_password(form.cleaned_data['password'])
    try:
        with transaction.atomic():
            first_account = not User.objects.exists()
            user.save()
            scenario = Scenario.objects.filter(owner__isnull=True).order_by('pk').first() if first_account else None
            if scenario:
                scenario.owner = user
                scenario.save(update_fields=['owner'])
            else:
                today = timezone.localdate()
                Scenario.objects.create(owner=user, name='Meu planejamento', opening_date=today, reference_date=today, opening_balance='0.00')
            login(request, user)
    except IntegrityError:
        return JsonResponse({'message': 'Este e-mail já está cadastrado.', 'errors': {'email': ['Este e-mail já está cadastrado.']}}, status=400)
    except OperationalError as error:
        if not any(word in str(error).lower() for word in ('locked', 'busy')):
            raise
        return JsonResponse({'message': 'O cadastro está temporariamente ocupado. Tente novamente.'}, status=503)
    return JsonResponse({'user': user_data(user)}, status=201)


@require_POST
@never_cache
def sign_out(request):
    logout(request)
    return JsonResponse({'user': None})
