from datetime import date, timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from finance.models import Occurrence, Scenario
from finance.services.projection import project


class PreventiveAlertTests(SimpleTestCase):
    reference = date(2026, 10, 23)

    def event(self, pk, amount, offset=0, direction="expense"):
        day = self.reference + timedelta(days=offset)
        return {"id": pk, "description": str(pk), "amount": Decimal(amount), "date": day, "due_date": day, "direction": direction}

    def simulate(self, events, balance="100.00", days=3):
        return project(Decimal(balance), self.reference, self.reference + timedelta(days=days - 1), events)

    def test_initial_crossing_first_day_peak_and_interval_peak_are_distinct(self):
        _, alerts = self.simulate([self.event(1, "150.00"), self.event(2, "250.00"), self.event(3, "100.00", 1), self.event(4, "600.00", 2, "income")])
        risk = next(a for a in alerts if a["type"] == "insufficient")
        self.assertEqual(risk["first_shortfall"], Decimal("50.00"))
        self.assertEqual(risk["first_day_shortfall"], Decimal("300.00"))
        self.assertEqual(risk["max_shortfall"], Decimal("400.00"))
        self.assertEqual(risk["max_shortfall_date"], self.reference + timedelta(days=1))
        self.assertEqual(risk["start_sequence"], 1)
        self.assertEqual(len([a for a in alerts if a["type"] == "insufficient"]), 1)
        self.assertFalse(risk["ongoing"])
        self.assertEqual(risk["end_reason"], "positive_margin")

    def test_zero_closes_deficit_without_claiming_positive_margin(self):
        _, alerts = self.simulate([self.event(1, "150.00"), self.event(2, "50.00", 0, "income")])
        risk = next(a for a in alerts if a["type"] == "insufficient")
        self.assertEqual(risk["end_reason"], "zero_margin")
        self.assertEqual(risk["recovery_balance"], Decimal("0.00"))
        self.assertIsNone(risk["margin_recovery_date"])
        self.assertEqual(len([a for a in alerts if a["type"] == "no_margin"]), 1)
        self.assertTrue(risk["income_dependency"]["recovery_relies_on_estimates"])

    def test_later_positive_income_records_margin_after_zero_exit(self):
        _, alerts = self.simulate([self.event(1, "150.00"), self.event(2, "50.00", 0, "income"), self.event(3, "10.00", 1, "income")])
        risk = next(a for a in alerts if a["type"] == "insufficient")
        self.assertEqual(risk["recovery_date"], self.reference)
        self.assertEqual(risk["margin_recovery_date"], self.reference + timedelta(days=1))
        self.assertEqual(risk["margin_recovery_income"]["id"], 3)

    def test_zero_followed_by_new_deficit_starts_another_episode(self):
        _, alerts = self.simulate([self.event(1, "150.00"), self.event(2, "50.00", 0, "income"), self.event(3, "20.00", 1), self.event(4, "30.00", 2, "income")])
        risks = [a for a in alerts if a["type"] == "insufficient"]
        self.assertEqual(len(risks), 2)
        self.assertIsNone(risks[0]["margin_recovery_date"])
        self.assertNotEqual(risks[0]["id"], risks[1]["id"])

    def test_partial_income_does_not_claim_recovery(self):
        _, alerts = self.simulate([self.event(1, "300.00"), self.event(2, "50.00", 0, "income"), self.event(3, "200.00", 2, "income")])
        risk = next(a for a in alerts if a["type"] == "insufficient")
        self.assertEqual([item["role"] for item in risk["recovery_incomes"]], ["partial_reduction", "closes_deficit"])
        self.assertEqual(risk["recovery_incomes"][0]["remaining_shortfall"], Decimal("150.00"))
        self.assertEqual(risk["recovery_incomes"][1]["remaining_shortfall"], Decimal("0.00"))

    def test_ongoing_initial_deficit_has_no_invented_expense_or_recovery(self):
        _, alerts = self.simulate([self.event(1, "10.00", 1, "income")], balance="-50.00")
        risk = next(a for a in alerts if a["type"] == "insufficient")
        self.assertTrue(risk["starts_with_deficit"])
        self.assertEqual(risk["start_sequence"], 0)
        self.assertEqual(risk["expenses"], [])
        self.assertTrue(risk["ongoing"])
        self.assertEqual(risk["end_reason"], "horizon_limit")
        self.assertNotIn("recovery_date", risk)
        self.assertFalse(risk["income_dependency"]["recovery_relies_on_estimates"])
        self.assertTrue(risk["income_dependency"]["reduction_relies_on_estimates"])

    def test_context_and_assumptions_are_limited_to_episode_dates(self):
        _, alerts = self.simulate([self.event(1, "10.00"), self.event(2, "150.00", 1), self.event(3, "100.00", 2, "income")])
        risk = next(a for a in alerts if a["type"] == "insufficient")
        self.assertEqual([expense["id"] for expense in risk["expenses"]], [2])
        self.assertIn("continuous_negative_episode", risk["assumption_codes"])
        self.assertIn("expenses_before_income", risk["assumption_codes"])
        self.assertEqual(risk["reference_date"], self.reference)
        self.assertEqual(risk["analysis_end"], self.reference + timedelta(days=2))

    def test_positive_close_does_not_hide_intraday_risk_and_ids_are_repeatable(self):
        events = [self.event(1, "200.00"), self.event(2, "300.00", 0, "income")]
        days, first = self.simulate(events)
        _, second = self.simulate(events)
        self.assertEqual(first, second)
        self.assertGreater(days[0]["closing_balance"], 0)
        self.assertTrue(any(a["type"] == "insufficient" for a in first))

    def test_zero_interval_is_not_repeated_on_each_empty_day(self):
        _, alerts = self.simulate([], balance="0.00", days=5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["type"], "no_margin")

    def test_recovery_day_expenses_are_context_not_a_payment_priority(self):
        _, alerts = self.simulate([self.event(1, "150.00"), self.event(2, "10.00", 1), self.event(3, "100.00", 1, "income"), self.event(4, "5.00", 2)])
        risk = next(a for a in alerts if a["type"] == "insufficient")
        self.assertEqual([item["id"] for item in risk["expenses"]], [1, 2])
        self.assertEqual(risk["end_sequence"], 2)


