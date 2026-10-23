"""Authenticated fixtures for existing financial behavior tests."""
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, Client


class AuthenticatedFixture:
    def _callSetUp(self):
        self.user = get_user_model().objects.create_user(username='financial-' + uuid4().hex)
        self.client.force_login(self.user)
        super()._callSetUp()

    def auth_client(self, **options):
        client = Client(**options)
        # Share only the session cookie; fresh CSRF cookies are obtained normally.
        from django.conf import settings
        client.cookies[settings.SESSION_COOKIE_NAME] = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        return client


class AuthenticatedTestCase(AuthenticatedFixture, TestCase):
    pass


class AuthenticatedTransactionTestCase(AuthenticatedFixture, TransactionTestCase):
    pass
