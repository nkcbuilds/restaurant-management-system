"use client"

import { useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Trash2, Package } from "lucide-react"
import type { DishIngredient, Ingredient } from "@/lib/types"

interface Props {
  value: DishIngredient[]
  onChange: (next: DishIngredient[]) => void
  ingredients: Ingredient[]
}

/**
 * Editable list of (ingredient_id, quantity, unit) entries that
 * comprise a dish. Adds and removes via callbacks; never touches the
 * server directly.
 */
export function RecipeBuilder({ value, onChange, ingredients }: Props) {
  const [selectedId, setSelectedId] = useState("")
  const [qty, setQty] = useState(0)

  const add = () => {
    const ing = ingredients.find((i) => i.id === selectedId)
    if (!ing || qty <= 0) return
    onChange([...value, { ingredient_id: ing.id, quantity: qty, unit: ing.unit }])
    setSelectedId("")
    setQty(0)
  }

  const remove = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx))
  }

  return (
    <div className="border-t pt-4 space-y-2">
      <div className="text-sm font-medium">Ingredients</div>
      <div className="flex gap-2">
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          <option value="">Select ingredient</option>
          {ingredients.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name} ({i.unit})
            </option>
          ))}
        </select>
        <Input
          type="number"
          placeholder="Qty"
          className="w-24"
          value={qty || ""}
          onChange={(e) => setQty(Number(e.target.value) || 0)}
        />
        <Button type="button" variant="outline" onClick={add}>
          Add
        </Button>
      </div>
      {value.length === 0 ? (
        <Card>
          <CardContent className="py-4 text-xs text-muted-foreground text-center">
            <Package className="h-4 w-4 inline-block mr-1 -mt-0.5" /> No ingredients yet.
          </CardContent>
        </Card>
      ) : (
        <ul className="text-sm space-y-1 mt-2">
          {value.map((row, idx) => {
            const ing = ingredients.find((i) => i.id === row.ingredient_id)
            return (
              <li
                key={`${row.ingredient_id}-${idx}`}
                className="flex items-center justify-between p-2 bg-muted rounded"
              >
                <span>
                  {ing?.name ?? "?"} — {row.quantity} {row.unit}
                </span>
                <Button size="sm" variant="ghost" onClick={() => remove(idx)}>
                  <Trash2 className="h-3 w-3" />
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
