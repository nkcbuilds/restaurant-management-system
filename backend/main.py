"""
RestaurantOS FastAPI app.

Phase 0 refactor:
  * No more try/except -> 500 swallowing. `core.errors.install_error_handlers`
    re-raises HTTPException, logs unexpected exceptions with an error_id,
    and returns a sanitised body.
  * No more auto-sync inside the API process. The lifespan only does
    initialisation. The worker is its own process.
  * Order creation is server-priced, idempotency-aware, defaults to
    'pending' status, and refuses negative stock.
  * CORS origins come from the `CORS_ALLOW_ORIGINS` env var.
  * /api/health actually checks the database.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from core import (
    CORS_ALLOW_ORIGINS,
    DEFAULT_TAX_RATE,
    DEMO_MODE_ENABLED,
    IDEMPOTENCY_REQUIRED,
    new_error_id,
)
from core.errors import install_error_handlers
from database import DatabaseManager
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from ml_predictions import PredictionEngine
from models import (
    ApiResponse,
    AuditEntry,
    DishCreate,
    DishResponse,
    DishUpdate,
    IngredientCreate,
    IngredientResponse,
    KitchenTicketResponse,
    OfflineOrder,
    OrderCreate,
    OrderResponse,
    OrderStatusUpdate,
    PaymentCreate,
    PaymentResponse,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    QuantityUpdate,
    SalesData,
    StockCountCreate,
    SupplierCreate,
    SupplierResponse,
    UserCreate,
    UserResponse,
    VarianceReport,
    VarianceReportEntry,
    WasteCreate,
)

# ----------------------------------------------------------------------------
# Globals
# ----------------------------------------------------------------------------
db_manager: DatabaseManager | None = None
prediction_engine: PredictionEngine | None = None

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Lifespan: initialise but DO NOT start any background work in the API process.
# ----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_manager, prediction_engine
    logger.info("Starting RestaurantOS API...")
    db_manager = DatabaseManager()
    logger.info("Database initialised at %s", db_manager.db_path)
    try:
        prediction_engine = PredictionEngine(db_manager)
        logger.info("Prediction engine initialised (idle — worker will drive jobs)")
    except Exception as e:  # prophet is heavy; allow API to boot even if it fails
        logger.warning("Prediction engine init failed: %s. Predictions disabled.", e)
        prediction_engine = None
    yield
    logger.info("Stopping RestaurantOS API...")


app = FastAPI(
    title="RestaurantOS API",
    description="Restaurant management system with inventory intelligence.",
    version="0.2.0",
    lifespan=lifespan,
)

# Install global error handlers FIRST so they wrap the rest of the app.
install_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# Dependencies
# ----------------------------------------------------------------------------
def get_db() -> DatabaseManager:
    if db_manager is None:
        raise HTTPException(status_code=503, detail="Database not initialised")
    return db_manager


def get_prediction_engine() -> PredictionEngine | None:
    """Phase 2: the engine is best-effort. Returning None lets the
    route decide whether to emit a degraded result instead of failing."""
    return prediction_engine


# ----------------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------------
@app.get("/api/health")
async def health(db: DatabaseManager = Depends(get_db)):
    """Real health check — verifies the database is reachable.

    Always returns a JSONResponse so the status code is reliable:
      * 200 + status="ok" when DB is reachable
      * 503 + status="degraded" otherwise (with an error_id for support)
    """
    db_ok = True
    db_error: str | None = None
    try:
        conn = db.get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except Exception as e:
        db_ok = False
        db_error = new_error_id()
        logger.error("DB health check failed id=%s: %s", db_error, e)

    body = {
        "success": db_ok,
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "ts": datetime.now().isoformat(),
    }
    if not db_ok:
        body["error_id"] = db_error
    return JSONResponse(status_code=200 if db_ok else 503, content=body)


# ----------------------------------------------------------------------------
# Dishes
# ----------------------------------------------------------------------------
@app.get("/api/dishes", response_model=ApiResponse[list[DishResponse]])
async def get_dishes(db: DatabaseManager = Depends(get_db)):
    return ApiResponse(success=True, data=db.get_dishes())


@app.post("/api/dishes", response_model=ApiResponse[DishResponse], status_code=201)
async def create_dish(dish: DishCreate, db: DatabaseManager = Depends(get_db)):
    dish_id = db.create_dish(dish.model_dump())
    created = db.get_dish_by_id(dish_id)
    return ApiResponse(success=True, data=created)


@app.put("/api/dishes/{dish_id}", response_model=ApiResponse[DishResponse])
async def update_dish(dish_id: str, dish: DishUpdate, db: DatabaseManager = Depends(get_db)):
    updated = db.update_dish(dish_id, dish.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Dish not found")
    return ApiResponse(success=True, data=db.get_dish_by_id(dish_id))


@app.delete("/api/dishes/{dish_id}", response_model=ApiResponse[dict])
async def delete_dish(dish_id: str, db: DatabaseManager = Depends(get_db)):
    if not db.delete_dish(dish_id):
        raise HTTPException(status_code=404, detail="Dish not found")
    return ApiResponse(success=True, data={"message": "Dish deleted"})


# ----------------------------------------------------------------------------
# Ingredients
# ----------------------------------------------------------------------------
@app.get("/api/ingredients", response_model=ApiResponse[list[IngredientResponse]])
async def get_ingredients(db: DatabaseManager = Depends(get_db)):
    return ApiResponse(success=True, data=db.get_ingredients())


@app.post("/api/ingredients", response_model=ApiResponse[IngredientResponse], status_code=201)
async def create_ingredient(ingredient: IngredientCreate, db: DatabaseManager = Depends(get_db)):
    ing_id = db.create_ingredient(ingredient.model_dump())
    return ApiResponse(success=True, data=db.get_ingredient_by_id(ing_id))


@app.put(
    "/api/ingredients/{ingredient_id}/quantity", response_model=ApiResponse[IngredientResponse]
)
async def update_ingredient_quantity(
    ingredient_id: str,
    quantity_update: QuantityUpdate,
    db: DatabaseManager = Depends(get_db),
):
    """Set the absolute quantity. The DELTA is recorded in the ledger."""
    existing = db.get_ingredient_by_id(ingredient_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    try:
        db.update_ingredient_quantity(ingredient_id, quantity_update.quantity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ApiResponse(success=True, data=db.get_ingredient_by_id(ingredient_id))


# ----------------------------------------------------------------------------
# Orders
# ----------------------------------------------------------------------------
@app.get("/api/orders", response_model=ApiResponse[list[OrderResponse]])
async def get_orders(
    start_date: str | None = None,
    end_date: str | None = None,
    db: DatabaseManager = Depends(get_db),
):
    return ApiResponse(success=True, data=db.get_orders(start_date, end_date))


@app.post("/api/orders")
async def create_order(
    order: OrderCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: DatabaseManager = Depends(get_db),
):
    """Create an order.

    Prices and totals are computed server-side from the dishes table.
    The client MAY (and SHOULD) send an `Idempotency-Key` header; a
    duplicate request with the same key returns the previously created
    order instead of creating a new one.

    Status codes:
      * 201 — a new order was created
      * 200 — an existing order with this Idempotency-Key was returned
      * 400 — invalid input (unknown dish, invalid quantity, etc.)
      * 409 — insufficient stock for the requested items
    """
    if IDEMPOTENCY_REQUIRED and not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required.",
        )

    if idempotency_key:
        existing = db.get_order_by_idempotency_key(idempotency_key)
        if existing:
            # 200 — we did not create anything, the client is seeing a
            # cached/duplicate response. The body is the original order.
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "data": existing,
                    "idempotent_replay": True,
                },
            )

    try:
        order_id = db.create_order(
            order.model_dump(),
            tax_rate=DEFAULT_TAX_RATE,
            idempotency_key=idempotency_key,
        )
    except ValueError as e:
        msg = str(e)
        if msg.startswith("Insufficient stock"):
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e

    # 201 — newly created
    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "data": db.get_order_by_id(order_id),
            "idempotent_replay": False,
        },
    )


# ----------------------------------------------------------------------------
# Analytics
# ----------------------------------------------------------------------------
@app.get("/api/analytics/sales", response_model=ApiResponse[list[SalesData]])
async def get_sales_data(
    start_date: str,
    end_date: str,
    db: DatabaseManager = Depends(get_db),
):
    return ApiResponse(success=True, data=db.get_sales_data(start_date, end_date))


@app.get("/api/analytics/daily-sales", response_model=ApiResponse[SalesData])
async def get_daily_sales(date: str, db: DatabaseManager = Depends(get_db)):
    sales = db.get_daily_sales(date)
    if not sales:
        raise HTTPException(status_code=404, detail=f"No sales data for {date}")
    return ApiResponse(success=True, data=sales)


# ----------------------------------------------------------------------------
# Predictions
# ----------------------------------------------------------------------------
@app.get("/api/predictions")
async def get_predictions(
    date: str,
    db: DatabaseManager = Depends(get_db),
    engine: PredictionEngine | None = Depends(get_prediction_engine),
):
    """Return structured predictions for the given date.

    Phase 2: each prediction includes the model that produced it, a
    realistic range, data sufficiency, and a human-readable reason.
    The endpoint does NOT raise 503 when Prophet is unavailable —
    baselines always run.
    """
    try:
        from ml_predictions import _PROPHET_AVAILABLE  # noqa: WPS433
    except Exception:
        _PROPHET_AVAILABLE = False

    if engine is None:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": [],
                "prophet_available": False,
                "count": 0,
                "warning": "Prediction engine not initialised",
            },
        )

    rows = engine.get_structured_predictions(date)
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": rows,
            "prophet_available": bool(_PROPHET_AVAILABLE),
            "count": len(rows),
        },
    )


@app.get("/api/predictions/status")
async def predictions_status():
    """Report the prediction engine's capability without exposing internals."""
    try:
        from ml_predictions import _PROPHET_AVAILABLE  # noqa: WPS433
    except Exception:
        _PROPHET_AVAILABLE = False
    return {
        "success": True,
        "data": {
            "prophet_available": bool(_PROPHET_AVAILABLE),
            "models_trained": 3,  # the three baselines are always trained
        },
    }


