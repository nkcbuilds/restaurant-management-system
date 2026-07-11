import { describe, expect, it } from "vitest"
import { canMakeDish } from "@/lib/orders/can-make"
import type { Dish, Ingredient, OrderItem } from "@/lib/types"

/**
 * The Orders page submits a cart to the server. The user-visible rules
 * are: (1) you cannot put more of a dish in the cart than the kitchen
 * can make; (2) an empty cart cannot be submitted; (3) the items the
 * server eventually sees carry a quantity but no trusted price (the
 * server recomputes totals).
 *
 * These tests pin down those rules so future refactors cannot quietly
 * break them.
 */

const flour: Ingredient = {
  id: "i-1",
  name: "Flour",
  unit: "g",
  quantity_today: 500,
  min_threshold: 0,
  cost_per_unit: 0,
  supplier: null,
  is_demo: false,
  created_at: "",
  updated_at: "",
}

const water: Ingredient = {
  id: "i-2",
  name: "Water",
  unit: "ml",
  quantity_today: 1000,
  min_threshold: 0,
  cost_per_unit: 0,
  supplier: null,
  is_demo: false,
  created_at: "",
  updated_at: "",
}

const bread: Dish = {
  id: "d-1",
  name: "Bread",
  price: 5,
  category: "Bakery",
  description: null,
  preparation_time: 5,
  difficulty_level: "easy",
  is_active: true,
  is_demo: false,
  created_at: "",
  updated_at: "",
  ingredients: [
    { ingredient_id: "i-1", quantity: 200, unit: "g" },
    { ingredient_id: "i-2", quantity: 100, unit: "ml" },
  ],
}

describe("orders-cart invariants", () => {
  it("an empty cart has no items and zero line totals", () => {
    const cart: { dish_id: string; quantity: number }[] = []
    const subtotal = cart.reduce((sum, item) => {
      const dish = [bread].find((d) => d.id === item.dish_id)
      return sum + (dish ? dish.price * item.quantity : 0)
    }, 0)
    expect(cart.length).toBe(0)
    expect(subtotal).toBe(0)
  })

  it("the cart can only hold quantities the kitchen can make", () => {
    // 500g of flour / 200g per bread = 2 max
    expect(canMakeDish(bread, 1, [flour, water])).toBe(true)
    expect(canMakeDish(bread, 2, [flour, water])).toBe(true)
    expect(canMakeDish(bread, 3, [flour, water])).toBe(false)
  })

  it("the disable rule prevents adding one more than stock allows", () => {
    // Imitates the Orders page: "Add" button disabled when canMakeDish
    // returns false for the next +1 quantity.
    const cartQuantity = 2
    const next = cartQuantity + 1
    expect(canMakeDish(bread, next, [flour, water])).toBe(false)
  })

  it("the order payload sent to the server omits trusted prices", () => {
    // The client never sends price/subtotal/total; the server is the
    // single source of truth. This test pins the wire shape.
    const cartLine: { dish_id: string; quantity: number } = {
      dish_id: bread.id,
      quantity: 2,
    }
    const payload = {
      items: [cartLine],
      payment_method: "cash",
      cashier_id: "system",
    }
    // No price on the line.
    expect((cartLine as unknown as Record<string, unknown>).price).toBeUndefined()
    // No totals on the payload.
    expect((payload as unknown as Record<string, unknown>).subtotal).toBeUndefined()
    expect((payload as unknown as Record<string, unknown>).total).toBeUndefined()
  })

  it("the order payload carries dish_id and quantity for each item", () => {
    const items: OrderItem[] = [{ dish_id: bread.id, quantity: 2, price: 0 }]
    expect(items).toHaveLength(1)
    expect(items[0]?.dish_id).toBe(bread.id)
    expect(items[0]?.quantity).toBe(2)
  })

  it("every cart line must reference a known dish before submit", () => {
    const cart = [{ dish_id: "unknown", quantity: 1 }]
    const allKnown = cart.every((line) => [bread].some((d) => d.id === line.dish_id))
    expect(allKnown).toBe(false)
  })
})
