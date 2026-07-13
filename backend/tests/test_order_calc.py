"""Server-side price, tax, and total calculation. The client never decides the price."""

import pytest


def _create_dish(db, name="Pizza", price=12.50):
    return db.create_dish(
        {
            "name": name,
            "price": price,
            "category": "Mains",
            "description": None,
            "preparation_time": 10,
            "difficulty_level": "easy",
            "ingredients": [],
            "is_active": True,
        }
    )


def test_subtotal_uses_dish_price_not_client_value(db):
    dish_id = _create_dish(db, price=12.50)
    order_id = db.create_order(
        {
            "items": [{"dish_id": dish_id, "quantity": 2, "price": 0.01}],  # client lies
            "payment_method": "cash",
            "cashier_id": "tester",
        },
        tax_rate=0.0,
    )
    order = db.get_order_by_id(order_id)
    assert order["subtotal"] == pytest.approx(25.00, abs=0.01)
    assert order["total"] == pytest.approx(25.00, abs=0.01)
    # The actual charged price is stored on the line item.
    assert order["items"][0]["price"] == pytest.approx(12.50, abs=0.01)


def test_tax_computed_server_side(db):
    dish_id = _create_dish(db, price=100.00)
    order_id = db.create_order(
        {
            "items": [{"dish_id": dish_id, "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "tester",
        },
        tax_rate=0.10,  # 10%
    )
    order = db.get_order_by_id(order_id)
    assert order["subtotal"] == pytest.approx(100.00, abs=0.01)
    assert order["tax"] == pytest.approx(10.00, abs=0.01)
    assert order["total"] == pytest.approx(110.00, abs=0.01)
    # And the client-supplied tax (if any) is ignored:
    assert order["tax"] != 0.01


def test_new_order_starts_submitted_not_completed(db):
    dish_id = _create_dish(db, price=5.00)
    order_id = db.create_order(
        {
            "items": [{"dish_id": dish_id, "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "tester",
        },
        tax_rate=0.0,
    )
    order = db.get_order_by_id(order_id)
    assert (
        order["status"] == "submitted"
    ), "Phase 1 ships orders in 'submitted' state (kitchen must accept next)"


def test_unknown_dish_rejected(db):
    with pytest.raises(ValueError, match="Unknown dish"):
        db.create_order(
            {
                "items": [{"dish_id": "does-not-exist", "quantity": 1, "price": 0.0}],
                "payment_method": "cash",
                "cashier_id": "tester",
            },
            tax_rate=0.0,
        )


def test_inactive_dish_rejected(db):
    dish_id = _create_dish(db, price=5.00)
    db.delete_dish(dish_id)  # soft delete -> is_active = 0
    with pytest.raises(ValueError, match="Inactive dish"):
        db.create_order(
            {
                "items": [{"dish_id": dish_id, "quantity": 1, "price": 0.0}],
                "payment_method": "cash",
                "cashier_id": "tester",
            },
            tax_rate=0.0,
        )


def test_empty_order_rejected(db):
    """An order with no items is meaningless. The DB should refuse it,
    not silently create a $0 order."""
    with pytest.raises(ValueError, match="at least one item"):
        db.create_order(
            {
                "items": [],
                "payment_method": "cash",
                "cashier_id": "tester",
            },
            tax_rate=0.0,
        )
