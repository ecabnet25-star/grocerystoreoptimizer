from __future__ import annotations

from dataclasses import dataclass

from .models import GroceryItem, OptimizationResult


@dataclass(frozen=True)
class OptimizationWeights:
    nutrition_weight: float = 1.0
    shelf_life_weight: float = 0.25
    cost_weight: float = 1.0


def _item_value_score(item: GroceryItem) -> float:
    cost = item.total_cost if item.total_cost > 0 else 0.01
    freshness_factor = max(item.shelf_life_days, 1) / 7
    return (item.nutrition_score * freshness_factor) / cost


def _utility_score(item: GroceryItem, weights: OptimizationWeights) -> float:
    cost = item.total_cost if item.total_cost > 0 else 0.01
    weighted_benefit = (
        (item.nutrition_score * weights.nutrition_weight)
        + (item.shelf_life_days * weights.shelf_life_weight)
    )
    return weighted_benefit - (cost * weights.cost_weight)


def _try_fill_required_categories(
    selected: list[GroceryItem],
    candidates: list[GroceryItem],
    budget: float,
    spent: float,
    required_categories: set[str],
    max_items: int | None,
) -> tuple[list[GroceryItem], float]:
    selected_categories = {item.category for item in selected}
    missing_required = required_categories - selected_categories

    if not missing_required:
        return selected, spent

    remaining = [item for item in candidates if item.category in missing_required and item not in selected]
    for item in remaining:
        if max_items is not None and len(selected) >= max_items:
            break
        if spent + item.total_cost > budget:
            continue
        selected.append(item)
        spent += item.total_cost
        selected_categories.add(item.category)
        if required_categories.issubset(selected_categories):
            break

    return selected, spent


def _expand_with_variety(
    selected: list[GroceryItem],
    candidates: list[GroceryItem],
    budget: float,
    spent: float,
    max_items: int | None,
    target_spend_ratio: float,
) -> tuple[list[GroceryItem], float]:
    """Use remaining budget for variety-focused additions once base needs are covered."""
    if not candidates or budget <= 0:
        return selected, spent

    target_spend = budget * max(0.0, min(target_spend_ratio, 1.0))
    selected_categories = {item.category for item in selected}

    remaining = [item for item in candidates if item not in selected]
    # Prefer filling categories not represented yet, then low-cost additions.
    remaining.sort(
        key=lambda item: (
            0 if item.category not in selected_categories else 1,
            item.total_cost,
            -_item_value_score(item),
        )
    )

    for item in remaining:
        if max_items is not None and len(selected) >= max_items:
            break
        if spent >= target_spend:
            break
        if spent + item.total_cost > budget:
            continue
        selected.append(item)
        spent += item.total_cost
        selected_categories.add(item.category)

    return selected, spent


def _greedy_select(
    items: list[GroceryItem],
    budget: float,
    max_items: int | None,
) -> tuple[list[GroceryItem], float, list[GroceryItem]]:
    sorted_items = sorted(items, key=_item_value_score, reverse=True)
    selected: list[GroceryItem] = []
    spent = 0.0

    for item in sorted_items:
        if max_items is not None and len(selected) >= max_items:
            break
        if spent + item.total_cost > budget:
            continue
        selected.append(item)
        spent += item.total_cost

    return selected, spent, sorted_items


