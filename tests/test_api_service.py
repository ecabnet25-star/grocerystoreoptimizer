import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from grocery_optimizer.api.schemas import CreateUserRequest, LoginRequest, OptimizeRequest
from grocery_optimizer.api.service import _select_deal_route_stores, get_locations, optimize_from_request
from grocery_optimizer.api.users import create_user_profile_with_db, login_user_with_db
from grocery_optimizer.stores import Store


class TestApiService(unittest.TestCase):
    def test_locations_endpoint_source(self):
        locations = get_locations()
        self.assertIn("montreal", locations)

    def test_optimize_from_request(self):
        payload = OptimizeRequest(
            budget=40.0,
            max_items=6,
            strategy="knapsack",
            required_categories=["produce", "protein"],
            excluded_categories=["dairy"],
            location="montreal",
            postal_code="H3A1A1",
        )

        result = optimize_from_request(payload)

        self.assertIn("summary", result)
        self.assertIn("items", result)
        self.assertEqual(result["location"]["location_id"], "montreal")
        self.assertEqual(result["summary"]["strategy"], "knapsack")
        self.assertIn("total_units", result["summary"])
        self.assertIn("average_shelf_life_days", result["summary"])
        self.assertIn("shortest_shelf_life_days", result["summary"])
        self.assertIn("longest_shelf_life_days", result["summary"])
        self.assertIn("stores", result)
        self.assertIn("pricing_mode", result["stores"])
        self.assertIn("provider_health", result["stores"])
        self.assertIn("live_quote_coverage_percent", result["stores"])
        self.assertIn("providers_with_live_quotes", result["stores"])
        self.assertIn("retailer_research", result["stores"])
        self.assertGreaterEqual(len(result["stores"]["retailer_research"]["top_priority_retailers"]), 6)
        self.assertIn("insights", result)
        self.assertGreaterEqual(result["insights"]["budget_used_percent"], 0)
        self.assertIsInstance(result["insights"]["category_breakdown"], list)
        self.assertIsInstance(result["insights"]["next_actions"], list)
        self.assertIn("route", result)
        self.assertIn("selection_reason", result["route"])
        self.assertLessEqual(len(result["route"]["stops"]), 3)
        self.assertIn("item_assignments", result["route"])
        self.assertIn("net_route_savings", result["route"])

    def test_route_selection_uses_per_item_multi_store_savings(self):
        stores = [
            Store("all", "All Store", "All", "1 Main", "H3A1A1", 45.50, -73.56, "mid", 4.0, "montreal"),
            Store("protein", "Protein Deals", "Protein", "2 Main", "H3A1A1", 45.51, -73.57, "budget", 4.0, "montreal"),
            Store("produce", "Produce Deals", "Produce", "3 Main", "H3A1A1", 45.52, -73.58, "budget", 4.0, "montreal"),
        ]
        nearby = [(stores[0], 1.0), (stores[1], 1.3), (stores[2], 1.4)]
        comparison = [
            {"store_id": "all", "name": "All Store", "estimated_total": 20.0, "distance_km": 1.0},
            {"store_id": "protein", "name": "Protein Deals", "estimated_total": 24.0, "distance_km": 1.3},
            {"store_id": "produce", "name": "Produce Deals", "estimated_total": 24.0, "distance_km": 1.4},
        ]
        item_quotes = [
            {"store_id": "all", "store_name": "All Store", "item_name": "Eggs", "quantity": 1, "line_total": 10.0},
            {"store_id": "all", "store_name": "All Store", "item_name": "Greens", "quantity": 1, "line_total": 10.0},
            {"store_id": "protein", "store_name": "Protein Deals", "item_name": "Eggs", "quantity": 1, "line_total": 4.0},
            {"store_id": "protein", "store_name": "Protein Deals", "item_name": "Greens", "quantity": 1, "line_total": 12.0},
            {"store_id": "produce", "store_name": "Produce Deals", "item_name": "Eggs", "quantity": 1, "line_total": 12.0},
            {"store_id": "produce", "store_name": "Produce Deals", "item_name": "Greens", "quantity": 1, "line_total": 4.0},
        ]

        selected, meta = _select_deal_route_stores(
            nearby=nearby,
            store_comparison=comparison,
            item_quotes=item_quotes,
            max_stops=3,
        )

        self.assertEqual({store.store_id for store in selected}, {"protein", "produce"})
        self.assertEqual(meta["multi_store_total"], 8.0)
        self.assertGreater(meta["net_route_savings"], 0)
        self.assertEqual(len(meta["item_assignments"]), 2)

    def test_duplicate_email_rejected(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "dup.db")
            create_user_profile_with_db(CreateUserRequest(name="A", email="a@example.com", password="Password123"), db_path=db_path)

            with self.assertRaises(ValueError):
                create_user_profile_with_db(CreateUserRequest(name="B", email="a@example.com", password="Password123"), db_path=db_path)

    def test_login_issues_token(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "login.db")
            created = create_user_profile_with_db(
                CreateUserRequest(name="A", email="a@example.com", password="Password123"),
                db_path=db_path,
            )
            logged = login_user_with_db(LoginRequest(email="a@example.com", password="Password123"), db_path=db_path)

            self.assertIn("auth_token", created)
            self.assertIn("auth_token", logged)
            self.assertNotEqual(created["auth_token"], logged["auth_token"])


if __name__ == "__main__":
    unittest.main()
