# SQLite database schema reference for the restaurant management system.
# The active DatabaseManager implementation is in database.py.
# This file is kept for schema reference only.

# Key tables (see database.py for the active implementation):
#
# dishes(id, name, price, category, description, preparation_time, difficulty_level,
#        is_active, is_demo, created_at, updated_at)
# ingredients(id, name, unit, quantity_today, min_threshold, cost_per_unit,
#             supplier, is_demo, created_at, updated_at)
# dish_ingredients(id, dish_id, ingredient_id, quantity, unit, sub_ingredient_data)
# orders(id, total, subtotal, tax, tax_rate, timestamp, status, payment_method,
#        customer_id, cashier_id, idempotency_key, is_demo)
# order_items(id, order_id, dish_id, quantity, price, notes)
# sales_analytics(id, date, period, orders_count, revenue, avg_order_value, ...)
# predictions(id, dish_id, prediction_date, period, predicted_demand,
#            confidence, recommended_prep, factors, ...)
# inventory_transactions(id, ingredient_id, transaction_type, quantity_change,
#                       reference_id, notes, timestamp)
# sync_log(id, sync_type, status, records_affected, error_message, timestamp)