# ----------------------------------------------------------------------------
# Phase 2: prep plans + purchase recommendations
# ----------------------------------------------------------------------------


@app.get("/api/prep-plan")
async def get_prep_plan(
    date: str,
    db: DatabaseManager = Depends(get_db),
    engine: PredictionEngine | None = Depends(get_prediction_engine),
):
    """Recommended prep quantities per dish for a given date.

    Wraps the structured predictions and adds the dish's recipe
    (ingredients needed) so the kitchen knows what to pull.
    """
    if engine is None:
        return JSONResponse(
            status_code=200,
            content={"success": True, "data": [], "warning": "Prediction engine not initialised"},
        )

    preds = engine.get_structured_predictions(date)
    dishes = {d["id"]: d for d in db.get_dishes()}
    out = []
    for p in preds:
        dish = dishes.get(p["dish_id"])
        if not dish:
            continue
        out.append(
            {
                "dish_id": p["dish_id"],
                "dish_name": p["dish_name"],
                "period": p["period"],
                "predicted_demand": p["predicted_demand"],
                "recommended_prep": p["recommended_prep"],
                "low": p["low"],
                "high": p["high"],
                "model_used": p["model_used"],
                "model_confidence": p["model_confidence"],
                "data_sufficiency": p["data_sufficiency"],
                "reason": p["reason"],
                "ingredients_needed": [
                    {
                        "ingredient_id": ing["ingredient_id"],
                        "quantity": ing["quantity"] * p["recommended_prep"],
                        "unit": ing["unit"],
                    }
                    for ing in dish.get("ingredients", [])
                ],
            }
        )
    return JSONResponse(status_code=200, content={"success": True, "data": out})


