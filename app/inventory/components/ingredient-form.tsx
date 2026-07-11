"use client"

import { useState } from "react"
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
import { Plus } from "lucide-react"
import { useCreateIngredient } from "@/lib/queries"

const EMPTY = {
  name: "",
  unit: "",
  quantity_today: 0,
  min_threshold: 0,
  cost_per_unit: 0,
  supplier: "",
}

export function IngredientForm() {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const create = useCreateIngredient()

  const submit = () => {
    if (!form.name.trim() || !form.unit.trim()) return
    create.mutate(
      {
        ...form,
        supplier: form.supplier.trim() || null,
      },
      {
        onSuccess: () => {
          setForm(EMPTY)
          setOpen(false)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4 mr-1" />
          Add
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Ingredient</DialogTitle>
          <DialogDescription>Track a new ingredient in inventory.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Flour"
              />
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={form.unit}
                onChange={(e) => setForm({ ...form, unit: e.target.value })}
                placeholder="g, ml, kg, …"
              />
            </div>
            <div className="space-y-1">
              <Label>Quantity</Label>
              <Input
                type="number"
                value={form.quantity_today || ""}
                onChange={(e) => setForm({ ...form, quantity_today: Number(e.target.value) || 0 })}
              />
            </div>
            <div className="space-y-1">
              <Label>Min Threshold</Label>
              <Input
                type="number"
                value={form.min_threshold || ""}
                onChange={(e) => setForm({ ...form, min_threshold: Number(e.target.value) || 0 })}
              />
            </div>
            <div className="space-y-1">
              <Label>Cost / Unit</Label>
              <Input
                type="number"
                step="0.01"
                value={form.cost_per_unit || ""}
                onChange={(e) => setForm({ ...form, cost_per_unit: Number(e.target.value) || 0 })}
              />
            </div>
            <div className="space-y-1">
              <Label>Supplier</Label>
              <Input
                value={form.supplier}
                onChange={(e) => setForm({ ...form, supplier: e.target.value })}
              />
            </div>
          </div>
          {create.isError && (
            <p className="text-xs text-destructive">
              {create.error instanceof Error ? create.error.message : "Failed to add ingredient"}
            </p>
          )}
          <Button onClick={submit} disabled={create.isPending} className="w-full">
            {create.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
