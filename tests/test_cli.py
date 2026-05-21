import unittest
from pathlib import Path

from grocery_optimizer.data_io import load_items_from_json


class TestCliFixtures(unittest.TestCase):
    def test_catalog_fixture_exists_and_loads(self):
        catalog = Path("config") / "catalog.json"
        items = load_items_from_json(catalog)

        self.assertGreaterEqual(len(items), 5)


if __name__ == "__main__":
    unittest.main()
