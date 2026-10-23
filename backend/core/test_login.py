import json
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from finance.models import Scenario


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='maria@example.com', email='maria@example.com', first_name='Maria', password='UmaSenhaForte!8932')
        cls.scenario = Scenario.objects.create(owner=cls.user, name='Meu planejamento', opening_date=date(2026, 10, 23), reference_date=date(2026, 10, 23), opening_balance='833.26')

    def login(self, client=None, **changes):
        return (client or self.client).post('/api/auth/login/', json.dumps({'email': 'maria@example.com', 'password': 'UmaSenhaForte!8932', **changes}), content_type='application/json')

    def test_email_login_restores_existing_account_and_balance(self):
        response = self.login(email='  MARIA@EXAMPLE.COM ')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['name'], 'Maria')
        self.assertNotIn('password', response.content.decode())
        self.assertEqual(self.client.get('/api/auth/me/').json()['user']['id'], self.user.pk)
        self.assertEqual(self.client.get('/api/dashboard/').json()['indicators']['current_balance'], '833.26')
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Scenario.objects.count(), 1)
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_wrong_password_unknown_email_and_disabled_account_are_generic(self):
        wrong = self.login(password='OutraSenha!09')
        unknown = self.login(email='naoexiste@example.com')
        self.user.is_active = False; self.user.save()
        inactive = self.login()
        self.assertEqual([wrong.status_code, unknown.status_code, inactive.status_code], [401, 401, 401])
        self.assertEqual(wrong.json(), unknown.json())
        self.assertEqual(wrong.json(), inactive.json())
        self.assertIsNone(self.client.get('/api/auth/me/').json()['user'])

    def test_invalid_payloads_and_methods(self):
        for changes in [{'email': ''}, {'email': 'invalid'}, {'password': ''}, {'password': {'value': 'bad'}}, {'owner': 1}]:
            self.assertEqual(self.login(**changes).status_code, 400)
        self.assertEqual(self.client.get('/api/auth/login/').status_code, 405)
        self.assertEqual(self.client.post('/api/auth/login/', 'bad', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post('/api/auth/login/', '{}', content_type='text/plain').status_code, 415)

    def test_csrf_is_required_and_rotated_at_login(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.login(client).status_code, 403)
        client.get('/api/auth/me/')
        old_csrf = client.cookies['csrftoken'].value
        response = client.post('/api/auth/login/', json.dumps({'email': 'maria@example.com', 'password': 'UmaSenhaForte!8932'}), content_type='application/json', HTTP_X_CSRFTOKEN=old_csrf)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(old_csrf, client.cookies['csrftoken'].value)

    def test_logout_and_login_again_keep_data_and_invalidate_old_session(self):
        self.login()
        old_cookie = self.client.cookies['sessionid'].value
        self.assertEqual(self.client.post('/api/auth/logout/', '{}', content_type='application/json').status_code, 200)
        stale = Client(); stale.cookies['sessionid'] = old_cookie
        self.assertEqual(stale.get('/api/dashboard/').status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get('/api/dashboard/').json()['indicators']['current_balance'], '833.26')

    def test_authenticated_user_cannot_switch_accounts_without_logout(self):
        self.login()
        self.assertEqual(self.login().status_code, 409)
        self.assertEqual(self.client.get('/api/auth/me/').json()['user']['id'], self.user.pk)

    def test_session_id_changes_and_password_spaces_are_preserved(self):
        session = self.client.session; session['probe'] = True; session.save()
        old_session = session.session_key
        self.user.set_password('  SenhaComEspacos!8932  '); self.user.save()
        self.assertEqual(self.login(password='  SenhaComEspacos!8932  ').status_code, 200)
        self.assertNotEqual(self.client.session.session_key, old_session)
