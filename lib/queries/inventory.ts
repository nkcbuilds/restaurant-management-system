"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "../http"

export const inventoryKeys = {
  all: ["inventory-ledger"] as const,
  waste: () => [...inventoryKeys.all, "waste"] as const,
  variance: (from: string, to: string) => [...inventoryKeys.all, "variance", from, to] as const,
}

export interface VarianceEntry {
  ingredient_id: string
  ingredient_name: string
  expected_stock: number | null
  physical_quantity: number | null
  variance: number | null
  waste_quantity: number
  consumption_quantity: number
  cost_impact: number
}

export interface VarianceReport {
  from_date: string
  to_date: string
  entries: VarianceEntry[]
  total_cost_impact: number
}

export function useVarianceReport(fromDate: string, toDate: string) {
  return useQuery({
    queryKey: inventoryKeys.variance(fromDate, toDate),
    queryFn: () =>
      http.get<VarianceReport>(
        `/api/inventory/variance?from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`,
      ),
    enabled: Boolean(fromDate && toDate),
  })
}

export interface RecordWasteInput {
  ingredient_id: string
  quantity: number
  reason: "spoilage" | "staff_meal" | "customer_complaint" | "prep_error" | "other"
  notes?: string
}

export function useRecordWaste() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: RecordWasteInput) =>
      http.post<Record<string, unknown>>("/api/inventory/waste", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ingredients"] })
      qc.invalidateQueries({ queryKey: inventoryKeys.all })
    },
  })
}

export interface StockCountInput {
  ingredient_id: string
  physical_quantity: number
  notes?: string
}

export function useRecordStockCount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: StockCountInput) =>
      http.post<Record<string, unknown>>("/api/inventory/count", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ingredients"] })
      qc.invalidateQueries({ queryKey: inventoryKeys.all })
    },
  })
}
