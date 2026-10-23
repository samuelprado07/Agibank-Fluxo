import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from finance.models import ExpenseHistory, ExpenseSeries, Movement, Occurrence, Scenario


class SimulationTests(TestCase):
    def setUp(self):
        self.scenario = Scenario.objects.create(name="Alternativas", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 23), opening_balance="100.00")
        self.expense = Occurrence.objects.create(scenario=self.scenario, description="Conta", amount="150.00", due_date=date(2026, 10, 24), direction="expense")
        self.income = Occurrence.objects.create(scenario=self.scenario, description="Renda", amount="200.00", due_date=date(2026, 11, 12), direction="income")

    def preview(self, changes=None, occurrence=None):
        return self.client.post("/api/simulations/preview/", data=json.dumps({"occurrence_id": (occurrence or self.expense).pk, "changes": {"amount": "50.00"} if changes is None else changes}), content_type="application/json")

    def apply(self, preview, key=None):
        return self.client.post("/api/simulations/apply/", data=json.dumps({"preview_token": preview["preview_token"], "key": key or str(uuid4())}), content_type="application/json")

    def test_preview_is_isolated_and_no_insufficiency_is_explicit(self):
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["comparison"]["before"]["first_deficit_date"], "2026-10-24")
        self.assertEqual(data["comparison"]["before"]["max_shortfall"], "50.00")
        self.assertIsNone(data["comparison"]["after"]["first_deficit_date"])
        self.assertEqual(data["comparison"]["after"]["max_shortfall"], "0.00")
        self.assertEqual(data["comparison"]["after"]["status"], "no_insufficiency")
        self.expense.refresh_from_db()
        self.assertEqual(str(self.expense.amount), "150.00")
        self.assertFalse(ExpenseHistory.objects.exists())
        self.assertFalse(Movement.objects.exists())

    def test_income_date_change_uses_same_horizon_and_marks_moved_event(self):
        response = self.preview({"date": "2026-12-01"}, self.income)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["before"]["period"], data["after"]["period"])
        self.assertEqual(data["before"]["projection_policy"], data["after"]["projection_policy"])
        self.assertEqual(data["before"]["period"]["end"], "2026-11-12")
        self.assertTrue(data["moved_outside_horizon"])
        self.assertTrue(data["warnings"])

    def test_income_outside_fixed_period_does_not_claim_commitment_until_that_date(self):
        response = self.preview({"date": "2026-12-01"}, self.income)
        self.assertEqual(response.status_code, 200)
        after = response.json()["after"]
        self.assertTrue(after["next_income"]["outside_analysis"])
        self.assertIsNone(after["indicators"]["committed"])
        self.assertIsNone(after["indicators"]["own_remaining"])

    def test_preview_does_not_materialize_recurring_rows(self):
        series = ExpenseSeries.objects.create(scenario=self.scenario, description="Mensal", amount="30.00", start_date=date(2026, 10, 25), due_day=25)
        counts = (Occurrence.objects.count(), ExpenseHistory.objects.count())
        with CaptureQueriesContext(connection) as queries:
            response = self.preview()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((Occurrence.objects.count(), ExpenseHistory.objects.count()), counts)
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")) for query in queries))
        self.assertFalse(series.occurrences.exists())
        events = [event for day in data["before"]["days"] for event in day["events"]]
        self.assertTrue(any(event["series_id"] == series.pk and event["is_recurring"] for event in events))

    def test_apply_once_updates_history_and_recalculates_dashboard(self):
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        data, key = response.json(), str(uuid4())
        applied = self.apply(data, key)
        self.assertEqual(applied.status_code, 200)
        self.assertTrue(applied.json()["applied"])
        self.assertEqual(self.apply(data, key).json(), applied.json())
        self.expense.refresh_from_db()
        self.assertEqual(str(self.expense.amount), "50.00")
        self.assertEqual(ExpenseHistory.objects.count(), 1)
        self.assertEqual(applied.json()["dashboard"]["alerts"], [])

    def test_changed_scenario_or_realization_rejects_stale_preview(self):
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.income.amount = "250.00"
        self.income.save()
        self.assertEqual(self.apply(data).status_code, 409)
        self.assertFalse(ExpenseHistory.objects.exists())
        fresh = self.preview().json()
        self.expense.status = "settled"
        self.expense.save()
        Movement.objects.create(scenario=self.scenario, occurrence=self.expense, direction="expense", description="Pago", amount="140.00", date=date(2026, 10, 23))
        self.assertEqual(self.apply(fresh).status_code, 409)
        self.expense.refresh_from_db()
        self.assertEqual(str(self.expense.amount), "150.00")

    def test_tampering_and_invalid_targets_and_values_are_rejected(self):
        for changes in ({}, {"amount": "0"}, {"amount": "NaN"}, {"amount": 10.0}, {"date": "2026-02-30"}, {"scope": "following"}, {"status": "settled"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.preview(changes).status_code, 400)
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        data["preview_token"] += "corrupt"
        self.assertEqual(self.apply(data).status_code, 400)
        self.expense.status = "cancelled"
        self.expense.save()
        self.assertEqual(self.preview().status_code, 409)

    def test_apply_rollback_preserves_forecast_on_history_failure(self):
        response = self.preview()
        self.assertEqual(response.status_code, 200)
        with patch("finance.services.expenses.ExpenseHistory.objects.create", side_effect=RuntimeError("audit")):
            with self.assertRaises(RuntimeError):
                self.apply(response.json())
        self.expense.refresh_from_db()
        self.assertEqual(str(self.expense.amount), "150.00")

    def test_received_income_is_protected_and_predicted_income_can_be_applied(self):
        response = self.preview({"amount": "300.00", "date": "2026-11-10"}, self.income)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.apply(response.json()).status_code, 200)
        self.income.refresh_from_db()
        self.assertEqual(str(self.income.amount), "300.00")
        self.assertEqual(self.income.due_date, date(2026, 11, 10))
        self.assertEqual(self.income.income_history.count(), 1)
        self.income.status = "settled"
        self.income.save()
        self.assertEqual(self.preview({"amount": "500.00"}, self.income).status_code, 409)

    def test_monthly_edit_affects_only_selected_occurrence(self):
        series = ExpenseSeries.objects.create(scenario=self.scenario, description="Mensal", amount="30.00", start_date=date(2026, 10, 25), due_day=25)
        first = Occurrence.objects.create(scenario=self.scenario, series=series, competence=date(2026, 10, 1), description="Mensal", amount="30.00", direction="expense", due_date=date(2026, 10, 25))
        second = Occurrence.objects.create(scenario=self.scenario, series=series, competence=date(2026, 11, 1), description="Mensal", amount="30.00", direction="expense", due_date=date(2026, 11, 25))
        response = self.preview({"amount": "20.00"}, first)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.apply(response.json()).status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_exception)
        self.assertEqual(str(second.amount), "30.00")

    def test_context_and_writes_require_csrf_and_no_multiple_targets(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/api/simulations/preview/", data='{}', content_type="application/json").status_code, 403)
        self.assertEqual(client.get("/api/simulations/context/").status_code, 200)
        self.assertIn("csrftoken", client.cookies)
        self.assertEqual(self.client.post("/api/simulations/preview/", data='{"changes":[]}', content_type="application/json").status_code, 400)


class ConcurrentSimulationTests(TransactionTestCase):
    def test_repeated_simultaneous_apply_is_one_change(self):
        scenario = Scenario.objects.create(name="Concorrência", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 23), opening_balance="100.00")
        expense = Occurrence.objects.create(scenario=scenario, description="Conta", amount="150.00", direction="expense", due_date=date(2026, 10, 24))
        response = Client().post("/api/simulations/preview/", data=json.dumps({"occurrence_id": expense.pk, "changes": {"amount": "50.00"}}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        payload = {"preview_token": response.json()["preview_token"], "key": str(uuid4())}
        barrier = Barrier(2)
        def apply(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                result = Client().post("/api/simulations/apply/", data=json.dumps(payload), content_type="application/json")
                return result.status_code, result.json()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(apply, range(2)))
        self.assertEqual([result[0] for result in results], [200, 200])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(ExpenseHistory.objects.count(), 1)
