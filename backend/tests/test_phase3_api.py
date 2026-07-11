"""Phase 3 API tests: suppliers, POs, payments, offline replay, audit, metrics."""
from fastapi.testclient import TestClient


def _client(db_path: str) -> TestClient:
    import main as main_module
    from database import DatabaseManager
    from ml_predictions import PredictionEngine

    DatabaseManager(db_path)
    main_module.db_manager = DatabaseManager(db_path)
    main_module.prediction_engine = PredictionEngine(main_module.db_manager)
    return TestClient(main_module.app)


def _seed_ingredient(client, name="Flour", qty=100) -> str:
    r = client.post(
        "/api/ingredients",
        json={
            "name": name,
            "unit": "g",
            "quantity_today": qty,
            "min_threshold": 0,
            "cost_per_unit": 1.0,
            "supplier": None,
        },
    )
    assert r.status_code == 201
    return r.json()["data"]["id"]


def _seed_supplier(client, name="Acme") -> str:
    r = client.post(
        "/api/suppliers",
        json={"name": name, "phone": "555-1212"},
        headers={"X-User-Role": "manager"},
    )
    assert r.status_code == 201
    return r.json()["data"]["id"]


# ---- Suppliers ---------------------------------------------------------


def test_supplier_create_and_list(temp_db_path):
    client = _client(temp_db_path)
    r = client.post(
        "/api/suppliers",
        json={"name": "Acme"},
        headers={"X-User-Role": "manager"},
    )
    assert r.status_code == 201
    sid = r.json()["data"]["id"]
    r = client.get("/api/suppliers")
    assert r.status_code == 200
    assert any(s["id"] == sid for s in r.json()["data"])


def test_supplier_requires_manager_role(temp_db_path):
    client = _client(temp_db_path)
    # cashier is below manager, so this should be 403.
    r = client.post(
        "/api/suppliers",
        json={"name": "Acme"},
        headers={"X-User-Role": "cashier"},
    )
    assert r.status_code == 403


# ---- Purchase orders ---------------------------------------------------


