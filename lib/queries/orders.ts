"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "../http"
import type { Order, OrderItem, OrderStatus } from "../types"

export const orderKeys = {
  all: ["orders"] as const,
  list: (start?: string, end?: string) =>
    [...orderKeys.all, "list", { start: start ?? null, end: end ?? null }] as const,
  detail: (id: string) => [...orderKeys.all, "detail", id] as const,
}

export function useOrders(startDate?: string, endDate?: string) {
  const params = new URLSearchParams()
  if (startDate) params.set("start_date", startDate)
  if (endDate) params.set("end_date", endDate)
  const path = `/api/orders${params.toString() ? `?${params.toString()}` : ""}`
  return useQuery({
    queryKey: orderKeys.list(startDate, endDate),
    queryFn: () => http.get<Order[]>(path),
  })
}

export interface PlaceOrderInput {
  items: OrderItem[]
  payment_method: string
  cashier_id: string
  customer_id?: string | null
}

/**
 * Place an order. Generates an Idempotency-Key per submission so a
 * double-click or a flaky network cannot create two orders. The server
 * stores the key in `orders.idempotency_key` and returns the original
 * order on duplicates.
 */
export function usePlaceOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (input: PlaceOrderInput) => {
      const key = crypto.randomUUID()
      return http.post<Order>("/api/orders", input, { "Idempotency-Key": key })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: orderKeys.all })
      qc.invalidateQueries({ queryKey: ["ingredients"] })
      qc.invalidateQueries({ queryKey: ["dishes"] })
    },
  })
}

/**
 * Move an order through its lifecycle (accepted -> preparing -> ready
 * -> served -> completed, or -> cancelled). Invalid transitions return
 * 409 from the server and surface as an `ApiError`.
 */
export function useTransitionOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: OrderStatus }) =>
      http.patch<Order>(`/api/orders/${id}/status`, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: orderKeys.all })
      qc.invalidateQueries({ queryKey: ["kitchen"] })
    },
  })
}
