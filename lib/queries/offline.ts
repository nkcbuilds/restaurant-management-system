"use client"

import { useCallback, useEffect, useState } from "react"
import {
  clearOfflineOrders,
  enqueueOfflineOrder,
  listOfflineOrders,
  replayOfflineOrders,
  type OfflineOrder,
} from "@/lib/offline"
import type { OrderItem } from "@/lib/types"

export interface OfflineQueueState {
  pending: OfflineOrder[]
  isReplaying: boolean
  lastResult: {
    accepted: string[]
    duplicates: string[]
    failed: { idempotency_key: string; detail: string }[]
  } | null
  lastError: string | null
}

/**
 * React hook around the offline outbox (Phase 3.6).
 *
 *  * `queue(...)` captures an order locally instead of posting it.
 *  * `flush()` replays the entire batch through the backend.
 *  * `clear()` empties the outbox (debug / dev tooling).
 *
 * The hook also auto-flushes whenever the browser regains network
 * connectivity.
 */
export function useOfflineQueue(): {
  state: OfflineQueueState
  queue: (input: {
    items: OrderItem[]
    payment_method: string
    cashier_id: string
    customer_id?: string | null
  }) => OfflineOrder
  flush: () => Promise<void>
  clear: () => void
} {
  const [state, setState] = useState<OfflineQueueState>({
    pending: [],
    isReplaying: false,
    lastResult: null,
    lastError: null,
  })

  // Initial load + listener for cross-tab updates.
  useEffect(() => {
    setState((s) => ({ ...s, pending: listOfflineOrders() }))
    const onStorage = (e: StorageEvent) => {
      if (e.key === "restaurantos:offline_outbox") {
        setState((s) => ({ ...s, pending: listOfflineOrders() }))
      }
    }
    window.addEventListener("storage", onStorage)
    return () => window.removeEventListener("storage", onStorage)
  }, [])

  const doFlush = useCallback(async () => {
    setState((s) => ({ ...s, isReplaying: true, lastError: null }))
    try {
      const result = await replayOfflineOrders()
      setState((s) => ({
        ...s,
        isReplaying: false,
        lastResult: result,
        pending: listOfflineOrders(),
      }))
    } catch (e) {
      setState((s) => ({
        ...s,
        isReplaying: false,
        lastError: e instanceof Error ? e.message : String(e),
      }))
    }
  }, [])

  // Auto-flush when the network comes back.
  useEffect(() => {
    if (typeof window === "undefined") return
    const onOnline = () => {
      void doFlush()
    }
    window.addEventListener("online", onOnline)
    return () => window.removeEventListener("online", onOnline)
  }, [doFlush])

  const queue = useCallback(
    (input: {
      items: OrderItem[]
      payment_method: string
      cashier_id: string
      customer_id?: string | null
    }): OfflineOrder => {
      const entry: OfflineOrder = {
        idempotency_key:
          typeof crypto !== "undefined" && "randomUUID" in crypto
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        captured_at: new Date().toISOString(),
        items: input.items,
        payment_method: input.payment_method,
        cashier_id: input.cashier_id,
        customer_id: input.customer_id ?? null,
      }
      enqueueOfflineOrder(entry)
      setState((s) => ({ ...s, pending: [...listOfflineOrders()] }))
      return entry
    },
    [],
  )

  const flush = doFlush

  const clear = useCallback(() => {
    clearOfflineOrders()
    setState((s) => ({ ...s, pending: [] }))
  }, [])

  return { state, queue, flush, clear }
}
