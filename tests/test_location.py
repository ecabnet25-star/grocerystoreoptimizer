import unittest

from grocery_optimizer.location import (
    apply_location_pricing,
    list_available_locations,
    load_location_profile,
)
from grocery_optimizer.models import GroceryItem


class TestLocationSupport(unittest.TestCase):
    def test_montreal_profile_exists(self):
        profile = load_location_profile("montreal")
        self.assertEqual(profile.location_id, "montreal")
        self.assertEqual(profile.currency, "CAD")

    def test_location_price_adjustment(self):
        profile = load_location_profile("montreal")
        items = [GroceryItem("Test Produce", "produce", 10.0, 5.0, 5, 1)]

        adjusted = apply_location_pricing(items, profile)

        self.assertEqual(len(adjusted), 1)
        self.assertNotEqual(adjusted[0].price, 10.0)
        self.assertGreater(adjusted[0].price, 10.0)

    def test_available_locations_contains_montreal(self):
        names = list_available_locations()
        self.assertIn("montreal", names)


if __name__ == "__main__":
    unittest.main()
