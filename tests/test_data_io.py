import unittest
from pathlib import Path

from grocery_optimizer.data_io import load_items_from_json


class TestDataIO(unittest.TestCase):
    def test_load_items_from_json(self):
        fixture = Path(__file__).parent / "fixtures" / "catalog_minimal.json"
        items = load_items_from_json(fixture)

        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].name, "Oats")
        self.assertEqual(items[1].category, "protein")


if __name__ == "__main__":
    unittest.main()
