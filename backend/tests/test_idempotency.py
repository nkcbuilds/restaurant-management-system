"""Idempotency: same key returns same order; different keys produce different orders."""


def _create_simple_dish(db):
    return db.create_dish(
        {
            "name": "Tea",
            "price": 2.00,
            "category": "Drinks",
            "description": None,
            "preparation_time": 2,
            "difficulty_level": "easy",
            "ingredients": [],
            "is_active": True,
        }
    )


def test_same_key_returns_same_order_id(db):
    dish_id = _create_simple_dish(db)
    order_data = {
        "items": [{"dish_id": dish_id, "quantity": 1, "price": 0.0}],
        "payment_method": "cash",
        "cashier_id": "t",
    }
    id1 = db.create_order(order_data, tax_rate=0.0, idempotency_key="key-abc")
    id2 = db.create_order(order_data, tax_rate=0.0, idempotency_key="key-abc")
    assert id1 == id2


def test_different_keys_produce_different_orders(db):
    dish_id = _create_simple_dish(db)
    order_data = {
        "items": [{"dish_id": dish_id, "quantity": 1, "price": 0.0}],
        "payment_method": "cash",
        "cashier_id": "t",
    }
    id1 = db.create_order(order_data, tax_rate=0.0, idempotency_key="k1")
    id2 = db.create_order(order_data, tax_rate=0.0, idempotency_key="k2")
    assert id1 != id2


def test_lookup_by_idempotency_key(db):
    dish_id = _create_simple_dish(db)
    order_id = db.create_order(
        {
            "items": [{"dish_id": dish_id, "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
        },
        tax_rate=0.0,
        idempotency_key="lookup-me",
    )
    found = db.get_order_by_idempotency_key("lookup-me")
    assert found is not None
    assert found["id"] == order_id
    assert db.get_order_by_idempotency_key("never-used") is None
