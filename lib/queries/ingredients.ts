"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "../http"
import type { Ingredient } from "../types"

export const ingredientKeys = {
  all: ["ingredients"] as const,
  list: () => [...ingredientKeys.all, "list"] as const,
}

export function useIngredients() {
  return useQuery({
    queryKey: ingredientKeys.list(),
    queryFn: () => http.get<Ingredient[]>("/api/ingredients"),
  })
}

export interface CreateIngredientInput {
  name: string
  unit: string
  quantity_today: number
  min_threshold: number
  cost_per_unit: number
  supplier?: string | null
}

export function useCreateIngredient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateIngredientInput) => http.post<Ingredient>("/api/ingredients", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingredientKeys.all })
    },
  })
}

export function useUpdateIngredientQuantity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, quantity }: { id: string; quantity: number }) =>
      http.put<Ingredient>(`/api/ingredients/${id}/quantity`, { quantity }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingredientKeys.all })
    },
  })
}
