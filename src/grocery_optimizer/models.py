from dataclasses import dataclass

from .unit_pricing import normalized_unit_price


@dataclass(frozen=True)
class GroceryItem:
    name: str
    category: str
    price: float
    nutrition_score: float
    shelf_life_days: int
    quantity: int = 1
    package_size: float | None = None
    package_unit: str = "package"
    package_label: str = ""

    @property
    def total_cost(self) -> float:
        return round(self.price * self.quantity, 2)

    @property
    def normalized_unit_price(self) -> float:
        return normalized_unit_price(self.price, self.package_size, self.package_unit)[0]

    @property
    def unit_price_basis(self) -> str:
        return normalized_unit_price(self.price, self.package_size, self.package_unit)[1]


@dataclass(frozen=True)
class OptimizationResult:
    selected_items: list[GroceryItem]
    total_cost: float
    total_nutrition_score: float
    total_shelf_life_days: int
    budget_remaining: float
    total_utility_score: float
    strategy: str
