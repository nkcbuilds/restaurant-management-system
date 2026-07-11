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
    DishCreate,
    DishResponse,
    DishUpdate,
    IngredientCreate,
    IngredientResponse,
    OrderCreate,
    OrderResponse,
    QuantityUpdate,
    SalesData,
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


def get_prediction_engine() -> PredictionEngine:
    if prediction_engine is None:
        raise HTTPException(status_code=503, detail="Prediction engine not available")
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
async def get_predictions(date: str, db: DatabaseManager = Depends(get_db)):
    """Return stored predictions for the given date.

    The endpoint does NOT raise 503 when Prophet is unavailable — it
    returns an empty list with `prophet_available: false` so the client
    can render an honest "no predictions yet" state instead of crashing.
    A separate `GET /api/predictions/status` reports engine capability.
    """
    try:
        from ml_predictions import _PROPHET_AVAILABLE  # noqa: WPS433
    except Exception:
        _PROPHET_AVAILABLE = False

    rows = db.get_predictions(date)
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
            "models_trained": 0,  # populated by the worker; placeholder for Phase 0
        },
    }


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
