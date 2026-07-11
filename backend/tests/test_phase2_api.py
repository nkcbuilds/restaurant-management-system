"""Phase 2 API tests: predictions, backtest, prep plan, purchase recs."""

from fastapi.testclient import TestClient


def _client_with_db(db_path: str) -> TestClient:
    import main as main_module
    from database import DatabaseManager
    from ml_predictions import PredictionEngine

    DatabaseManager(db_path)
    main_module.db_manager = DatabaseManager(db_path)
    main_module.prediction_engine = PredictionEngine(main_module.db_manager)
    return TestClient(main_module.app)


def test_predictions_endpoint_returns_empty_when_no_history(temp_db_path):
    client = _client_with_db(temp_db_path)
    r = client.get("/api/predictions?date=2026-07-15")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"] == []


def test_predictions_status(temp_db_path):
    client = _client_with_db(temp_db_path)
    r = client.get("/api/predictions/status")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["models_trained"] == 3  # three baselines
    assert "prophet_available" in body["data"]


def test_backtest_endpoint_returns_empty_when_no_history(temp_db_path):
    client = _client_with_db(temp_db_path)
    r = client.get("/api/predictions/backtest?days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    # Empty history -> empty overall + warning.
    assert body["data"]["overall"] == {}
    assert "warning" in body["data"]


def test_prep_plan_empty_when_no_history(temp_db_path):
    client = _client_with_db(temp_db_path)
    r = client.get("/api/prep-plan?date=2026-07-15")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"] == []


def test_purchase_recommendations_empty_when_no_history(temp_db_path):
    client = _client_with_db(temp_db_path)
    r = client.get("/api/purchase-recommendations?date=2026-07-15")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"] == []


def test_predictions_returns_structured_fields(temp_db_path):
    """With at least one historical point, the response carries model provenance."""
    import sqlite3
    from datetime import datetime, timedelta

    client = _client_with_db(temp_db_path)
    # Seed a dish with history.
    dish = client.post(
        "/api/dishes",
        json={"name": "Pizza", "price": 12.0, "category": "Mains", "ingredients": []},
    ).json()["data"]
    dish_id = dish["id"]

    # Inject 8 historical orders at constant demand.
    import uuid

    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()
    today = datetime.now().date()
    for days_ago in range(0, 8):
        d = datetime.combine(today - timedelta(days=days_ago), datetime.min.time())
        oid = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO orders (id, total, subtotal, tax, tax_rate, timestamp, status, payment_method, customer_id, cashier_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (oid, 12.0, 12.0, 0, 0, d.isoformat(), "completed", "cash", None, "t"),
        )
        cur.execute(
            "INSERT INTO order_items (order_id, dish_id, quantity, price, notes)"
            " VALUES (?, ?, ?, ?, ?)",
            (oid, dish_id, 5, 12.0, None),
        )
    conn.commit()
    conn.close()

    target = (today + timedelta(days=1)).isoformat()
    r = client.get(f"/api/predictions?date={target}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["count"] >= 1
    entry = body["data"][0]
    # Required Phase 2 fields
    for k in (
        "dish_id",
        "dish_name",
        "period",
        "predicted_demand",
        "low",
        "high",
        "recommended_prep",
        "model_used",
        "model_confidence",
        "data_sufficiency",
        "reason",
        "all_baselines",
    ):
        assert k in entry, f"missing {k}"
    # We expect one of the baseline names to be the chosen model.
    assert entry["model_used"] in {
        "baseline_same_weekday",
        "baseline_ma",
        "baseline_recent",
    }