@app.get("/api/purchase-recommendations")
async def get_purchase_recommendations(
    date: str,
    db: DatabaseManager = Depends(get_db),
    engine: PredictionEngine | None = Depends(get_prediction_engine),
):
    """Sum expected consumption vs current stock; flag ingredients needing reorder."""
    if engine is None:
        return JSONResponse(
            status_code=200,
            content={"success": True, "data": [], "warning": "Prediction engine not initialised"},
        )

    preds = engine.get_structured_predictions(date)
    dishes = {d["id"]: d for d in db.get_dishes()}
    ingredients = {i["id"]: i for i in db.get_ingredients()}

    # Aggregate expected consumption per ingredient.
    needed: dict[str, float] = {}
    for p in preds:
        dish = dishes.get(p["dish_id"])
        if not dish:
            continue
        for ing in dish.get("ingredients", []):
            needed[ing["ingredient_id"]] = (
                needed.get(ing["ingredient_id"], 0.0) + ing["quantity"] * p["recommended_prep"]
            )

    out = []
    for ing_id, qty_needed in needed.items():
        ing = ingredients.get(ing_id)
        if not ing:
            continue
        on_hand = float(ing["quantity_today"])
        shortage = max(0.0, qty_needed - on_hand)
        out.append(
            {
                "ingredient_id": ing_id,
                "ingredient_name": ing["name"],
                "unit": ing["unit"],
                "on_hand": on_hand,
                "needed": round(qty_needed, 2),
                "shortage": round(shortage, 2),
                "needs_reorder": shortage > 0,
                "cost_estimate": round(shortage * float(ing.get("cost_per_unit", 0.0) or 0.0), 2),
            }
        )
    out.sort(key=lambda r: r["shortage"], reverse=True)
    return JSONResponse(status_code=200, content={"success": True, "data": out})


