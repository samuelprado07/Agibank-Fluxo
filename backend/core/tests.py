from django.test import SimpleTestCase


class HealthEndpointTests(SimpleTestCase):
    def test_health_returns_json_status_without_openai_or_database(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "agibank-preventivo"})

    def test_health_does_not_accept_writes(self):
        response = self.client.post("/api/health/", data={})
        self.assertEqual(response.status_code, 405)
