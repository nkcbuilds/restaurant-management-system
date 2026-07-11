"""Phase 1 inventory ledger: waste, stock counts, variance report."""


def _seed_ingredient(db, qty=100, name="Sugar", cost=2.0):
    return db.create_ingredient(
        {
            "name": name,
            "unit": "g",
            "quantity_today": qty,
            "min_threshold": 0,
            "cost_per_unit": cost,
            "supplier": None,
        }
    )


def test_waste_reduces_stock_and_writes_signed_ledger(db):
    ing = _seed_ingredient(db, qty=100)
    db.record_waste(ing, 30, reason="spoilage", notes="Power outage")
    after = db.get_ingredient_by_id(ing)
    assert after["quantity_today"] == 70.0

    # And the ledger captured a -30 waste row.
    conn = db.get_connection()
    row = conn.execute(
        """
        SELECT transaction_type, quantity_change, reason, notes
        FROM inventory_transactions WHERE ingredient_id = ? AND transaction_type = 'waste'
    """,
        (ing,),
    ).fetchone()
    conn.close()
    assert row["quantity_change"] == -30.0
    assert row["reason"] == "spoilage"


def test_waste_rejects_more_than_stock(db):
    ing = _seed_ingredient(db, qty=10)
    import pytest

    with pytest.raises(ValueError, match="negative"):
        db.record_waste(ing, 50, reason="spoilage")
    assert db.get_ingredient_by_id(ing)["quantity_today"] == 10.0


def test_stock_count_records_signed_delta(db):
    ing = _seed_ingredient(db, qty=100)
    db.record_stock_count(ing, 75, notes="Morning count")
    assert db.get_ingredient_by_id(ing)["quantity_today"] == 75.0

    conn = db.get_connection()
    row = conn.execute(
        """
        SELECT transaction_type, quantity_change, reason, notes
        FROM inventory_transactions WHERE ingredient_id = ? AND transaction_type = 'physical_count'
    """,
        (ing,),
    ).fetchone()
    conn.close()
    assert row["quantity_change"] == -25.0
    assert row["reason"] == "variance"
    assert row["notes"] == "Morning count"


def test_stock_count_at_zero_writes_match(db):
    ing = _seed_ingredient(db, qty=100)
    db.record_stock_count(ing, 100, notes="Spot on")
    conn = db.get_connection()
    row = conn.execute(
        """
        SELECT quantity_change, reason FROM inventory_transactions
        WHERE ingredient_id = ? AND transaction_type = 'physical_count'
    """,
        (ing,),
    ).fetchone()
    conn.close()
    assert row["quantity_change"] == 0.0
    assert row["reason"] == "count_match"


def test_variance_report_basic_shape(db):
    ing_a = _seed_ingredient(db, qty=100, name="A", cost=1.0)
    ing_b = _seed_ingredient(db, qty=100, name="B", cost=2.0)
    # Two waste entries on A.
    db.record_waste(ing_a, 10, reason="spoilage")
    db.record_waste(ing_a, 5, reason="staff_meal")
    # One stock count on B with variance -3.
    db.record_stock_count(ing_b, 97, notes="end of shift")

    report = db.get_variance_report("2000-01-01", "2999-12-31")
    by_id = {r["ingredient_id"]: r for r in report}
    assert by_id[ing_a]["waste_quantity"] == 15.0
    assert by_id[ing_b]["variance"] == -3.0
    assert by_id[ing_b]["cost_impact"] == -6.0  # -3 * 2.0


def test_variance_report_empty_when_no_activity(db):
    _seed_ingredient(db, qty=100)
    report = db.get_variance_report("2000-01-01", "2999-12-31")
    assert len(report) == 1
    assert report[0]["waste_quantity"] == 0.0
    assert report[0]["consumption_quantity"] == 0.0
