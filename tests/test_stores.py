import unittest
from pathlib import Path

from grocery_optimizer.stores import (
    PostalCodeInfo,
    Store,
    calculate_distance_km,
    find_nearby_stores,
    get_price_tier_multiplier,
    load_postal_codes,
    load_stores,
    optimize_route,
)

# Resolve config directories relative to this project's root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_STORES_DIR = _PROJECT_ROOT / "config" / "stores"
_POSTAL_CODES_DIR = _PROJECT_ROOT / "config" / "postal_codes"


class TestHaversineDistance(unittest.TestCase):
    """Tests for calculate_distance_km (Haversine formula)."""

    def test_same_point_returns_zero(self):
        dist = calculate_distance_km(45.5017, -73.5673, 45.5017, -73.5673)
        self.assertEqual(dist, 0.0)

    def test_known_distance_montreal_to_toronto(self):
        # Montreal (45.5017, -73.5673) to Toronto (43.6532, -79.3832)
        # Real distance is approximately 504 km.
        dist = calculate_distance_km(45.5017, -73.5673, 43.6532, -79.3832)
        self.assertAlmostEqual(dist, 504.0, delta=10.0)

    def test_short_distance_within_montreal(self):
        # Two close Montreal points: H3A1A1 (45.5017, -73.5673) and
        # IGA Downtown (45.4959, -73.5768).  Should be roughly 1 km.
        dist = calculate_distance_km(45.5017, -73.5673, 45.4959, -73.5768)
        self.assertGreater(dist, 0.0)
        self.assertLess(dist, 5.0)

    def test_distance_is_symmetric(self):
        d1 = calculate_distance_km(45.5017, -73.5673, 40.7128, -74.0060)
        d2 = calculate_distance_km(40.7128, -74.0060, 45.5017, -73.5673)
        self.assertEqual(d1, d2)

    def test_returns_float(self):
        dist = calculate_distance_km(0.0, 0.0, 1.0, 1.0)
        self.assertIsInstance(dist, float)


class TestLoadStores(unittest.TestCase):
    """Tests for load_stores()."""

    def test_loads_non_empty_list(self):
        stores = load_stores(base_dir=_STORES_DIR)
        self.assertIsInstance(stores, list)
        self.assertGreater(len(stores), 0)

    def test_items_are_store_objects(self):
        stores = load_stores(base_dir=_STORES_DIR)
        for store in stores:
            self.assertIsInstance(store, Store)

    def test_store_has_required_fields(self):
        stores = load_stores(base_dir=_STORES_DIR)
        store = stores[0]
        self.assertTrue(store.store_id)
        self.assertTrue(store.name)
        self.assertTrue(store.chain)
        self.assertIsInstance(store.latitude, float)
        self.assertIsInstance(store.longitude, float)
        self.assertIn(store.price_tier, ("budget", "mid", "premium"))

    def test_missing_directory_returns_empty(self):
        stores = load_stores(base_dir="/nonexistent/path/stores")
        self.assertEqual(stores, [])


class TestLoadPostalCodes(unittest.TestCase):
    """Tests for load_postal_codes()."""

    def test_loads_non_empty_dict(self):
        codes = load_postal_codes(base_dir=_POSTAL_CODES_DIR)
        self.assertIsInstance(codes, dict)
        self.assertGreater(len(codes), 0)

    def test_values_are_postal_code_info(self):
        codes = load_postal_codes(base_dir=_POSTAL_CODES_DIR)
        for key, info in codes.items():
            self.assertIsInstance(info, PostalCodeInfo)
            self.assertEqual(key, info.postal_code)

    def test_h3a1a1_present(self):
        codes = load_postal_codes(base_dir=_POSTAL_CODES_DIR)
        self.assertIn("H3A1A1", codes)
        self.assertEqual(codes["H3A1A1"].city, "Montreal")

    def test_missing_directory_returns_empty(self):
        codes = load_postal_codes(base_dir="/nonexistent/path/postal_codes")
        self.assertEqual(codes, {})


