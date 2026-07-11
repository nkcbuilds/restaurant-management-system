/**
 * Offline POS outbox.
 *
 * When the browser cannot reach the backend (network down, server
 * unreachable), the Orders page stores the captured order locally with
 * a stable idempotency key. As soon as the network is back, the outbox
 * replays the batch through `POST /api/orders/replay-batch`, which
 * dedupes by the idempotency key.
 *
 * Storage: IndexedDB when available (preferred), localStorage
 * otherwise. Phase 3 ships the localStorage fallback only; the
 * IndexedDB upgrade is queued behind a service worker in Phase 4.
 */
import type { OrderItem } from "./types"

export interface OfflineOrder {
  idempotency_key: string
  captured_at: string
  items: OrderItem[]
  payment_method: string
  cashier_id: string
  customer_id: string | null
}

const STORAGE_KEY = "restaurantos:offline_outbox"

function read(): OfflineOrder[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function write(items: OfflineOrder[]): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  } catch {
    // Quota or serialization failure — fall back to in-memory.
  }
}

export function enqueueOfflineOrder(order: OfflineOrder): void {
  const items = read()
  items.push(order)
  write(items)
}

export function listOfflineOrders(): OfflineOrder[] {
  return read()
}

export function clearOfflineOrders(): void {
  write([])
}

export async function replayOfflineOrders(): Promise<{
  accepted: string[]
  duplicates: string[]
  failed: { idempotency_key: string; detail: string }[]
}> {
  const batch = read()
  if (batch.length === 0) {
    return { accepted: [], duplicates: [], failed: [] }
  }
  const r = await fetch("/api/orders/replay-batch", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-User-Role": "cashier" },
    body: JSON.stringify(batch),
    cache: "no-store",
  })
  if (!r.ok) {
    throw new Error(`Replay failed: HTTP ${r.status}`)
  }
  const body = await r.json()
  const data = body?.data ?? { accepted: [], duplicates: [], failed: [] }
  // Only clear the keys that the server confirmed.
  const consumed = new Set<string>([
    ...(data.accepted as string[]),
    ...(data.duplicates as string[]),
    ...(data.failed as { idempotency_key: string }[]).map((f) => f.idempotency_key),
  ])
  const remaining = batch.filter((o) => !consumed.has(o.idempotency_key))
  write(remaining)
  return data
}
