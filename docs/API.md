# API reference

The FastAPI backend exposes a REST API. The **source of truth** is the
auto-generated OpenAPI schema — start the backend and visit
[`http://localhost:8000/docs`](http://localhost:8000/docs) for the
interactive Swagger UI, or `/openapi.json` for the raw schema.

This document gives you a quick textual map and the conventions used
by every endpoint.

---

## Conventions

### Envelope

Every response is wrapped in an `ApiResponse<T>`:

```json
{ "success": true,  "data": <T>, "error": null }
{ "success": false, "data": null, "error": { "detail": ..., "error_id": "..." } }
```

Some legacy / non-wrapped endpoints (the `/api/sync*` proxies, the
`/metrics` endpoint, the predictions endpoints, `/api/health`) return
their own shape. They're documented per-endpoint below.

### Status codes

| Code | Meaning                                                                         |
| ---- | ------------------------------------------------------------------------------- |
| 200  | Success.                                                                        |
| 201  | Resource created. Used by POSTs that don't return an existing resource.         |
| 400  | Bad request (validation error, unknown dish, invalid quantity).                 |
| 403  | RBAC: your `X-User-Role` is below the required minimum.                         |
| 404  | Resource not found.                                                             |
| 409  | Conflict (illegal state transition, insufficient stock, duplicate idempotency). |
| 500  | Server error. Body includes `error_id`; check the backend logs.                 |
| 503  | Backend is degraded (DB unreachable, prediction engine not initialised).        |

### Headers

| Header                           | When                                                                                                                                   |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `Content-Type: application/json` | Always (the API is JSON-only).                                                                                                         |
| `Idempotency-Key`                | Required for `POST /api/orders` and `POST /api/payments`. A UUID is fine.                                                              |
| `X-User-Role`                    | `cashier` / `kitchen` / `inventory` / `manager` / `owner`. Defaults to the minimum required by the route if absent. **Dev-only auth.** |

---

## Health & sync

| Method | Path               | Notes                                                                                |
| ------ | ------------------ | ------------------------------------------------------------------------------------ |
| GET    | `/api/health`      | Returns `{status, db, ts}` with 200 if DB reachable, 503 if not.                     |
| POST   | `/api/sync`        | Next.js proxy. Proxies to FastAPI `/api/sync`; returns 503 when backend unreachable. |
| GET    | `/api/sync/health` | Next.js proxy. Used by the dashboard's sync-status badge.                            |

---

## Dishes

| Method | Path               | Notes                                                                                        |
| ------ | ------------------ | -------------------------------------------------------------------------------------------- |
| GET    | `/api/dishes`      | All active dishes with their recipes.                                                        |
| POST   | `/api/dishes`      | Create. Body: `{name, price, category, ingredients: [{ingredient_id, quantity, unit}], ...}` |
| PUT    | `/api/dishes/{id}` | Update. Partial body.                                                                        |
| DELETE | `/api/dishes/{id}` | Soft delete (sets `is_active = 0`).                                                          |

---

## Ingredients

| Method | Path                                        | Notes                                                                                                     |
| ------ | ------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| GET    | `/api/ingredients`                          | All ingredients.                                                                                          |
| POST   | `/api/ingredients`                          | Create.                                                                                                   |
| PUT    | `/api/ingredients/{id}/quantity`            | Set absolute quantity. **Ledger records the delta, not the value.**                                       |
| POST   | `/api/inventory/waste`                      | Record wastage. Body: `{ingredient_id, quantity, reason, notes?}`. Inventory role required.               |
| POST   | `/api/inventory/count`                      | Record a physical count. Body: `{ingredient_id, physical_quantity, notes?}`. Ledger records the variance. |
| GET    | `/api/inventory/variance?from_date&to_date` | Theoretical vs actual for the date range. Manager role required.                                          |

---

## Orders

| Method | Path                        | Notes                                                                                                                                                                                                |
| ------ | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/api/orders`               | All orders (optional `?start_date&end_date`).                                                                                                                                                        |
| POST   | `/api/orders`               | Create. **Requires `Idempotency-Key` header.** Body: `{items, payment_method, cashier_id, customer_id?}`. Server ignores client-supplied prices and computes subtotal/tax/total from the dish table. |
| PATCH  | `/api/orders/{id}/status`   | Move along the lifecycle. Body: `{status, notes?}`. See [Lifecycle](#lifecycle). Invalid transitions return 409.                                                                                     |
| GET    | `/api/orders/{id}/payments` | List payments attached to this order.                                                                                                                                                                |
| POST   | `/api/orders/replay-batch`  | Offline replay. Body: `[{idempotency_key, captured_at, items, ...}, ...]`. Dedupes by key. Returns `{accepted, duplicates, failed}`.                                                                 |

### Lifecycle

```
draft → submitted → accepted → preparing → ready → served → completed
   ↓        ↓           ↓            ↓
                 cancelled (terminal)
```

Server-enforced. Illegal transitions return 409. Cancellation reverses
inventory consumption according to the `reverse_on_cancel` policy:

- `always` (default) — always reverse.
- `preparing_only` — only reverse if status was in `{draft, submitted,
accepted}` at the time of cancellation.
- `never` — never reverse; the consumption stays as waste.

---

## Payments

| Method    | Path                                    | Notes                                                                                                                                |
| --------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| POST      | `/api/payments`                         | Record a payment. **Idempotent** by `Idempotency-Key` header. Body: `{order_id, amount, method, reference?}`. Cashier role required. |
| (Phase 4) | `POST /api/payments/webhook/{provider}` | Real-provider webhooks (Razorpay / Stripe) — not implemented.                                                                        |

---

## Kitchen

| Method    | Path                      | Notes                                                             |
| --------- | ------------------------- | ----------------------------------------------------------------- | -------- | --------- | ----- | ------ | ---------------------------------- |
| GET       | `/api/kitchen/tickets`    | All open tickets. Optional `?status=submitted                     | accepted | preparing | ready | served | completed`. Kitchen role required. |
| (Phase 4) | `GET /api/kitchen/stream` | SSE stream of ticket updates. Polling fallback is in place today. |

---

## Predictions

| Method | Path                                          | Notes                                                                                                                                                      |
| ------ | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/api/predictions?date=`                      | Structured predictions for the date. Each carries `model_used`, `model_confidence`, `data_sufficiency`, `low`/`high` range, and a human-readable `reason`. |
| GET    | `/api/predictions/status`                     | Engine capability: `{prophet_available, models_trained}`.                                                                                                  |
| GET    | `/api/predictions/backtest?days=90&horizon=7` | Per-model and per-(dish, period) WAPE / MAE / bias / waste from the walk-forward backtest.                                                                 |
| GET    | `/api/prep-plan?date=`                        | Per-(dish, period) prep recommendations with the ingredients needed.                                                                                       |
| GET    | `/api/purchase-recommendations?date=`         | Per-ingredient shortage and cost estimate.                                                                                                                 |

---

## Analytics

| Method | Path                                       | Notes                                                          |
| ------ | ------------------------------------------ | -------------------------------------------------------------- |
| GET    | `/api/analytics/sales?start_date&end_date` | Per-day, per-period (morning/afternoon/evening) sales summary. |
| GET    | `/api/analytics/daily-sales?date=`         | One day's breakdown. 404 if no sales on that date.             |

---

## Users & RBAC

| Method | Path         | Notes                                                                       |
| ------ | ------------ | --------------------------------------------------------------------------- |
| POST   | `/api/users` | Create. Body: `{username, display_name, role}`. Role defaults to `cashier`. |
| GET    | `/api/users` | List.                                                                       |

The available roles (ascending privilege):

```
cashier → kitchen → inventory → manager → owner
```

Use the `X-User-Role` header to assume a role in dev. **Do not deploy
with header-based auth.**

---

## Suppliers & purchase orders (Phase 3)

| Method | Path                                | Notes                                                                                                       |
| ------ | ----------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| POST   | `/api/suppliers`                    | Create. Manager role required.                                                                              |
| GET    | `/api/suppliers`                    | List.                                                                                                       |
| POST   | `/api/purchase-orders`              | Create draft PO. Inventory role required.                                                                   |
| GET    | `/api/purchase-orders`              | List (optional `?supplier_id=`).                                                                            |
| POST   | `/api/purchase-orders/{id}/receive` | Receive goods. Writes `purchase` ledger entries and updates `cost_per_unit` to a quantity-weighted average. |
| POST   | `/api/purchase-orders/{id}/cancel`  | Cancel. Manager role required.                                                                              |

---

## Audit & observability

| Method | Path         | Notes                                                                                             |
| ------ | ------------ | ------------------------------------------------------------------------------------------------- |
| GET    | `/api/audit` | Recent 100 audit entries. Owner role required.                                                    |
| GET    | `/metrics`   | Prometheus-style exposition with `restaurantos_ingredients_total`, `_low_stock`, `_orders_total`. |

---

## Demo mode

| Method | Path             | Notes                                                                                     |
| ------ | ---------------- | ----------------------------------------------------------------------------------------- |
| POST   | `/api/demo/seed` | Only available when `RESTAURANT_DEMO_MODE=true`. Stub in Phase 0; richer seed in Phase 4. |

---

## Example: full order lifecycle

```bash
# 1. Create an ingredient
ING=$(curl -s -X POST http://localhost:8000/api/ingredients \
  -H "Content-Type: application/json" \
  -d '{"name":"Flour","unit":"g","quantity_today":1000,"min_threshold":0,"cost_per_unit":1}' \
  | jq -r .data.id)

# 2. Create a dish that uses it
DISH=$(curl -s -X POST http://localhost:8000/api/dishes \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Bread\",\"price\":5,\"category\":\"Bakery\",\"ingredients\":[{\"ingredient_id\":\"$ING\",\"quantity\":100,\"unit\":\"g\"}]}" \
  | jq -r .data.id)

# 3. Place an order
ORDER=$(curl -s -X POST http://localhost:8000/api/orders \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "X-User-Role: cashier" \
  -d "{\"items\":[{\"dish_id\":\"$DISH\",\"quantity\":1,\"price\":0}],\"payment_method\":\"cash\",\"cashier_id\":\"alice\"}" \
  | jq -r .data.id)

# 4. Walk through the lifecycle
curl -X PATCH "http://localhost:8000/api/orders/$ORDER/status" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: kitchen" \
  -d '{"status":"accepted"}'

curl -X PATCH "http://localhost:8000/api/orders/$ORDER/status" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: kitchen" \
  -d '{"status":"preparing"}'

# ... ready, served, completed
```

---

## When something fails

Every error response (except 4xx user errors) carries an `error_id`. To
correlate a user-visible error with the backend log:

```bash
# After seeing { "error_id": "abc123def456" } in the UI
grep "abc123def456" backend/restaurant_api.log
```

The `error_id` is a short hex string printed in the log on the same
line as the full traceback.
