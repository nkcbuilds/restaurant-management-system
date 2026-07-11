"""
Inventory ledger correctness.

Specifically: `update_ingredient_quantity` must record the SIGNED DELTA
between the old and new quantity, not the absolute new value. The
previous implementation wrote the absolute value, which corrupted the
ledger (a manual edit that moved stock from 200g to 500g was recorded
as a +500g "consumption").
"""


def test_absolute_update_records_delta(db):
    ing_id = db.create_ingredient(
        {
            "name": "Sugar",
            "unit": "g",
            "quantity_today": 200.0,
            "min_threshold": 0,
            "cost_per_unit": 0.0,
            "supplier": None,
        }
    )

    db.update_ingredient_quantity(ing_id, 500.0)  # absolute set

    # The new quantity is correct.
    assert db.get_ingredient_by_id(ing_id)["quantity_today"] == 500.0

    # And the ledger recorded a +300 adjustment (not +500).
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT transaction_type, quantity_change, notes FROM inventory_transactions WHERE ingredient_id = ?",
        (ing_id,),
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["transaction_type"] == "adjustment"
    assert rows[0]["quantity_change"] == 300.0
    assert rows[0]["notes"] == "Manual quantity update"


def test_no_op_does_not_write_transaction(db):
    ing_id = db.create_ingredient(
        {
            "name": "Salt",
            "unit": "g",
            "quantity_today": 100.0,
            "min_threshold": 0,
            "cost_per_unit": 0.0,
            "supplier": None,
        }
    )
    db.update_ingredient_quantity(ing_id, 100.0)  # same value
    conn = db.get_connection()
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM inventory_transactions WHERE ingredient_id = ?",
        (ing_id,),
    ).fetchone()["c"]
    conn.close()
    assert n == 0


def test_negative_delta_is_signed(db):
    ing_id = db.create_ingredient(
        {
            "name": "Pepper",
            "unit": "g",
            "quantity_today": 100.0,
            "min_threshold": 0,
            "cost_per_unit": 0.0,
            "supplier": None,
        }
    )
    db.update_ingredient_quantity(ing_id, 30.0)
    conn = db.get_connection()
    row = conn.execute(
        "SELECT quantity_change FROM inventory_transactions WHERE ingredient_id = ?",
        (ing_id,),
    ).fetchone()
    conn.close()
    assert row["quantity_change"] == -70.0
