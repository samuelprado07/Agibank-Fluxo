import json
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase

from finance.models import ExpenseSeries, Movement, Occurrence, PaymentHistory, PaymentOperation, Scenario


class PaymentTests(TestCase):
    def setUp(self):
        self.scenario = Scenario.objects.create(name="Pagamentos", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 22), opening_balance="1000.00")
        self.expense = Occurrence.objects.create(scenario=self.scenario, description="Luz", amount="120.00", due_date=date(2026, 10, 25), direction="expense", essential=True)
        self.url = f"/api/expenses/{self.expense.pk}/payment/"

    def send(self, action="confirm", version=0, key=None, **values):
        payload = {"key": key or str(uuid4()), "version": version, **values}
        if action != "undo":
            payload = {"amount": "110.50", "date": "2026-10-21", **payload}
        if action != "confirm":
            payload.setdefault("reason", "Correção de informação")
        return self.client.post(self.url + ("undo/" if action == "undo" else ""), data=json.dumps(payload), content_type="application/json") if action != "correct" else self.client.patch(self.url, data=json.dumps(payload), content_type="application/json")

    def test_payment_replaces_forecast_using_effective_amount_and_date(self):
        response = self.send()
        self.assertEqual(response.status_code, 200)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, "settled")
        self.assertEqual(str(self.expense.amount), "120.00")
        dashboard = self.client.get("/api/dashboard/").json()["indicators"]
        self.assertEqual(dashboard["current_balance"], "889.50")
        self.assertEqual(dashboard["pending_essential"], "0.00")
        self.assertEqual(dashboard["projected_final"], "889.50")

    def test_replay_and_key_payload_conflict(self):
        key = str(uuid4())
        first = self.send(key=key)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.send(key=key).json(), first.json())
        self.assertEqual(self.send(key=key, amount="112.00").status_code, 409)
        self.assertEqual(self.send().status_code, 409)
        self.assertEqual(Movement.objects.count(), 1)

    def test_correct_undo_and_reconfirm_preserve_history_and_prevent_stale_requests(self):
        key = str(uuid4())
        self.assertEqual(self.send(key=key).status_code, 200)
        self.assertEqual(self.send("correct", version=1, amount="130.00").status_code, 200)
        self.assertEqual(self.send("correct", version=1).status_code, 409)
        self.assertEqual(self.send("undo", version=2).status_code, 200)
        self.assertEqual(self.send(key=key).status_code, 200)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, "pending")
        indicators = self.client.get("/api/dashboard/").json()["indicators"]
        self.assertEqual(indicators["current_balance"], "1000.00")
        self.assertEqual(indicators["pending_essential"], "120.00")
        self.assertEqual(self.client.delete(f"/api/expenses/{self.expense.pk}/").status_code, 409)
        self.assertEqual(self.send().status_code, 409)
        self.assertEqual(self.send(version=3).status_code, 200)
        self.assertEqual(Movement.objects.count(), 1)
        detail = self.client.get(f"/api/expenses/{self.expense.pk}/").json()
        self.assertEqual(len(detail["payment_history"]), 4)

    def test_invalid_values_dates_versions_and_reason(self):
        for values in ({"amount": "0"}, {"amount": "-1"}, {"amount": "NaN"}, {"amount": "1.001"}, {"amount": 1.2}, {"amount": "1000000000000"}, {"date": "2026-10-23"}, {"date": "2026-09-30"}, {"date": "2026-02-30"}, {"version": True}, {"key": "invalid"}):
            with self.subTest(values=values):
                self.assertEqual(self.send(**values).status_code, 400)
        self.assertEqual(Movement.objects.count(), 0)
        self.assertEqual(self.send(amount="1500.00").status_code, 200)
        self.assertEqual(self.send("undo", version=1, reason=" ").status_code, 400)

    def test_cancelled_and_income_are_not_payable(self):
        self.expense.status = "cancelled"
        self.expense.save()
        self.assertEqual(self.send().status_code, 409)
        self.expense.direction = "income"
        self.expense.save()
        self.assertEqual(self.send().status_code, 404)

    def test_transaction_rolls_back_if_audit_fails(self):
        with patch("finance.services.payments.PaymentHistory.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.send()
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, "pending")
        self.assertFalse(Movement.objects.exists())
        self.assertFalse(PaymentOperation.objects.exists())

    def test_correction_changes_effective_values_and_preserves_previous_audit(self):
        self.send()
        self.assertEqual(self.send("correct", version=1, amount="130.00", date="2026-10-01").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard/").json()["indicators"]["current_balance"], "870.00")
        history = PaymentHistory.objects.order_by("pk").last()
        self.assertEqual(history.before["amount"], "110.50")
        self.assertEqual(history.after["date"], "2026-10-01")

    def test_undo_restores_overdue_occurrence_even_after_series_closed(self):
        series = ExpenseSeries.objects.create(scenario=self.scenario, description="Luz", amount="120.00", start_date=date(2026, 10, 15), due_day=15)
        self.expense.series = series
        self.expense.competence = date(2026, 10, 1)
        self.expense.due_date = date(2026, 10, 15)
        self.expense.save()
        following = Occurrence.objects.create(scenario=self.scenario, series=series, competence=date(2026, 11, 1), description="Luz", amount="120.00", due_date=date(2026, 11, 15), direction="expense")
        self.assertEqual(self.send().status_code, 200)
        series.cancelled_from = date(2026, 10, 15)
        series.save()
        self.assertEqual(self.send("undo", version=1).status_code, 200)
        following.refresh_from_db()
        self.assertEqual(following.status, "pending")
        self.assertFalse(Movement.objects.filter(occurrence=following).exists())
        indicators = self.client.get("/api/dashboard/").json()["indicators"]
        self.assertEqual(indicators["current_balance"], "1000.00")
        self.assertEqual(indicators["pending_essential"], "120.00")

    def test_failed_correction_preserves_original_payment_and_history(self):
        self.send()
        with patch("finance.services.payments.PaymentHistory.objects.create", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                self.send("correct", version=1, amount="900.00")
        movement = Movement.objects.get()
        self.assertEqual(str(movement.amount), "110.50")
        self.assertEqual(movement.version, 1)
        self.assertEqual(PaymentOperation.objects.count(), 1)
        self.assertEqual(PaymentHistory.objects.count(), 1)

    def test_payment_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, data="{}", content_type="application/json").status_code, 403)


