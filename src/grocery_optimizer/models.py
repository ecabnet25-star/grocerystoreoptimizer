from dataclasses import dataclass


@dataclass(frozen=True)
class GroceryItem:
    name: str
    category: str
    price: float
    nutrition_score: float
    shelf_life_days: int
    quantity: int = 1

    @property
    def total_cost(self) -> float:
        return round(self.price * self.quantity, 2)


@dataclass(frozen=True)
class OptimizationResult:
    selected_items: list[GroceryItem]
    total_cost: float
    total_nutrition_score: float
    total_shelf_life_days: int
    budget_remaining: float
    total_utility_score: float
    strategy: str
