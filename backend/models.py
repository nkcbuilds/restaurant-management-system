from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Generic API response model"""

    success: bool
    data: T | None = None
    error: str | None = None


class OrderStatus(str, Enum):
    """Order lifecycle.

    Linear flow:
        DRAFT -> SUBMITTED -> ACCEPTED -> PREPARING -> READY -> SERVED -> COMPLETED

    Plus a terminal CANCELLED state reachable from DRAFT/SUBMITTED/ACCEPTED
    depending on the restaurant's cancellation policy (see
    `reverse_on_cancel` in core config).
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    READY = "ready"
    SERVED = "served"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Allowed forward transitions. Backwards moves (e.g. PREPARING -> ACCEPTED)
# are not allowed by this map; an idempotent re-assert of the same state
# is always permitted (see `is_valid_transition`).
ORDER_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "cancelled"},
    "submitted": {"accepted", "cancelled"},
    "accepted": {"preparing", "cancelled"},
    "preparing": {"ready", "cancelled"},
    "ready": {"served"},
    "served": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Return True if `from_status -> to_status` is a legal lifecycle move."""
    if from_status == to_status:
        return True  # idempotent re-asserts are fine
    return to_status in ORDER_STATUS_TRANSITIONS.get(from_status, set())


class TransactionType(str, Enum):
    """Inventory ledger transaction kinds."""

    OPENING = "opening"
    PURCHASE = "purchase"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    CONSUMPTION = "consumption"  # alias for the legacy 'usage' value
    USAGE = "usage"  # kept for backwards compatibility with the existing ledger
    WASTE = "waste"
    ADJUSTMENT = "adjustment"
    PHYSICAL_COUNT = "physical_count"


class WasteReason(str, Enum):
    SPOILAGE = "spoilage"
    STAFF_MEAL = "staff_meal"
    CUSTOMER_COMPLAINT = "customer_complaint"
    PREP_ERROR = "prep_error"
    OTHER = "other"


class UserRole(str, Enum):
    OWNER = "owner"
    MANAGER = "manager"
    CASHIER = "cashier"
    KITCHEN = "kitchen"
    INVENTORY = "inventory"


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


class OrderStatusUpdate(BaseModel):
    """PATCH /api/orders/{id}/status body."""

    status: OrderStatus
    notes: str | None = None


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


class WasteCreate(BaseModel):
    ingredient_id: str
    quantity: float  # positive; the ledger records -quantity
    reason: WasteReason = WasteReason.OTHER
    notes: str | None = None


class StockCountCreate(BaseModel):
    ingredient_id: str
    physical_quantity: float
    notes: str | None = None


class VarianceReportEntry(BaseModel):
    ingredient_id: str
    ingredient_name: str
    expected_stock: float | None = None
    physical_quantity: float | None = None
    variance: float | None = None  # physical - expected (positive = overage)
    waste_quantity: float
    consumption_quantity: float
    cost_impact: float


class VarianceReport(BaseModel):
    from_date: str
    to_date: str
    entries: list[VarianceReportEntry]
    total_cost_impact: float


class UserCreate(BaseModel):
    username: str
    display_name: str
    role: UserRole = UserRole.CASHIER


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    created_at: datetime


class KitchenTicketResponse(BaseModel):
    id: int
    order_id: str
    status: str  # mirrors the underlying order status for now
    station: str | None = None
    items: list[OrderItem]
    created_at: datetime
    updated_at: datetime


# ---- Phase 3: suppliers, POs, payments, audit, metrics ------------------


class SupplierBase(BaseModel):
    name: str
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None


class SupplierCreate(SupplierBase):
    pass


class SupplierResponse(SupplierBase):
    id: str
    is_active: bool
    created_at: datetime


class PurchaseOrderItem(BaseModel):
    ingredient_id: str
    quantity: float
    unit_cost: float


class PurchaseOrderCreate(BaseModel):
    supplier_id: str
    items: list[PurchaseOrderItem]
    notes: str | None = None


class PurchaseOrderResponse(BaseModel):
    id: str
    supplier_id: str
    status: str  # 'draft' | 'sent' | 'received' | 'cancelled'
    items: list[PurchaseOrderItem]
    total: float
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PaymentCreate(BaseModel):
    order_id: str
    amount: float
    method: str  # 'cash' | 'card' | 'upi' | 'other'
    reference: str | None = None


class PaymentResponse(BaseModel):
    id: int
    order_id: str
    amount: float
    method: str
    reference: str | None
    status: str  # 'pending' | 'completed' | 'failed'
    created_at: datetime


class OfflineOrder(BaseModel):
    """A single offline-captured order that the POS will replay later.

    The browser fills the same shape it would send to /api/orders and
    tags it with a client-side `captured_at` so duplicates can be
    detected on replay.
    """

    idempotency_key: str
    captured_at: str
    items: list[OrderItem]
    payment_method: str
    cashier_id: str
    customer_id: str | None = None


class AuditEntry(BaseModel):
    id: int
    actor: str  # user id or "system"
    action: str  # 'order.create', 'order.cancel', etc.
    entity_type: str  # 'order', 'dish', etc.
    entity_id: str
    payload: dict[str, Any] | None = None
    created_at: datetime


# System models
class SyncStatus(BaseModel):
    last_sync: datetime | None = None
    is_running: bool = False
    records_synced: dict[str, int] = {}
    errors: list[str] = []