def test_create_and_receive_purchase_order(temp_db_path):
    client = _client(temp_db_path)
    ing = _seed_ingredient(client, qty=100)
    sup = _seed_supplier(client)

    # Create PO
    r = client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": sup,
            "items": [{"ingredient_id": ing, "quantity": 50, "unit_cost": 1.5}],
        },
        headers={"X-User-Role": "inventory"},
    )
    assert r.status_code == 201, r.text
    po_id = r.json()["data"]["id"]
    assert r.json()["data"]["status"] == "draft"
    assert r.json()["data"]["total"] == 75.0

    # Receive
    r = client.post(
        f"/api/purchase-orders/{po_id}/receive",
        headers={"X-User-Role": "inventory"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "received"

    # Stock + cost adjusted.
    r = client.get("/api/ingredients")
    ing_now = next(i for i in r.json()["data"] if i["id"] == ing)
    assert ing_now["quantity_today"] == 150.0
    # Weighted avg: old=100@1.0, new=50@1.5 -> (100+75)/150 = 1.166...
    assert abs(ing_now["cost_per_unit"] - 1.1666) < 0.01


def test_cancel_received_po_is_rejected(temp_db_path):
    client = _client(temp_db_path)
    ing = _seed_ingredient(client, qty=100)
    sup = _seed_supplier(client)
    r = client.post(
        "/api/purchase-orders",
        json={
            "supplier_id": sup,
            "items": [{"ingredient_id": ing, "quantity": 10, "unit_cost": 1.0}],
        },
        headers={"X-User-Role": "inventory"},
    )
    po_id = r.json()["data"]["id"]
    client.post(
        f"/api/purchase-orders/{po_id}/receive",
        headers={"X-User-Role": "inventory"},
    )
    r = client.post(
        f"/api/purchase-orders/{po_id}/cancel",
        headers={"X-User-Role": "manager"},
    )
    assert r.status_code == 409


# ---- Payments ----------------------------------------------------------


def test_create_payment(temp_db_path):
    client = _client(temp_db_path)
    # Seed a dish and order.
    dish = client.post(
        "/api/dishes",
        json={"name": "P", "price": 10.0, "category": "x", "ingredients": []},
    ).json()["data"]
    order = client.post(
        "/api/orders",
        json={
            "items": [{"dish_id": dish["id"], "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
        },
        headers={"Idempotency-Key": "ord-1"},
    ).json()["data"]

    r = client.post(
        "/api/payments",
        json={"order_id": order["id"], "amount": 10.0, "method": "cash"},
        headers={"X-User-Role": "cashier"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["data"]["status"] == "completed"

    r = client.get(f"/api/orders/{order['id']}/payments")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1


def test_payment_idempotency(temp_db_path):
    client = _client(temp_db_path)
    dish = client.post(
        "/api/dishes",
        json={"name": "P", "price": 10.0, "category": "x", "ingredients": []},
    ).json()["data"]
    order = client.post(
        "/api/orders",
        json={
            "items": [{"dish_id": dish["id"], "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
        },
        headers={"Idempotency-Key": "ord-2"},
    ).json()["data"]
    body = {"order_id": order["id"], "amount": 5.0, "method": "upi"}
    r1 = client.post(
        "/api/payments",
        json=body,
        headers={"X-User-Role": "cashier", "Idempotency-Key": "pay-1"},
    )
    r2 = client.post(
        "/api/payments",
        json=body,
        headers={"X-User-Role": "cashier", "Idempotency-Key": "pay-1"},
    )
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]


# ---- Offline replay ----------------------------------------------------


def test_offline_replay_dedupes(temp_db_path):
    client = _client(temp_db_path)
    dish = client.post(
        "/api/dishes",
        json={"name": "P", "price": 10.0, "category": "x", "ingredients": []},
    ).json()["data"]

    payload = [
        {
            "idempotency_key": "offline-1",
            "captured_at": "2026-07-12T00:00:00",
            "items": [{"dish_id": dish["id"], "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
            "customer_id": None,
        },
        {
            # Same key as above -> duplicate
            "idempotency_key": "offline-1",
            "captured_at": "2026-07-12T00:00:00",
            "items": [{"dish_id": dish["id"], "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
            "customer_id": None,
        },
        {
            "idempotency_key": "offline-2",
            "captured_at": "2026-07-12T00:01:00",
            "items": [{"dish_id": dish["id"], "quantity": 2, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
            "customer_id": None,
        },
    ]
    r = client.post(
        "/api/orders/replay-batch",
        json=payload,
        headers={"X-User-Role": "cashier"},
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert len(body["accepted"]) == 2  # offline-1 once, offline-2 once
    assert len(body["duplicates"]) == 1  # offline-1 the second time
    assert body["failed"] == []


def test_offline_replay_handles_failed_order(temp_db_path):
    client = _client(temp_db_path)
    # Unknown dish -> rejected with ValueError, captured in `failed`.
    payload = [
        {
            "idempotency_key": "offline-bad",
            "captured_at": "2026-07-12T00:00:00",
            "items": [{"dish_id": "nope", "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
            "customer_id": None,
        }
    ]
    r = client.post(
        "/api/orders/replay-batch",
        json=payload,
        headers={"X-User-Role": "cashier"},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["accepted"] == []
    assert len(body["failed"]) == 1
    assert "Unknown dish" in body["failed"][0]["detail"]


# ---- Audit log ---------------------------------------------------------


def test_audit_records_critical_actions(temp_db_path):
    client = _client(temp_db_path)
    # Create a supplier (audit-worthy action that writes to audit_log).
    client.post(
        "/api/suppliers",
        json={"name": "Auditable Co"},
        headers={"X-User-Role": "manager"},
    )
    r = client.get("/api/audit", headers={"X-User-Role": "owner"})
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()["data"]]
    assert "supplier.create" in actions


def test_audit_owner_only(temp_db_path):
    client = _client(temp_db_path)
    # cashier is below owner -> 403
    r = client.get("/api/audit", headers={"X-User-Role": "cashier"})
    assert r.status_code == 403


# ---- Metrics -----------------------------------------------------------


def test_metrics_endpoint(temp_db_path):
    client = _client(temp_db_path)
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()["data"]
    assert "restaurantos_ingredients_total" in body
    assert "restaurantos_orders_total" in body
