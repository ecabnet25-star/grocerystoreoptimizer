from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from statistics import mean, pstdev
from typing import Any


def predict_price_drops(
    history: list[dict[str, Any]], *, horizon_days: int = 7, language: str = "en"
) -> dict[str, Any]:
    """Estimate short-term direction from timestamped observed prices."""
    grouped: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)
    for row in history:
        try:
            timestamp = datetime.fromisoformat(str(row["fetched_at_utc"]).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            price = float(row["unit_price"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0:
            continue
        key = (str(row.get("item_name", "Item")).strip(), str(row.get("store_chain", "Store")).strip())
        grouped[key].append((timestamp, price))

    predictions: list[dict[str, Any]] = []
    for (item_name, store_chain), observations in grouped.items():
        observations.sort(key=lambda value: value[0])
        if len(observations) < 3:
            continue
        start = observations[0][0]
        xs = [(timestamp - start).total_seconds() / 86400 for timestamp, _ in observations]
        ys = [price for _, price in observations]
        x_mean = mean(xs)
        y_mean = mean(ys)
        denominator = sum((value - x_mean) ** 2 for value in xs)
        if denominator <= 0:
            continue
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator
        current = ys[-1]
        predicted = max(0.01, current + slope * horizon_days)
        change_percent = ((predicted - current) / current) * 100
        volatility = pstdev(ys) / y_mean if y_mean else 1.0
        confidence = round(max(0.15, min(0.92, min(1.0, len(observations) / 10) * (1 - min(volatility, 0.8)))), 2)
        predictions.append({
            "item_name": item_name,
            "store_chain": store_chain,
            "current_price": round(current, 2),
            "predicted_price": round(predicted, 2),
            "change_percent": round(change_percent, 1),
            "direction": "drop" if change_percent <= -2 else "rise" if change_percent >= 2 else "steady",
            "confidence": confidence,
            "observations": len(observations),
        })

    predictions.sort(key=lambda row: (float(row["change_percent"]), -float(row["confidence"])))
    drops = [row for row in predictions if row["direction"] == "drop" and row["confidence"] >= 0.35]
    if drops:
        action = "wait"
        recommendation = (
            "Attendez quelques jours pour les baisses prevues sur certains articles."
            if language == "fr"
            else "Wait a few days for predicted drops on selected items."
        )
    elif predictions:
        action = "shop_now"
        recommendation = (
            "Les prix semblent stables; magasinez au moment qui vous convient."
            if language == "fr"
            else "Prices look stable; shop when your schedule allows."
        )
    else:
        action = "insufficient_history"
        recommendation = (
            "Utilisez les offres actuelles pendant que nous accumulons plus d'historique."
            if language == "fr"
            else "Shop now based on current deals while more price history is collected."
        )
    return {
        "action": action,
        "recommendation": recommendation,
        "horizon_days": horizon_days,
        "model": "recency_trend_v1",
        "prediction_count": len(predictions),
        "drops": drops[:5],
        "predictions": predictions[:12],
        "disclaimer": (
            "Ces previsions utilisent les prix observes; les dates de rabais ne sont pas garanties."
            if language == "fr"
            else "Forecasts use observed prices and are estimates, not guaranteed sale dates."
        ),
    }
