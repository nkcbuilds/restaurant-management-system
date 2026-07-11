"use client"

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "../http"
import type { OrderItem } from "../types"

export interface KitchenTicketItem extends OrderItem {
  dish_name?: string
  category?: string
}

export interface KitchenTicket {
  id: number
  order_id: string
  status: string
  station: string | null
  items: KitchenTicketItem[]
  created_at: string
  updated_at: string
}

export const kitchenKeys = {
  all: ["kitchen"] as const,
  tickets: (status?: string) => [...kitchenKeys.all, "tickets", status ?? "all"] as const,
}

export function useKitchenTickets(status?: string) {
  const path = status ? `/api/kitchen/tickets?status=${encodeURIComponent(status)}` : "/api/kitchen/tickets"
  return useQuery({
    queryKey: kitchenKeys.tickets(status),
    queryFn: () => http.get<KitchenTicket[]>(path),
    // Kitchen display should refresh every 10s in addition to on-focus.
    refetchInterval: 10_000,
  })
}

export function useInvalidateKitchen() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: kitchenKeys.all })
}
