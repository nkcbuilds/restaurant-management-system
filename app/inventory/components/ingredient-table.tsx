"use client"

import { useState } from "react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { useIngredients, useUpdateIngredientQuantity } from "@/lib/queries"
import type { Ingredient } from "@/lib/types"

/**
 * Read-only-ish table of ingredients. Quantity is editable inline; the
 * server records the signed delta in the inventory_transactions ledger.
 */
export function IngredientTable() {
  const { data: ingredients = [], isLoading } = useIngredients()
  const updateQty = useUpdateIngredientQuantity()

  if (isLoading) {
    return <p className="text-sm text-muted-foreground py-6 text-center">Loading ingredients…</p>
  }
  if (ingredients.length === 0) {
    return <p className="text-sm text-muted-foreground py-6 text-center">No ingredients yet.</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Quantity</TableHead>
          <TableHead>Cost / Unit</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {ingredients.map((ing) => (
          <IngredientRow
            key={ing.id}
            ingredient={ing}
            onQuantityCommit={(qty) => updateQty.mutate({ id: ing.id, quantity: qty })}
          />
        ))}
      </TableBody>
    </Table>
  )
}

function IngredientRow({
  ingredient,
  onQuantityCommit,
}: {
  ingredient: Ingredient
  onQuantityCommit: (qty: number) => void
}) {
  const [draft, setDraft] = useState(ingredient.quantity_today)

  const low = ingredient.quantity_today <= ingredient.min_threshold
  return (
    <TableRow>
      <TableCell className="font-medium">
        {ingredient.name}
        {ingredient.supplier ? (
          <span className="block text-xs text-muted-foreground">{ingredient.supplier}</span>
        ) : null}
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            className="w-24 h-8"
            value={draft}
            onChange={(e) => setDraft(Number(e.target.value) || 0)}
            onBlur={() => {
              if (draft !== ingredient.quantity_today) onQuantityCommit(draft)
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                ;(e.target as HTMLInputElement).blur()
              }
            }}
          />
          <span className="text-xs text-muted-foreground">{ingredient.unit}</span>
        </div>
      </TableCell>
      <TableCell>
        <span className="text-sm">${ingredient.cost_per_unit.toFixed(2)}</span>
      </TableCell>
      <TableCell>
        {low ? <Badge variant="destructive">Low</Badge> : <Badge variant="secondary">OK</Badge>}
      </TableCell>
    </TableRow>
  )
}
