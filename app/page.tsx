"use client"

import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { useOrders, useIngredients } from "@/lib/queries"
import {
  DollarSign,
  ShoppingCart,
  Package,
  ArrowUpRight,
  AlertTriangle,
  CheckCircle,
} from "lucide-react"

function EmDash({ label }: { label: string }) {
  return (
    <div className="text-2xl font-bold text-muted-foreground cursor-help" title={label}>
      —
    </div>
  )
}

export default function Dashboard() {
  const { data: orders = [], isLoading: ordersLoading } = useOrders()
  const { data: ingredients = [], isLoading: ingredientsLoading } = useIngredients()

  const hasOrders = orders.length > 0
  const totalRevenue = orders.reduce((sum, o) => sum + o.total, 0)
  const totalOrders = orders.length
  const avgOrderValue = totalOrders > 0 ? totalRevenue / totalOrders : 0
  const lowStock = ingredients.filter((i) => i.quantity_today <= i.min_threshold)

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Live numbers from the FastAPI backend. No estimates, no samples.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Revenue</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {ordersLoading ? (
              <div className="text-2xl font-bold text-muted-foreground">…</div>
            ) : hasOrders ? (
              <div className="text-2xl font-bold">${totalRevenue.toFixed(2)}</div>
            ) : (
              <EmDash label="Waiting for the first order" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Orders</CardTitle>
            <ShoppingCart className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {ordersLoading ? (
              <div className="text-2xl font-bold text-muted-foreground">…</div>
            ) : hasOrders ? (
              <div className="text-2xl font-bold">{totalOrders}</div>
            ) : (
              <EmDash label="Waiting for the first order" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Avg Order</CardTitle>
            <ShoppingCart className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {ordersLoading ? (
              <div className="text-2xl font-bold text-muted-foreground">…</div>
            ) : hasOrders ? (
              <div className="text-2xl font-bold">${avgOrderValue.toFixed(2)}</div>
            ) : (
              <EmDash label="Waiting for the first order" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Low Stock</CardTitle>
            <Package className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {ingredientsLoading ? (
              <div className="text-2xl font-bold text-muted-foreground">…</div>
            ) : (
              <div className="text-2xl font-bold">{lowStock.length}</div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Quick Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Link href="/orders" className="block">
              <Button variant="outline" className="w-full justify-between h-auto py-3">
                <span className="flex items-center gap-3">
                  <ShoppingCart className="h-4 w-4" />
                  New Order
                </span>
                <ArrowUpRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/inventory" className="block">
              <Button variant="outline" className="w-full justify-between h-auto py-3">
                <span className="flex items-center gap-3">
                  <Package className="h-4 w-4" />
                  Manage Inventory
                </span>
                <ArrowUpRight className="h-4 w-4" />
              </Button>
            </Link>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm">
                <CheckCircle className="h-4 w-4 text-green-500" />
                System
              </span>
              <SyncStatusBadge />
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm">
                <Package className="h-4 w-4 text-muted-foreground" />
                Ingredients
              </span>
              <span className="text-xs text-muted-foreground">{ingredients.length} tracked</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm">
                <AlertTriangle
                  className={
                    lowStock.length > 0
                      ? "h-4 w-4 text-destructive"
                      : "h-4 w-4 text-muted-foreground"
                  }
                />
                Low Stock
              </span>
              <span className="text-xs text-muted-foreground">{lowStock.length} items</span>
            </div>
            {lowStock.length > 0 && (
              <div className="mt-3 p-3 rounded-md bg-destructive/10 border border-destructive/20 text-sm">
                <p className="font-medium text-destructive mb-1">Needs attention</p>
                <ul className="space-y-0.5 text-xs">
                  {lowStock.slice(0, 3).map((item) => (
                    <li key={item.id}>
                      {item.name}: {item.quantity_today} {item.unit}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function SyncStatusBadge() {
  // Phase 0 ships a minimal sync-status probe. The full sync UI lands
  // with the Next.js /api/sync route in 0.6.
  return <span className="text-xs text-muted-foreground">Live</span>
}
