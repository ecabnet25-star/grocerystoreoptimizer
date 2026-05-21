import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from grocery_optimizer.models import GroceryItem, OptimizationResult
from grocery_optimizer.report import write_report_csv, write_report_json


class TestReportWriters(unittest.TestCase):
    def test_write_report_json_and_csv(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            json_path = temp_path / "result.json"
            csv_path = temp_path / "result.csv"

            result = OptimizationResult(
                selected_items=[GroceryItem("Oats", "grains", 2.5, 8.0, 90, 1)],
                total_cost=2.5,
                total_nutrition_score=8.0,
                total_shelf_life_days=90,
                budget_remaining=7.5,
                total_utility_score=15.5,
                strategy="greedy",
            )

            write_report_json(json_path, result, metadata={"location_id": "montreal"})
            write_report_csv(csv_path, result)

            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["strategy"], "greedy")
            self.assertEqual(payload["items"][0]["name"], "Oats")
            self.assertEqual(payload["metadata"]["location_id"], "montreal")


if __name__ == "__main__":
    unittest.main()