class TestFindNearbyStores(unittest.TestCase):
    """Tests for find_nearby_stores()."""

    def setUp(self):
        self.stores = load_stores(base_dir=_STORES_DIR)
        self.postal_codes = load_postal_codes(base_dir=_POSTAL_CODES_DIR)

    def test_finds_montreal_stores_for_h3a1a1(self):
        nearby = find_nearby_stores("H3A1A1", self.stores, self.postal_codes, max_distance_km=20.0)
        self.assertIsInstance(nearby, list)
        self.assertGreater(len(nearby), 0)

    def test_results_are_store_distance_tuples(self):
        nearby = find_nearby_stores("H3A1A1", self.stores, self.postal_codes, max_distance_km=20.0)
        for store, distance in nearby:
            self.assertIsInstance(store, Store)
            self.assertIsInstance(distance, float)
            self.assertLessEqual(distance, 20.0)

    def test_results_sorted_by_distance(self):
        nearby = find_nearby_stores("H3A1A1", self.stores, self.postal_codes, max_distance_km=20.0)
        distances = [d for _, d in nearby]
        self.assertEqual(distances, sorted(distances))

    def test_unknown_postal_code_returns_empty(self):
        nearby = find_nearby_stores("ZZZZZZ", self.stores, self.postal_codes, max_distance_km=20.0)
        self.assertEqual(nearby, [])

    def test_handles_spaces_in_postal_code(self):
        nearby = find_nearby_stores("H3A 1A1", self.stores, self.postal_codes, max_distance_km=20.0)
        self.assertGreater(len(nearby), 0)

    def test_finds_montreal_location_stores(self):
        nearby = find_nearby_stores("H3A1A1", self.stores, self.postal_codes, max_distance_km=20.0)
        location_ids = {store.location_id for store, _ in nearby}
        self.assertIn("montreal", location_ids)

    def test_montreal_includes_spreadsheet_seed_stores(self):
        stores = load_stores(base_dir=_STORES_DIR)
        ids = {store.store_id for store in stores}
        self.assertIn("tnt-vsl-mtl", ids)
        self.assertIn("akhavan-ndg-mtl", ids)
        self.assertIn("pa-du-parc-mtl", ids)


class TestOptimizeRoute(unittest.TestCase):
    """Tests for optimize_route()."""

    def setUp(self):
        self.origin = PostalCodeInfo(
            postal_code="H3A1A1",
            latitude=45.5017,
            longitude=-73.5673,
            city="Montreal",
            province_state="QC",
            country="CA",
        )
        self.stores = [
            Store(
                store_id="s1", name="Store A", chain="ChainA",
                address="Addr A", postal_code="H3G1R8",
                latitude=45.4959, longitude=-73.5768,
                price_tier="mid", quality_rating=4.0, location_id="montreal",
            ),
            Store(
                store_id="s2", name="Store B", chain="ChainB",
                address="Addr B", postal_code="H4C2G3",
                latitude=45.4849, longitude=-73.5817,
                price_tier="budget", quality_rating=3.5, location_id="montreal",
            ),
            Store(
                store_id="s3", name="Store C", chain="ChainC",
                address="Addr C", postal_code="H2X3P9",
                latitude=45.5101, longitude=-73.5832,
                price_tier="premium", quality_rating=4.5, location_id="montreal",
            ),
        ]

    def test_returns_list_of_correct_tuples(self):
        route = optimize_route(self.stores, self.origin)
        self.assertIsInstance(route, list)
        self.assertEqual(len(route), len(self.stores))
        for store, distance, order in route:
            self.assertIsInstance(store, Store)
            self.assertIsInstance(distance, float)
            self.assertIsInstance(order, int)

    def test_orders_are_sequential(self):
        route = optimize_route(self.stores, self.origin)
        orders = [order for _, _, order in route]
        self.assertEqual(orders, list(range(1, len(self.stores) + 1)))

    def test_distances_are_positive(self):
        route = optimize_route(self.stores, self.origin)
        for _, distance, _ in route:
            self.assertGreaterEqual(distance, 0.0)

    def test_empty_stores_returns_empty(self):
        route = optimize_route([], self.origin)
        self.assertEqual(route, [])

    def test_all_stores_visited(self):
        route = optimize_route(self.stores, self.origin)
        visited_ids = {store.store_id for store, _, _ in route}
        expected_ids = {store.store_id for store in self.stores}
        self.assertEqual(visited_ids, expected_ids)


class TestGetPriceTierMultiplier(unittest.TestCase):
    """Tests for get_price_tier_multiplier()."""

    def test_budget_multiplier(self):
        self.assertEqual(get_price_tier_multiplier("budget"), 0.85)

    def test_mid_multiplier(self):
        self.assertEqual(get_price_tier_multiplier("mid"), 1.0)

    def test_premium_multiplier(self):
        self.assertEqual(get_price_tier_multiplier("premium"), 1.25)

    def test_unknown_tier_defaults_to_1(self):
        self.assertEqual(get_price_tier_multiplier("unknown"), 1.0)

    def test_empty_string_defaults_to_1(self):
        self.assertEqual(get_price_tier_multiplier(""), 1.0)


if __name__ == "__main__":
    unittest.main()
