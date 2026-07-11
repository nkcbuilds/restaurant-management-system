"use client"

import { useMemo } from "react"
import Link from "next/link"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ShoppingCart, Plus, Minus, Check, Clock, WifiOff, RefreshCw } from "lucide-react"
import { useDishes, useIngredients, useOrders, usePlaceOrder } from "@/lib/queries"
import { useOfflineQueue } from "@/lib/queries/offline"
import { useUIStore } from "@/lib/store"
import { ApiError } from "@/lib/http"

export default function OrdersPage() {
  const { data: dishes = [], isLoading: dishesLoading } = useDishes()
  const { data: ingredients = [], isLoading: ingredientsLoading } = useIngredients()
  const { data: orders = [], isLoading: ordersLoading } = useOrders()
  const placeOrder = usePlaceOrder()
  const offline = useOfflineQueue()

  const cart = useUIStore((s) => s.cart)
  const addToCart = useUIStore((s) => s.addToCart)
  const removeFromCart = useUIStore((s) => s.removeFromCart)
  const clearCart = useUIStore((s) => s.clearCart)

  const grouped = useMemo(() => {
    return dishes.reduce(
      (acc, dish) => {
        const k = dish.category || "Other"
        ;(acc[k] ||= []).push(dish)
        return acc
      },
      {} as Record<string, typeof dishes>,
    )
  }, [dishes])

  /**
   * Local availability check uses the SAME ingredient rows the
   * backend uses, so the user sees an honest "you can't order this"
   * state. The server is the final word on the order itself.
   */
  const canMake = (dishId: string, qty: number): boolean => {
    const dish = dishes.find((d) => d.id === dishId)
    if (!dish) return false
    return dish.ingredients.every((ing) => {
      const stock = ingredients.find((i) => i.id === ing.ingredient_id)
      return stock !== undefined && stock.quantity_today >= ing.quantity * qty
    })
  }

  const total = cart.reduce((sum, item) => {
    const dish = dishes.find((d) => d.id === item.dish_id)
    return sum + (dish ? dish.price * item.quantity : 0)
  }, 0)

  const submit = async () => {
    if (cart.length === 0 || placeOrder.isPending) return
    try {
      await placeOrder.mutateAsync({
        items: cart.map((c) => ({ dish_id: c.dish_id, quantity: c.quantity, price: 0 })),
        payment_method: "cash",
        cashier_id: "system",
      })
      clearCart()
      return
    } catch (err) {
      // Network / backend outage -> capture locally and let the outbox
      // replay when the connection is back.
      if (err instanceof ApiError || (err instanceof TypeError && navigator?.onLine === false)) {
        offline.queue({
          items: cart.map((c) => ({ dish_id: c.dish_id, quantity: c.quantity, price: 0 })),
          payment_method: "cash",
          cashier_id: "system",
        })
        clearCart()
      } else {
        // Real validation/insufficient-stock error — surface it.
        throw err
      }
    }
  }

  if (dishesLoading || ingredientsLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading…</div>
  }

  if (Object.keys(grouped).length === 0) {
    return (
      <div className="p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Orders</h1>
          <p className="text-sm text-muted-foreground">Take orders and update inventory</p>
        </div>
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No dishes available.{" "}
            <Link href="/inventory" className="text-primary underline-offset-4 hover:underline">
              Add dishes in Inventory
            </Link>{" "}
            first.
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Orders</h1>
        <p className="text-sm text-muted-foreground">Take orders and update inventory</p>
      </div>

      {offline.state.pending.length > 0 ? (
        <Card className="border-amber-500/40 bg-amber-500/5">
          <CardContent className="py-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm">
              <WifiOff className="h-4 w-4 text-amber-600" />
              <span>
                {offline.state.pending.length} order
                {offline.state.pending.length === 1 ? "" : "s"} waiting to sync.
              </span>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void offline.flush()}
              disabled={offline.state.isReplaying}
            >
              <RefreshCw
                className={`h-3 w-3 mr-1 ${offline.state.isReplaying ? "animate-spin" : ""}`}
              />
              {offline.state.isReplaying ? "Syncing…" : "Sync now"}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          {Object.entries(grouped).map(([category, items]) => (
            <Card key={category}>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{category}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                {items.map((dish) => {
                  const inCart = cart.find((c) => c.dish_id === dish.id)?.quantity ?? 0
                  const available = canMake(dish.id, 1)
                  return (
                    <div
                      key={dish.id}
                      className={`p-3 border rounded-lg ${available ? "" : "opacity-50"}`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <h3 className="font-medium text-sm">{dish.name}</h3>
                          <p className="text-sm font-semibold">${dish.price.toFixed(2)}</p>
                        </div>
                        {!available ? <Badge variant="destructive">Out</Badge> : null}
                      </div>
                      {inCart > 0 ? (
                        <div className="flex items-center gap-1">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => removeFromCart(dish.id)}
                          >
                            <Minus className="h-3 w-3" />
                          </Button>
                          <span className="px-2 text-sm font-medium">{inCart}</span>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => addToCart(dish.id, 1)}
                            disabled={!canMake(dish.id, inCart + 1)}
                          >
                            <Plus className="h-3 w-3" />
                          </Button>
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => addToCart(dish.id, 1)}
                          disabled={!available}
                          className="w-full"
                        >
                          Add
                        </Button>
                      )}
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <ShoppingCart className="h-4 w-4" />
                Current Order
              </CardTitle>
            </CardHeader>
            <CardContent>
              {cart.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">No items</p>
              ) : (
                <div className="space-y-3">
                  <ul className="space-y-2 text-sm">
                    {cart.map((item) => {
                      const dish = dishes.find((d) => d.id === item.dish_id)
                      if (!dish) return null
                      return (
                        <li key={item.dish_id} className="flex justify-between">
                          <span>
                            {dish.name} × {item.quantity}
                          </span>
                          <span className="font-medium">
                            ${(dish.price * item.quantity).toFixed(2)}
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                  <div className="border-t pt-3 flex justify-between font-semibold">
                    <span>Subtotal (display)</span>
                    <span>${total.toFixed(2)}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    The server computes the final price including tax. The subtotal shown here is a
                    UI estimate only.
                  </p>
                  {placeOrder.isError ? (
                    <p className="text-xs text-destructive">
                      {placeOrder.error instanceof Error
                        ? placeOrder.error.message
                        : "Order failed"}
                    </p>
                  ) : null}
                  <Button onClick={submit} className="w-full" disabled={placeOrder.isPending}>
                    <Check className="h-4 w-4 mr-2" />
                    {placeOrder.isPending ? "Placing…" : "Complete"}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {orders.length > 0 ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Clock className="h-4 w-4" />
                  Recent
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {orders.slice(0, 5).map((order) => {
                  const item = order.items[0]
                  const dish = dishes.find((d) => d.id === item?.dish_id)
                  return (
                    <div key={order.id} className="flex justify-between text-sm p-2 border rounded">
                      <div>
                        <p className="font-medium">{dish?.name ?? "Item"}</p>
                        <p className="text-xs text-muted-foreground">
                          {new Date(order.timestamp).toLocaleTimeString()} · {order.status}
                        </p>
                      </div>
                      <p className="font-semibold">${order.total.toFixed(2)}</p>
                    </div>
                  )
                })}
                {ordersLoading ? <p className="text-xs text-muted-foreground">Loading…</p> : null}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}
