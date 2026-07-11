"use client"

import { useQuery } from "@tanstack/react-query"
import { http } from "../http"

export const predictionKeys = {
  all: ["predictions"] as const,
  list: (date: string) => [...predictionKeys.all, "list", date] as const,
  status: () => [...predictionKeys.all, "status"] as const,
  backtest: (days: number, horizon: number) =>
    [...predictionKeys.all, "backtest", days, horizon] as const,
  prepPlan: (date: string) => [...predictionKeys.all, "prep-plan", date] as const,
  purchase: (date: string) => [...predictionKeys.all, "purchase", date] as const,
}

export interface BaselineOutput {
  model: string
  point: number
  low: number
  high: number
  confidence: number
  data_sufficiency: "insufficient" | "low" | "ok" | "strong"
}

export interface Prediction {
  dish_id: string
  dish_name: string
  period: "morning" | "afternoon" | "evening" | string
  predicted_demand: number
  low: number
  high: number
  recommended_prep: number
  model_used: string
  model_confidence: number
  data_sufficiency: "insufficient" | "low" | "ok" | "strong"
  reason: string
  all_baselines: BaselineOutput[]
  prediction_date: string
}

export function usePredictions(date: string) {
  return useQuery({
    queryKey: predictionKeys.list(date),
    queryFn: () => http.get<Prediction[]>(`/api/predictions?date=${encodeURIComponent(date)}`),
  })
}

export interface PredictionStatus {
  prophet_available: boolean
  models_trained: number
}

export function usePredictionStatus() {
  return useQuery({
    queryKey: predictionKeys.status(),
    queryFn: () => http.get<PredictionStatus>("/api/predictions/status"),
  })
}

export interface BacktestWinner {
  dish_id: string
  period: string
  winner_model: string | null
  models: Record<
    string,
    { mae: number; wape: number; bias: number; stockout_rate: number; waste: number; n: number }
  >
}

export interface BacktestReport {
  from_date: string
  to_date: string
  by_dish_period: BacktestWinner[]
  overall: Record<string, { n: number; mae: number; wape: number; bias: number; waste: number }>
  warning?: string
}

export function useBacktest(days = 90, horizon = 7) {
  return useQuery({
    queryKey: predictionKeys.backtest(days, horizon),
    queryFn: () => http.get<BacktestReport>(`/api/predictions/backtest?days=${days}&horizon=${horizon}`),
    refetchInterval: 5 * 60_000, // 5 min
  })
}

export interface PrepIngredientNeed {
  ingredient_id: string
  quantity: number
  unit: string
}

export interface PrepPlanEntry {
  dish_id: string
  dish_name: string
  period: string
  predicted_demand: number
  recommended_prep: number
  low: number
  high: number
  model_used: string
  model_confidence: number
  data_sufficiency: "insufficient" | "low" | "ok" | "strong"
  reason: string
  ingredients_needed: PrepIngredientNeed[]
}

export function usePrepPlan(date: string) {
  return useQuery({
    queryKey: predictionKeys.prepPlan(date),
    queryFn: () => http.get<PrepPlanEntry[]>(`/api/prep-plan?date=${encodeURIComponent(date)}`),
  })
}

export interface PurchaseRecommendation {
  ingredient_id: string
  ingredient_name: string
  unit: string
  on_hand: number
  needed: number
  shortage: number
  needs_reorder: boolean
  cost_estimate: number
}

export function usePurchaseRecommendations(date: string) {
  return useQuery({
    queryKey: predictionKeys.purchase(date),
    queryFn: () =>
      http.get<PurchaseRecommendation[]>(
        `/api/purchase-recommendations?date=${encodeURIComponent(date)}`,
      ),
  })
}
