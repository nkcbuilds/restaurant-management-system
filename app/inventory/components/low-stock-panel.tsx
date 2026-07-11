"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { AlertTriangle } from "lucide-react"
import type { Ingredient } from "@/lib/types"

/**
 * Top-of-page banner listing ingredients that are at or below their
 * minimum threshold. Hidden when there's nothing to flag.
 */
export function LowStockPanel({ ingredients }: { ingredients: Ingredient[] }) {
  const low = ingredients.filter((i) => i.quantity_today <= i.min_threshold)
  if (low.length === 0) return null
  return (
    <Card className="border-destructive/40 bg-destructive/5">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-destructive text-base">
          <AlertTriangle className="h-4 w-4" />
          Low Stock
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {low.map((ing) => (
          <Badge key={ing.id} variant="destructive">
            {ing.name}: {ing.quantity_today} {ing.unit}
          </Badge>
        ))}
      </CardContent>
    </Card>
  )
}
