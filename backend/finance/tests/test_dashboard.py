from .auth_support import AuthenticatedTestCase, AuthenticatedTransactionTestCase
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from finance.models import Movement, Occurrence, Scenario


class DashboardTests(AuthenticatedTestCase):
    def setUp(self):
        self.today = date(2026, 10, 22)
        self.scenario = Scenario.objects.create(owner=self.user, name="Teste", opening_date=self.today - timedelta(days=2), reference_date=self.today, opening_balance="1000.10")

    def event(self, amount, offset, direction="expense", **kwargs):
        return Occurrence.objects.create(scenario=self.scenario, description="Conta", amount=amount, due_date=self.today + timedelta(days=offset), direction=direction, essential=direction == "expense", **kwargs)

    def dashboard(self):
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_current_balance_uses_only_realized_since_opening_without_duplicate(self):
        expense = self.event("200.05", -1, status="settled")
        Movement.objects.create(scenario=self.scenario, occurrence=expense, description="Pago", amount="200.05", date=self.today, direction="expense")
        Movement.objects.create(scenario=self.scenario, description="Anterior à abertura", amount="999.00", date=self.today - timedelta(days=3), direction="expense")
        self.event("1500.00", 10, direction="income")
        data = self.dashboard()
        self.assertEqual(data["indicators"]["current_balance"], "800.05")
        self.assertEqual(data["indicators"]["pending_essential"], "0.00")
        self.assertEqual(data["indicators"]["projected_final"], "2300.05")

    def test_overdue_today_and_income_day_expenses_are_committed(self):
        self.event("100.00", -2)
        self.event("200.00", 0)
        self.event("300.00", 5)
        self.event("400.00", 6)
        self.event("50.00", 1, status="cancelled")
        self.event("1800.00", 5, direction="income")
        data = self.dashboard()
        self.assertEqual(data["indicators"]["committed"], "600.00")
        self.assertEqual(data["indicators"]["own_remaining"], "400.10")
        self.assertEqual(data["indicators"]["pending_essential"], "1000.00")
        self.assertEqual(data["days"][0]["expenses"], "300.00")
        self.assertEqual(data["indicators"]["projected_final"], "1800.10")

    def test_risk_beyond_chart_and_same_day_recovery(self):
        self.event("1100.10", 17)
        self.event("200.00", 18)
        self.event("500.00", 20, direction="income")
        data = self.dashboard()
        self.assertEqual(data["period"]["end"], "2026-11-11")
        self.assertEqual(len(data["chart_days"]), 15)
        risk = next(a for a in data["alerts"] if a["type"] == "insufficient")
        self.assertEqual(risk["first_shortfall"], "100.00")
        self.assertEqual(risk["max_shortfall"], "300.00")
        self.assertTrue(risk["outside_chart"])
        self.assertEqual(risk["recovery_date"], "2026-11-11")

    def test_expenses_before_same_day_income_detect_intraday_shortfall(self):
        self.event("1200.10", 0)
        self.event("1500.00", 0, direction="income")
        data = self.dashboard()
        self.assertEqual(data["days"][0]["minimum_balance"], "-200.00")
        self.assertEqual(data["days"][0]["closing_balance"], "1300.00")
        self.assertTrue(any(a["type"] == "insufficient" for a in data["alerts"]))

    def test_absent_overdue_and_out_of_horizon_income_do_not_fake_coverage(self):
        self.event("9000.00", -1, direction="income")
        self.event("9000.00", 60, direction="income")
        self.event("100.00", 59)
        self.event("999.00", 60)
        data = self.dashboard()
        self.assertEqual(len(data["days"]), 60)
        self.assertIsNone(data["next_income"])
        self.assertIsNone(data["indicators"]["committed"])
        self.assertIsNone(data["indicators"]["own_remaining"])
        self.assertEqual(data["indicators"]["pending_essential"], "100.00")
        self.assertEqual(data["indicators"]["projected_final"], "900.10")
        self.assertTrue(any("atrasado" in w for w in data["warnings"]))

    def test_future_realized_and_settled_without_movement_are_flagged(self):
        self.event("100.00", 3, status="settled")
        Movement.objects.create(scenario=self.scenario, description="Futuro realizado", amount="999.00", date=self.today + timedelta(days=1), direction="income")
        data = self.dashboard()
        self.assertEqual(data["indicators"]["current_balance"], "1000.10")
        self.assertTrue(any("futura" in w for w in data["warnings"]))
        self.assertTrue(any("sem movimentação" in w for w in data["warnings"]))

    def test_linked_pending_occurrence_is_not_counted_twice(self):
        occurrence = self.event("100.00", 1)
        Movement.objects.create(scenario=self.scenario, occurrence=occurrence, description="Pago", amount="100.00", date=self.today, direction="expense")
        data = self.dashboard()
        self.assertEqual(data["indicators"]["current_balance"], "900.10")
        self.assertEqual(data["indicators"]["pending_essential"], "0.00")
        self.assertTrue(any("situação" in w for w in data["warnings"]))

    def test_invalid_or_future_movement_does_not_hide_pending_expense(self):
        for offset, direction, amount in [(1, "expense", "100.00"), (0, "income", "100.00"), (0, "expense", "-100.00")]:
            occurrence = self.event("100.00", 2)
            Movement.objects.create(scenario=self.scenario, occurrence=occurrence, description="Inconsistente", amount=amount, date=self.today + timedelta(days=offset), direction=direction)
        data = self.dashboard()
        self.assertEqual(data["indicators"]["current_balance"], "1000.10")
        self.assertEqual(data["indicators"]["pending_essential"], "300.00")
        self.assertEqual(data["indicators"]["projected_final"], "700.10")

    def test_zero_balance_is_no_margin_and_variable_expenses_affect_projection(self):
        self.event("1000.10", 0)
        self.event("50.00", 1, direction="expense", category="Variável")
        data = self.dashboard()
        self.assertTrue(any(a["type"] == "no_margin" for a in data["alerts"]))
        self.assertEqual(data["indicators"]["projected_final"], "-50.00")

    def test_same_day_zero_crossings_produce_only_one_margin_notice(self):
        self.scenario.opening_balance = Decimal("0.00")
        self.scenario.save()
        self.event("100.00", 0)
        self.event("100.00", 0, direction="income")
        data = self.dashboard()
        notices = [a for a in data["alerts"] if a["type"] == "no_margin" and a["date"] == self.today.isoformat()]
        self.assertEqual(len(notices), 1)

    def test_confirmed_income_updates_current_balance_without_repeating_forecast(self):
        income = self.event("100.00", 0, direction="income", status="settled")
        Movement.objects.create(scenario=self.scenario, occurrence=income, description="Recebido", amount="125.25", date=self.today, direction="income")
        data = self.dashboard()
        self.assertEqual(data["indicators"]["current_balance"], "1125.35")
        self.assertEqual(data["indicators"]["projected_final"], "1125.35")
        self.assertIsNone(data["next_income"])

    def test_invalid_opening_date_and_no_risk_scenario(self):
        data = self.dashboard()
        self.assertEqual(data["alerts"], [])
        self.scenario.opening_date = self.today + timedelta(days=1)
        self.scenario.save()
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 422)

    def test_empty_scenario_and_read_only_api(self):
        self.scenario.delete()
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 404)
        self.assertEqual(self.client.post("/api/dashboard/").status_code, 405)

    def test_demo_load_is_repeatable(self):
        call_command("load_demo", stdout=StringIO())
        counts = (Scenario.objects.count(), Occurrence.objects.count(), Movement.objects.count())
        call_command("load_demo", stdout=StringIO())
        self.assertEqual(counts, (Scenario.objects.count(), Occurrence.objects.count(), Movement.objects.count()))
