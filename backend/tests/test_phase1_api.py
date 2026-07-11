"""Phase 1 API-level integration tests.

These exercise the FastAPI app through the TestClient so they cover both
the DB layer and the HTTP envelope (status codes, JSON shape, RBAC).
"""

from fastapi.testclient import TestClient


def _client_with_db(db_path: str) -> TestClient:
    import main as main_module
    from database import DatabaseManager

    DatabaseManager(db_path)
    main_module.db_manager = DatabaseManager(db_path)
    main_module.prediction_engine = None
    return TestClient(main_module.app)


def _create_dish(client, name="Pizza", price=12.5, ings=None) -> str:
    body = {
        "name": name,
        "price": price,
        "category": "Mains",
        "ingredients": ings or [],
    }
    r = client.post("/api/dishes", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _create_ingredient(client, name="Flour", qty=100) -> str:
    body = {
        "name": name,
        "unit": "g",
        "quantity_today": qty,
        "min_threshold": 0,
        "cost_per_unit": 0,
        "supplier": None,
    }
    r = client.post("/api/ingredients", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _place_order(client, dish_id, qty=1, key=None) -> str:
    body = {
        "items": [{"dish_id": dish_id, "quantity": qty, "price": 0.0}],
        "payment_method": "cash",
        "cashier_id": "tester",
    }
    headers = {"Idempotency-Key": key or f"key-{dish_id}-{qty}"}
    r = client.post("/api/orders", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


# ---- Order lifecycle via API --------------------------------------------


def test_order_lifecycle_via_api(temp_db_path):
    client = _client_with_db(temp_db_path)
    dish_id = _create_dish(client)
    order_id = _place_order(client, dish_id)

    # Initially submitted.
    r = client.get("/api/orders")
    statuses = {o["id"]: o["status"] for o in r.json()["data"]}
    assert statuses[order_id] == "submitted"

    # Move through the lifecycle.
    for new_status in ["accepted", "preparing", "ready", "served", "completed"]:
        r = client.patch(
            f"/api/orders/{order_id}/status",
            json={"status": new_status},
            headers={"X-User-Role": "kitchen"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == new_status

    # Terminal — cannot cancel a completed order.
    r = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers={"X-User-Role": "manager"},
    )
    assert r.status_code == 409, r.text


def test_status_patch_rejects_illegal_jump(temp_db_path):
    client = _client_with_db(temp_db_path)
    dish_id = _create_dish(client)
    order_id = _place_order(client, dish_id)

    r = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "completed"},
        headers={"X-User-Role": "owner"},
    )
    assert r.status_code == 409, r.text


def test_status_patch_enforces_role(temp_db_path):
    client = _client_with_db(temp_db_path)
    dish_id = _create_dish(client)
    order_id = _place_order(client, dish_id)

    # A bare 'cashier' cannot advance an order (need kitchen role for non-cancel).
    r = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "accepted"},
        headers={"X-User-Role": "cashier"},
    )
    assert r.status_code == 403, r.text


def test_cancel_allowed_for_cashier(temp_db_path):
    client = _client_with_db(temp_db_path)
    dish_id = _create_dish(client)
    order_id = _place_order(client, dish_id)
    r = client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "cancelled"},
        headers={"X-User-Role": "cashier"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "cancelled"


# ---- Kitchen tickets -----------------------------------------------------


def test_kitchen_tickets_listing(temp_db_path):
    client = _client_with_db(temp_db_path)
    dish_id = _create_dish(client)
    _place_order(client, dish_id, key="kt-1")
    _place_order(client, dish_id, key="kt-2")

    r = client.get("/api/kitchen/tickets", headers={"X-User-Role": "kitchen"})
    assert r.status_code == 200
    assert len(r.json()["data"]) == 2

    r = client.get("/api/kitchen/tickets?status=submitted", headers={"X-User-Role": "kitchen"})
    assert r.status_code == 200
    assert len(r.json()["data"]) == 2

    r = client.get("/api/kitchen/tickets?status=preparing", headers={"X-User-Role": "kitchen"})
    assert r.status_code == 200
    assert len(r.json()["data"]) == 0


# ---- Waste + stock counts + variance -------------------------------------


def test_waste_endpoint(temp_db_path):
    client = _client_with_db(temp_db_path)
    ing = _create_ingredient(client, qty=100)
    r = client.post(
        "/api/inventory/waste",
        json={"ingredient_id": ing, "quantity": 20, "reason": "spoilage"},
        headers={"X-User-Role": "inventory"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["quantity_today"] == 80.0


def test_waste_requires_inventory_role(temp_db_path):
    client = _client_with_db(temp_db_path)
    ing = _create_ingredient(client, qty=100)
    r = client.post(
        "/api/inventory/waste",
        json={"ingredient_id": ing, "quantity": 5, "reason": "spoilage"},
        headers={"X-User-Role": "cashier"},
    )
    assert r.status_code == 403, r.text


def test_stock_count_endpoint(temp_db_path):
    client = _client_with_db(temp_db_path)
    ing = _create_ingredient(client, qty=100)
    r = client.post(
        "/api/inventory/count",
        json={"ingredient_id": ing, "physical_quantity": 85, "notes": "Morning"},
        headers={"X-User-Role": "inventory"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["quantity_today"] == 85.0


def test_variance_report_endpoint(temp_db_path):
    client = _client_with_db(temp_db_path)
    ing = _create_ingredient(client, qty=100, name="Sugar")
    client.post(
        "/api/inventory/waste",
        json={"ingredient_id": ing, "quantity": 10, "reason": "spoilage"},
        headers={"X-User-Role": "inventory"},
    )
    r = client.get(
        "/api/inventory/variance?from_date=2000-01-01&to_date=2999-12-31",
        headers={"X-User-Role": "manager"},
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["from_date"] == "2000-01-01"
    assert len(body["entries"]) >= 1
    sugar = next(e for e in body["entries"] if e["ingredient_name"] == "Sugar")
    assert sugar["waste_quantity"] == 10.0


# ---- Users ---------------------------------------------------------------


def test_create_and_list_users(temp_db_path):
    client = _client_with_db(temp_db_path)
    r = client.post(
        "/api/users",
        json={"username": "alice", "display_name": "Alice", "role": "manager"},
    )
    assert r.status_code == 201, r.text
    r = client.get("/api/users")
    assert r.status_code == 200
    usernames = [u["username"] for u in r.json()["data"]]
    assert "alice" in usernames
