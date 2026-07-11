"""
Health endpoint: real DB check, not just "service is up".

Phase 0 ships three flavours:
  1. Direct DatabaseManager health probe (unit test).
  2. The /api/health route integration test (FastAPI TestClient).
  3. /api/health returns 503 when the DB is unreachable.
"""

from fastapi.testclient import TestClient


def test_db_round_trip(db):
    """If init_database ran, get_ingredients returns an empty list, not an error."""
    assert db.get_ingredients() == []


def _client_with_db(db_path: str) -> TestClient:
    """Build a TestClient wired to a fresh on-disk DB."""
    import main as main_module
    from database import DatabaseManager

    DatabaseManager(db_path)
    main_module.db_manager = DatabaseManager(db_path)
    main_module.prediction_engine = None  # avoid Prophet import
    return TestClient(main_module.app)


def test_health_endpoint_returns_200_when_db_ok(temp_db_path):
    client = _client_with_db(temp_db_path)
    resp = client.get("/api/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] is True
    assert body["success"] is True
    assert "ts" in body
    assert "error_id" not in body


def test_health_endpoint_returns_503_when_db_missing(temp_db_path):
    """If the DB file is deleted under the running app, /api/health must report 503."""
    import main as main_module

    # Create a fresh DB, then replace it with a stub that fails on connect.
    from database import DatabaseManager

    DatabaseManager(temp_db_path)
    main_module.db_manager = DatabaseManager(temp_db_path)

    class BrokenDB:
        def __init__(self, fake_path: str) -> None:
            self.db_path = fake_path

        def get_connection(self):
            raise RuntimeError("simulated DB outage")

    main_module.db_manager = BrokenDB(temp_db_path + ".deleted")
    client = TestClient(main_module.app)
    resp = client.get("/api/health")
    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] is False
    assert body["success"] is False
    assert "error_id" in body


def test_predictions_returns_empty_when_no_data(temp_db_path):
    """Predictions endpoint must NOT 503 when there is simply no data yet."""
    client = _client_with_db(temp_db_path)
    resp = client.get("/api/predictions?date=2025-01-01")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"] == []
    assert "prophet_available" in body
    assert body["count"] == 0


def test_idempotent_order_returns_200_not_201(temp_db_path):
    """Same Idempotency-Key twice must return 200 the second time, not 201."""
    from models import OrderCreate, OrderItem

    client = _client_with_db(temp_db_path)

    # Seed a dish.
    dish = client.post(
        "/api/dishes",
        json={
            "name": "Test Pizza",
            "price": 12.50,
            "category": "Mains",
            "ingredients": [],
        },
    ).json()["data"]

    body = OrderCreate(
        items=[OrderItem(dish_id=dish["id"], quantity=1, price=0.0)],
        payment_method="cash",
        cashier_id="tester",
    ).model_dump()

    # First request: 201 (newly created).
    r1 = client.post("/api/orders", json=body, headers={"Idempotency-Key": "abc-123"})
    assert r1.status_code == 201, r1.text
    assert r1.json()["idempotent_replay"] is False

    # Same key: 200 (replay), not 201.
    r2 = client.post("/api/orders", json=body, headers={"Idempotency-Key": "abc-123"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["idempotent_replay"] is True
    assert r2.json()["data"]["id"] == r1.json()["data"]["id"]
