"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "../http"
import type { Dish, DishIngredient } from "../types"

export const dishKeys = {
  all: ["dishes"] as const,
  list: () => [...dishKeys.all, "list"] as const,
  detail: (id: string) => [...dishKeys.all, "detail", id] as const,
}

export function useDishes() {
  return useQuery({
    queryKey: dishKeys.list(),
    queryFn: () => http.get<Dish[]>("/api/dishes"),
  })
}

export interface CreateDishInput {
  name: string
  price: number
  category: string
  description?: string | null
  preparation_time?: number | null
  difficulty_level?: string | null
  ingredients: DishIngredient[]
}

export function useCreateDish() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateDishInput) => http.post<Dish>("/api/dishes", input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: dishKeys.all })
    },
  })
}

export function useUpdateDish() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<CreateDishInput> }) =>
      http.put<Dish>(`/api/dishes/${id}`, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: dishKeys.all })
    },
  })
}

export function useDeleteDish() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => http.delete<{ message: string }>(`/api/dishes/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: dishKeys.all })
    },
  })
}
