"use client"

import { useMemo, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Brain, TrendingUp, AlertTriangle, ShoppingCart } from "lucide-react"
import {
  usePredictions,
  usePredictionStatus,
  usePrepPlan,
  usePurchaseRecommendations,
  useBacktest,
  type Prediction,
} from "@/lib/queries/predictions"

const SUFFICIENCY_COLORS: Record<string, "destructive" | "secondary" | "default" | "outline"> = {
  insufficient: "destructive",
  low: "outline",
  ok: "secondary",
  strong: "default",
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

export default function PredictionsPage() {
  const [date, setDate] = useState(todayISO())
  const { data: predictions = [], isLoading } = usePredictions(date)
  const { data: status } = usePredictionStatus()
  const { data: prep = [] } = usePrepPlan(date)
  const { data: purchases = [] } = usePurchaseRecommendations(date)
  const { data: backtest } = useBacktest(90, 7)

  const groupedByDish = useMemo(() => {
    const out = new Map<string, Prediction[]>()
    for (const p of predictions) {
      if (!out.has(p.dish_id)) out.set(p.dish_id, [])
      out.get(p.dish_id)!.push(p)
    }
    return out
  }, [predictions])

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Brain className="h-6 w-6" />
          Predictions & Prep Plan
        </h1>
        <p className="text-sm text-muted-foreground">
          Each forecast shows which model produced it, a realistic range, and why we recommend what
          we recommend. The backtest at the bottom tells you how accurate each model has actually
          been.
        </p>
      </div>

      <div className="flex items-end gap-3">
        <div className="space-y-1">
          <label htmlFor="pred-date" className="text-sm">
            Forecast for
          </label>
          <input
            id="pred-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="border rounded px-2 py-1 text-sm bg-background"
          />
        </div>
        <div className="text-xs text-muted-foreground pb-1">
          {status?.models_trained !== undefined
            ? `${status.models_trained} baseline models loaded${
                status.prophet_available ? " (Prophet enabled)" : ""
              }`
            : "Engine status unknown"}
        </div>
      </div>

      {/* Predictions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <TrendingUp className="h-4 w-4" />
            Demand forecasts
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : predictions.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No predictions yet — they appear once orders have been placed.
            </p>
          ) : (
            [...groupedByDish.entries()].map(([dishId, preds]) => (
              <div key={dishId} className="border rounded-lg p-3">
                <h3 className="font-semibold">{preds[0]?.dish_name}</h3>
                <div className="grid gap-2 sm:grid-cols-3 mt-2">
                  {preds.map((p) => (
                    <div
                      key={`${p.dish_id}-${p.period}`}
                      className="text-sm bg-muted/30 rounded p-2"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium capitalize">{p.period}</span>
                        <Badge variant={SUFFICIENCY_COLORS[p.data_sufficiency] ?? "outline"}>
                          {p.data_sufficiency}
                        </Badge>
                      </div>
                      <p className="text-2xl font-bold mt-1">
                        {p.predicted_demand}
                        <span className="text-xs text-muted-foreground ml-1">
                          ({p.low}–{p.high})
                        </span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        prep {p.recommended_prep} · {p.model_used} · conf{" "}
                        {Math.round(p.model_confidence * 100)}%
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-1 italic">{p.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {/* Prep plan */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ingredients to pull</CardTitle>
        </CardHeader>
        <CardContent>
          {prep.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              No prep plan yet — place orders with completed status to populate history.
            </p>
          ) : (
            <ul className="text-sm space-y-2">
              {prep.slice(0, 10).map((entry) => (
                <li key={`${entry.dish_id}-${entry.period}`} className="border rounded p-2">
                  <div className="flex justify-between items-center">
                    <span className="font-medium">
                      {entry.dish_name} ({entry.period})
                    </span>
                    <span className="text-xs text-muted-foreground">
                      prep {entry.recommended_prep} · need {entry.ingredients_needed.length}{" "}
                      ingredients
                    </span>
                  </div>
                  {entry.ingredients_needed.length > 0 ? (
                    <ul className="text-xs mt-1 space-y-0.5">
                      {entry.ingredients_needed.map((ing) => (
                        <li key={ing.ingredient_id}>
                          · {ing.quantity} {ing.unit}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground mt-1">no recipe attached</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Purchase recommendations */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShoppingCart className="h-4 w-4" />
            Reorder list
          </CardTitle>
        </CardHeader>
        <CardContent>
          {purchases.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">
              Nothing to reorder yet — either stock is sufficient or no history exists.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1">Ingredient</th>
                  <th className="py-1 text-right">On hand</th>
                  <th className="py-1 text-right">Needed</th>
                  <th className="py-1 text-right">Shortage</th>
                  <th className="py-1 text-right">Cost</th>
                </tr>
              </thead>
              <tbody>
                {purchases.slice(0, 12).map((r) => (
                  <tr key={r.ingredient_id} className="border-t">
                    <td className="py-1">{r.ingredient_name}</td>
                    <td className="py-1 text-right">{r.on_hand}</td>
                    <td className="py-1 text-right">{r.needed}</td>
                    <td className="py-1 text-right">
                      <span className={r.needs_reorder ? "text-destructive font-semibold" : ""}>
                        {r.shortage}
                      </span>
                    </td>
                    <td className="py-1 text-right">${r.cost_estimate.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Backtest */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertTriangle className="h-4 w-4" />
            Model backtest (last 90 days)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {backtest?.warning ? (
            <p className="text-sm text-muted-foreground">{backtest.warning}</p>
          ) : (
            <>
              <p className="text-xs text-muted-foreground">
                This is the honest number. Lower WAPE = better. The model the engine actually uses
                for each (dish, period) is the one with the lowest historical WAPE here.
              </p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground">
                    <th className="py-1">Model</th>
                    <th className="py-1 text-right">N</th>
                    <th className="py-1 text-right">MAE</th>
                    <th className="py-1 text-right">WAPE</th>
                    <th className="py-1 text-right">Bias</th>
                    <th className="py-1 text-right">Waste</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(backtest?.overall ?? {}).map(([model, stats]) => (
                    <tr key={model} className="border-t">
                      <td className="py-1">{model.replace(/_/g, " ")}</td>
                      <td className="py-1 text-right">{stats.n}</td>
                      <td className="py-1 text-right">{stats.mae.toFixed(2)}</td>
                      <td className="py-1 text-right">{stats.wape.toFixed(3)}</td>
                      <td className="py-1 text-right">{stats.bias.toFixed(2)}</td>
                      <td className="py-1 text-right">{stats.waste.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {backtest && backtest.by_dish_period.length > 0 ? (
                <div>
                  <h4 className="text-sm font-medium mt-3 mb-1">Per dish winner</h4>
                  <ul className="text-xs space-y-0.5">
                    {backtest.by_dish_period.map((entry, idx) => (
                      <li key={idx}>
                        dish {entry.dish_id.slice(0, 8)} ({entry.period}) →{" "}
                        <span className="font-mono">
                          {entry.winner_model?.replace(/_/g, " ") ?? "—"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                onClick={() => window.location.reload()}
                className="mt-2"
              >
                Refresh
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
