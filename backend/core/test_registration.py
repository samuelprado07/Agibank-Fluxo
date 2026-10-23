import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from finance.models import Scenario, Occurrence


class RegistrationTests(TestCase):
    def setUp(self):
        self.original = Scenario.objects.create(name='Meu planejamento', opening_date=date(2026, 10, 23), reference_date=date(2026, 10, 23), opening_balance='833.26')

    def register(self, client=None, **changes):
        values = {'name': 'Maria Silva', 'email': 'maria@example.com', 'password': 'UmaSenhaForte!8932', 'password_confirmation': 'UmaSenhaForte!8932', **changes}
        return (client or self.client).post('/api/auth/register/', json.dumps(values), content_type='application/json')

    def test_first_registration_claims_existing_scenario_and_hashes_password(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get()
        self.assertNotEqual(user.password, 'UmaSenhaForte!8932')
        self.assertTrue(user.check_password('UmaSenhaForte!8932'))
        self.original.refresh_from_db()
        self.assertEqual(self.original.owner_id, user.pk)
        self.assertEqual(self.original.opening_balance, Decimal('833.26'))
        self.assertEqual(self.client.get('/api/auth/me/').json()['user']['name'], 'Maria Silva')
        dashboard = self.client.get('/api/dashboard/')
        self.assertEqual(dashboard.json()['indicators']['current_balance'], '833.26')
        self.assertEqual(dashboard.headers['Cache-Control'], 'no-store')
        self.assertNotIn('password', response.content.decode())

    def test_second_account_gets_zero_balance_and_isolation(self):
        self.assertEqual(self.register().status_code, 201)
        expense = Occurrence.objects.create(scenario=self.original, direction='expense', description='Privada', amount='20.00', due_date=date(2026, 10, 24))
        other = Client()
        response = self.register(other, name='João', email='joao@example.com')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(other.get('/api/dashboard/').json()['indicators']['current_balance'], '0.00')
        self.assertEqual(other.get('/api/expenses/').json()['expenses'], [])
        self.assertEqual(other.get(f'/api/expenses/{expense.pk}/').status_code, 404)
        self.assertEqual(other.post(f'/api/expenses/{expense.pk}/payment/', json.dumps({'key': str(uuid4()), 'version': 0, 'amount': '20.00', 'date': '2026-10-23'}), content_type='application/json').status_code, 404)
        self.assertEqual(Scenario.objects.count(), 2)

    def test_financial_routes_require_session(self):
        for path in ['/api/dashboard/', '/api/expenses/', '/api/incomes/', '/api/recurrences/', '/api/simulations/context/', '/api/assistant/context/']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertIsNone(self.client.get('/api/auth/me/').json()['user'])

    def test_invalid_registration_does_not_claim_scenario(self):
        for changes in [{'email': 'invalid'}, {'name': ''}, {'password_confirmation': 'diferente'}, {'password': '123', 'password_confirmation': '123'}, {'owner': 1}]:
            self.assertEqual(self.register(**changes).status_code, 400)
        self.assertFalse(get_user_model().objects.exists())
        self.original.refresh_from_db()
        self.assertIsNone(self.original.owner_id)

    def test_duplicate_email_is_case_insensitive(self):
        self.assertEqual(self.register(email='Maria@Example.Com').status_code, 201)
        response = self.register(Client(), email=' maria@example.com ')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_signup_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.register(client).status_code, 403)
        self.assertEqual(client.get('/api/auth/me/').status_code, 200)
        token = client.cookies['csrftoken'].value
        response = client.post('/api/auth/register/', json.dumps({'name': 'Maria', 'email': 'maria@example.com', 'password': 'UmaSenhaForte!8932', 'password_confirmation': 'UmaSenhaForte!8932'}), content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201)

    def test_second_user_cannot_claim_remaining_unowned_scenarios(self):
        extra = Scenario.objects.create(name='Outro cenário antigo', opening_date=date(2026, 10, 23), reference_date=date(2026, 10, 23), opening_balance='500.00')
        self.register()
        self.register(Client(), email='outro@example.com')
        extra.refresh_from_db()
        self.assertIsNone(extra.owner_id)

    def test_logout_ends_session(self):
        self.register()
        self.assertEqual(self.client.post('/api/auth/logout/', '{}', content_type='application/json').status_code, 200)
        self.assertEqual(self.client.get('/api/dashboard/').status_code, 401)

    def test_tokens_and_idempotency_results_do_not_cross_accounts(self):
        self.register()
        own = Occurrence.objects.create(scenario=self.original, direction='expense', description='Privada', amount='20.00', due_date=date(2026, 10, 23))
        payload = {'key': str(uuid4()), 'version': 0, 'amount': '20.00', 'date': '2026-10-23'}
        paid = self.client.post(f'/api/expenses/{own.pk}/payment/', json.dumps(payload), content_type='application/json')
        self.assertEqual(paid.status_code, 200)
        forecast = Occurrence.objects.create(scenario=self.original, direction='expense', description='Alternativa privada', amount='30.00', due_date=date(2026, 10, 24))
        preview = self.client.post('/api/simulations/preview/', json.dumps({'occurrence_id': forecast.pk, 'changes': {'amount': '10.00'}}), content_type='application/json').json()
        application = {'key': str(uuid4()), 'preview_token': preview['preview_token']}
        self.assertEqual(self.client.post('/api/simulations/apply/', json.dumps(application), content_type='application/json').status_code, 200)
        other = Client()
        self.register(other, email='outro@example.com')
        self.assertEqual(other.post(f'/api/expenses/{own.pk}/payment/', json.dumps(payload), content_type='application/json').status_code, 404)
        response = other.post('/api/simulations/apply/', json.dumps(application), content_type='application/json')
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('comparison', response.json())

    def test_assistant_history_is_bound_to_owner(self):
        from django.core import signing
        from finance.services.assistant import HISTORY_SALT
        self.register()
        other = Client(); self.register(other, email='outro@example.com')
        version = other.get('/api/assistant/context/').json()['projection_version']
        token = signing.dumps({'version': version, 'scenario_id': self.original.pk, 'owner_id': self.client.get('/api/auth/me/').json()['user']['id'], 'turns': []}, salt=HISTORY_SALT)
        with patch('finance.services.assistant.generate') as generate:
            response = other.post('/api/assistant/messages/', json.dumps({'message': 'Explique', 'projection_version': version, 'history_token': token}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        generate.assert_not_called()

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase


class ConcurrentRegistrationTests(TransactionTestCase):
    def test_simultaneous_accounts_claim_legacy_scenario_once(self):
        scenario = Scenario.objects.create(name='Legado', opening_date=date(2026, 10, 23), reference_date=date(2026, 10, 23), opening_balance='833.26')
        barrier = Barrier(2)
        def create(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return Client().post('/api/auth/register/', json.dumps({'name': 'Pessoa', 'email': f'pessoa{index}@example.com', 'password': 'UmaSenhaForte!8932', 'password_confirmation': 'UmaSenhaForte!8932'}), content_type='application/json').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(create, range(2)))
        self.assertEqual(statuses, [201, 201])
        scenario.refresh_from_db()
        self.assertIsNotNone(scenario.owner_id)
        self.assertEqual(Scenario.objects.exclude(pk=scenario.pk).get().opening_balance, Decimal('0.00'))
        self.assertEqual(get_user_model().objects.count(), 2)