class AlertApiTests(TestCase):
    def setUp(self):
        self.reference = date(2026, 10, 23)
        self.scenario = Scenario.objects.create(name="Alertas", opening_date=self.reference, reference_date=self.reference, opening_balance="100.00")

    def event(self, amount, offset, direction="expense", status="pending"):
        return Occurrence.objects.create(scenario=self.scenario, description=direction, amount=amount, direction=direction, status=status, due_date=self.reference + timedelta(days=offset))

    def test_next_income_outside_analysis_is_explicit_and_not_a_recovery(self):
        self.event("10.00", 1, "income")
        self.event("200.00", 2)
        later = self.event("500.00", 20, "income")
        self.event("9000.00", -1, "income")
        self.event("9000.00", 3, "income", "cancelled")
        data = self.client.get("/api/dashboard/").json()
        risk = next(a for a in data["alerts"] if a["type"] == "insufficient")
        self.assertEqual(risk["next_income"]["id"], later.pk)
        self.assertTrue(risk["next_income"]["outside_analysis"])
        self.assertTrue(risk["ongoing"])
        self.assertEqual(risk["recovery_incomes"], [])
        self.assertEqual(data["period"]["analysis_days"], 15)
        for code in risk["assumption_codes"]:
            self.assertIn(code, data["assumption_details"])

    def test_update_recalculates_alerts_without_persisting_alert_records(self):
        expense = self.event("200.00", 1)
        self.assertTrue(self.client.get("/api/dashboard/").json()["alerts"])
        response = self.client.patch(f"/api/expenses/{expense.pk}/", data='{"amount":"50.00"}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard/").json()["alerts"], [])

    def test_zero_alert_does_not_call_applied_income_the_next_receipt(self):
        self.event("150.00", 0)
        first = self.event("50.00", 0, "income")
        following = self.event("10.00", 1, "income")
        alerts = self.client.get("/api/dashboard/").json()["alerts"]
        risk = next(item for item in alerts if item["type"] == "insufficient")
        margin = next(item for item in alerts if item["type"] == "no_margin")
        self.assertEqual(risk["next_income"]["id"], first.pk)
        self.assertEqual(margin["next_income"]["id"], following.pk)
