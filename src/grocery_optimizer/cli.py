from __future__ import annotations

import argparse
from pathlib import Path

from .data_io import load_items_from_json
from .location import apply_location_pricing, list_available_locations, load_location_profile
from .optimizer import OptimizationWeights, optimize_grocery_list
from .report import write_report_csv, write_report_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grocery Optimizer CLI")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("config") / "catalog.json",
        help="Path to grocery catalog JSON file",
    )
    parser.add_argument("--budget", type=float, default=50.0, help="Budget limit")
    parser.add_argument("--max-items", type=int, default=10, help="Maximum number of items")
    parser.add_argument(
        "--required-categories",
        nargs="*",
        default=[],
        help="Category names that should be included if possible",
    )
    parser.add_argument(
        "--excluded-categories",
        nargs="*",
        default=[],
        help="Category names to always exclude",
    )
    parser.add_argument(
        "--strategy",
        choices=["greedy", "knapsack"],
        default="greedy",
        help="Optimization strategy",
    )
    parser.add_argument("--nutrition-weight", type=float, default=1.0, help="Weight for nutrition score")
    parser.add_argument("--shelf-life-weight", type=float, default=0.25, help="Weight for shelf life score")
    parser.add_argument("--cost-weight", type=float, default=1.0, help="Penalty weight for item cost")
    parser.add_argument("--out-json", type=Path, default=None, help="Optional output report JSON path")
    parser.add_argument("--out-csv", type=Path, default=None, help="Optional output report CSV path")
    parser.add_argument("--location", default="montreal", help="Location identifier (default: montreal)")
    parser.add_argument("--postal-code", default="", help="Optional postal code for future hyper-local support")
    parser.add_argument(
        "--list-locations",
        action="store_true",
        help="List all available configured locations and exit",
    )
    return parser


def run_cli() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list_locations:
        for location_name in list_available_locations():
            print(location_name)
        return 0

    items = load_items_from_json(args.catalog)
    location_profile = load_location_profile(args.location)
    items = apply_location_pricing(items, location_profile)
    weights = OptimizationWeights(
        nutrition_weight=args.nutrition_weight,
        shelf_life_weight=args.shelf_life_weight,
        cost_weight=args.cost_weight,
    )

    result = optimize_grocery_list(
        items=items,
        budget=args.budget,
        max_items=args.max_items,
        required_categories=set(args.required_categories),
        excluded_categories=set(args.excluded_categories),
        strategy=args.strategy,
        weights=weights,
    )

    print("Optimized Grocery Plan")
    print("-" * 24)
    for item in result.selected_items:
        print(f"{item.name:18} ${item.total_cost:>6.2f}  {item.category}")
    print("-" * 24)
    print(f"Total Cost:        ${result.total_cost:.2f}")
    print(f"Budget Remaining:  ${result.budget_remaining:.2f}")
    print(f"Nutrition Score:   {result.total_nutrition_score:.2f}")
    print(f"Shelf-Life Total:  {result.total_shelf_life_days} days")
    print(f"Utility Score:     {result.total_utility_score:.2f}")
    print(f"Strategy:          {result.strategy}")
    print(f"Location:          {location_profile.display_name}")
    print(f"Currency:          {location_profile.currency}")
    if args.postal_code:
        print(f"Postal Code:       {args.postal_code}")

    if args.out_json:
        write_report_json(
            args.out_json,
            result,
            metadata={
                "location_id": location_profile.location_id,
                "location_name": location_profile.display_name,
                "currency": location_profile.currency,
                "postal_code": args.postal_code,
            },
        )
        print(f"JSON report:       {args.out_json}")

    if args.out_csv:
        write_report_csv(args.out_csv, result)
        print(f"CSV report:        {args.out_csv}")

    return 0
