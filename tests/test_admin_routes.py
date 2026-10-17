"""Diagnostics and maintenance endpoints must never be public."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from prism.api.main import app


class AdminRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_debug_and_maintenance_routes_reject_unauthenticated_requests(self):
        with patch.dict("os.environ", {"PRISM_ADMIN_API_KEY": "test-only-secret"}):
            for path in (
                "/api/debug/auth",
                "/api/debug/db",
                "/api/debug/kalshi-log",
                "/api/debug/kalshi-log/download",
                "/api/debug/trading-pipeline-runs",
                "/api/debug/trading-pipeline-runs/example",
                "/api/debug/trading-pipeline-runs/example/download",
            ):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)
            self.assertEqual(self.client.post("/api/admin/sync-cache").status_code, 404)
            self.assertEqual(self.client.post("/api/debug/trading-pipeline-runs", json={}).status_code, 404)

    def test_admin_token_must_be_explicitly_configured(self):
        with patch.dict("os.environ", {"PRISM_ADMIN_API_KEY": ""}):
            response = self.client.get("/api/debug/auth", headers={"X-Prism-Admin-Key": "anything"})
            self.assertEqual(response.status_code, 404)

    def test_valid_admin_token_allows_diagnostic(self):
        with patch.dict("os.environ", {"PRISM_ADMIN_API_KEY": "test-only-secret"}):
            response = self.client.get("/api/debug/auth", headers={"X-Prism-Admin-Key": "test-only-secret"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["step"], "header")


if __name__ == "__main__":
    unittest.main()
