"""Order placement reduces ingredient stock; a second order that would go negative is refused."""


def _seed_dish_with_ingredient(db, ingredient_qty=200, dish_uses=100):
    ing_id = db.create_ingredient(
        {
            "name": "Flour",
            "unit": "g",
            "quantity_today": ingredient_qty,
            "min_threshold": 50,
            "cost_per_unit": 0.0,
            "supplier": None,
        }
    )
    dish_id = db.create_dish(
        {
            "name": "Bread",
            "price": 5.00,
            "category": "Bakery",
            "description": None,
            "preparation_time": 5,
            "difficulty_level": "easy",
            "ingredients": [{"ingredient_id": ing_id, "quantity": dish_uses, "unit": "g"}],
            "is_active": True,
        }
    )
    return ing_id, dish_id


def test_order_reduces_stock(db):
    ing_id, dish_id = _seed_dish_with_ingredient(db, ingredient_qty=200, dish_uses=100)
    db.create_order(
        {
            "items": [{"dish_id": dish_id, "quantity": 1, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
        },
        tax_rate=0.0,
    )
    after = db.get_ingredient_by_id(ing_id)
    assert after["quantity_today"] == 100.0  # 200 - 1 * 100


def test_order_exceeding_stock_rejected_with_clear_message(db):
    ing_id, dish_id = _seed_dish_with_ingredient(db, ingredient_qty=200, dish_uses=100)
    with __import__("pytest").raises(ValueError, match="Insufficient stock"):
        db.create_order(
            {
                # 3 breads * 100g = 300g needed, but only 200g in stock
                "items": [{"dish_id": dish_id, "quantity": 3, "price": 0.0}],
                "payment_method": "cash",
                "cashier_id": "t",
            },
            tax_rate=0.0,
        )
    # And nothing was consumed.
    after = db.get_ingredient_by_id(ing_id)
    assert after["quantity_today"] == 200.0


def test_consumption_recorded_in_ledger(db):
    ing_id, dish_id = _seed_dish_with_ingredient(db, ingredient_qty=500, dish_uses=100)
    db.create_order(
        {
            "items": [{"dish_id": dish_id, "quantity": 2, "price": 0.0}],
            "payment_method": "cash",
            "cashier_id": "t",
        },
        tax_rate=0.0,
    )
    # The DB-level test for ledger delta is in test_inventory_ledger.py.
    # Here we just verify the stock moved.
    assert db.get_ingredient_by_id(ing_id)["quantity_today"] == 300.0
