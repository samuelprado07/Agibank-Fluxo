from .auth_support import AuthenticatedTestCase, AuthenticatedTransactionTestCase
import json
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase

from finance.models import Movement, Occurrence, Scenario


class IncomeTests(AuthenticatedTestCase):
    def setUp(self):
        self.scenario = Scenario.objects.create(owner=self.user, name="Renda", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 22), opening_balance="1000.00")
        self.payload = {"description": "Benefício", "amount": "2200.00", "expected_date": "2026-10-25", "frequency": "single"}

    def create(self, **changes):
        return self.client.post("/api/incomes/", data=json.dumps({**self.payload, **changes}), content_type="application/json")

    def test_future_income_is_projected_but_not_own_money(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "pending")
        self.assertFalse(response.json()["overdue"])
        dashboard = self.client.get("/api/dashboard/").json()
        self.assertEqual(dashboard["indicators"]["current_balance"], "1000.00")
        self.assertEqual(dashboard["indicators"]["own_remaining"], "1000.00")
        self.assertEqual(dashboard["indicators"]["projected_final"], "3200.00")

    def test_overdue_is_excluded_from_projection_and_next_income_and_listed_separately(self):
        response = self.create(expected_date="2026-10-21")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["overdue"])
        dashboard = self.client.get("/api/dashboard/").json()
        self.assertIsNone(dashboard["next_income"])
        self.assertEqual(dashboard["indicators"]["projected_final"], "1000.00")
        self.assertEqual(dashboard["overdue_incomes"][0]["id"], response.json()["id"])

    def test_cancelled_income_is_excluded_and_expense_cannot_be_modified(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        pk = response.json()["id"]
        cancelled = self.client.post(f"/api/incomes/{pk}/cancel/", data='{}', content_type="application/json")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.assertIsNone(self.client.get("/api/dashboard/").json()["next_income"])
        expense = Occurrence.objects.create(scenario=self.scenario, description="Despesa", amount="1.00", due_date=self.scenario.reference_date, direction="expense")
        self.assertEqual(self.client.get(f"/api/incomes/{expense.pk}/").status_code, 404)

    def test_invalid_values_do_not_create_income(self):
        for values in ({"amount": 1.5}, {"amount": "NaN"}, {"amount": "0"}, {"amount": "1.001"}, {"description": " "}, {"expected_date": "2026-02-30"}, {"frequency": "weekly"}, {"status": "settled"}):
            with self.subTest(values=values):
                self.assertEqual(self.create(**values).status_code, 400)
        self.assertEqual(Occurrence.objects.count(), 0)
        self.assertEqual(Movement.objects.count(), 0)

    def test_csrf_and_no_scenario(self):
        client = self.auth_client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/api/incomes/", data=json.dumps(self.payload), content_type="application/json").status_code, 403)
        self.scenario.delete()
        self.assertEqual(self.client.get("/api/incomes/").status_code, 404)

    def test_reforecast_restores_projection_and_preserves_history(self):
        response = self.create(expected_date="2026-10-21")
        self.assertEqual(response.status_code, 201)
        pk = response.json()["id"]
        updated = self.client.patch(f"/api/incomes/{pk}/", data=json.dumps({"expected_date": "2026-10-26", "amount": "2100.00"}), content_type="application/json")
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["overdue"])
        self.assertEqual(len(updated.json()["history"]), 1)
        self.assertEqual(updated.json()["history"][0]["before"]["expected_date"], "2026-10-21")
        self.assertEqual(self.client.get("/api/dashboard/").json()["indicators"]["projected_final"], "3100.00")
        self.assertEqual(self.client.patch(f"/api/incomes/{pk}/", data=json.dumps({"frequency": "monthly"}), content_type="application/json").status_code, 400)

    def receipt(self, pk, action="confirm", version=0, key=None, **values):
        payload = {"key": key or str(uuid4()), "version": version, **({"amount": "2000.00", "date": "2026-10-22"} if action != "undo" else {}), **({"reason": "Correção"} if action != "confirm" else {}), **values}
        url = f"/api/incomes/{pk}/receipt/" + ("undo/" if action == "undo" else "")
        return getattr(self.client, "patch" if action == "correct" else "post")(url, data=json.dumps(payload), content_type="application/json")

    def test_effective_receipt_replaces_whole_forecast_and_replay_is_idempotent(self):
        created = self.create()
        self.assertEqual(created.status_code, 201)
        pk = created.json()["id"]
        key = str(uuid4())
        confirmed = self.receipt(pk, key=key)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(self.receipt(pk, key=key).json(), confirmed.json())
        self.assertEqual(self.receipt(pk, key=key, amount="1999.00").status_code, 409)
        self.assertEqual(self.receipt(pk).status_code, 409)
        income = Occurrence.objects.get(pk=pk)
        self.assertEqual(str(income.amount), "2200.00")
        self.assertEqual(income.status, "settled")
        indicators = self.client.get("/api/dashboard/").json()["indicators"]
        self.assertEqual(indicators["current_balance"], "3000.00")
        self.assertEqual(indicators["projected_final"], "3000.00")
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(self.client.patch(f"/api/incomes/{pk}/", data='{"amount":"1.00"}', content_type="application/json").status_code, 409)

    def test_receipt_correction_and_undo_restore_overdue_forecast(self):
        created = self.create(expected_date="2026-10-21")
        self.assertEqual(created.status_code, 201)
        pk = created.json()["id"]
        key = str(uuid4())
        self.assertEqual(self.receipt(pk, key=key).status_code, 200)
        self.assertEqual(self.receipt(pk, "correct", 1, amount="1900.00", date="2026-10-01").status_code, 200)
        self.assertEqual(self.receipt(pk, "correct", 1).status_code, 409)
        self.assertEqual(self.client.get("/api/dashboard/").json()["indicators"]["current_balance"], "2900.00")
        self.assertEqual(self.receipt(pk, "undo", 2).status_code, 200)
        self.assertEqual(self.receipt(pk, key=key).status_code, 200)
        detail = self.client.get(f"/api/incomes/{pk}/").json()
        self.assertTrue(detail["overdue"])
        self.assertEqual(len(detail["receipt_history"]), 3)
        self.assertEqual(self.client.get("/api/dashboard/").json()["indicators"]["projected_final"], "1000.00")

    def test_receipt_validation_and_audit_rollback(self):
        created = self.create()
        self.assertEqual(created.status_code, 201)
        pk = created.json()["id"]
        for values in ({"date": "2026-10-23"}, {"date": "2026-09-30"}, {"amount": "0"}, {"amount": "NaN"}, {"amount": "1.001"}, {"version": True}):
            self.assertEqual(self.receipt(pk, **values).status_code, 400)
        with patch("finance.services.payments.ReceiptHistory.objects.create", side_effect=RuntimeError("audit")):
            with self.assertRaises(RuntimeError):
                self.receipt(pk)
        self.assertFalse(Movement.objects.exists())
        self.assertEqual(Occurrence.objects.get(pk=pk).status, "pending")

    def test_monthly_clamping_exception_revisions_stop_and_no_duplicates(self):
        self.scenario.reference_date = date(2026, 1, 31)
        self.scenario.opening_date = date(2026, 1, 1)
        self.scenario.save()
        response = self.create(expected_date="2026-01-31", frequency="monthly")
        self.assertEqual(response.status_code, 201)
        series_id = response.json()["series_id"]
        rows = list(Occurrence.objects.filter(income_series_id=series_id).order_by("competence"))
        self.assertEqual([row.due_date.isoformat() for row in rows], ["2026-01-31", "2026-02-28", "2026-03-31"])
        january, february, march = rows
        self.assertEqual(self.receipt(january.pk, date="2026-01-31").status_code, 200)
        self.assertEqual(Occurrence.objects.get(pk=february.pk).status, "pending")
        self.assertEqual(self.client.patch(f"/api/incomes/{march.pk}/", data='{"amount":"99.00"}', content_type="application/json").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/incomes/{february.pk}/", data='{"scope":"following","amount":"2100.00","due_day":30}', content_type="application/json").status_code, 200)
        march.refresh_from_db()
        self.assertEqual(str(march.amount), "99.00")
        self.assertEqual(self.client.post(f"/api/income-recurrences/{series_id}/cancel/", data='{"from_date":"2026-02-01","cancel_pending":true}', content_type="application/json").status_code, 200)
        self.client.get("/api/incomes/")
        self.client.get("/api/dashboard/")
        self.assertEqual(Occurrence.objects.filter(income_series_id=series_id).count(), 3)
        self.assertEqual(Occurrence.objects.get(pk=january.pk).status, "settled")
        self.assertEqual(Occurrence.objects.get(pk=february.pk).status, "cancelled")

    def test_same_day_receipts_remain_separate_in_next_incomes(self):
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create(description="Outra renda", amount="100.00").status_code, 201)
        dashboard = self.client.get("/api/dashboard/").json()
        self.assertEqual([item["amount"] for item in dashboard["next_incomes"]], ["2200.00", "100.00"])
        self.assertEqual(dashboard["indicators"]["projected_final"], "3300.00")

    def test_monthly_revision_reaches_new_months_and_end_is_inclusive(self):
        response = self.create(expected_date="2026-10-25", frequency="monthly", end_date="2027-01-25")
        self.assertEqual(response.status_code, 201)
        pk = response.json()["id"]
        series_id = response.json()["series_id"]
        self.assertEqual(self.client.patch(f"/api/incomes/{pk}/", data='{"scope":"following","amount":"2300.00","due_day":25}', content_type="application/json").status_code, 200)
        self.scenario.reference_date = date(2027, 1, 1)
        self.scenario.save()
        self.client.get("/api/incomes/")
        january = Occurrence.objects.get(income_series_id=series_id, competence=date(2027, 1, 1))
        self.assertEqual(str(january.amount), "2300.00")
        self.assertFalse(Occurrence.objects.filter(income_series_id=series_id, competence__gt=date(2027, 1, 1)).exists())

    def test_scope_and_state_validation_and_other_scenario_isolation(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        pk = response.json()["id"]
        self.assertEqual(self.client.patch(f"/api/incomes/{pk}/", data='{"scope":"following"}', content_type="application/json").status_code, 400)
        self.assertEqual(self.create(frequency="monthly", end_date="2026-01-01").status_code, 400)
        other = Scenario.objects.create(name="Outro", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 22), opening_balance="0.00")
        hidden = Occurrence.objects.create(scenario=other, direction="income", description="Privada", amount="100.00", due_date=date(2026, 10, 23))
        self.assertEqual(self.client.get(f"/api/incomes/{hidden.pk}/").status_code, 404)
        self.assertEqual(self.receipt(hidden.pk).status_code, 404)

    def test_series_edit_cannot_move_existing_occurrences_outside_its_validity(self):
        for day, end, new_day in ((25, "2026-12-26", 31), (25, "2026-12-31", 1)):
            with self.subTest(new_day=new_day):
                created = self.create(expected_date=f"2026-10-{day}", frequency="monthly", end_date=end)
                self.assertEqual(created.status_code, 201)
                pk = created.json()["id"]
                series_id = created.json()["series_id"]
                # Generate the last month so the end-bound check covers existing rows.
                from finance.services.income_recurrences import ensure_income_occurrences
                ensure_income_occurrences(self.scenario, date(2026, 12, 31))
                before = list(Occurrence.objects.filter(income_series_id=series_id).values_list("due_date", "amount"))
                updated = self.client.patch(f"/api/incomes/{pk}/", data=json.dumps({"scope": "following", "due_day": new_day, "amount": "999.00"}), content_type="application/json")
                self.assertEqual(updated.status_code, 400)
                self.assertEqual(list(Occurrence.objects.filter(income_series_id=series_id).values_list("due_date", "amount")), before)


class ConcurrentReceiptTests(AuthenticatedTransactionTestCase):
    def test_simultaneous_receipts_with_same_or_distinct_keys(self):
        scenario = Scenario.objects.create(owner=self.user, name="Concorrência", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 22), opening_balance="0.00")
        for same_key in (True, False):
            income = Occurrence.objects.create(scenario=scenario, description="Renda", amount="100.00", due_date=date(2026, 10, 22), direction="income")
            barrier = Barrier(2)
            key = str(uuid4())
            def confirm(index):
                close_old_connections()
                try:
                    barrier.wait(timeout=10)
                    return self.auth_client().post(f"/api/incomes/{income.pk}/receipt/", data=json.dumps({"key": key if same_key else str(uuid4()), "version": 0, "amount": "100.00", "date": "2026-10-22"}), content_type="application/json").status_code
                finally:
                    close_old_connections()
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = sorted(pool.map(confirm, range(2)))
            self.assertEqual(statuses, [200, 200] if same_key else [200, 409])
            self.assertEqual(Movement.objects.filter(occurrence=income).count(), 1)