def _knapsack_select(
    items: list[GroceryItem],
    budget: float,
    max_items: int | None,
    weights: OptimizationWeights,
) -> tuple[list[GroceryItem], float, list[GroceryItem]]:
    sorted_items = list(items)
    # Discretize to dimes (10-cent granularity) to reduce state space by 10x
    # with minimal accuracy loss.
    budget_dimes = int(round(budget * 10))

    dp: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {(0, 0): (0.0, ())}

    for index, item in enumerate(sorted_items):
        item_cost = int(round(item.total_cost * 10))
        item_utility = _utility_score(item, weights)
        # Build new states into a separate dict, then merge -- avoids copying
        # the entire dp dict while also preventing the current item from being
        # considered more than once (0-1 knapsack property).
        new_states: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {}

        for (spent_dimes, count), (score, chosen_indices) in dp.items():
            next_spent = spent_dimes + item_cost
            next_count = count + 1
            if next_spent > budget_dimes:
                continue
            if max_items is not None and next_count > max_items:
                continue

            candidate_score = score + item_utility
            candidate_indices = chosen_indices + (index,)

            prev_new = new_states.get((next_spent, next_count))
            prev_dp = dp.get((next_spent, next_count))
            # Keep best across both existing dp and new_states
            best_existing = max(
                (v for v in (prev_new, prev_dp) if v is not None),
                key=lambda v: v[0],
                default=None,
            )
            if best_existing is None or candidate_score > best_existing[0]:
                new_states[(next_spent, next_count)] = (candidate_score, candidate_indices)

        dp.update(new_states)

    best_state = max(dp.items(), key=lambda entry: entry[1][0])
    best_spent_dimes, _ = best_state[0]
    _, best_indices = best_state[1]

    selected = [sorted_items[i] for i in best_indices]
    return selected, round(best_spent_dimes / 10, 2), sorted_items


def optimize_grocery_list(
    items: list[GroceryItem],
    budget: float,
    max_items: int | None = None,
    required_categories: set[str] | None = None,
    required_item_names: set[str] | None = None,
    excluded_categories: set[str] | None = None,
    strategy: str = "greedy",
    weights: OptimizationWeights | None = None,
    target_spend_ratio: float = 0.92,
) -> OptimizationResult:
    if budget <= 0:
        return OptimizationResult([], 0.0, 0.0, 0, round(budget, 2), 0.0, strategy)

    required_categories = required_categories or set()
    required_item_names = {name.strip().lower() for name in (required_item_names or set()) if name.strip()}
    excluded_categories = excluded_categories or set()
    weights = weights or OptimizationWeights()

    eligible_items = [item for item in items if item.category not in excluded_categories]
    required_items = [item for item in eligible_items if item.name.strip().lower() in required_item_names]
    required_cost = round(sum(item.total_cost for item in required_items), 2)
    if required_cost > budget or (max_items is not None and len(required_items) > max_items):
        required_items = []

    remaining_items = [item for item in eligible_items if item not in required_items]
    remaining_budget = max(0.0, budget - sum(item.total_cost for item in required_items))
    remaining_limit = None if max_items is None else max(0, max_items - len(required_items))

    if strategy == "knapsack":
        selected, spent, ordered_candidates = _knapsack_select(remaining_items, remaining_budget, remaining_limit, weights)
    else:
        selected, spent, ordered_candidates = _greedy_select(remaining_items, remaining_budget, remaining_limit)

    selected = required_items + selected
    spent += sum(item.total_cost for item in required_items)
    ordered_candidates = required_items + ordered_candidates

    selected, spent = _try_fill_required_categories(
        selected=selected,
        candidates=ordered_candidates,
        budget=budget,
        spent=spent,
        required_categories=required_categories,
        max_items=max_items,
    )

    selected, spent = _expand_with_variety(
        selected=selected,
        candidates=ordered_candidates,
        budget=budget,
        spent=spent,
        max_items=max_items,
        target_spend_ratio=target_spend_ratio,
    )

    total_nutrition = round(sum(item.nutrition_score for item in selected), 2)
    total_shelf_life = sum(item.shelf_life_days for item in selected)
    total_utility_score = round(sum(_utility_score(item, weights) for item in selected), 2)
    spent = round(spent, 2)

    return OptimizationResult(
        selected_items=selected,
        total_cost=spent,
        total_nutrition_score=total_nutrition,
        total_shelf_life_days=total_shelf_life,
        budget_remaining=round(budget - spent, 2),
        total_utility_score=total_utility_score,
        strategy=strategy,
    )
