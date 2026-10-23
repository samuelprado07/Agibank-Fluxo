from .auth_support import AuthenticatedTestCase, AuthenticatedTransactionTestCase
import json
from datetime import date
from uuid import uuid4

from django.test import TestCase

from finance.models import Movement, Occurrence, Scenario


class EstimateTests(AuthenticatedTestCase):
    def setUp(self):
        self.scenario = Scenario.objects.create(owner=self.user, name="Estimativas", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 22), opening_balance="1000.00")
        Occurrence.objects.create(scenario=self.scenario, description="Renda", direction="income", amount="1000.00", due_date=date(2026, 11, 1))
        self.payload = {"description": "Alimentação", "amount": "30.00", "category": "Alimentação", "due_date": "2026-10-24", "essential": False, "is_estimate": True}

    def create(self, **values):
        return self.client.post("/api/expenses/", data=json.dumps({**self.payload, **values}), content_type="application/json")

    def test_estimate_is_explicit_and_dated_not_a_realized_payment(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["is_estimate"])
        self.assertFalse(Movement.objects.exists())
        dashboard = self.client.get("/api/dashboard/").json()
        self.assertEqual(dashboard["indicators"]["current_balance"], "1000.00")
        self.assertEqual(dashboard["indicators"]["committed"], "30.00")
        self.assertEqual(dashboard["indicators"]["own_remaining"], "970.00")
        self.assertEqual(dashboard["indicators"]["pending_essential"], "0.00")
        self.assertEqual(dashboard["chart_days"][2]["expenses"], "30.00")

    def test_all_pending_expenses_are_committed_including_income_day_and_overdue(self):
        self.assertEqual(self.create().status_code, 201)
        for amount, due, essential in (("20.00", "2026-10-20", True), ("40.00", "2026-11-01", False), ("50.00", "2026-11-02", False)):
            Occurrence.objects.create(scenario=self.scenario, description="Conta", amount=amount, due_date=date.fromisoformat(due), direction="expense", essential=essential)
        indicators = self.client.get("/api/dashboard/").json()["indicators"]
        self.assertEqual(indicators["committed"], "90.00")
        self.assertEqual(indicators["own_remaining"], "910.00")
        self.assertEqual(indicators["pending_essential"], "20.00")

    def test_adjust_cancel_and_no_reactivation(self):
        created = self.create()
        self.assertEqual(created.status_code, 201)
        pk = created.json()["id"]
        updated = self.client.patch(f"/api/expenses/{pk}/", data='{"amount":"45.00","due_date":"2026-10-25"}', content_type="application/json")
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["is_estimate"])
        self.assertTrue(updated.json()["history"][0]["before"]["is_estimate"])
        self.assertEqual(self.client.post(f"/api/expenses/{pk}/cancel/", data='{}', content_type="application/json").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard/").json()["indicators"]["committed"], "0.00")
        self.assertEqual(self.client.patch(f"/api/expenses/{pk}/", data='{"status":"pending"}', content_type="application/json").status_code, 409)

    def test_same_category_does_not_deduplicate_independent_entries(self):
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create(is_estimate=False, amount="70.00").status_code, 201)
        self.assertEqual(self.client.get("/api/dashboard/").json()["indicators"]["committed"], "100.00")

    def test_explicit_actual_payment_replaces_estimate_once(self):
        created = self.create()
        self.assertEqual(created.status_code, 201)
        pk = created.json()["id"]
        payment = {"key": str(uuid4()), "version": 0, "amount": "25.00", "date": "2026-10-22"}
        self.assertEqual(self.client.post(f"/api/expenses/{pk}/payment/", data=json.dumps(payment), content_type="application/json").status_code, 200)
        indicators = self.client.get("/api/dashboard/").json()["indicators"]
        self.assertEqual(indicators["current_balance"], "975.00")
        self.assertEqual(indicators["committed"], "0.00")
        self.assertEqual(indicators["projected_final"], "1975.00")

    def test_legacy_and_validation_and_warning(self):
        payload = {key: value for key, value in self.payload.items() if key != "is_estimate"}
        created = self.client.post("/api/expenses/", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(created.status_code, 201)
        self.assertFalse(created.json()["is_estimate"])
        self.assertEqual(self.create(is_estimate="true").status_code, 400)
        self.scenario.variable_expenses_included = True
        self.scenario.save()
        self.assertTrue(any("ausentes" in text for text in self.client.get("/api/dashboard/").json()["warnings"]))

    def test_monthly_estimate_preserved_in_revisions_and_new_months(self):
        created = self.create(recurring=True)
        self.assertEqual(created.status_code, 201)
        pk, series_id = created.json()["id"], created.json()["series_id"]
        self.assertTrue(all(Occurrence.objects.filter(series_id=series_id).values_list("is_estimate", flat=True)))
        self.assertEqual(self.client.patch(f"/api/expenses/{pk}/", data='{"scope":"following","amount":"35.00"}', content_type="application/json").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/recurrences/{series_id}/", data='{"amount":"40.00"}', content_type="application/json").status_code, 200)
        self.scenario.reference_date = date(2027, 1, 1)
        self.scenario.save()
        self.client.get("/api/dashboard/")
        january = Occurrence.objects.get(series_id=series_id, competence=date(2027, 1, 1))
        self.assertTrue(january.is_estimate)
        self.assertEqual(str(january.amount), "40.00")

    def test_estimate_is_identified_in_shortfall_details(self):
        self.assertEqual(self.create(amount="1100.00").status_code, 201)
        alert = next(item for item in self.client.get("/api/dashboard/").json()["alerts"] if item["type"] == "insufficient")
        self.assertTrue(alert["expenses"][0]["is_estimate"])
