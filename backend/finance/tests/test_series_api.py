import json
from datetime import date

from django.test import Client, TestCase

from finance.models import ExpenseSeries, Movement, Occurrence, Scenario


class SeriesApiTests(TestCase):
    def setUp(self):
        self.scenario = Scenario.objects.create(name="Conta", opening_date=date(2026, 1, 1), reference_date=date(2026, 1, 15), opening_balance="1500.00")
        payload = {"description": "Aluguel", "amount": "500.00", "category": "Moradia", "due_date": "2026-01-31", "essential": True, "recurring": True}
        response = self.send("post", "/api/expenses/", payload)
        self.assertEqual(response.status_code, 201)
        self.series = ExpenseSeries.objects.get(pk=response.json()["series_id"])
        self.url = f"/api/recurrences/{self.series.pk}/"

    def send(self, method, url, payload):
        return getattr(self.client, method)(url, data=json.dumps(payload), content_type="application/json")

    def test_list_exposes_effective_configuration_and_explicit_due_day(self):
        response = self.client.get("/api/recurrences/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["recurrences"][0]["due_day"], 31)
        self.assertEqual(self.send("patch", self.url, {"amount": "600.00", "effective_from": "2026-01-01"}).status_code, 200)
        self.assertEqual(self.client.get(self.url).json()["amount"], "600.00")

    def test_future_configuration_is_shown_separately_from_current_values(self):
        self.assertEqual(self.send("patch", self.url, {"amount": "610.00", "effective_from": "2026-02-01"}).status_code, 200)
        data = self.client.get(self.url).json()
        self.assertEqual(data["amount"], "500.00")
        self.assertEqual(data["next_change"], {"date": "2026-02-01", "amount": "610.00", "due_day": 31})

    def test_stop_generation_can_keep_all_existing_pending_occurrences(self):
        self.assertEqual(self.send("post", self.url + "cancel/", {"from_date": "2026-02-01", "cancel_pending": False}).status_code, 200)
        self.assertEqual(Occurrence.objects.filter(status="pending").count(), 2)
        self.scenario.reference_date = date(2026, 3, 1)
        self.scenario.save()
        self.client.get("/api/dashboard/")
        self.assertEqual(Occurrence.objects.count(), 2)

    def test_optional_cancel_uses_actual_due_date_and_preserves_paid_occurrences(self):
        january = Occurrence.objects.get(competence=date(2026, 1, 1))
        january.due_date = date(2026, 2, 4)
        january.is_exception = True
        january.save()
        february = Occurrence.objects.get(competence=date(2026, 2, 1))
        february.status = "settled"
        february.save()
        Movement.objects.create(scenario=self.scenario, occurrence=february, description="Pago", amount="500.00", date=date(2026, 1, 15), direction="expense")
        self.assertEqual(self.send("post", self.url + "cancel/", {"from_date": "2026-02-01", "cancel_pending": True}).status_code, 200)
        january.refresh_from_db()
        february.refresh_from_db()
        self.assertEqual(january.status, "cancelled")
        self.assertEqual(february.status, "settled")

    def test_shorter_vigency_preserves_existing_occurrences_but_stops_new_ones(self):
        self.assertEqual(self.send("patch", self.url, {"end_date": "2026-01-31"}).status_code, 200)
        self.assertEqual(Occurrence.objects.filter(status="pending").count(), 2)
        self.scenario.reference_date = date(2026, 3, 1)
        self.scenario.save()
        self.client.get("/api/dashboard/")
        self.assertEqual(Occurrence.objects.count(), 2)

    def test_february_edit_does_not_change_monthly_day_31_accidentally(self):
        february = Occurrence.objects.get(competence=date(2026, 2, 1))
        response = self.send("patch", f"/api/expenses/{february.pk}/", {"amount": "510.00", "scope": "following"})
        self.assertEqual(response.status_code, 200)
        self.scenario.reference_date = date(2026, 3, 1)
        self.scenario.save()
        self.client.get("/api/dashboard/")
        self.assertTrue(Occurrence.objects.filter(due_date=date(2026, 3, 31), amount="510.00").exists())

    def test_series_edit_preserves_exceptions_and_cancelled_occurrences(self):
        february = Occurrence.objects.get(competence=date(2026, 2, 1))
        february.is_exception = True
        february.amount = "700.00"
        february.save()
        self.assertEqual(self.send("patch", self.url, {"amount": "550.00", "due_day": 20, "effective_from": "2026-01-01"}).status_code, 200)
        february.refresh_from_db()
        self.assertEqual(str(february.amount), "700.00")
        self.assertEqual(february.due_date, date(2026, 2, 28))

    def test_invalid_fields_and_start_date_changes_are_rejected(self):
        for payload in ({"due_day": 32}, {"due_day": True}, {"due_day": "31"}, {"amount": "0"}, {"start_date": "2026-02-01"}, {"end_date": "2025-01-01"}, {"essential": "true"}):
            with self.subTest(payload=payload):
                self.assertEqual(self.send("patch", self.url, payload).status_code, 400)
        self.assertEqual(self.send("post", self.url + "cancel/", {"from_date": "2026-01-14", "cancel_pending": True}).status_code, 400)

    def test_invalid_end_date_types_return_validation_errors(self):
        for value in (123, True, ["2026-02-01"], {"date": "2026-02-01"}):
            with self.subTest(value=value):
                self.assertEqual(self.send("patch", self.url, {"end_date": value}).status_code, 400)

    def test_series_writes_require_csrf_and_use_only_active_scenario(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.patch(self.url, data='{}', content_type="application/json").status_code, 403)
        self.assertEqual(client.post(self.url + "cancel/", data='{}', content_type="application/json").status_code, 403)
        other = Scenario.objects.create(name="Outra conta", opening_date=date(2026, 1, 1), reference_date=date(2026, 1, 15), opening_balance="0.00")
        hidden = ExpenseSeries.objects.create(scenario=other, description="Outra série", amount="10.00", start_date=date(2026, 1, 1), due_day=1)
        self.assertEqual(self.client.get(f"/api/recurrences/{hidden.pk}/").status_code, 404)
        self.assertEqual(self.send("patch", f"/api/recurrences/{hidden.pk}/", {"amount": "20.00"}).status_code, 404)

    def test_paid_occurrence_is_independent_and_dashboard_never_adds_series_twice(self):
        january = Occurrence.objects.get(competence=date(2026, 1, 1))
        january.status = "settled"
        january.save()
        Movement.objects.create(scenario=self.scenario, occurrence=january, description="Aluguel pago", amount="500.00", date=self.scenario.reference_date, direction="expense")
        data = self.client.get("/api/dashboard/").json()
        self.assertEqual(data["indicators"]["current_balance"], "1000.00")
        self.assertEqual(data["indicators"]["pending_essential"], "500.00")
        self.assertEqual(data["indicators"]["projected_final"], "500.00")
        self.assertEqual(Occurrence.objects.get(competence=date(2026, 2, 1)).status, "pending")
