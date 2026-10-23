import json
from datetime import date
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from finance.models import Scenario, Occurrence, Movement


class AssistantTests(TestCase):
    def setUp(self):
        self.scenario = Scenario.objects.create(name='Teste', opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 23), opening_balance='100.00')
        self.expense = Occurrence.objects.create(scenario=self.scenario, description='Aluguel', amount='150.00', due_date=date(2026, 10, 24), direction='expense', essential=True)
        Occurrence.objects.create(scenario=self.scenario, description='Renda', amount='200.00', due_date=date(2026, 10, 30), direction='income')

    def context(self):
        response = self.client.get('/api/assistant/context/')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def send(self, **extra):
        return self.client.post('/api/assistant/messages/', json.dumps({'message': 'Explique meu risco', 'projection_version': self.context()['projection_version'], **extra}), content_type='application/json')

    def test_context_matches_dashboard_and_is_readonly(self):
        dashboard = self.client.get('/api/dashboard/').json()
        with CaptureQueriesContext(connection) as queries:
            context = self.context()
        self.assertEqual(context['projection_version'], dashboard['projection_version'])
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertNotIn('facts', context)

    @patch('finance.services.assistant.generate')
    def test_fact_reference_is_resolved_by_backend(self, generate):
        generate.return_value = {'paragraphs': ['Seu saldo atual é {{indicators.current_balance}}. Os recebimentos são estimados.']}
        response = self.send()
        self.assertEqual(response.status_code, 200)
        self.assertIn('100,00', response.json()['text'])
        self.assertEqual(response.json()['references'][0]['id'], 'indicators.current_balance')
        self.assertFalse(response.json()['stale'])
        self.assertEqual(generate.call_count, 1)
        self.assertFalse(Movement.objects.exists())
        self.expense.refresh_from_db()
        self.assertEqual(str(self.expense.amount), '150.00')

    @patch('finance.services.assistant.generate')
    def test_rejects_unreferenced_numbers_and_invalid_references(self, generate):
        for answer in ['Você terá R$ 900 amanhã.', '{{inexistente}}', 'Seu saldo é 3 mil.', 'Garantimos um retorno de 20%.']:
            generate.return_value = {'paragraphs': [answer]}
            response = self.send()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['fallback_reason'], 'invalid_response')

    @patch('finance.services.assistant.generate')
    def test_stale_version_is_rejected_before_provider(self, generate):
        version = self.context()['projection_version']
        self.expense.amount = '170.00'; self.expense.save()
        response = self.client.post('/api/assistant/messages/', json.dumps({'message': 'Explique', 'projection_version': version}), content_type='application/json')
        self.assertEqual(response.status_code, 409)
        generate.assert_not_called()

    @patch('finance.services.assistant.generate')
    def test_change_during_generation_marks_response_as_previous(self, generate):
        def answer(*args):
            self.expense.amount = '175.00'; self.expense.save()
            return {'paragraphs': ['Os dados desta resposta são estimados.']}
        generate.side_effect = answer
        response = self.send()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['stale'])
        self.assertNotEqual(response.json()['projection_version'], response.json()['current_projection_version'])

    @patch('finance.services.assistant.generate')
    def test_invalid_requests_and_history(self, generate):
        for extra in [{'message': ''}, {'message': 'a' * 2001}, {'history_token': 'forjado'}, {'indicators': {'current_balance': '999'}}]:
            self.assertEqual(self.send(**extra).status_code, 400)
        generate.assert_not_called()

    @patch('finance.services.assistant.generate')
    def test_signed_history_is_bounded_and_old_history_not_reused(self, generate):
        generate.return_value = {'paragraphs': ['Confira as estimativas.']}
        first = self.send().json()
        self.assertEqual(self.send(history_token=first['history_token']).status_code, 200)
        self.assertEqual(len(generate.call_args.args[2]), 1)
        self.expense.amount = '180.00'; self.expense.save()
        self.assertEqual(self.send(history_token=first['history_token']).status_code, 200)
        self.assertEqual(generate.call_args.args[2], [])

    @patch('finance.services.assistant.generate')
    def test_alternative_uses_backend_and_remains_readonly(self, generate):
        preview = self.client.post('/api/simulations/preview/', json.dumps({'occurrence_id': self.expense.pk, 'changes': {'amount': '50.00'}}), content_type='application/json').json()
        generate.return_value = {'paragraphs': ['Na alternativa, a maior falta calculada é {{alternative.comparison.after.max_shortfall}}.']}
        with CaptureQueriesContext(connection) as queries:
            response = self.send(alternative_token=preview['preview_token'])
        self.assertEqual(response.status_code, 200)
        self.assertIn('0,00', response.json()['text'])
        self.assertTrue(response.json()['alternative_version'])
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertEqual(self.send(alternative_token='inválido').status_code, 400)

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get('/api/assistant/context/').status_code, 200)
        self.assertIn('csrftoken', client.cookies)
        self.assertEqual(client.post('/api/assistant/messages/', '{}', content_type='application/json').status_code, 403)

    @override_settings(GEMINI_API_KEY='')
    def test_missing_configuration_is_safe(self):
        response = self.send()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['provider'], 'local')
        self.assertNotIn('GEMINI_API_KEY', response.content.decode())

from types import SimpleNamespace
from django.test import SimpleTestCase
from finance.services.projection_context import AssistantError
from finance.services.gemini_provider import generate


@override_settings(GEMINI_API_KEY='test-only-not-a-secret', GEMINI_MODEL='gemini-3.6-flash')
class GeminiProviderTests(SimpleTestCase):
    @patch('google.genai.Client')
    def test_sdk_request_is_backend_only_and_has_no_tools(self, client):
        model = client.return_value.__enter__.return_value.models
        model.generate_content.return_value = SimpleNamespace(text='{"paragraphs":["Confira suas estimativas."]}')
        result = generate({'facts': {}}, 'Explique', [])
        self.assertEqual(result['paragraphs'], ['Confira suas estimativas.'])
        call = model.generate_content.call_args.kwargs
        self.assertEqual(call['model'], 'gemini-3.6-flash')
        self.assertIsNone(call['config'].tools)
        self.assertNotIn('test-only-not-a-secret', call['contents'])
        self.assertEqual(client.call_args.kwargs['http_options'].timeout, 25000)

    @patch('google.genai.Client')
    def test_timeout_is_sanitized(self, client):
        import httpx
        client.return_value.__enter__.return_value.models.generate_content.side_effect = httpx.ReadTimeout('private-details')
        with self.assertRaises(AssistantError) as raised:
            generate({}, 'Pergunta', [])
        self.assertEqual(raised.exception.status, 504)
        self.assertNotIn('private-details', str(raised.exception))

    @patch('google.genai.Client')
    def test_api_limits_and_unavailable_are_sanitized(self, client):
        from google.genai import errors
        for code, status in [(429, 429), (503, 503), (403, 503)]:
            client.return_value.__enter__.return_value.models.generate_content.side_effect = errors.APIError(code, {'error': {'message': 'private-details'}})
            with self.assertRaises(AssistantError) as raised:
                generate({}, 'Pergunta', [])
            self.assertEqual(raised.exception.status, status)
            self.assertNotIn('private-details', str(raised.exception))

    @patch('google.genai.Client')
    def test_blocked_and_invalid_output(self, client):
        for content in [None, 'invalid-json']:
            client.return_value.__enter__.return_value.models.generate_content.return_value = SimpleNamespace(text=content)
            with self.assertRaises(AssistantError) as raised:
                generate({}, 'Pergunta', [])
            self.assertEqual(raised.exception.status, 502)
