from grocery_optimizer.price_prediction import predict_price_drops


def test_predicts_drop_from_observed_downtrend():
    history = [
        {"item_name": "Milk", "store_chain": "Metro", "unit_price": price, "fetched_at_utc": day}
        for price, day in [
            (5.0, "2026-06-01T12:00:00Z"),
            (4.7, "2026-06-03T12:00:00Z"),
            (4.4, "2026-06-05T12:00:00Z"),
            (4.1, "2026-06-07T12:00:00Z"),
        ]
    ]

    forecast = predict_price_drops(history)

    assert forecast["action"] == "wait"
    assert forecast["drops"][0]["item_name"] == "Milk"
    assert forecast["drops"][0]["predicted_price"] < forecast["drops"][0]["current_price"]


def test_sparse_history_does_not_claim_a_sale():
    forecast = predict_price_drops([
        {"item_name": "Rice", "store_chain": "IGA", "unit_price": 4.0, "fetched_at_utc": "2026-06-01T12:00:00Z"}
    ])

    assert forecast["action"] == "insufficient_history"
    assert forecast["predictions"] == []