@app.get("/api/predictions/backtest")
async def run_backtest(
    days: int = 90,
    horizon: int = 7,
    db: DatabaseManager = Depends(get_db),
):
    """Walk forward through `days` of history, evaluating each baseline.

    Returns per-(dish, period) winners and an overall per-model summary.
    This is what gives the operator trust in the prediction numbers:
    they can see which model is actually best per dish.
    """
    from datetime import date as _date
    from datetime import timedelta

    from backtest import backtest

    raw = db.get_historical_order_data(days=days)
    if not raw:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "from_date": "",
                    "to_date": "",
                    "by_dish_period": [],
                    "overall": {},
                    "warning": "No historical data yet — place orders first.",
                },
            },
        )

    rows: list[tuple[str, str, str, float]] = [
        (r["dish_id"], r["period"], r["ds"], float(r["y"])) for r in raw
    ]
    end = _date.today()
    start = end - timedelta(days=days)
    report = backtest(
        rows,
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        horizon_days=horizon,
        min_train_size=4,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "from_date": report.from_date,
                "to_date": report.to_date,
                "by_dish_period": report.by_dish_period,
                "overall": report.overall,
            },
        },
    )


# ----------------------------------------------------------------------------
# Phase 1: Order lifecycle, kitchen, inventory ledger, RBAC
# ----------------------------------------------------------------------------

ROLE_ORDER = ["cashier", "kitchen", "inventory", "manager", "owner"]


def _require_role(header_role: str | None, minimum: str) -> str:
    """Minimal role-based gate using the X-User-Role header.

    This is dev-only auth — see PHASES.md 1.6 for the production story.
    Returns the effective role (the header value, or the minimum if no
    header was sent) so we can log it.
    """
    role = (header_role or minimum).lower()
    if ROLE_ORDER.index(role) < ROLE_ORDER.index(minimum):
        raise HTTPException(
            status_code=403,
            detail=f"Requires role '{minimum}' or higher (got '{role}').",
        )
    return role


