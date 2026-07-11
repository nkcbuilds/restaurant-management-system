"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ChefHat, CheckCircle2, Clock } from "lucide-react"
import { useKitchenTickets, useTransitionOrder } from "@/lib/queries"
import type { OrderStatus } from "@/lib/types"

/**
 * Phase 1 kitchen display.
 *
 * - Polls /api/kitchen/tickets every 10s.
 * - Lets the kitchen advance tickets through the lifecycle:
 *   submitted -> accepted -> preparing -> ready -> served -> completed
 * - "Cancel" is intentionally NOT here: cashiers cancel, not kitchen.
 */
const NEXT_STATUS: Record<string, { status: OrderStatus; label: string }> = {
  submitted: { status: "accepted", label: "Accept" },
  accepted: { status: "preparing", label: "Start preparing" },
  preparing: { status: "ready", label: "Mark ready" },
  ready: { status: "served", label: "Mark served" },
  served: { status: "completed", label: "Close" },
}

const STATUS_COLORS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  submitted: "outline",
  accepted: "secondary",
  preparing: "secondary",
  ready: "default",
  served: "default",
  completed: "default",
}

export default function KitchenPage() {
  const { data: tickets = [], isLoading } = useKitchenTickets()
  const transition = useTransitionOrder()

  const open = tickets.filter((t) => t.status !== "completed" && t.status !== "cancelled")
  const done = tickets.filter((t) => t.status === "completed" || t.status === "cancelled")

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ChefHat className="h-6 w-6" />
          Kitchen
        </h1>
        <p className="text-sm text-muted-foreground">
          Tickets auto-refresh every 10 seconds. Click a card to advance it through the lifecycle.
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading tickets…</p>
      ) : open.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No open tickets. Orders appear here the moment a cashier submits one.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {open.map((t) => {
            const next = NEXT_STATUS[t.status]
            return (
              <Card key={t.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">Order {t.order_id.slice(0, 8)}</CardTitle>
                    <Badge variant={STATUS_COLORS[t.status] ?? "outline"}>{t.status}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {new Date(t.created_at).toLocaleTimeString()}
                  </p>
                </CardHeader>
                <CardContent className="space-y-3">
                  <ul className="text-sm space-y-1">
                    {t.items.map((it, idx) => (
                      <li key={idx} className="flex justify-between">
                        <span>
                          {it.dish_name ?? "?"} × {it.quantity}
                        </span>
                        {it.notes ? (
                          <span className="text-xs text-muted-foreground italic">{it.notes}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                  {next ? (
                    <Button
                      className="w-full"
                      onClick={() => transition.mutate({ id: t.order_id, status: next.status })}
                      disabled={transition.isPending}
                    >
                      <CheckCircle2 className="h-4 w-4 mr-2" />
                      {next.label}
                    </Button>
                  ) : (
                    <p className="text-xs text-muted-foreground text-center">
                      No further action available from kitchen.
                    </p>
                  )}
                  {transition.isError && transition.variables?.id === t.order_id ? (
                    <p className="text-xs text-destructive">
                      {transition.error instanceof Error
                        ? transition.error.message
                        : "Transition failed"}
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {done.length > 0 ? (
        <div>
          <h2 className="text-sm font-semibold mb-2 text-muted-foreground">Recently closed</h2>
          <ul className="text-xs space-y-1 text-muted-foreground">
            {done.slice(0, 8).map((t) => (
              <li key={t.id}>
                {t.order_id.slice(0, 8)} · {t.status} ·{" "}
                {new Date(t.updated_at).toLocaleTimeString()}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
