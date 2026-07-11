"use client"

import { create } from "zustand"

/**
 * Transient UI state ONLY.
 *
 * The previous incarnation of this store mixed server data (dishes,
 * ingredients, orders) with UI state. That was the source of the
 * "sidebar disagrees with the inventory page" bug class. Server data
 * now lives in TanStack Query (see lib/queries/*). This store keeps
 * only ephemeral state the React tree needs to coordinate.
 */
export interface CartItem {
  dish_id: string
  quantity: number
}

export interface UIState {
  cart: CartItem[]
  categoryFilter: string | null
  addToCart: (dishId: string, delta?: number) => void
  removeFromCart: (dishId: string) => void
  clearCart: () => void
  setCategoryFilter: (category: string | null) => void
}

export const useUIStore = create<UIState>((set) => ({
  cart: [],
  categoryFilter: null,
  addToCart: (dishId, delta = 1) =>
    set((s) => {
      const existing = s.cart.find((c) => c.dish_id === dishId)
      if (existing) {
        const next = existing.quantity + delta
        if (next <= 0) {
          return { cart: s.cart.filter((c) => c.dish_id !== dishId) }
        }
        return {
          cart: s.cart.map((c) => (c.dish_id === dishId ? { ...c, quantity: next } : c)),
        }
      }
      if (delta <= 0) return {}
      return { cart: [...s.cart, { dish_id: dishId, quantity: delta }] }
    }),
  removeFromCart: (dishId) => set((s) => ({ cart: s.cart.filter((c) => c.dish_id !== dishId) })),
  clearCart: () => set({ cart: [] }),
  setCategoryFilter: (category) => set({ categoryFilter: category }),
}))

/**
 * Tiny helper for components that only need one slice of the UI store
 * and want a non-hook subscription (handy for derived computations).
 */
export function useCart() {
  return useUIStore((s) => s.cart)
}
