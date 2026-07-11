"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
import { Plus, Trash2, Package } from "lucide-react"
import { useCreateDish, useDeleteDish, useDishes, useIngredients } from "@/lib/queries"
import { LowStockPanel } from "./components/low-stock-panel"
import { IngredientForm } from "./components/ingredient-form"
import { IngredientTable } from "./components/ingredient-table"
import { RecipeBuilder } from "./components/recipe-builder"
import type { DishIngredient } from "@/lib/types"

const EMPTY_DISH = {
  name: "",
  price: 0,
  category: "",
  description: "",
  ingredients: [] as DishIngredient[],
}

export default function InventoryPage() {
  const { data: ingredients = [] } = useIngredients()
  const { data: dishes = [] } = useDishes()
  const createDish = useCreateDish()
  const deleteDish = useDeleteDish()
  const [showDishDialog, setShowDishDialog] = useState(false)
  const [newDish, setNewDish] = useState(EMPTY_DISH)

  const submitDish = () => {
    if (!newDish.name.trim() || newDish.price <= 0) return
    createDish.mutate(
      {
        name: newDish.name.trim(),
        price: newDish.price,
        category: newDish.category.trim() || "Uncategorised",
        description: newDish.description.trim() || null,
        ingredients: newDish.ingredients,
      },
      {
        onSuccess: () => {
          setNewDish(EMPTY_DISH)
          setShowDishDialog(false)
        },
      },
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Inventory</h1>
        <p className="text-sm text-muted-foreground">Manage dishes and ingredients</p>
      </div>

      <LowStockPanel ingredients={ingredients} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="flex items-center gap-2">
              <Package className="h-4 w-4" />
              Dishes
            </CardTitle>
            <Dialog open={showDishDialog} onOpenChange={setShowDishDialog}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="h-4 w-4 mr-1" />
                  Add
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>Add Dish</DialogTitle>
                  <DialogDescription>Create a new dish and its ingredients.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <Label htmlFor="name">Name</Label>
                      <Input
                        id="name"
                        value={newDish.name}
                        onChange={(e) => setNewDish({ ...newDish, name: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="price">Price</Label>
                      <Input
                        id="price"
                        type="number"
                        step="0.01"
                        value={newDish.price || ""}
                        onChange={(e) =>
                          setNewDish({ ...newDish, price: Number(e.target.value) || 0 })
                        }
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="category">Category</Label>
                      <Input
                        id="category"
                        value={newDish.category}
                        onChange={(e) => setNewDish({ ...newDish, category: e.target.value })}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="desc">Description</Label>
                      <Input
                        id="desc"
                        value={newDish.description}
                        onChange={(e) => setNewDish({ ...newDish, description: e.target.value })}
                      />
                    </div>
                  </div>

                  <RecipeBuilder
                    value={newDish.ingredients}
                    onChange={(ingredients) => setNewDish({ ...newDish, ingredients })}
                    ingredients={ingredients}
                  />

                  {createDish.isError ? (
                    <p className="text-xs text-destructive">
                      {createDish.error instanceof Error
                        ? createDish.error.message
                        : "Failed to save dish"}
                    </p>
                  ) : null}
                  <Button onClick={submitDish} disabled={createDish.isPending} className="w-full">
                    {createDish.isPending ? "Saving…" : "Save Dish"}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </CardHeader>
          <CardContent className="space-y-3">
            {dishes.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">No dishes yet</p>
            ) : (
              dishes.map((dish) => (
                <div key={dish.id} className="p-3 border rounded-lg">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-medium">{dish.name}</h3>
                      <p className="text-xs text-muted-foreground">{dish.category}</p>
                      {dish.description ? <p className="text-xs mt-1">{dish.description}</p> : null}
                      <p className="text-sm font-semibold mt-1">${dish.price.toFixed(2)}</p>
                      {dish.ingredients.length > 0 ? (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {dish.ingredients.map((ing, idx) => {
                            const data = ingredients.find((i) => i.id === ing.ingredient_id)
                            return (
                              <Badge key={idx} variant="secondary" className="text-xs">
                                {data?.name ?? "?"}: {ing.quantity}
                                {ing.unit}
                              </Badge>
                            )
                          })}
                        </div>
                      ) : null}
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => deleteDish.mutate(dish.id)}
                      disabled={deleteDish.isPending}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle>Ingredients</CardTitle>
            <IngredientForm />
          </CardHeader>
          <CardContent>
            <IngredientTable />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
