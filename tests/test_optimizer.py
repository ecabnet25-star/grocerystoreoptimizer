import unittest

from grocery_optimizer.models import GroceryItem
from grocery_optimizer.optimizer import OptimizationWeights, optimize_grocery_list


class TestOptimizer(unittest.TestCase):
    def test_optimizer_respects_budget(self):
        items = [
            GroceryItem("A", "cat1", 10.0, 10.0, 5, 1),
            GroceryItem("B", "cat2", 5.0, 6.0, 5, 1),
            GroceryItem("C", "cat3", 3.0, 2.0, 1, 1),
        ]

        result = optimize_grocery_list(items, budget=8.0)

        self.assertLessEqual(result.total_cost, 8.0)
        self.assertTrue(all(item.total_cost <= 8.0 for item in result.selected_items))
        self.assertEqual(result.strategy, "greedy")

    def test_optimizer_required_category_if_possible(self):
        items = [
            GroceryItem("Rice", "grains", 3.0, 7.0, 100, 1),
            GroceryItem("Beans", "protein", 2.0, 8.0, 300, 1),
            GroceryItem("Apple", "produce", 1.0, 6.0, 10, 1),
        ]

        result = optimize_grocery_list(items, budget=6.0, required_categories={"produce"})
        categories = {item.category for item in result.selected_items}

        self.assertIn("produce", categories)

    def test_optimizer_excluded_categories(self):
        items = [
            GroceryItem("Milk", "dairy", 4.0, 7.0, 7, 1),
            GroceryItem("Rice", "grains", 3.0, 7.0, 90, 1),
        ]

        result = optimize_grocery_list(items, budget=10.0, excluded_categories={"dairy"})
        categories = {item.category for item in result.selected_items}

        self.assertNotIn("dairy", categories)

    def test_knapsack_strategy_sets_metadata(self):
        items = [
            GroceryItem("High Cost", "protein", 12.0, 15.0, 2, 1),
            GroceryItem("Balanced", "protein", 6.0, 10.0, 7, 1),
            GroceryItem("Budget", "produce", 3.0, 6.0, 10, 1),
        ]
        weights = OptimizationWeights(nutrition_weight=1.2, shelf_life_weight=0.3, cost_weight=1.0)

        result = optimize_grocery_list(items, budget=9.0, strategy="knapsack", weights=weights)

        self.assertEqual(result.strategy, "knapsack")
        self.assertGreaterEqual(result.total_utility_score, 0.0)

    def test_optimizer_expands_with_variety_when_budget_remains(self):
        items = [
            GroceryItem("Rice", "grains", 3.0, 8.0, 120, 1),
            GroceryItem("Beans", "protein", 2.5, 7.5, 240, 1),
            GroceryItem("Berries", "produce", 5.0, 8.0, 7, 1),
            GroceryItem("Olive Oil", "pantry", 7.0, 6.0, 365, 1),
        ]

        result = optimize_grocery_list(items, budget=15.0, max_items=4)

        self.assertLessEqual(result.total_cost, 15.0)
        self.assertGreaterEqual(result.total_cost, 12.0)


if __name__ == "__main__":
    unittest.main()
