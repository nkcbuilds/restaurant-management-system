import type { Dish, Ingredient } from "@/lib/types"

/**
 * Single source of truth for "can the kitchen make N of this dish right
 * now?". Returns false for missing data so the UI can show an honest
 * "out" state instead of letting a user place an unfulfillable order.
 */
export function canMakeDish(
  dish: Dish | null | undefined,
  quantity: number,
  ingredients: Ingredient[],
): boolean {
  if (!dish) return false
  if (!Number.isFinite(quantity) || quantity <= 0) return false
  return dish.ingredients.every((ing) => {
    const stock = ingredients.find((i) => i.id === ing.ingredient_id)
    if (!stock) return false
    return stock.quantity_today >= ing.quantity * quantity
  })
}