@app.patch("/api/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    body: OrderStatusUpdate,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    """Move an order along the lifecycle.

    Cancellation is allowed for `cashier` and above; everything else
    needs at least `kitchen` because the kitchen drives PREPARING,
    READY, SERVED, COMPLETED.
    """
    minimum = "cashier" if body.status == "cancelled" else "kitchen"
    _require_role(x_user_role, minimum)
    try:
        updated = db.transition_order_status(order_id, body.status.value)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        if "Illegal transition" in msg:
            raise HTTPException(status_code=409, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    return ApiResponse(success=True, data=updated)


# ---- Kitchen -------------------------------------------------------------


@app.get("/api/kitchen/tickets", response_model=ApiResponse[list[KitchenTicketResponse]])
async def list_kitchen_tickets(
    status: str | None = None,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    """List kitchen tickets. Optional ?status=submitted|accepted|preparing|..."""
    _require_role(x_user_role, "kitchen")
    statuses = [status] if status else None
    return ApiResponse(success=True, data=db.get_kitchen_tickets(statuses))


# ---- Inventory: waste + stock counts + variance --------------------------


@app.post("/api/inventory/waste", response_model=ApiResponse[dict])
async def post_waste(
    body: WasteCreate,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    """Record wastage. Stock is reduced; the ledger records a negative
    consumption-style entry with a reason tag."""
    _require_role(x_user_role, "inventory")
    try:
        updated = db.record_waste(
            body.ingredient_id,
            body.quantity,
            body.reason.value,
            body.notes,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    return ApiResponse(success=True, data=updated)


@app.post("/api/inventory/count", response_model=ApiResponse[dict])
async def post_stock_count(
    body: StockCountCreate,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    """Record a physical stock count and adjust to match."""
    _require_role(x_user_role, "inventory")
    try:
        updated = db.record_stock_count(body.ingredient_id, body.physical_quantity, body.notes)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    return ApiResponse(success=True, data=updated)


@app.get("/api/inventory/variance", response_model=ApiResponse[VarianceReport])
async def get_variance(
    from_date: str,
    to_date: str,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    """Theoretical vs actual usage over a date range."""
    _require_role(x_user_role, "manager")
    rows = db.get_variance_report(from_date, to_date)
    entries = [VarianceReportEntry(**row) for row in rows]
    total_cost = sum(e.cost_impact for e in entries)
    return ApiResponse(
        success=True,
        data=VarianceReport(
            from_date=from_date,
            to_date=to_date,
            entries=entries,
            total_cost_impact=round(total_cost, 2),
        ),
    )


# ---- Users / RBAC --------------------------------------------------------


@app.post("/api/users", response_model=ApiResponse[UserResponse], status_code=201)
async def create_user(body: UserCreate, db: DatabaseManager = Depends(get_db)):
    db.create_user(body.username, body.display_name, body.role.value)
    user = db.get_user_by_username(body.username)
    return ApiResponse(success=True, data=user)


@app.get("/api/users", response_model=ApiResponse[list[UserResponse]])
async def list_users(db: DatabaseManager = Depends(get_db)):
    return ApiResponse(success=True, data=db.list_users())


# ----------------------------------------------------------------------------
# Phase 3: suppliers, purchase orders, payments, offline replay, audit
# ----------------------------------------------------------------------------


# ---- Suppliers + purchase orders --------------------------------------


@app.post("/api/suppliers", response_model=ApiResponse[SupplierResponse], status_code=201)
async def create_supplier(
    body: SupplierCreate,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    _require_role(x_user_role, "manager")
    sid = db.create_supplier(
        body.name,
        contact_name=body.contact_name,
        phone=body.phone,
        email=body.email,
        address=body.address,
    )
    db.write_audit(
        actor=(x_user_role or "system"),
        action="supplier.create",
        entity_type="supplier",
        entity_id=sid,
        payload={"name": body.name},
    )
    return ApiResponse(success=True, data=db.get_supplier(sid))


@app.get("/api/suppliers", response_model=ApiResponse[list[SupplierResponse]])
async def list_suppliers(db: DatabaseManager = Depends(get_db)):
    return ApiResponse(success=True, data=db.list_suppliers())


@app.post(
    "/api/purchase-orders",
    response_model=ApiResponse[PurchaseOrderResponse],
    status_code=201,
)
async def create_purchase_order(
    body: PurchaseOrderCreate,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    _require_role(x_user_role, "inventory")
    if not db.get_supplier(body.supplier_id):
        raise HTTPException(status_code=404, detail="Supplier not found")
    po_id = db.create_purchase_order(
        body.supplier_id,
        [it.model_dump() for it in body.items],
        body.notes,
    )
    db.write_audit(
        actor=(x_user_role or "system"),
        action="purchase_order.create",
        entity_type="purchase_order",
        entity_id=po_id,
        payload={"supplier_id": body.supplier_id, "n_items": len(body.items)},
    )
    return ApiResponse(success=True, data=db.get_purchase_order(po_id))


@app.post(
    "/api/purchase-orders/{po_id}/receive",
    response_model=ApiResponse[PurchaseOrderResponse],
)
async def receive_purchase_order(
    po_id: str,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    _require_role(x_user_role, "inventory")
    try:
        po = db.receive_purchase_order(po_id, actor=x_user_role or "system")
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    db.write_audit(
        actor=(x_user_role or "system"),
        action="purchase_order.receive",
        entity_type="purchase_order",
        entity_id=po_id,
    )
    return ApiResponse(success=True, data=po)


@app.post(
    "/api/purchase-orders/{po_id}/cancel",
    response_model=ApiResponse[PurchaseOrderResponse],
)
async def cancel_purchase_order(
    po_id: str,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    _require_role(x_user_role, "manager")
    result = db.cancel_purchase_order(po_id)
    if result is None:
        raise HTTPException(
            status_code=409,
            detail="Cannot cancel (already received, cancelled, or missing).",
        )
    db.write_audit(
        actor=(x_user_role or "system"),
        action="purchase_order.cancel",
        entity_type="purchase_order",
        entity_id=po_id,
    )
    return ApiResponse(success=True, data=result)


@app.get("/api/purchase-orders", response_model=ApiResponse[list[PurchaseOrderResponse]])
async def list_purchase_orders(
    supplier_id: str | None = None,
    db: DatabaseManager = Depends(get_db),
):
    return ApiResponse(success=True, data=db.list_purchase_orders(supplier_id))


# ---- Payments ---------------------------------------------------------


@app.post("/api/payments", response_model=ApiResponse[PaymentResponse], status_code=201)
async def create_payment(
    body: PaymentCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    _require_role(x_user_role, "cashier")
    if not db.get_order_by_id(body.order_id):
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        payment = db.create_payment(
            body.order_id,
            body.amount,
            body.method,
            body.reference,
            idempotency_key=idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.write_audit(
        actor=(x_user_role or "system"),
        action="payment.create",
        entity_type="payment",
        entity_id=str(payment.get("id", "")),
        payload={
            "order_id": body.order_id,
            "amount": body.amount,
            "method": body.method,
        },
    )
    return ApiResponse(success=True, data=payment)


@app.get("/api/orders/{order_id}/payments", response_model=ApiResponse[list[PaymentResponse]])
async def list_order_payments(order_id: str, db: DatabaseManager = Depends(get_db)):
    if not db.get_order_by_id(order_id):
        raise HTTPException(status_code=404, detail="Order not found")
    return ApiResponse(success=True, data=db.list_payments_for_order(order_id))


# ---- Offline POS replay (idempotent batch) ----------------------------


@app.post("/api/orders/replay-batch", response_model=ApiResponse[dict])
async def replay_offline_batch(
    orders: list[OfflineOrder],
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    """Replay a batch of offline-captured orders.

    Each entry carries its own idempotency_key (the client generates one
    at capture time and persists it). The server deduplicates by key,
    so a network blip that causes the client to retry the whole batch
    cannot create duplicate orders.
    """
    _require_role(x_user_role, "cashier")
    accepted: list[str] = []
    duplicates: list[str] = []
    failed: list[dict[str, str]] = []
    for entry in orders:
        existing = db.get_order_by_idempotency_key(entry.idempotency_key)
        if existing:
            duplicates.append(entry.idempotency_key)
            continue
        try:
            oid = db.create_order(
                {
                    "items": [it.model_dump() for it in entry.items],
                    "payment_method": entry.payment_method,
                    "cashier_id": entry.cashier_id,
                    "customer_id": entry.customer_id,
                },
                tax_rate=DEFAULT_TAX_RATE,
                idempotency_key=entry.idempotency_key,
            )
            accepted.append(oid)
        except ValueError as e:
            failed.append({"idempotency_key": entry.idempotency_key, "detail": str(e)})
    db.write_audit(
        actor=(x_user_role or "system"),
        action="orders.replay_batch",
        entity_type="batch",
        entity_id="offline",
        payload={"accepted": len(accepted), "duplicates": len(duplicates), "failed": len(failed)},
    )
    return ApiResponse(
        success=True,
        data={"accepted": accepted, "duplicates": duplicates, "failed": failed},
    )


# ---- Audit log --------------------------------------------------------


@app.get("/api/audit", response_model=ApiResponse[list[AuditEntry]])
async def get_audit(
    limit: int = 100,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    db: DatabaseManager = Depends(get_db),
):
    _require_role(x_user_role, "owner")
    return ApiResponse(success=True, data=db.list_audit(limit=limit))


# ---- Prometheus-style metrics (Phase 3.9) ----------------------------


@app.get("/metrics")
async def prometheus_metrics(db: DatabaseManager = Depends(get_db)):
    """Tiny /metrics endpoint — enough for a Phase 3 smoke test.

    Real Prometheus exposition format has more required fields; this is
    a deliberately minimal version that documents the counters we care
    about. Operators can plug a richer exporter in Phase 4.
    """
    ingredients = db.get_ingredients()
    orders = db.get_orders()
    low_stock = sum(1 for i in ingredients if i["quantity_today"] <= i["min_threshold"])
    lines = [
        "# HELP restaurantos_ingredients_total Number of tracked ingredients",
        "# TYPE restaurantos_ingredients_total gauge",
        f"restaurantos_ingredients_total {len(ingredients)}",
        "# HELP restaurantos_ingredients_low_stock Ingredients at or below threshold",
        "# TYPE restaurantos_ingredients_low_stock gauge",
        f"restaurantos_ingredients_low_stock {low_stock}",
        "# HELP restaurantos_orders_total Total orders in DB",
        "# TYPE restaurantos_orders_total counter",
        f"restaurantos_orders_total {len(orders)}",
    ]
    return JSONResponse(
        status_code=200,
        content={"success": True, "data": "\n".join(lines) + "\n"},
        media_type="text/plain",
    )


# ----------------------------------------------------------------------------
# Demo mode (only when explicitly enabled in env)
# ----------------------------------------------------------------------------
@app.post("/api/demo/seed")
async def demo_seed(db: DatabaseManager = Depends(get_db)):
    """Insert a labelled demo dataset. Only available when DEMO_MODE is on."""
    if not DEMO_MODE_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")
    # Phase 0 ships a minimal seed; richer demo data lands in Phase 1.
    return ApiResponse(success=True, data={"message": "Demo seed endpoint — see Phase 1."})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
