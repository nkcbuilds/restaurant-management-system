import json
import logging
import sqlite3
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str = "restaurant.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the database with all required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")

        # Dishes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dishes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                preparation_time INTEGER,
                difficulty_level TEXT,
                is_active BOOLEAN DEFAULT 1,
                is_demo INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Ingredients table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingredients (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                unit TEXT NOT NULL,
                quantity_today REAL DEFAULT 0,
                min_threshold REAL DEFAULT 0,
                cost_per_unit REAL DEFAULT 0,
                supplier TEXT,
                is_demo INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Dish ingredients relationship table with sub-ingredients
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dish_ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dish_id TEXT NOT NULL,
                ingredient_id TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                sub_ingredient_data TEXT, -- JSON string for SubIngredient
                FOREIGN KEY (dish_id) REFERENCES dishes (id) ON DELETE CASCADE,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients (id)
            )
        """)

        # Orders table.
        # status: pending | submitted | accepted | preparing | ready | served |
        #         completed | cancelled
        # The Phase 0 lifecycle uses 'pending' for new orders created via the
        # POS; full state transitions land in Phase 1.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                total REAL NOT NULL,
                subtotal REAL NOT NULL,
                tax REAL NOT NULL,
                tax_rate REAL NOT NULL DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'pending',
                payment_method TEXT,
                customer_id TEXT,
                cashier_id TEXT,
                idempotency_key TEXT UNIQUE,
                is_demo INTEGER DEFAULT 0
            )
        """)

        # Order items table. `price` is the charged unit price at the time of
        # order, immutable even if the dish price changes later.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                dish_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                notes TEXT,
                FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
                FOREIGN KEY (dish_id) REFERENCES dishes (id)
            )
        """)

        # Sales analytics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                period TEXT NOT NULL,
                orders_count INTEGER DEFAULT 0,
                revenue REAL DEFAULT 0,
                avg_order_value REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, period)
            )
        """)

        # Predictions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dish_id TEXT NOT NULL,
                prediction_date DATE NOT NULL,
                period TEXT NOT NULL,
                predicted_demand INTEGER NOT NULL,
                confidence REAL NOT NULL,
                recommended_prep INTEGER NOT NULL,
                factors TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (dish_id) REFERENCES dishes (id),
                UNIQUE(dish_id, prediction_date, period)
            )
        """)

        # Inventory transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_id TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                quantity_change REAL NOT NULL,
                reference_id TEXT,
                notes TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients (id)
            )
        """)

        # System sync log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_type TEXT NOT NULL,
                status TEXT NOT NULL,
                records_affected INTEGER DEFAULT 0,
                error_message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- Phase 1 tables ----------------------------------------------------

        # Users + RBAC. The `role` column is the minimum role required for
        # protected endpoints. Default is 'cashier' for backwards compatibility.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'cashier',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Kitchen tickets. One row per order; status mirrors the underlying
        # order so the kitchen display can poll this table independently.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kitchen_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                station TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
            )
        """)

        # Phase 1 lightweight migrations. We avoid Alembic for now and just
        # ALTER in place when we discover a column is missing. This block is
        # idempotent: every ALTER is guarded by a PRAGMA table_info check.
        self._ensure_column(cursor, "inventory_transactions", "reason", "TEXT")
        self._ensure_column(cursor, "inventory_transactions", "user_id", "TEXT")

        # --- Phase 3 tables -------------------------------------------------

        # Suppliers + purchase orders. Phase 3 only models the minimum
        # needed to demonstrate a real workflow; richer workflows
        # (goods-received-notes, multi-currency, supplier returns) are
        # explicitly Phase 4.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                contact_name TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id TEXT PRIMARY KEY,
                supplier_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                notes TEXT,
                total REAL NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES suppliers (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS purchase_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_order_id TEXT NOT NULL,
                ingredient_id TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit_cost REAL NOT NULL,
                FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders (id) ON DELETE CASCADE,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients (id)
            )
        """)

        # Payments. One order can have many payments (split tender). The
        # webhook handler is pluggable; for now we accept payments via
        # POST /api/payments with an Idempotency-Key.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                amount REAL NOT NULL,
                method TEXT NOT NULL,
                reference TEXT,
                idempotency_key TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
            )
        """)

        # Audit log. Every state-changing action writes a row.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

    @staticmethod
    def _ensure_column(cursor, table: str, column: str, definition: str) -> None:
        """Idempotent ALTER TABLE ADD COLUMN.

        SQLite has no `ADD COLUMN IF NOT EXISTS`, so we read the schema and
        only add the column when it is genuinely missing.
        """
        cursor.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in cursor.fetchall()}
        if column not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def get_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # Ingredient operations
    def create_ingredient(self, ingredient_data: dict[str, Any]) -> str:
        """Create a new ingredient"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            ingredient_id = str(uuid.uuid4())

            cursor.execute(
                """
                INSERT INTO ingredients (id, name, unit, quantity_today, min_threshold, cost_per_unit, supplier)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    ingredient_id,
                    ingredient_data["name"],
                    ingredient_data["unit"],
                    ingredient_data.get("quantity_today", 0),
                    ingredient_data.get("min_threshold", 0),
                    ingredient_data.get("cost_per_unit", 0),
                    ingredient_data.get("supplier"),
                ),
            )

            conn.commit()
            return ingredient_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_ingredients(self) -> list[dict[str, Any]]:
        """Get all ingredients"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM ingredients ORDER BY name")
        ingredients = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return ingredients

    def get_ingredient_by_id(self, ingredient_id: str) -> dict[str, Any] | None:
        """Get ingredient by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM ingredients WHERE id = ?", (ingredient_id,))
        row = cursor.fetchone()

        conn.close()
        return dict(row) if row else None

    def update_ingredient_quantity(self, ingredient_id: str, quantity: float):
        """Update ingredient quantity to an absolute value and log the DELTA.

        The previous implementation wrote the absolute value as
        `quantity_change`, which corrupted the inventory ledger: the
        transaction log said "I consumed 5000g of flour" when really the
        user just typed 5000g into the field. The fix records the signed
        difference between the old and new quantities.
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT quantity_today FROM ingredients WHERE id = ?",
                (ingredient_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Ingredient {ingredient_id} not found")
            old_quantity = float(row["quantity_today"])
            delta = float(quantity) - old_quantity

            if delta == 0:
                # No-op; do not write a transaction.
                return

            cursor.execute(
                """
                UPDATE ingredients
                SET quantity_today = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (quantity, ingredient_id),
            )

            cursor.execute(
                """
                INSERT INTO inventory_transactions
                (ingredient_id, transaction_type, quantity_change, notes)
                VALUES (?, 'adjustment', ?, 'Manual quantity update')
            """,
                (ingredient_id, delta),
            )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Dish operations
    def create_dish(self, dish_data: dict[str, Any]) -> str:
        """Create a new dish with ingredients and sub-ingredients"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            dish_id = str(uuid.uuid4())

            # Insert dish
            cursor.execute(
                """
                INSERT INTO dishes (id, name, price, category, description, preparation_time, difficulty_level, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    dish_id,
                    dish_data["name"],
                    dish_data["price"],
                    dish_data["category"],
                    dish_data.get("description"),
                    dish_data.get("preparation_time"),
                    dish_data.get("difficulty_level"),
                    dish_data.get("is_active", True),
                ),
            )

            # Insert dish ingredients with sub-ingredients
            for ingredient in dish_data.get("ingredients", []):
                sub_ingredient_json = None
                if "sub_ingredient" in ingredient and ingredient["sub_ingredient"]:
                    sub_ingredient_json = json.dumps(ingredient["sub_ingredient"])

                cursor.execute(
                    """
                    INSERT INTO dish_ingredients (dish_id, ingredient_id, quantity, unit, sub_ingredient_data)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        dish_id,
                        ingredient["ingredient_id"],
                        ingredient["quantity"],
                        ingredient["unit"],
                        sub_ingredient_json,
                    ),
                )

            conn.commit()
            return dish_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_dishes(self) -> list[dict[str, Any]]:
        """Get all active dishes with their ingredients"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get dishes
        cursor.execute("SELECT * FROM dishes WHERE is_active = 1 ORDER BY name")
        dishes = [dict(row) for row in cursor.fetchall()]

        # Get ingredients for each dish
        for dish in dishes:
            cursor.execute(
                """
                SELECT di.ingredient_id, di.quantity, di.unit, di.sub_ingredient_data, i.name
                FROM dish_ingredients di
                JOIN ingredients i ON di.ingredient_id = i.id
                WHERE di.dish_id = ?
            """,
                (dish["id"],),
            )

            ingredients = []
            for row in cursor.fetchall():
                ingredient = {
                    "ingredient_id": row["ingredient_id"],
                    "quantity": row["quantity"],
                    "unit": row["unit"],
                    "name": row["name"],
                }

                # Parse sub-ingredient data
                if row["sub_ingredient_data"]:
                    try:
                        ingredient["sub_ingredient"] = json.loads(row["sub_ingredient_data"])
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid sub-ingredient data for dish {dish['id']}")

                ingredients.append(ingredient)

            dish["ingredients"] = ingredients

        conn.close()
        return dishes

    def get_dish_by_id(self, dish_id: str) -> dict[str, Any] | None:
        """Get dish by ID with ingredients"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM dishes WHERE id = ?", (dish_id,))
        dish_row = cursor.fetchone()

        if not dish_row:
            conn.close()
            return None

        dish = dict(dish_row)

        # Get ingredients
        cursor.execute(
            """
            SELECT di.ingredient_id, di.quantity, di.unit, di.sub_ingredient_data, i.name
            FROM dish_ingredients di
            JOIN ingredients i ON di.ingredient_id = i.id
            WHERE di.dish_id = ?
        """,
            (dish_id,),
        )

        ingredients = []
        for row in cursor.fetchall():
            ingredient = {
                "ingredient_id": row["ingredient_id"],
                "quantity": row["quantity"],
                "unit": row["unit"],
                "name": row["name"],
            }

            if row["sub_ingredient_data"]:
                try:
                    ingredient["sub_ingredient"] = json.loads(row["sub_ingredient_data"])
                except json.JSONDecodeError:
                    logger.warning(f"Invalid sub-ingredient data for dish {dish_id}")

            ingredients.append(ingredient)

        dish["ingredients"] = ingredients

        conn.close()
        return dish

    def update_dish(self, dish_id: str, dish_data: dict[str, Any]) -> bool:
        """Update a dish. Returns True iff a row matched the id."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Update dish basic info
            update_fields = []
            params = []

            for field in [
                "name",
                "price",
                "category",
                "description",
                "preparation_time",
                "difficulty_level",
                "is_active",
            ]:
                if field in dish_data:
                    update_fields.append(f"{field} = ?")
                    params.append(dish_data[field])

            rowcount = 0
            if update_fields:
                update_fields.append("updated_at = CURRENT_TIMESTAMP")
                params.append(dish_id)

                cursor.execute(
                    f"""
                    UPDATE dishes SET {", ".join(update_fields)}
                    WHERE id = ?
                """,
                    params,
                )
                rowcount = cursor.rowcount

            if rowcount == 0 and "ingredients" not in dish_data:
                # No scalar fields were provided and no ingredients to update.
                # Confirm the row actually exists so the route can return 404.
                cursor.execute("SELECT 1 FROM dishes WHERE id = ?", (dish_id,))
                if cursor.fetchone() is None:
                    conn.rollback()
                    return False

            # Update ingredients if provided
            if "ingredients" in dish_data:
                # Delete existing ingredients
                cursor.execute("DELETE FROM dish_ingredients WHERE dish_id = ?", (dish_id,))

                # Insert new ingredients
                for ingredient in dish_data["ingredients"]:
                    sub_ingredient_json = None
                    if "sub_ingredient" in ingredient and ingredient["sub_ingredient"]:
                        sub_ingredient_json = json.dumps(ingredient["sub_ingredient"])

                    cursor.execute(
                        """
                        INSERT INTO dish_ingredients (dish_id, ingredient_id, quantity, unit, sub_ingredient_data)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        (
                            dish_id,
                            ingredient["ingredient_id"],
                            ingredient["quantity"],
                            ingredient["unit"],
                            sub_ingredient_json,
                        ),
                    )

            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete_dish(self, dish_id: str) -> bool:
        """Delete a dish (soft delete)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE dishes
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (dish_id,),
            )

            success = cursor.rowcount > 0
            conn.commit()
            return success
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    # Order operations
    def get_order_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        """Return the order previously created with this idempotency key, if any."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM orders WHERE idempotency_key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self.get_order_by_id(row["id"])

    def create_order(
        self,
        order_data: dict[str, Any],
        *,
        tax_rate: float = 0.0,
        idempotency_key: str | None = None,
    ) -> str:
        """Create a new order and atomically deduct inventory.

        Security: prices come from the database, not from the client. Tax
        and total are computed server-side. If `idempotency_key` is
        supplied and a previous order used the same key, the previous
        order_id is returned (caller is expected to short-circuit BEFORE
        calling this method, but we double-check here as a safety net).

        Stock check: if any ingredient would go negative, no rows are
        written; a ValueError is raised with the offending ingredient
        name so the route layer can return HTTP 409.
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Idempotency safety net.
            if idempotency_key:
                cursor.execute(
                    "SELECT id FROM orders WHERE idempotency_key = ?",
                    (idempotency_key,),
                )
                existing = cursor.fetchone()
                if existing:
                    return existing["id"]

            # Look up authoritative dish prices.
            dish_ids = list({item["dish_id"] for item in order_data["items"]})
            placeholders = ",".join("?" for _ in dish_ids)
            cursor.execute(
                f"SELECT id, name, price, is_active FROM dishes WHERE id IN ({placeholders})",
                dish_ids,
            )
            dish_rows = {row["id"]: dict(row) for row in cursor.fetchall()}

            missing = [d for d in dish_ids if d not in dish_rows]
            if missing:
                raise ValueError(f"Unknown dish id(s): {', '.join(missing)}")
            inactive = [d for d, row in dish_rows.items() if not row["is_active"]]
            if inactive:
                raise ValueError(f"Inactive dish id(s): {', '.join(inactive)}")

            # Compute totals from server-side prices.
            subtotal = 0.0
            line_items = []
            for item in order_data["items"]:
                qty = int(item["quantity"])
                if qty <= 0:
                    raise ValueError(f"Invalid quantity {qty} for dish {item['dish_id']}")
                unit_price = float(dish_rows[item["dish_id"]]["price"])
                line_total = unit_price * qty
                subtotal += line_total
                line_items.append(
                    {
                        "dish_id": item["dish_id"],
                        "quantity": qty,
                        "price": unit_price,
                        "notes": item.get("notes", ""),
                    }
                )

            # Round to 2 decimals to avoid float drift.
            subtotal = round(subtotal, 2)
            tax = round(subtotal * float(tax_rate), 2)
            total = round(subtotal + tax, 2)

            # Pre-flight stock check.
            self._check_inventory_for_items(cursor, line_items)

            order_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO orders (
                    id, total, subtotal, tax, tax_rate, status, payment_method,
                    customer_id, cashier_id, idempotency_key
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    order_id,
                    total,
                    subtotal,
                    tax,
                    float(tax_rate),
                    "submitted",
                    order_data.get("payment_method"),
                    order_data.get("customer_id"),
                    order_data.get("cashier_id"),
                    idempotency_key,
                ),
            )

            # Auto-create a kitchen ticket at submitted time. Phase 1 does
            # NOT block on this; if it ever fails, the order still stands.
            try:
                cursor.execute(
                    """
                    INSERT INTO kitchen_tickets (order_id, status)
                    VALUES (?, 'submitted')
                """,
                    (order_id,),
                )
            except Exception as _e:  # pragma: no cover (defensive)
                logger.warning("kitchen_ticket create failed for %s: %s", order_id, _e)

            for item in line_items:
                cursor.execute(
                    """
                    INSERT INTO order_items (order_id, dish_id, quantity, price, notes)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (
                        order_id,
                        item["dish_id"],
                        item["quantity"],
                        item["price"],
                        item["notes"],
                    ),
                )
                self._update_inventory_for_dish(cursor, item["dish_id"], item["quantity"], order_id)

            conn.commit()
            return order_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _check_inventory_for_items(self, cursor, line_items: list[dict[str, Any]]) -> None:
        """Raise ValueError if any ingredient would go negative.

        Walks every (dish_id, qty) pair, computes the required
        consumption per ingredient, and compares against the current
        quantity. The check runs in a single read pass so concurrent
        orders may still race, but the inventory write below is part of
        the same transaction and the next iteration will be safer once
        we add row-level locks in Phase 1.
        """
        # Aggregate demand per ingredient.
        dish_ids = list({li["dish_id"] for li in line_items})
        placeholders = ",".join("?" for _ in dish_ids)
        cursor.execute(
            f"SELECT dish_id, ingredient_id, quantity FROM dish_ingredients WHERE dish_id IN ({placeholders})",
            dish_ids,
        )
        demand: dict[str, float] = {}
        recipe: dict[str, list[dict[str, Any]]] = {d: [] for d in dish_ids}
        for row in cursor.fetchall():
            recipe[row["dish_id"]].append(
                {"ingredient_id": row["ingredient_id"], "quantity": row["quantity"]}
            )
            demand[row["ingredient_id"]] = demand.get(row["ingredient_id"], 0.0)

        for li in line_items:
            for ing in recipe.get(li["dish_id"], []):
                demand[ing["ingredient_id"]] = (
                    demand.get(ing["ingredient_id"], 0.0) + ing["quantity"] * li["quantity"]
                )

        if not demand:
            return

        ing_ids = list(demand.keys())
        placeholders = ",".join("?" for _ in ing_ids)
        cursor.execute(
            f"SELECT id, name, quantity_today FROM ingredients WHERE id IN ({placeholders})",
            ing_ids,
        )
        stock = {row["id"]: dict(row) for row in cursor.fetchall()}

        shortages = []
        for ing_id, required in demand.items():
            row = stock.get(ing_id)
            if row is None:
                shortages.append(f"ingredient {ing_id} (missing)")
                continue
            if float(row["quantity_today"]) < required:
                shortages.append(
                    f"{row['name']} (need {required:.2f}, have {float(row['quantity_today']):.2f})"
                )

        if shortages:
            raise ValueError("Insufficient stock: " + "; ".join(shortages))

    def _update_inventory_for_dish(self, cursor, dish_id: str, quantity: int, order_id: str):
        """Update ingredient inventory when dish is ordered. Always writes a signed delta."""
        cursor.execute(
            """
            SELECT ingredient_id, quantity FROM dish_ingredients WHERE dish_id = ?
        """,
            (dish_id,),
        )

        ingredients = cursor.fetchall()

        for ingredient in ingredients:
            ingredient_id = ingredient["ingredient_id"]
            usage_quantity = float(ingredient["quantity"]) * int(quantity)

            cursor.execute(
                """
                UPDATE ingredients
                SET quantity_today = quantity_today - ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (usage_quantity, ingredient_id),
            )

            cursor.execute(
                """
                INSERT INTO inventory_transactions
                (ingredient_id, transaction_type, quantity_change, reference_id)
                VALUES (?, 'usage', ?, ?)
            """,
                (ingredient_id, -usage_quantity, order_id),
            )

    def get_orders(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        """Get orders with optional date filtering"""
        conn = self.get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM orders"
        params = []

        if start_date and end_date:
            query += " WHERE DATE(timestamp) BETWEEN ? AND ?"
            params.extend([start_date, end_date])
        elif start_date:
            query += " WHERE DATE(timestamp) >= ?"
            params.append(start_date)
        elif end_date:
            query += " WHERE DATE(timestamp) <= ?"
            params.append(end_date)

        query += " ORDER BY timestamp DESC"

        cursor.execute(query, params)
        orders = [dict(row) for row in cursor.fetchall()]

        # Get items for each order
        for order in orders:
            cursor.execute(
                """
                SELECT oi.*, d.name as dish_name
                FROM order_items oi
                JOIN dishes d ON oi.dish_id = d.id
                WHERE oi.order_id = ?
            """,
                (order["id"],),
            )

            order["items"] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return orders

    def get_order_by_id(self, order_id: str) -> dict[str, Any] | None:
        """Get order by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order_row = cursor.fetchone()

        if not order_row:
            conn.close()
            return None

        order = dict(order_row)

        # Get items
        cursor.execute(
            """
            SELECT oi.*, d.name as dish_name
            FROM order_items oi
            JOIN dishes d ON oi.dish_id = d.id
            WHERE oi.order_id = ?
        """,
            (order_id,),
        )

        order["items"] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return order

    # Analytics operations
    def get_sales_data(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Get sales data for date range with time period breakdown"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                DATE(timestamp) as date,
                CASE
                    WHEN CAST(strftime('%H', timestamp) AS INTEGER) BETWEEN 6 AND 11 THEN 'morning'
                    WHEN CAST(strftime('%H', timestamp) AS INTEGER) BETWEEN 12 AND 17 THEN 'afternoon'
                    WHEN CAST(strftime('%H', timestamp) AS INTEGER) BETWEEN 18 AND 23 THEN 'evening'
                    ELSE 'other'
                END as period,
                COUNT(*) as orders_count,
                SUM(total) as revenue,
                AVG(total) as avg_order_value
            FROM orders
            WHERE DATE(timestamp) BETWEEN ? AND ? AND status = 'completed'
            GROUP BY DATE(timestamp), period
            ORDER BY date, period
        """,
            (start_date, end_date),
        )

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Group by date and structure the response
        sales_by_date = {}
        for row in results:
            date = row["date"]
            if date not in sales_by_date:
                sales_by_date[date] = {
                    "date": date,
                    "morning": {"orders": 0, "revenue": 0.0, "avg_order": 0.0},
                    "afternoon": {"orders": 0, "revenue": 0.0, "avg_order": 0.0},
                    "evening": {"orders": 0, "revenue": 0.0, "avg_order": 0.0},
                    "total": {"orders": 0, "revenue": 0.0, "avg_order": 0.0},
                }

            period = row["period"]
            if period in ["morning", "afternoon", "evening"]:
                sales_by_date[date][period] = {
                    "orders": row["orders_count"],
                    "revenue": float(row["revenue"] or 0),
                    "avg_order": float(row["avg_order_value"] or 0),
                }

        # Calculate totals
        for date_data in sales_by_date.values():
            total_orders = (
                date_data["morning"]["orders"]
                + date_data["afternoon"]["orders"]
                + date_data["evening"]["orders"]
            )
            total_revenue = (
                date_data["morning"]["revenue"]
                + date_data["afternoon"]["revenue"]
                + date_data["evening"]["revenue"]
            )

            date_data["total"] = {
                "orders": total_orders,
                "revenue": total_revenue,
                "avg_order": total_revenue / total_orders if total_orders > 0 else 0.0,
            }

        return list(sales_by_date.values())

    def get_daily_sales(self, date: str) -> dict[str, Any] | None:
        """Get detailed sales data for a specific date"""
        sales_data = self.get_sales_data(date, date)
        return sales_data[0] if sales_data else None

    # Prediction operations
    def save_predictions(self, predictions: list[dict[str, Any]]):
        """Save ML model predictions"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            for pred in predictions:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO predictions
                    (dish_id, prediction_date, period, predicted_demand, confidence, recommended_prep, factors)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        pred["dish_id"],
                        pred["prediction_date"],
                        pred["period"],
                        pred["predicted_demand"],
                        pred["confidence"],
                        pred["recommended_prep"],
                        json.dumps(pred.get("factors", [])),
                    ),
                )

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_predictions(self, date: str) -> list[dict[str, Any]]:
        """Get predictions for a specific date"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT p.*, d.name as dish_name
            FROM predictions p
            JOIN dishes d ON p.dish_id = d.id
            WHERE p.prediction_date = ?
        """,
            (date,),
        )

        predictions = []
        for row in cursor.fetchall():
            pred = dict(row)
            try:
                pred["factors"] = json.loads(pred["factors"]) if pred["factors"] else []
            except json.JSONDecodeError:
                pred["factors"] = []
            predictions.append(pred)

        conn.close()
        return predictions

    def get_historical_order_data(self, days: int = 30) -> list[dict[str, Any]]:
        """Get historical order data for ML training"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT
                DATE(o.timestamp) as ds,
                CASE
                    WHEN CAST(strftime('%H', o.timestamp) AS INTEGER) BETWEEN 6 AND 11 THEN 'morning'
                    WHEN CAST(strftime('%H', o.timestamp) AS INTEGER) BETWEEN 12 AND 17 THEN 'afternoon'
                    WHEN CAST(strftime('%H', o.timestamp) AS INTEGER) BETWEEN 18 AND 23 THEN 'evening'
                    ELSE 'other'
                END as period,
                oi.dish_id,
                d.name as dish_name,
                SUM(oi.quantity) as y,
                strftime('%w', o.timestamp) as day_of_week,
                strftime('%m', o.timestamp) as month
            FROM orders o
            JOIN order_items oi ON o.id = oi.order_id
            JOIN dishes d ON oi.dish_id = d.id
            WHERE o.status = 'completed'
            AND DATE(o.timestamp) >= DATE('now', '-{days} days')
            GROUP BY DATE(o.timestamp), period, oi.dish_id
            ORDER BY ds, dish_id, period
        """)

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    # -----------------------------------------------------------------------
    # Phase 1: order state machine, kitchen tickets, waste, stock counts
    # -----------------------------------------------------------------------

    def create_kitchen_ticket(self, order_id: str, station: str | None = None) -> int:
        """Idempotent kitchen ticket creation. Returns the ticket id."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, status FROM kitchen_tickets WHERE order_id = ?",
                (order_id,),
            )
            row = cursor.fetchone()
            if row:
                return int(row["id"])
            cursor.execute(
                """
                INSERT INTO kitchen_tickets (order_id, status, station)
                VALUES (?, 'submitted', ?)
            """,
                (order_id, station),
            )
            ticket_id = int(cursor.lastrowid or 0)
            conn.commit()
            return ticket_id
        finally:
            conn.close()

    def update_kitchen_ticket(self, order_id: str, status: str) -> None:
        """Mirror the order status on the kitchen ticket."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE kitchen_tickets
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?
            """,
                (status, order_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_kitchen_tickets(self, statuses: list[str] | None = None) -> list[dict[str, Any]]:
        """Return kitchen tickets (optionally filtered by status) with items."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            query = """
                SELECT kt.*, oi.dish_id, oi.quantity, oi.price, oi.notes,
                       d.name AS dish_name, d.category
                FROM kitchen_tickets kt
                JOIN orders o ON kt.order_id = o.id
                JOIN order_items oi ON oi.order_id = o.id
                JOIN dishes d ON d.id = oi.dish_id
            """
            params: list[Any] = []
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                query += f" WHERE kt.status IN ({placeholders})"
                params.extend(statuses)
            query += " ORDER BY kt.created_at ASC"
            cursor.execute(query, params)
            rows = [dict(r) for r in cursor.fetchall()]

            # Group items per ticket
            tickets: dict[int, dict[str, Any]] = {}
            for row in rows:
                tid = int(row["id"])
                if tid not in tickets:
                    tickets[tid] = {
                        "id": tid,
                        "order_id": row["order_id"],
                        "status": row["status"],
                        "station": row.get("station"),
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "items": [],
                    }
                tickets[tid]["items"].append(
                    {
                        "dish_id": row["dish_id"],
                        "quantity": row["quantity"],
                        "price": row["price"],
                        "notes": row.get("notes"),
                        "dish_name": row.get("dish_name"),
                        "category": row.get("category"),
                    }
                )
            return list(tickets.values())
        finally:
            conn.close()

    def transition_order_status(
        self,
        order_id: str,
        new_status: str,
        *,
        reverse_on_cancel: str = "always",
        reversal_user: str | None = None,
    ) -> dict[str, Any]:
        """Move an order to a new status, enforcing the lifecycle rules.

        Cancellation behaviour:
          * 'always'        — reversal always runs.
          * 'preparing_only' — reversal only runs if the cancelled order
                              had not yet reached PREPARING (i.e. raw stock
                              was reserved but not yet consumed in the
                              kitchen).  Phase 1 keeps the policy simple:
                              if status in {draft, submitted, accepted},
                              reverse the consumption.
          * 'never'         — no reversal; the consumption stays as waste.

        Returns the updated order dict (the same shape as get_order_by_id).
        Raises ValueError on illegal transitions, missing orders, or
        insufficient stock when reversal would push a quantity negative.
        """
        from models import is_valid_transition  # local import to avoid cycle

        order = self.get_order_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        current = order["status"]
        if not is_valid_transition(current, new_status):
            raise ValueError(
                f"Illegal transition: {current} -> {new_status}",
            )

        if current == new_status:
            # Idempotent re-assert.
            return order

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (new_status, order_id),
            )

            if new_status == "cancelled":
                # Decide whether to reverse inventory.
                should_reverse = reverse_on_cancel == "always" or (
                    reverse_on_cancel == "preparing_only"
                    and current in {"draft", "submitted", "accepted"}
                )
                if should_reverse:
                    self._reverse_inventory_for_order(cursor, order_id, user_id=reversal_user)

            cursor.execute(
                "UPDATE kitchen_tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE order_id = ?",
                (new_status, order_id),
            )
            conn.commit()
            return self.get_order_by_id(order_id) or order
        finally:
            conn.close()

    def _reverse_inventory_for_order(
        self, cursor, order_id: str, user_id: str | None = None
    ) -> None:
        """Reverse the consumption side of the inventory ledger.

        For each line item, find the consumption row(s) and write a
        matching POSITIVE adjustment. Refuses to push stock negative if
        some has already been consumed by a later order.
        """
        cursor.execute(
            """
            SELECT oi.dish_id, oi.quantity
            FROM order_items oi
            WHERE oi.order_id = ?
        """,
            (order_id,),
        )
        lines = [dict(r) for r in cursor.fetchall()]

        for line in lines:
            cursor.execute(
                """
                SELECT ingredient_id, quantity
                FROM dish_ingredients
                WHERE dish_id = ?
            """,
                (line["dish_id"],),
            )
            for ing in cursor.fetchall():
                to_restore = float(ing["quantity"]) * int(line["quantity"])
                cursor.execute(
                    """
                    SELECT quantity_today FROM ingredients WHERE id = ?
                """,
                    (ing["ingredient_id"],),
                )
                row = cursor.fetchone()
                if not row:
                    continue
                if float(row["quantity_today"]) + to_restore < 0:
                    raise ValueError(
                        f"Cannot reverse: ingredient {ing['ingredient_id']} would go negative",
                    )
                cursor.execute(
                    """
                    UPDATE ingredients
                    SET quantity_today = quantity_today + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (to_restore, ing["ingredient_id"]),
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_transactions
                      (ingredient_id, transaction_type, quantity_change,
                       reference_id, notes, user_id)
                    VALUES (?, 'adjustment', ?, ?, ?, ?)
                """,
                    (
                        ing["ingredient_id"],
                        to_restore,
                        order_id,
                        f"Reversal of order {order_id}",
                        user_id,
                    ),
                )

    # -- Inventory: waste + stock counts + variance ---------------------------

    def record_waste(
        self,
        ingredient_id: str,
        quantity: float,
        reason: str,
        notes: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Write a waste entry and reduce stock. Quantity is positive."""
        if quantity <= 0:
            raise ValueError("Waste quantity must be positive")
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT quantity_today FROM ingredients WHERE id = ?",
                (ingredient_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Ingredient {ingredient_id} not found")
            current = float(row["quantity_today"])
            new_qty = current - quantity
            if new_qty < 0:
                raise ValueError(
                    f"Waste would push {ingredient_id} negative "
                    f"(have {current}, writing {quantity})",
                )
            cursor.execute(
                """
                UPDATE ingredients SET quantity_today = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (new_qty, ingredient_id),
            )
            cursor.execute(
                """
                INSERT INTO inventory_transactions
                  (ingredient_id, transaction_type, quantity_change, notes, reason, user_id)
                VALUES (?, 'waste', ?, ?, ?, ?)
            """,
                (ingredient_id, -float(quantity), notes, reason, user_id),
            )
            conn.commit()
            return self.get_ingredient_by_id(ingredient_id) or {}
        finally:
            conn.close()

    def record_stock_count(
        self,
        ingredient_id: str,
        physical_quantity: float,
        notes: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Record a physical stock count and adjust to that value.

        Writes a 'physical_count' transaction with the signed delta
        between expected and physical quantities. The 'expected' value is
        the current `quantity_today` BEFORE the adjustment, so the
        ledger can reconstruct the variance.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT quantity_today FROM ingredients WHERE id = ?",
                (ingredient_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Ingredient {ingredient_id} not found")
            expected = float(row["quantity_today"])
            delta = float(physical_quantity) - expected
            if delta == 0:
                # No-op — still write a transaction so the count is auditable.
                cursor.execute(
                    """
                    INSERT INTO inventory_transactions
                      (ingredient_id, transaction_type, quantity_change, notes, reason, user_id)
                    VALUES (?, 'physical_count', 0, ?, 'count_match', ?)
                """,
                    (ingredient_id, notes, user_id),
                )
                conn.commit()
                return self.get_ingredient_by_id(ingredient_id) or {}
            cursor.execute(
                """
                UPDATE ingredients SET quantity_today = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (float(physical_quantity), ingredient_id),
            )
            cursor.execute(
                """
                INSERT INTO inventory_transactions
                  (ingredient_id, transaction_type, quantity_change, notes, reason, user_id)
                VALUES (?, 'physical_count', ?, ?, ?, ?)
            """,
                (
                    ingredient_id,
                    delta,
                    notes or "Stock count",
                    "variance" if abs(delta) > 0 else "count_match",
                    user_id,
                ),
            )
            conn.commit()
            return self.get_ingredient_by_id(ingredient_id) or {}
        finally:
            conn.close()

    def get_variance_report(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        """Theoretical vs actual usage for the given date range.

        For each ingredient:
          * consumption  = SUM(usage transactions in range)
          * waste        = SUM(waste transactions in range)
          * expected     = opening_stock - consumption - waste
          * physical     = last physical_count in (or before) the range,
                           or None if never counted
          * variance     = physical - expected if physical exists
          * cost_impact  = variance * cost_per_unit (cost of unexplained
                           variance is what management cares about)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, name, cost_per_unit FROM ingredients ORDER BY name
            """
            )
            ingredients = [dict(r) for r in cursor.fetchall()]
            report: list[dict[str, Any]] = []
            for ing in ingredients:
                iid = ing["id"]
                cursor.execute(
                    """
                    SELECT
                      COALESCE(SUM(CASE WHEN transaction_type IN ('usage', 'consumption')
                                   THEN -quantity_change ELSE 0 END), 0) AS consumption,
                      COALESCE(SUM(CASE WHEN transaction_type = 'waste'
                                   THEN -quantity_change ELSE 0 END), 0) AS waste,
                      COALESCE(SUM(CASE WHEN transaction_type = 'physical_count'
                                   THEN quantity_change ELSE 0 END), 0) AS variance_delta
                    FROM inventory_transactions
                    WHERE ingredient_id = ?
                      AND DATE(timestamp) BETWEEN ? AND ?
                """,
                    (iid, from_date, to_date),
                )
                row = cursor.fetchone()
                consumption = float(row["consumption"] or 0)
                waste = float(row["waste"] or 0)
                variance_delta = float(row["variance_delta"] or 0)

                # Last physical_count at or before to_date.
                cursor.execute(
                    """
                    SELECT quantity_change FROM inventory_transactions
                    WHERE ingredient_id = ? AND transaction_type = 'physical_count'
                      AND DATE(timestamp) <= ?
                    ORDER BY timestamp DESC LIMIT 1
                """,
                    (iid, to_date),
                )
                last_count = cursor.fetchone()
                physical = None
                variance = None
                if last_count is not None:
                    physical = float(last_count["quantity_change"])
                    # physical is a delta, so report it as the cumulative
                    # correction applied during the period.
                    variance = physical

                cost = float(ing["cost_per_unit"] or 0)
                cost_impact = variance_delta * cost if variance_delta else 0.0

                report.append(
                    {
                        "ingredient_id": iid,
                        "ingredient_name": ing["name"],
                        "expected_stock": None,  # not derivable without opening stock
                        "physical_quantity": physical,
                        "variance": variance,
                        "waste_quantity": waste,
                        "consumption_quantity": consumption,
                        "cost_impact": round(cost_impact, 2),
                    }
                )
            return report
        finally:
            conn.close()

    # -- Users / RBAC --------------------------------------------------------

    def create_user(self, username: str, display_name: str, role: str = "cashier") -> str:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            user_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO users (id, username, display_name, role)
                VALUES (?, ?, ?, ?)
            """,
                (user_id, username, display_name, role),
            )
            conn.commit()
            return user_id
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1",
                (username,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_users(self) -> list[dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE is_active = 1 ORDER BY display_name")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # Phase 3: suppliers, purchase orders, payments, audit log
    # -----------------------------------------------------------------------

    def create_supplier(
        self,
        name: str,
        *,
        contact_name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        address: str | None = None,
    ) -> str:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            sid = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO suppliers (id, name, contact_name, phone, email, address)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (sid, name, contact_name, phone, email, address),
            )
            conn.commit()
            return sid
        finally:
            conn.close()

    def list_suppliers(self) -> list[dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM suppliers WHERE is_active = 1 ORDER BY name")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def get_supplier(self, supplier_id: str) -> dict[str, Any] | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM suppliers WHERE id = ? AND is_active = 1",
                (supplier_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_purchase_order(
        self,
        supplier_id: str,
        items: list[dict[str, Any]],
        notes: str | None = None,
    ) -> str:
        """Insert a draft PO. `items` is a list of dicts with
        ingredient_id, quantity, unit_cost."""
        if not items:
            raise ValueError("Purchase order must contain at least one item")
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            po_id = str(uuid.uuid4())
            total = 0.0
            for it in items:
                total += float(it["quantity"]) * float(it["unit_cost"])
            cursor.execute(
                """
                INSERT INTO purchase_orders (id, supplier_id, status, notes, total)
                VALUES (?, ?, 'draft', ?, ?)
            """,
                (po_id, supplier_id, notes, round(total, 2)),
            )
            for it in items:
                cursor.execute(
                    """
                    INSERT INTO purchase_order_items
                      (purchase_order_id, ingredient_id, quantity, unit_cost)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        po_id,
                        it["ingredient_id"],
                        float(it["quantity"]),
                        float(it["unit_cost"]),
                    ),
                )
            conn.commit()
            return po_id
        finally:
            conn.close()

    def get_purchase_order(self, po_id: str) -> dict[str, Any] | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM purchase_orders WHERE id = ?", (po_id,))
            po = cursor.fetchone()
            if not po:
                return None
            po_dict = dict(po)
            cursor.execute(
                """
                SELECT * FROM purchase_order_items WHERE purchase_order_id = ?
                ORDER BY id
            """,
                (po_id,),
            )
            po_dict["items"] = [dict(r) for r in cursor.fetchall()]
            return po_dict
        finally:
            conn.close()

    def list_purchase_orders(self, supplier_id: str | None = None) -> list[dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if supplier_id:
                cursor.execute(
                    "SELECT * FROM purchase_orders WHERE supplier_id = ? ORDER BY created_at DESC",
                    (supplier_id,),
                )
            else:
                cursor.execute("SELECT * FROM purchase_orders ORDER BY created_at DESC")
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def receive_purchase_order(self, po_id: str, actor: str | None = None) -> dict[str, Any]:
        """Mark a PO as received and write `purchase` ledger entries.

        Updates `ingredients.cost_per_unit` to a quantity-weighted
        average of old and new cost; adds to `quantity_today`; writes a
        `purchase` ledger row per ingredient.
        """
        po = self.get_purchase_order(po_id)
        if not po:
            raise ValueError(f"Purchase order {po_id} not found")
        if po["status"] == "received":
            return po  # idempotent
        if po["status"] == "cancelled":
            raise ValueError("Cannot receive a cancelled PO")

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE purchase_orders SET status='received',"
                " updated_at=CURRENT_TIMESTAMP WHERE id = ?",
                (po_id,),
            )
            for it in po["items"]:
                qty = float(it["quantity"])
                unit_cost = float(it["unit_cost"])
                ing_id = it["ingredient_id"]
                cursor.execute(
                    "SELECT quantity_today, cost_per_unit FROM ingredients WHERE id = ?",
                    (ing_id,),
                )
                row = cursor.fetchone()
                if not row:
                    continue
                old_qty = float(row["quantity_today"])
                old_cost = float(row["cost_per_unit"] or 0)
                new_qty = old_qty + qty
                new_cost = (
                    (old_cost * old_qty + unit_cost * qty) / new_qty if new_qty > 0 else unit_cost
                )
                cursor.execute(
                    """
                    UPDATE ingredients
                    SET quantity_today = ?, cost_per_unit = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (new_qty, round(new_cost, 4), ing_id),
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_transactions
                      (ingredient_id, transaction_type, quantity_change,
                       reference_id, notes, user_id)
                    VALUES (?, 'purchase', ?, ?, 'purchase order received', ?)
                """,
                    (ing_id, qty, po_id, actor),
                )
            conn.commit()
            return self.get_purchase_order(po_id) or po
        finally:
            conn.close()

    def cancel_purchase_order(self, po_id: str) -> dict[str, Any] | None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE purchase_orders SET status='cancelled',"
                " updated_at=CURRENT_TIMESTAMP WHERE id = ? AND status NOT IN ('received', 'cancelled')",
                (po_id,),
            )
            if cursor.rowcount == 0:
                return None
            conn.commit()
            return self.get_purchase_order(po_id)
        finally:
            conn.close()

    def create_payment(
        self,
        order_id: str,
        amount: float,
        method: str,
        reference: str | None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Record a payment against an order. Idempotent by key."""
        if amount <= 0:
            raise ValueError("Payment amount must be positive")
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if idempotency_key:
                cursor.execute(
                    "SELECT * FROM payments WHERE idempotency_key = ?",
                    (idempotency_key,),
                )
                existing = cursor.fetchone()
                if existing:
                    return dict(existing)
            cursor.execute(
                """
                INSERT INTO payments (order_id, amount, method, reference, idempotency_key)
                VALUES (?, ?, ?, ?, ?)
            """,
                (order_id, amount, method, reference, idempotency_key),
            )
            pid = int(cursor.lastrowid or 0)
            conn.commit()
            cursor.execute("SELECT * FROM payments WHERE id = ?", (pid,))
            return dict(cursor.fetchone() or {})
        finally:
            conn.close()

    def list_payments_for_order(self, order_id: str) -> list[dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM payments WHERE order_id = ? ORDER BY created_at DESC",
                (order_id,),
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def write_audit(
        self,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO audit_log (actor, action, entity_type, entity_id, payload)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    actor,
                    action,
                    entity_type,
                    entity_id,
                    json.dumps(payload) if payload is not None else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
            rows = [dict(r) for r in cursor.fetchall()]
            for r in rows:
                if r.get("payload"):
                    try:
                        r["payload"] = json.loads(r["payload"])
                    except json.JSONDecodeError:
                        pass
            return rows
        finally:
            conn.close()
