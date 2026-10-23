import json
from unittest.mock import patch
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from finance.models import Movement
from finance.services.projection_context import AssistantError
from . import test_assistant as baseline


class LocalExplanationTests(TestCase):
    setUp = baseline.AssistantTests.setUp
    context = baseline.AssistantTests.context
    send = baseline.AssistantTests.send

    @patch('finance.services.assistant.generate')
    def test_transient_and_configuration_failures_use_local_explanation(self, generate):
        for code in ['provider_timeout', 'provider_unavailable', 'provider_rate_limit', 'provider_configuration', 'assistant_unavailable', 'invalid_response']:
            generate.side_effect = AssistantError('private-details', code, 503)
            with CaptureQueriesContext(connection) as queries:
                response = self.send()
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['provider'], 'local')
            self.assertEqual(data['response_mode'], 'local')
            self.assertEqual(data['fallback_reason'], code)
            self.assertEqual(data['label'], 'Explicações automáticas demonstrativas')
            self.assertTrue(data['template_version'])
            self.assertIn('50,00', data['text'])
            self.assertNotIn('private-details', data['text'])
            self.assertEqual(data['projection_version'], self.context()['projection_version'])
            self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
            self.assertFalse(Movement.objects.exists())

    @patch('finance.services.assistant.generate')
    def test_blocked_response_does_not_trigger_fallback(self, generate):
        generate.side_effect = AssistantError('Bloqueado', 'blocked_response', 502)
        response = self.send()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['code'], 'blocked_response')

    @patch('finance.services.assistant.generate')
    def test_provider_recovers_on_next_question(self, generate):
        generate.side_effect = [AssistantError('Timeout', 'provider_timeout', 504), {'paragraphs': ['Confira as estimativas.']}]
        first = self.send().json()
        second = self.send(history_token=first['history_token']).json()
        self.assertEqual(first['provider'], 'local')
        self.assertEqual(second['provider'], 'gemini')
        self.assertIsNone(second['fallback_reason'])
        self.assertEqual(generate.call_count, 2)

    @patch('finance.services.assistant.generate')
    def test_invalid_generated_numbers_are_discarded(self, generate):
        generate.return_value = {'paragraphs': ['Você receberá R$ 99999.']}
        response = self.send()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['provider'], 'local')
        self.assertNotIn('99999', response.json()['text'])

    @patch('finance.services.assistant.generate')
    def test_alternative_explanation_uses_backend_comparison(self, generate):
        generate.side_effect = AssistantError('Indisponível', 'provider_unavailable', 503)
        preview = self.client.post('/api/simulations/preview/', json.dumps({'occurrence_id': self.expense.pk, 'changes': {'amount': '50.00'}}), content_type='application/json').json()
        data = self.send(alternative_token=preview['preview_token']).json()
        self.assertEqual(data['provider'], 'local')
        self.assertTrue(data['alternative_version'])
        self.assertIn('0,00', data['text'])
        self.assertTrue(any(item['id'].startswith('alternative.comparison.') for item in data['references']))

    @patch('finance.services.assistant.generate')
    def test_local_zero_no_deficit_and_missing_income(self, generate):
        generate.side_effect = AssistantError('Timeout', 'provider_timeout', 504)
        self.expense.amount = '100.00'; self.expense.save()
        data = self.send().json()
        self.assertIn('margem', data['text'])
        self.expense.amount = '20.00'; self.expense.save()
        data = self.send().json()
        self.assertIn('Nenhuma insuficiência', data['text'])
        self.scenario.occurrences.filter(direction='income').delete()
        data = self.send(message='Quanto vou ganhar no próximo ano?').json()
        self.assertIn('não permite', data['text'])
        self.assertIn('recebimento', data['text'])

    @patch('finance.services.assistant.generate')
    def test_change_during_failed_generation_marks_local_response_stale(self, generate):
        def fail(*args):
            self.expense.amount = '170.00'; self.expense.save()
            raise AssistantError('Timeout', 'provider_timeout', 504)
        generate.side_effect = fail
        data = self.send().json()
        self.assertTrue(data['stale'])
        self.assertIn('50,00', data['text'])

    @patch('finance.services.assistant.generate')
    def test_overdue_and_missing_data_warnings_use_engine_facts(self, generate):
        generate.side_effect = AssistantError('Indisponível', 'provider_unavailable', 503)
        income = self.scenario.occurrences.get(direction='income')
        income.due_date = self.scenario.opening_date; income.save()
        self.expense.due_date = self.scenario.opening_date; self.expense.save()
        response = self.send()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('recebimento atrasado', data['text'])
        self.assertIn('até confirmação', data['text'])
        self.assertTrue(any(item['id'] == 'warnings.0' for item in data['references']))

    @patch('finance.services.assistant.generate')
    def test_invalid_context_still_fails_without_fallback(self, generate):
        version = self.context()['projection_version']
        self.expense.amount = '170.00'; self.expense.save()
        response = self.client.post('/api/assistant/messages/', json.dumps({'message': 'Explique', 'projection_version': version}), content_type='application/json')
        self.assertEqual(response.status_code, 409)
        generate.assert_not_called()
