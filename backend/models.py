from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Generic API response model"""

    success: bool
    data: T | None = None
    error: str | None = None


class OrderStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TransactionType(str, Enum):
    USAGE = "usage"
    RESTOCK = "restock"
    ADJUSTMENT = "adjustment"


class TimePeriod(str, Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


# Ingredient models
class SubIngredient(BaseModel):
    """Sub-ingredient model for combined ingredient states"""

    name: str
    description: str | None = None
    preparation_method: str | None = None
    cooking_time: int | None = None  # in minutes
    temperature: str | None = None
    notes: str | None = None


class DishIngredient(BaseModel):
    ingredient_id: str
    quantity: float
    unit: str
    sub_ingredient: SubIngredient | None = None


class IngredientBase(BaseModel):
    name: str
    unit: str
    cost_per_unit: float | None = 0.0
    supplier: str | None = None


class IngredientCreate(IngredientBase):
    quantity_today: float = 0
    min_threshold: float = 0


class IngredientUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    quantity_today: float | None = None
    min_threshold: float | None = None
    cost_per_unit: float | None = None
    supplier: str | None = None


class IngredientResponse(IngredientBase):
    id: str
    quantity_today: float
    min_threshold: float
    created_at: datetime
    updated_at: datetime


class QuantityUpdate(BaseModel):
    quantity: float


# Dish models
class DishBase(BaseModel):
    name: str
    price: float
    category: str
    description: str | None = None
    preparation_time: int | None = None  # in minutes
    difficulty_level: str | None = None


class DishCreate(DishBase):
    ingredients: list[DishIngredient] = []


class DishUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    category: str | None = None
    description: str | None = None
    preparation_time: int | None = None
    difficulty_level: str | None = None
    ingredients: list[DishIngredient] | None = None
    is_active: bool | None = None


class DishResponse(DishBase):
    id: str
    ingredients: list[DishIngredient]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# Order models
class OrderItem(BaseModel):
    dish_id: str
    quantity: int
    price: float
    notes: str | None = None


class OrderBase(BaseModel):
    payment_method: str
    customer_id: str | None = None
    cashier_id: str


class OrderCreate(OrderBase):
    items: list[OrderItem]
    # The client may send these, but the server recomputes them from the
    # authoritative dish prices. They are kept in the model so a client
    # that does send them gets a 200 (the values are simply ignored).
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None


class OrderResponse(OrderBase):
    id: str
    items: list[OrderItem]
    subtotal: float
    tax: float
    total: float
    timestamp: datetime
    status: OrderStatus


# Analytics models
class PeriodData(BaseModel):
    orders: int
    revenue: float
    avg_order: float


class SalesData(BaseModel):
    date: str
    morning: PeriodData
    afternoon: PeriodData
    evening: PeriodData
    total: PeriodData


# Prediction models
class PredictionData(BaseModel):
    dish_id: str
    dish_name: str
    period: TimePeriod
    predicted_demand: int
    confidence: float
    recommended_prep: int
    factors: list[str]
    prediction_date: str


class InventoryTransaction(BaseModel):
    id: int
    ingredient_id: str
    transaction_type: TransactionType
    quantity_change: float
    reference_id: str | None = None
    notes: str | None = None
    timestamp: datetime


# System models
class SyncStatus(BaseModel):
    last_sync: datetime | None = None
    is_running: bool = False
    records_synced: dict[str, int] = {}
    errors: list[str] = []
