/**
 * Domain types mirroring the FastAPI Pydantic models in backend/models.py.
 *
 * Keep this file hand-written for Phase 0; Phase 1 introduces an
 * `openapi-typescript` generation step so the source of truth lives on
 * the backend.
 */
export type UUID = string

export interface SubIngredient {
  name: string
  description?: string | null
  preparation_method?: string | null
  cooking_time?: number | null
  temperature?: string | null
  notes?: string | null
}

export interface DishIngredient {
  ingredient_id: UUID
  quantity: number
  unit: string
  sub_ingredient?: SubIngredient | null
}

export interface Dish {
  id: UUID
  name: string
  price: number
  category: string
  description?: string | null
  preparation_time?: number | null
  difficulty_level?: string | null
  is_active: boolean
  ingredients: DishIngredient[]
  is_demo?: boolean
  created_at: string
  updated_at: string
}

export interface Ingredient {
  id: UUID
  name: string
  unit: string
  quantity_today: number
  min_threshold: number
  cost_per_unit: number
  supplier?: string | null
  is_demo?: boolean
  created_at: string
  updated_at: string
}

export interface OrderItem {
  dish_id: UUID
  quantity: number
  price: number
  notes?: string | null
}

export type OrderStatus =
  | "pending"
  | "submitted"
  | "accepted"
  | "preparing"
  | "ready"
  | "served"
  | "completed"
  | "cancelled"

export interface Order {
  id: UUID
  items: OrderItem[]
  subtotal: number
  tax: number
  total: number
  timestamp: string
  status: OrderStatus
  payment_method: string
  customer_id?: string | null
  cashier_id: string
}

export interface PeriodData {
  orders: number
  revenue: number
  avg_order: number
}

export interface SalesData {
  date: string
  morning: PeriodData
  afternoon: PeriodData
  evening: PeriodData
  total: PeriodData
}

export interface Prediction {
  dish_id: UUID
  dish_name: string
  period: "morning" | "afternoon" | "evening"
  predicted_demand: number
  confidence: number
  recommended_prep: number
  factors: string[]
  prediction_date: string
}
