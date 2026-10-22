import json
from datetime import date

from django.test import Client, TestCase

from finance.models import Occurrence, Scenario


class ExpenseApiTests(TestCase):
    def setUp(self):
        self.scenario = Scenario.objects.create(name="Despesas", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 22), opening_balance="1000.00")
        self.payload = {"description": "Conta de luz", "amount": "120.35", "category": "Moradia", "due_date": "2026-10-25", "essential": True}

    def create_expense(self, payload=None, client=None):
        return (client or self.client).post("/api/expenses/", data=json.dumps(self.payload if payload is None else payload), content_type="application/json")

    def test_create_pending_expense_updates_dashboard_and_preserves_current_balance(self):
        response = self.create_expense()
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["amount"], "120.35")
        self.assertEqual(data["status"], "pending")
        self.assertTrue(data["essential"])
        dashboard = self.client.get("/api/dashboard/").json()
        self.assertEqual(dashboard["indicators"]["pending_essential"], "120.35")
        self.assertEqual(dashboard["indicators"]["current_balance"], "1000.00")

    def test_nonessential_expense_is_projected_but_not_committed_as_essential(self):
        payload = {**self.payload, "essential": False}
        self.assertEqual(self.create_expense(payload).status_code, 201)
        dashboard = self.client.get("/api/dashboard/").json()
        self.assertEqual(dashboard["indicators"]["pending_essential"], "0.00")
        self.assertEqual(dashboard["indicators"]["projected_final"], "879.65")

    def test_list_and_detail_are_limited_to_expenses_in_active_scenario(self):
        own = Occurrence.objects.create(scenario=self.scenario, direction="expense", status="settled", description="Internet", amount="100.00", due_date=date(2026, 10, 1))
        income = Occurrence.objects.create(scenario=self.scenario, direction="income", description="Renda", amount="2000.00", due_date=date(2026, 11, 1))
        other = Scenario.objects.create(name="Outro", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 22), opening_balance="0.00")
        hidden = Occurrence.objects.create(scenario=other, direction="expense", description="Outra conta", amount="999.00", due_date=date(2026, 10, 23))
        response = self.client.get("/api/expenses/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["expenses"]], [own.pk])
        self.assertEqual(self.client.get(f"/api/expenses/{own.pk}/").json()["status"], "settled")
        for pk in (income.pk, hidden.pk):
            self.assertEqual(self.client.get(f"/api/expenses/{pk}/").status_code, 404)

    def test_invalid_input_returns_field_errors_without_saving(self):
        for patch in ({"amount": "0.00"}, {"amount": "-1.00"}, {"amount": "1.001"}, {"amount": "NaN"}, {"amount": 1.2}, {"description": "   "}, {"due_date": "2026-02-30"}, {"essential": "false"}, {"status": "settled"}, {"direction": "income"}):
            with self.subTest(patch=patch):
                response = self.create_expense({**self.payload, **patch})
                self.assertEqual(response.status_code, 400)
                self.assertIn("errors", response.json())
        self.assertEqual(Occurrence.objects.count(), 0)

    def test_malformed_and_non_object_payloads_return_json_errors(self):
        for body in ('{', '[]', 'null'):
            response = self.client.post("/api/expenses/", data=body, content_type="application/json")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post("/api/expenses/", data=self.payload).status_code, 415)

    def test_write_requires_csrf_and_accepts_valid_token_from_bootstrap(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.create_expense(client=client).status_code, 403)
        client.get("/api/expenses/")
        token = client.cookies["csrftoken"].value
        response = client.post("/api/expenses/", data=json.dumps(self.payload), content_type="application/json", HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="http://127.0.0.1:5173")
        self.assertEqual(response.status_code, 201)

    def test_missing_scenario_returns_explicit_error_without_creating_one(self):
        self.scenario.delete()
        self.assertEqual(self.client.get("/api/expenses/").status_code, 404)
        self.assertEqual(self.create_expense().status_code, 404)
        self.assertFalse(Scenario.objects.exists())

    def test_editing_essentiality_refreshes_commitment_without_changing_balance(self):
        expense = self.create_expense().json()
        Occurrence.objects.create(scenario=self.scenario, description="Renda", direction="income", amount="2000.00", due_date=date(2026, 10, 30))
        response = self.client.patch(f"/api/expenses/{expense['id']}/", data=json.dumps({"essential": False, "amount": "130.45"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        dashboard = self.client.get("/api/dashboard/").json()
        self.assertEqual(dashboard["indicators"]["committed"], "0.00")
        self.assertEqual(dashboard["indicators"]["current_balance"], "1000.00")
        self.assertEqual(dashboard["indicators"]["projected_final"], "2869.55")

    def test_all_write_routes_reject_missing_csrf_and_income_targets(self):
        expense = self.create_expense().json()
        client = Client(enforce_csrf_checks=True)
        for method, path in [("patch", f"/api/expenses/{expense['id']}/"), ("delete", f"/api/expenses/{expense['id']}/"), ("post", f"/api/expenses/{expense['id']}/cancel/")]:
            response = getattr(client, method)(path, data="{}", content_type="application/json")
            self.assertEqual(response.status_code, 403)
        income = Occurrence.objects.create(scenario=self.scenario, description="Renda", direction="income", amount="2000.00", due_date=date(2026, 10, 30))
        for method, suffix in [("patch", "/"), ("delete", "/"), ("post", "/cancel/")]:
            self.assertEqual(getattr(self.client, method)(f"/api/expenses/{income.pk}{suffix}", data="{}", content_type="application/json").status_code, 404)
