from __future__ import annotations

import re

_MEASURE_ALIASES = {
    "g": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "ct": "count",
    "count": "count",
    "pk": "count",
    "pack": "count",
    "packs": "count",
    "un": "count",
    "unit": "count",
    "units": "count",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
}


def normalize_package_unit(value: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    return _MEASURE_ALIASES.get(normalized, normalized or "package")


def parse_package_size(text: str) -> tuple[float | None, str, str]:
    value = text.strip()
    if not value:
        return None, "package", ""

    dozen_match = re.search(r"\b(\d+(?:\.\d+)?)?\s*dozen\b", value, flags=re.IGNORECASE)
    if dozen_match:
        dozens = float(dozen_match.group(1) or 1)
        count = dozens * 12
        return count, "count", f"{int(count) if count.is_integer() else count:g} count"

    measure_match = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s*(kg|kilograms?|g|grams?|ml|millilit(?:er|re)s?|l|lit(?:er|re)s?|lbs?|pounds?|oz|ounces?)\b",
        value,
        flags=re.IGNORECASE,
    )
    if measure_match:
        size = float(measure_match.group(1).replace(",", "."))
        unit = normalize_package_unit(measure_match.group(2))
        return size, unit, f"{size:g} {unit}"

    count_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:pk|pack|ct|count|un(?:it)?s?)\b",
        value,
        flags=re.IGNORECASE,
    )
    if count_match:
        size = float(count_match.group(1))
        return size, "count", f"{size:g} count"

    return None, "package", ""


def normalized_unit_price(price: float, package_size: float | None, package_unit: str) -> tuple[float, str]:
    amount = max(float(price), 0.0)
    size = float(package_size or 0.0)
    unit = normalize_package_unit(package_unit)
    if size <= 0:
        return round(amount, 4), "package"

    if unit == "kg":
        size *= 1000
        unit = "g"
    elif unit == "lb":
        size *= 453.59237
        unit = "g"
    elif unit == "oz":
        size *= 28.349523125
        unit = "g"
    elif unit == "l":
        size *= 1000
        unit = "ml"

    if unit == "g":
        return round(amount / size * 100, 4), "100 g"
    if unit == "ml":
        return round(amount / size * 100, 4), "100 ml"
    if unit == "count":
        return round(amount / size, 4), "unit"
    return round(amount, 4), "package"
