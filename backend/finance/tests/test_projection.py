from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from django.db import OperationalError, close_old_connections, connection
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase

from finance.models import Movement, Occurrence, Scenario
from finance.services.dashboard import build_dashboard
from finance.services.payments import change_payment
from finance.services.projection import project


class ProjectionTraceTests(SimpleTestCase):
    def test_sequence_explains_minimum_closing_balance_and_intraday_risk(self):
        reference = date(2026, 10, 22)
        def event(pk, amount, direction):
            return {"id": pk, "description": str(pk), "amount": Decimal(amount), "date": reference, "due_date": reference, "direction": direction}
        events = [event(1, "200.00", "income"), event(3, "80.00", "expense"), event(2, "50.00", "expense")]
        days, alerts = project(Decimal("100.00"), reference, reference + timedelta(days=1), events)
        first, empty = days
        self.assertEqual([item["occurrence_id"] for item in first["events"]], [2, 3, 1])
        self.assertEqual([item["sequence"] for item in first["events"]], [1, 2, 3])
        self.assertEqual([item["balance_after"] for item in first["events"]], [Decimal("50.00"), Decimal("-30.00"), Decimal("170.00")])
        for day in days:
            signed = sum((item["amount"] if item["direction"] == "income" else -item["amount"] for item in day["events"]), Decimal("0.00"))
            self.assertEqual(day["opening_balance"] + signed, day["closing_balance"])
            self.assertEqual(min([day["opening_balance"], *[item["balance_after"] for item in day["events"]]]), day["minimum_balance"])
        self.assertTrue(any(item["type"] == "insufficient" for item in alerts))
        self.assertEqual(first["minimum_balance"], Decimal("-30.00"))
        self.assertGreater(first["closing_balance"], 0)
        self.assertIn("reference_cutoff", first["assumption_codes"])
        self.assertEqual(empty["events"], [])
        self.assertEqual(empty["opening_balance"], first["closing_balance"])
        self.assertIn("no_events", empty["assumption_codes"])


class ProjectionApiTests(TestCase):
    def setUp(self):
        self.reference = date(2026, 10, 22)
        self.scenario = Scenario.objects.create(name="Projeção", opening_date=date(2026, 10, 1), reference_date=self.reference, opening_balance="1000.00")

    def test_reference_cutoff_overdue_dates_and_event_origins(self):
        paid = Occurrence.objects.create(scenario=self.scenario, description="Pago", amount="100.00", due_date=self.reference, direction="expense", status="settled")
        Movement.objects.create(scenario=self.scenario, occurrence=paid, description="Pago", amount="80.00", date=self.reference, direction="expense")
        estimate = Occurrence.objects.create(scenario=self.scenario, description="Transporte", amount="30.00", due_date=self.reference - timedelta(days=1), direction="expense", is_estimate=True)
        Occurrence.objects.create(scenario=self.scenario, description="Renda atrasada", amount="9000.00", due_date=self.reference - timedelta(days=1), direction="income")
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        day = data["days"][0]
        self.assertEqual(day["opening_balance"], "920.00")
        self.assertEqual(day["closing_balance"], "890.00")
        self.assertEqual(len(day["events"]), 1)
        event = day["events"][0]
        self.assertEqual(event["occurrence_id"], estimate.pk)
        self.assertEqual(event["original_date"], "2026-10-21")
        self.assertEqual(event["effective_date"], "2026-10-22")
        self.assertEqual(event["source"], "estimate")
        self.assertIn("overdue_expense_at_reference", day["assumption_codes"])
        for item in data["days"]:
            for code in item["assumption_codes"]:
                self.assertIn(code, data["assumption_details"])
        self.assertTrue(data["current_balance_basis"]["includes_reference_day"])
        self.assertEqual(data["period"]["chart_start"], "2026-10-22")
        self.assertEqual(data["period"]["chart_end"], "2026-11-05")
        self.assertEqual(data["projection_policy"]["same_day_order"], "expenses_then_income_then_id")

    def test_monthly_origins_and_horizon_boundaries(self):
        self.client.post("/api/expenses/", data='{"description":"Conta mensal","amount":"10.00","category":"Casa","due_date":"2026-10-23","essential":true,"recurring":true}', content_type="application/json")
        Occurrence.objects.create(scenario=self.scenario, description="Renda", amount="200.00", due_date=self.reference + timedelta(days=20), direction="income")
        data = self.client.get("/api/dashboard/").json()
        self.assertEqual(len(data["chart_days"]), 15)
        self.assertEqual(len(data["days"]), 21)
        self.assertEqual(data["days"][-1]["date"], data["period"]["end"])
        event = data["days"][1]["events"][0]
        self.assertTrue(event["is_recurring"])
        self.assertEqual(event["series_type"], "expense")
        self.assertEqual(event["competence"], "2026-10-01")
        self.assertIn("monthly_occurrence", data["days"][1]["assumption_codes"])

    def test_capture_reloads_scenario_before_projecting(self):
        Scenario.objects.filter(pk=self.scenario.pk).update(opening_balance="2000.00")
        self.assertEqual(build_dashboard(self.scenario)["indicators"]["current_balance"], Decimal("2000.00"))

    def test_database_busy_returns_retryable_response_without_hiding_other_errors(self):
        with patch("finance.views.build_dashboard", side_effect=OperationalError("database is locked")):
            response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "1")
        self.assertEqual(response.json()["code"], "projection_busy")
        with patch("finance.views.build_dashboard", side_effect=OperationalError("missing table")):
            with self.assertRaises(OperationalError):
                self.client.get("/api/dashboard/")


class ProjectionSnapshotTests(TransactionTestCase):
    def test_confirmation_cannot_split_movement_and_occurrence_capture(self):
        reference = date(2026, 10, 22)
        scenario = Scenario.objects.create(name="Snapshot", opening_date=date(2026, 10, 1), reference_date=reference, opening_balance="1000.00")
        expense = Occurrence.objects.create(scenario=scenario, description="Conta", amount="100.00", due_date=reference, direction="expense")
        capture_paused, resume_capture, writer_started, writer_done = Event(), Event(), Event(), Event()

        def reader():
            close_old_connections()
            def pause_before_occurrences(execute, sql, params, many, context):
                if 'FROM "finance_occurrence"' in sql and not capture_paused.is_set():
                    capture_paused.set()
                    if not resume_capture.wait(10):
                        raise TimeoutError("capture not resumed")
                return execute(sql, params, many, context)
            try:
                with connection.execute_wrapper(pause_before_occurrences):
                    return build_dashboard(scenario)
            finally:
                close_old_connections()

        def writer():
            close_old_connections()
            writer_started.set()
            try:
                return change_payment(expense.pk, "confirm", {"key": str(uuid4()), "version": 0, "amount": "80.00", "date": reference.isoformat()})
            finally:
                writer_done.set()
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(reader)
            try:
                self.assertTrue(capture_paused.wait(10))
                writing = pool.submit(writer)
                self.assertTrue(writer_started.wait(10))
                writer_finished_during_capture = writer_done.wait(0.3)
            finally:
                resume_capture.set()
            before = reading.result(timeout=10)
            writing.result(timeout=10)
        self.assertFalse(writer_finished_during_capture)
        self.assertEqual(before["indicators"]["current_balance"], Decimal("1000.00"))
        self.assertEqual(before["days"][0]["closing_balance"], Decimal("900.00"))
        after = self.client.get("/api/dashboard/").json()
        self.assertEqual(after["indicators"]["current_balance"], "920.00")
        self.assertEqual(after["days"][0]["events"], [])
