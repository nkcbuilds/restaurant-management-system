import { describe, expect, it } from "vitest"
import { canMakeDish } from "@/lib/orders/can-make"
import type { Dish, Ingredient } from "@/lib/types"

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

describe("canMakeDish", () => {
  it("returns true when stock is sufficient", () => {
    expect(canMakeDish(bread, 1, [flour, water])).toBe(true)
  })

  it("returns true at the exact stock limit", () => {
    expect(canMakeDish(bread, 2, [flour, water])).toBe(true) // 2 * 200 = 400 ≤ 500
  })

  it("returns false when one ingredient is short", () => {
    expect(canMakeDish(bread, 3, [flour, water])).toBe(false) // 3 * 200 = 600 > 500
  })

  it("returns false when the dish references a missing ingredient", () => {
    expect(canMakeDish(bread, 1, [flour])).toBe(false) // water missing
  })

  it("returns false for an unknown dish", () => {
    expect(canMakeDish(null, 1, [flour, water])).toBe(false)
  })

  it("returns false for zero or negative quantity", () => {
    expect(canMakeDish(bread, 0, [flour, water])).toBe(false)
    expect(canMakeDish(bread, -1, [flour, water])).toBe(false)
  })
})
