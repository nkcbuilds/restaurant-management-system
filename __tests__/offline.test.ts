/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import {
  enqueueOfflineOrder,
  listOfflineOrders,
  clearOfflineOrders,
  replayOfflineOrders,
  type OfflineOrder,
} from "@/lib/offline"

const STORAGE_KEY = "restaurantos:offline_outbox"

function makeOrder(overrides: Partial<OfflineOrder> = {}): OfflineOrder {
  return {
    idempotency_key: overrides.idempotency_key ?? `k-${Math.random()}`,
    captured_at: overrides.captured_at ?? new Date().toISOString(),
    items: overrides.items ?? [{ dish_id: "d1", quantity: 1, price: 0 }],
    payment_method: overrides.payment_method ?? "cash",
    cashier_id: overrides.cashier_id ?? "test",
    customer_id: overrides.customer_id ?? null,
  }
}

describe("offline outbox", () => {
  beforeEach(() => {
    window.localStorage.clear()
    // Mock fetch globally.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(
          JSON.stringify({
            success: true,
            data: { accepted: ["o1"], duplicates: [], failed: [] },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        )
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("stores and retrieves orders", () => {
    enqueueOfflineOrder(makeOrder({ idempotency_key: "k1" }))
    enqueueOfflineOrder(makeOrder({ idempotency_key: "k2" }))
    const all = listOfflineOrders()
    expect(all).toHaveLength(2)
    expect(all.map((o) => o.idempotency_key).sort()).toEqual(["k1", "k2"])
  })

  it("clearOfflineOrders empties the outbox", () => {
    enqueueOfflineOrder(makeOrder({ idempotency_key: "k1" }))
    expect(listOfflineOrders()).toHaveLength(1)
    clearOfflineOrders()
    expect(listOfflineOrders()).toHaveLength(0)
  })

  it("replayOfflineOrders posts the batch and clears consumed keys", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(
          JSON.stringify({
            success: true,
            data: { accepted: ["k1", "k2"], duplicates: [], failed: [] },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        )
      }),
    )
    enqueueOfflineOrder(makeOrder({ idempotency_key: "k1" }))
    enqueueOfflineOrder(makeOrder({ idempotency_key: "k2" }))
    const result = await replayOfflineOrders()
    expect(result.accepted).toEqual(["k1", "k2"])
    expect(listOfflineOrders()).toHaveLength(0)

    // fetch must have been called once with both orders in the body.
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const callArgs = fetchMock.mock.calls[0]
    expect(callArgs).toBeDefined()
    const init = callArgs?.[1] as RequestInit | undefined
    const body = JSON.parse(String(init?.body ?? "[]"))
    expect(body).toHaveLength(2)
  })

  it("replayOfflineOrders keeps unconfirmed orders for retry", async () => {
    enqueueOfflineOrder(makeOrder({ idempotency_key: "k1" }))
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(
          JSON.stringify({
            success: true,
            data: { accepted: ["k1"], duplicates: [], failed: [] },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        )
      }),
    )
    const result = await replayOfflineOrders()
    expect(result.accepted).toEqual(["k1"])
    expect(listOfflineOrders()).toHaveLength(0)
  })

  it("replayOfflineOrders does nothing for an empty outbox", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>
    fetchMock.mockClear()
    const result = await replayOfflineOrders()
    expect(result.accepted).toEqual([])
    expect(result.duplicates).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("replayOfflineOrders throws on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("boom", { status: 500 })),
    )
    enqueueOfflineOrder(makeOrder({ idempotency_key: "k1" }))
    await expect(replayOfflineOrders()).rejects.toThrow(/Replay failed/)
    // The order stays in the outbox for the next attempt.
    expect(listOfflineOrders()).toHaveLength(1)
  })

  it("uses the documented storage key", () => {
    expect(STORAGE_KEY).toBe("restaurantos:offline_outbox")
  })
})
