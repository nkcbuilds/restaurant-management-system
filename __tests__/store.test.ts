import { describe, expect, it, beforeEach } from "vitest"
import { useUIStore } from "@/lib/store"

/**
 * The cart lives in the Zustand UI store. It is intentionally the only
 * piece of order-shaped state still in Zustand — the actual order
 * submission goes through TanStack Query.
 */
describe("ui store cart", () => {
  beforeEach(() => {
    useUIStore.setState({ cart: [], categoryFilter: null })
  })

  it("adds a new item", () => {
    useUIStore.getState().addToCart("dish-1", 1)
    expect(useUIStore.getState().cart).toEqual([{ dish_id: "dish-1", quantity: 1 }])
  })

  it("increments an existing item", () => {
    useUIStore.getState().addToCart("dish-1", 1)
    useUIStore.getState().addToCart("dish-1", 1)
    useUIStore.getState().addToCart("dish-1", 1)
    expect(useUIStore.getState().cart).toEqual([{ dish_id: "dish-1", quantity: 3 }])
  })

  it("removes an item when the cart quantity drops to zero", () => {
    useUIStore.getState().addToCart("dish-1", 1)
    useUIStore.getState().addToCart("dish-1", -1)
    expect(useUIStore.getState().cart).toEqual([])
  })

  it("removes an item via removeFromCart", () => {
    useUIStore.getState().addToCart("dish-1", 1)
    useUIStore.getState().addToCart("dish-2", 1)
    useUIStore.getState().removeFromCart("dish-1")
    expect(useUIStore.getState().cart).toEqual([{ dish_id: "dish-2", quantity: 1 }])
  })

  it("clears the entire cart", () => {
    useUIStore.getState().addToCart("dish-1", 1)
    useUIStore.getState().addToCart("dish-2", 2)
    useUIStore.getState().clearCart()
    expect(useUIStore.getState().cart).toEqual([])
  })

  it("ignores adding a non-positive delta to a new item", () => {
    useUIStore.getState().addToCart("dish-1", 0)
    useUIStore.getState().addToCart("dish-1", -3)
    expect(useUIStore.getState().cart).toEqual([])
  })
})
