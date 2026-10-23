from .auth_support import AuthenticatedTestCase, AuthenticatedTransactionTestCase
import json
from datetime import date

from django.test import TestCase

from finance.models import ExpenseHistory, Movement, Occurrence, Scenario


class ExpenseLifecycleTests(AuthenticatedTestCase):
    def setUp(self):
        self.scenario = Scenario.objects.create(owner=self.user, name="Mensal", opening_date=date(2026, 1, 1), reference_date=date(2026, 1, 15), opening_balance="1500.00")
        self.payload = {"description": "Aluguel", "amount": "500.00", "category": "Moradia", "due_date": "2026-01-31", "essential": True}

    def request(self, method, path, payload=None):
        return getattr(self.client, method)(path, data=json.dumps(payload or {}), content_type="application/json")

    def create(self, recurring=False, **kwargs):
        response = self.request("post", "/api/expenses/", {**self.payload, "recurring": recurring, **kwargs})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_monthly_day_31_is_clamped_and_queries_do_not_duplicate(self):
        self.create(True)
        self.client.get("/api/dashboard/")
        self.client.get("/api/expenses/")
        self.client.get("/api/dashboard/")
        self.assertEqual(list(Occurrence.objects.order_by("due_date").values_list("due_date", flat=True)), [date(2026, 1, 31), date(2026, 2, 28)])
        self.assertEqual(Occurrence.objects.values("series", "competence").distinct().count(), 2)
        self.scenario.reference_date = date(2026, 3, 1)
        self.scenario.save()
        data = self.client.get("/api/expenses/").json()
        self.assertIn("2026-03-31", [e["due_date"] for e in data["expenses"]])
        self.assertEqual(Occurrence.objects.filter(due_date=date(2026, 1, 31), status="pending").count(), 1)

    def test_retroactive_start_and_end_date_are_respected(self):
        self.create(True, due_date="2025-12-31", end_date="2026-02-28")
        self.client.get("/api/dashboard/")
        self.assertEqual(Occurrence.objects.count(), 3)
        self.scenario.reference_date = date(2026, 4, 1)
        self.scenario.save()
        self.client.get("/api/dashboard/")
        self.assertEqual(Occurrence.objects.count(), 3)

    def test_edit_single_then_series_preserves_other_exceptions_and_paid_history(self):
        first = self.create(True)
        self.client.get("/api/expenses/")
        second = Occurrence.objects.get(competence=date(2026, 2, 1))
        response = self.request("patch", f"/api/expenses/{second.pk}/", {**self.payload, "amount": "650.00", "due_date": "2026-02-20", "scope": "this"})
        self.assertEqual(response.status_code, 200)
        response = self.request("patch", f"/api/expenses/{first['id']}/", {**self.payload, "amount": "600.00", "scope": "following"})
        self.assertEqual(response.status_code, 200)
        second.refresh_from_db()
        self.assertEqual(str(second.amount), "650.00")
        self.assertEqual(second.due_date, date(2026, 2, 20))
        self.assertGreater(ExpenseHistory.objects.count(), 0)
        self.scenario.reference_date = date(2026, 3, 1)
        self.scenario.save()
        self.client.get("/api/expenses/")
        self.assertEqual(str(Occurrence.objects.get(competence=date(2026, 3, 1)).amount), "600.00")

    def test_single_cancel_is_not_recreated_and_following_cancel_keeps_paid(self):
        first = self.create(True)
        self.client.get("/api/expenses/")
        second = Occurrence.objects.get(competence=date(2026, 2, 1))
        self.assertEqual(self.request("post", f"/api/expenses/{second.pk}/cancel/", {"scope": "this"}).status_code, 200)
        self.assertEqual(self.request("patch", f"/api/expenses/{first['id']}/", {**self.payload, "scope": "following"}).status_code, 200)
        second.refresh_from_db()
        self.assertEqual(second.status, "cancelled")
        second.status = "settled"
        second.save()
        Movement.objects.create(scenario=self.scenario, occurrence=second, description="Pago", amount="500.00", date=date(2026, 1, 15), direction="expense")
        self.assertEqual(self.request("post", f"/api/expenses/{first['id']}/cancel/", {"scope": "following"}).status_code, 200)
        second.refresh_from_db()
        self.assertEqual(second.status, "settled")
        self.scenario.reference_date = date(2026, 3, 1)
        self.scenario.save()
        self.client.get("/api/dashboard/")
        self.assertEqual(Occurrence.objects.count(), 2)

    def test_delete_only_clean_occurrence_and_do_not_regenerate_deleted_month(self):
        first = self.create(True)
        self.assertEqual(self.request("delete", f"/api/expenses/{first['id']}/").status_code, 204)
        self.client.get("/api/expenses/")
        self.assertFalse(Occurrence.objects.filter(competence=date(2026, 1, 1)).exists())
        second = Occurrence.objects.first()
        self.assertEqual(self.request("patch", f"/api/expenses/{second.pk}/", {**self.payload, "due_date": "2026-02-28", "amount": "501.00"}).status_code, 200)
        self.assertEqual(self.request("delete", f"/api/expenses/{second.pk}/").status_code, 409)

    def test_paid_occurrence_cannot_be_edited_cancelled_or_deleted(self):
        expense = self.create()
        occurrence = Occurrence.objects.get(pk=expense["id"])
        occurrence.status = "settled"
        occurrence.save()
        movement = Movement.objects.create(scenario=self.scenario, occurrence=occurrence, description="Pago", amount="490.00", date=date(2026, 1, 15), direction="expense")
        for method, suffix in [("patch", "/"), ("delete", "/"), ("post", "/cancel/")]:
            response = self.request(method, f"/api/expenses/{occurrence.pk}{suffix}", self.payload)
            self.assertEqual(response.status_code, 409)
        movement.refresh_from_db()
        self.assertEqual(str(movement.amount), "490.00")

    def test_cancelling_essential_updates_dashboard_without_changing_realized_balance(self):
        expense = self.create()
        self.assertEqual(self.request("post", f"/api/expenses/{expense['id']}/cancel/", {"scope": "this"}).status_code, 200)
        data = self.client.get("/api/dashboard/").json()
        self.assertEqual(data["indicators"]["pending_essential"], "0.00")
        self.assertEqual(data["indicators"]["current_balance"], "1500.00")
        self.assertEqual(self.request("delete", f"/api/expenses/{expense['id']}/").status_code, 409)

    def test_latest_series_edit_overrides_older_future_revision(self):
        first = self.create(True)
        self.client.get("/api/expenses/")
        second = Occurrence.objects.get(competence=date(2026, 2, 1))
        self.assertEqual(self.request("patch", f"/api/expenses/{second.pk}/", {**self.payload, "amount": "600.00", "due_date": "2026-02-28", "scope": "following"}).status_code, 200)
        self.assertEqual(self.request("patch", f"/api/expenses/{first['id']}/", {**self.payload, "amount": "700.00", "scope": "following"}).status_code, 200)
        self.scenario.reference_date = date(2026, 3, 1)
        self.scenario.save()
        self.client.get("/api/expenses/")
        self.assertEqual(str(Occurrence.objects.get(competence=date(2026, 3, 1)).amount), "700.00")

    def test_edit_that_marks_month_as_exception_is_kept_in_history(self):
        first = self.create(True)
        self.assertEqual(self.request("patch", f"/api/expenses/{first['id']}/", {**self.payload, "scope": "this"}).status_code, 200)
        self.assertTrue(ExpenseHistory.objects.filter(occurrence_id=first["id"]).exists())
        self.assertEqual(self.request("delete", f"/api/expenses/{first['id']}/").status_code, 409)
