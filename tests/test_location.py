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
        items = [
            GroceryItem(
                "Test Produce",
                "produce",
                10.0,
                5.0,
                5,
                1,
                package_size=500,
                package_unit="g",
                package_label="500 g",
            )
        ]

        adjusted = apply_location_pricing(items, profile)

        self.assertEqual(len(adjusted), 1)
        self.assertNotEqual(adjusted[0].price, 10.0)
        self.assertGreater(adjusted[0].price, 10.0)
        self.assertEqual(adjusted[0].package_size, 500)
        self.assertEqual(adjusted[0].package_unit, "g")
        self.assertEqual(adjusted[0].package_label, "500 g")
        self.assertEqual(adjusted[0].unit_price_basis, "100 g")

    def test_available_locations_contains_montreal(self):
        names = list_available_locations()
        self.assertIn("montreal", names)


if __name__ == "__main__":
    unittest.main()
