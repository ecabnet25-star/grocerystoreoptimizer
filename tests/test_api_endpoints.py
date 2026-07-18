import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def _unique_email(prefix: str = "test") -> str:
    """Generate a unique email for each test run to avoid IntegrityError."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


class _MockHttpResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class TestAPIEndpoints(unittest.TestCase):
    """HTTP-level tests for the Grocery Optimizer API."""

    @classmethod
    def setUpClass(cls):
        # Use a temporary database so tests don't pollute production data.
        cls._tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmp_db_path = cls._tmp_db.name
        cls._tmp_db.close()
        os.environ["GROCERY_DB_PATH"] = cls._tmp_db_path

        # Clear the storage module's initialization cache so it picks up the
        # new DB path.  Import *after* setting the env var.
        from grocery_optimizer.api import storage as _storage_mod
        _storage_mod._initialized.clear()
        _storage_mod.DEFAULT_DB_PATH = cls._tmp_db_path  # type: ignore[assignment]
        _storage_mod.init_db(cls._tmp_db_path)

        from grocery_optimizer.api.app import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls._tmp_db_path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # GET /health
    # ------------------------------------------------------------------
    def test_health_returns_200(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data["status"], ("ok", "degraded"))
        self.assertEqual(data["service"], "grocery-optimizer-api")

    def test_security_headers_are_present(self):
        response = self.client.get("/health")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("strict-origin", response.headers["Referrer-Policy"])

    def test_request_id_header_is_propagated(self):
        response = self.client.get("/health", headers={"X-Request-ID": "test-request-id"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Request-ID"], "test-request-id")

    def test_observability_metrics_returns_request_stats(self):
        self.client.get("/health")
        response = self.client.get("/observability/metrics")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("requests", data)
        self.assertGreaterEqual(data["requests"]["total"], 1)
        self.assertIn("providers", data)

    def test_deployment_status_reports_config_checks(self):
        response = self.client.get("/deployment/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("database", data)
        self.assertIn("warnings", data)

    def test_backup_database_endpoint_creates_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"GROCERY_BACKUP_DIR": temp_dir}, clear=False):
                response = self.client.post("/maintenance/backup-database")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["backed_up"])
            self.assertTrue(Path(data["backup_path"]).exists())

    # ------------------------------------------------------------------
    # GET /ready
    # ------------------------------------------------------------------
    def test_ready_returns_200(self):
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("ready", data)

    def test_ready_blocks_unsafe_production_config(self):
        with patch.dict(os.environ, {"GROCERY_ENV": "production", "GROCERY_API_CORS_ORIGINS": "*"}, clear=False):
            response = self.client.get("/ready")
        self.assertEqual(response.status_code, 503)

    # ------------------------------------------------------------------
    # GET /
    # ------------------------------------------------------------------
    def test_root_returns_200_with_service(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["service"], "grocery-optimizer-api")

    def test_api_root_returns_service_metadata(self):
        response = self.client.get("/api")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "grocery-optimizer-api")

    def test_vercel_root_redirects_to_frontend(self):
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=False):
            response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/index.html")

    # ------------------------------------------------------------------
    # GET /locations
    # ------------------------------------------------------------------
    def test_locations_returns_200_with_list(self):
        response = self.client.get("/locations")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("locations", data)
        self.assertIsInstance(data["locations"], list)
        self.assertGreater(len(data["locations"]), 0)
        montreal = next((loc for loc in data["locations"] if loc["location_id"] == "montreal"), None)
        self.assertIsNotNone(montreal)
        self.assertIn("retailer_research", montreal)
        self.assertIn("top_priority_retailers", montreal["retailer_research"])

    def test_retailer_research_returns_montreal_payload(self):
        response = self.client.get("/retailer-research/montreal")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["research"]["location_id"], "montreal")
        self.assertGreaterEqual(len(data["summary"]["top_priority_retailers"]), 6)
        self.assertGreaterEqual(data["summary"]["verified_seed_count"], 3)

    def test_retailer_research_unknown_location_returns_404(self):
        response = self.client.get("/retailer-research/unknown")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # GET /sample-request
    # ------------------------------------------------------------------
    def test_sample_request_returns_200_with_fields(self):
        response = self.client.get("/sample-request")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should contain default OptimizeRequest fields.
        self.assertIn("budget", data)
        self.assertIn("max_items", data)
        self.assertIn("strategy", data)
        self.assertIn("location", data)

    # ------------------------------------------------------------------
    # POST /optimize
    # ------------------------------------------------------------------
    def test_optimize_minimal_payload(self):
        payload = {"budget": 30, "max_items": 5}
        response = self.client.post("/optimize", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)

    def test_optimize_returns_summary(self):
        payload = {"budget": 30, "max_items": 5}
        response = self.client.post("/optimize", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("summary", data)
        self.assertIn("total_cost", data["summary"])
        self.assertIn("insights", data)
        self.assertIn("budget_used_percent", data["insights"])
        self.assertIn("category_breakdown", data["insights"])

    def test_optimize_rejects_invalid_strategy(self):
        payload = {"budget": 30, "max_items": 5, "strategy": "random"}
        response = self.client.post("/optimize", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_optimize_rejects_non_positive_budget(self):
        payload = {"budget": 0, "max_items": 5}
        response = self.client.post("/optimize", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_pricing_live_rejects_invalid_query_values(self):
        response = self.client.get("/pricing/live?budget=0&max_items=8&strategy=knapsack")
        self.assertEqual(response.status_code, 422)

        response = self.client.get("/pricing/live?budget=30&max_items=8&strategy=random")
        self.assertEqual(response.status_code, 422)

    def test_road_route_returns_normalized_geometry(self):
        payload = {
            "routes": [
                {
                    "distance": 1234.0,
                    "duration": 456.0,
                    "geometry": {
                        "coordinates": [
                            [-73.5673, 45.5017],
                            [-73.58, 45.49],
                            [-73.62, 45.47],
                        ]
                    },
                }
            ]
        }
        with patch("grocery_optimizer.api.app.urlopen", return_value=_MockHttpResponse(payload)):
            response = self.client.post(
                "/route/road",
                json={
                    "points": [
                        {"latitude": 45.5017, "longitude": -73.5673},
                        {"latitude": 45.47, "longitude": -73.62},
                    ]
                },
            )

        self.assertEqual(response.status_code, 200)
        route = response.json()["route"]
        self.assertEqual(route["provider"], "osrm")
        self.assertEqual(route["distance_km"], 1.23)
        self.assertEqual(route["duration_minutes"], 7.6)
        self.assertEqual(route["coordinates"][0], {"latitude": 45.5017, "longitude": -73.5673})

    def test_road_route_rejects_invalid_point_count(self):
        response = self.client.post(
            "/route/road",
            json={"points": [{"latitude": 45.5017, "longitude": -73.5673}]},
        )
        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------------
    # POST /users  and  POST /auth/login
    # ------------------------------------------------------------------
    def test_create_user_returns_user_and_token(self):
        email = _unique_email("create")
        payload = {"name": "Test User", "email": email, "password": "Password123"}
        response = self.client.post("/users", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("user", data)
        self.assertIn("auth_token", data)
        self.assertEqual(data["user"]["name"], "Test User")
        self.assertEqual(data["user"]["email"], email)

    def test_login_with_created_user(self):
        email = _unique_email("login")
        # First create a user.
        create_payload = {"name": "Login Test", "email": email, "password": "Password123"}
        create_response = self.client.post("/users", json=create_payload)
        self.assertEqual(create_response.status_code, 200)

        # Then login with the same email.
        login_payload = {"email": email, "password": "Password123"}
        login_response = self.client.post("/auth/login", json=login_payload)
        self.assertEqual(login_response.status_code, 200)
        data = login_response.json()
        self.assertIn("user", data)
        self.assertIn("auth_token", data)
        self.assertTrue(data["auth_token"])

    def test_login_unknown_email_returns_401(self):
        login_payload = {"email": "nonexistent@example.com", "password": "Password123"}
        response = self.client.post("/auth/login", json=login_payload)
        self.assertEqual(response.status_code, 401)

    def test_login_wrong_password_returns_401(self):
        email = _unique_email("wrongpw")
        create_response = self.client.post(
            "/users",
            json={"name": "Wrong Password", "email": email, "password": "Password123"},
        )
        self.assertEqual(create_response.status_code, 200)

        response = self.client.post(
            "/auth/login",
            json={"email": email, "password": "Wrongpass123"},
        )
        self.assertEqual(response.status_code, 401)

    def test_saved_plan_crud_accepts_authorization_header(self):
        email = _unique_email("plan")
        create_response = self.client.post(
            "/users",
            json={"name": "Plan User", "email": email, "password": "Password123"},
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        user_id = created["user"]["id"]
        token = created["auth_token"]
        headers = {"Authorization": f"Bearer {token}"}

        save_response = self.client.post(
            f"/users/{user_id}/plans",
            headers=headers,
            json={
                "label": "Header Plan",
                "optimize_request": {"budget": 25, "max_items": 4, "location": "montreal"},
                "optimization_result": {
                    "summary": {"total_cost": 12.34},
                    "items": [],
                    "source": "precomputed-test-result",
                },
            },
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(save_response.json()["result"]["source"], "precomputed-test-result")
        plan_id = save_response.json()["saved"]["id"]

        list_response = self.client.get(f"/users/{user_id}/plans", headers=headers)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["plans"][0]["id"], plan_id)

        rename_response = self.client.patch(
            f"/users/{user_id}/plans/{plan_id}",
            headers=headers,
            json={"label": "Renamed Header Plan"},
        )
        self.assertEqual(rename_response.status_code, 200)
        self.assertTrue(rename_response.json()["updated"])

        get_response = self.client.get(f"/users/{user_id}/plans/{plan_id}", headers=headers)
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["plan"]["label"], "Renamed Header Plan")

        delete_response = self.client.delete(f"/users/{user_id}/plans/{plan_id}", headers=headers)
        self.assertEqual(delete_response.status_code, 200)
        self.assertTrue(delete_response.json()["deleted"])

    def test_auth_token_actions_accept_authorization_header(self):
        email = _unique_email("token")
        create_response = self.client.post(
            "/users",
            json={"name": "Token User", "email": email, "password": "Password123"},
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        user_id = created["user"]["id"]
        token = created["auth_token"]

        refresh_response = self.client.post(
            "/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": user_id},
        )
        self.assertEqual(refresh_response.status_code, 200)
        refreshed_token = refresh_response.json()["auth_token"]
        self.assertNotEqual(token, refreshed_token)

        logout_response = self.client.post(
            "/auth/logout",
            headers={"Authorization": f"Bearer {refreshed_token}"},
            json={"user_id": user_id},
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertTrue(logout_response.json()["revoked"])

    def test_admin_endpoint_requires_configured_token_in_production(self):
        with patch.dict(os.environ, {"GROCERY_ENV": "production", "GROCERY_ADMIN_TOKEN": ""}, clear=False):
            response = self.client.post("/maintenance/cleanup-tokens")
        self.assertEqual(response.status_code, 503)

    def test_admin_endpoint_rejects_invalid_token(self):
        with patch.dict(os.environ, {"GROCERY_ENV": "production", "GROCERY_ADMIN_TOKEN": "secret"}, clear=False):
            response = self.client.post(
                "/maintenance/cleanup-tokens",
                headers={"Authorization": "Bearer wrong"},
            )
        self.assertEqual(response.status_code, 403)

    def test_admin_endpoint_accepts_valid_token(self):
        with patch.dict(os.environ, {"GROCERY_ENV": "production", "GROCERY_ADMIN_TOKEN": "secret"}, clear=False):
            response = self.client.post(
                "/maintenance/cleanup-tokens",
                headers={"Authorization": "Bearer secret"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("removed_tokens", response.json())


if __name__ == "__main__":
    unittest.main()