class ConcurrentPaymentTests(TransactionTestCase):
    def setUp(self):
        scenario = Scenario.objects.create(name="Concorrência", opening_date=date(2026, 10, 1), reference_date=date(2026, 10, 22), opening_balance="1000.00")
        self.expense = Occurrence.objects.create(scenario=scenario, description="Luz", amount="120.00", due_date=date(2026, 10, 25), direction="expense")

    def race(self, keys):
        self.assertNotIn("memory", str(connection.settings_dict["NAME"]))
        barrier = Barrier(2)
        def confirm(key):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = Client().post(f"/api/expenses/{self.expense.pk}/payment/", data=json.dumps({"key": key, "version": 0, "amount": "120.00", "date": "2026-10-22"}), content_type="application/json")
                return response.status_code, response.json()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(confirm, keys))

    def test_simultaneous_same_key_returns_one_result_and_one_audit(self):
        from finance.models import PaymentHistory, PaymentOperation
        key = str(uuid4())
        results = self.race([key, key])
        self.assertEqual([result[0] for result in results], [200, 200])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(Movement.objects.count(), 1)
        self.assertEqual(PaymentHistory.objects.count(), 1)
        self.assertEqual(PaymentOperation.objects.count(), 1)

    def test_simultaneous_distinct_keys_do_not_double_pay(self):
        results = self.race([str(uuid4()), str(uuid4())])
        self.assertEqual(sorted(result[0] for result in results), [200, 409])
        self.assertEqual(Movement.objects.count(), 1)
