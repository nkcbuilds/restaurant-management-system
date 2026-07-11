"""Order state machine: lifecycle transitions, cancellation, kitchen tickets."""

import pytest


def _make_dish_and_ingredient(db, ingredient_qty=500, dish_uses=100, price=10.0):
    ing = db.create_ingredient(
        {
            "name": "Flour",
            "unit": "g",
            "quantity_today": ingredient_qty,
            "min_threshold": 0,
            "cost_per_unit": 0,
            "supplier": None,
        }
    )
    dish = db.create_dish(
        {
            "name": "Bread",
            "price": price,
            "category": "Bakery",
            "description": None,
            "preparation_time": 5,
            "difficulty_level": "easy",
            "ingredients": [{"ingredient_id": ing, "quantity": dish_uses, "unit": "g"}],
            "is_active": True,
        }
    )
    return ing, dish


def _place_order(db, dish_id, qty=1, key="k1"):
    return db.create_order(
        {
            "items": [{"dish_id": dish_id, "quantity": qty, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
        },
        tax_rate=0.0,
        idempotency_key=key,
    )


def test_order_lifecycle_walks_full_path(db):
    ing, dish = _make_dish_and_ingredient(db)
    order_id = _place_order(db, dish)

    for new_status in ["accepted", "preparing", "ready", "served", "completed"]:
        updated = db.transition_order_status(order_id, new_status)
        assert updated["status"] == new_status

    # Terminal state cannot move further.
    with pytest.raises(ValueError, match="Illegal transition"):
        db.transition_order_status(order_id, "cancelled")


def test_illegal_transition_rejected(db):
    ing, dish = _make_dish_and_ingredient(db)
    order_id = _place_order(db, dish)

    # Cannot jump from submitted -> completed
    with pytest.raises(ValueError, match="Illegal transition"):
        db.transition_order_status(order_id, "completed")


def test_idempotent_reassert_is_noop(db):
    ing, dish = _make_dish_and_ingredient(db)
    order_id = _place_order(db, dish)
    # Re-asserting the same state is allowed.
    updated = db.transition_order_status(order_id, "submitted")
    assert updated["status"] == "submitted"


def test_cancel_from_submitted_reverses_stock(db):
    ing, dish = _make_dish_and_ingredient(db, ingredient_qty=500, dish_uses=100)
    order_id = _place_order(db, dish, qty=2)
    assert db.get_ingredient_by_id(ing)["quantity_today"] == 300.0  # 500 - 200

    db.transition_order_status(order_id, "cancelled")
    assert db.get_ingredient_by_id(ing)["quantity_today"] == 500.0  # restored


def test_cancel_from_preparing_does_not_reverse_stock(db):
    ing, dish = _make_dish_and_ingredient(db, ingredient_qty=500, dish_uses=100)
    order_id = _place_order(db, dish, qty=2)
    db.transition_order_status(order_id, "accepted")
    db.transition_order_status(order_id, "preparing")
    stock_at_preparing = db.get_ingredient_by_id(ing)["quantity_today"]
    assert stock_at_preparing == 300.0

    # With preparing_only policy, cancelling should NOT restore stock.
    db.transition_order_status(order_id, "cancelled", reverse_on_cancel="preparing_only")
    assert db.get_ingredient_by_id(ing)["quantity_today"] == stock_at_preparing


def test_cancel_from_preparing_with_always_reverses(db):
    ing, dish = _make_dish_and_ingredient(db, ingredient_qty=500, dish_uses=100)
    order_id = _place_order(db, dish, qty=2)
    db.transition_order_status(order_id, "accepted")
    db.transition_order_status(order_id, "preparing")

    # With always policy, cancellation always restores.
    db.transition_order_status(order_id, "cancelled", reverse_on_cancel="always")
    assert db.get_ingredient_by_id(ing)["quantity_today"] == 500.0


def test_kitchen_ticket_created_with_order(db):
    ing, dish = _make_dish_and_ingredient(db)
    order_id = _place_order(db, dish, key="ticket-1")
    tickets = db.get_kitchen_tickets()
    assert len(tickets) == 1
    assert tickets[0]["order_id"] == order_id
    assert tickets[0]["status"] == "submitted"


def test_kitchen_ticket_status_tracks_order(db):
    ing, dish = _make_dish_and_ingredient(db)
    order_id = _place_order(db, dish, key="ticket-2")
    db.transition_order_status(order_id, "accepted")
    db.transition_order_status(order_id, "preparing")

    tickets = db.get_kitchen_tickets()
    assert tickets[0]["status"] == "preparing"


def test_kitchen_tickets_filtered_by_status(db):
    ing, dish = _make_dish_and_ingredient(db)
    a = _place_order(db, dish, key="a")
    db.create_order(
        {
            "items": [{"dish_id": dish, "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
        },
        tax_rate=0.0,
        idempotency_key="b",
    )
    db.transition_order_status(a, "accepted")

    open_tix = db.get_kitchen_tickets(statuses=["submitted"])
    active_tix = db.get_kitchen_tickets(statuses=["accepted"])
    assert len(open_tix) == 1
    assert len(active_tix) == 1
    assert active_tix[0]["order_id"] == a


def test_transition_unknown_order_raises(db):
    with pytest.raises(ValueError, match="not found"):
        db.transition_order_status("does-not-exist", "accepted")
