#!/usr/bin/env node
/*
 * RestaurantOS end-to-end smoke test.
 *
 * Requires the FastAPI backend to be running on http://localhost:8000.
 *
 * Verifies:
 *   1. Backend /api/health is reachable.
 *   2. We can create a dish and an ingredient.
 *   3. POST /api/orders with a random Idempotency-Key succeeds, and the
 *      server-side total matches the dish price (not the client value).
 *   4. Re-posting the same key returns the SAME order id.
 *   5. Posting an order that exceeds stock fails with 409.
 *
 * Usage: node scripts/e2e-smoke.cjs
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

function log(msg, ok) {
  const mark = ok === true ? "✓" : ok === false ? "✗" : "·"
  console.log(`${mark} ${msg}`)
}

function assert(cond, msg) {
  if (!cond) {
    log(msg, false)
    process.exit(1)
  }
  log(msg, true)
}

async function http(path, init = {}) {
  const res = await fetch(`${API_URL.replace(/\/$/, "")}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
    cache: "no-store",
  })
  const text = await res.text()
  let body
  try { body = JSON.parse(text) } catch { body = text }
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status} on ${path}: ${JSON.stringify(body)}`)
    err.status = res.status
    err.body = body
    throw err
  }
  return body
}

function uuid() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16)
  })
}

async function main() {
  log(`Smoke test against ${API_URL}`)

  // 1. Health
  const health = await http("/api/health")
  assert(health.status === "ok", "backend /api/health returns ok")
  assert(health.db === true, "backend reports db is healthy")

  // 2. Create dish
  const dish = (await http("/api/dishes", {
    method: "POST",
    body: JSON.stringify({
      name: `Smoke Pizza ${Date.now()}`,
      price: 12.5,
      category: "Smoke",
      description: null,
      ingredients: [],
    }),
  })).data
  assert(dish.id, `created dish id=${dish.id}`)

  // 3. Create ingredient with very low stock
  const ing = (await http("/api/ingredients", {
    method: "POST",
    body: JSON.stringify({
      name: `Smoke Flour ${Date.now()}`,
      unit: "g",
      quantity_today: 100,
      min_threshold: 0,
      cost_per_unit: 0,
      supplier: null,
    }),
  })).data
  assert(ing.id, `created ingredient id=${ing.id}`)

  // Add the ingredient to the dish so stock check is meaningful.
  // (We do this via the existing dish endpoint; an existing dish with
  // empty ingredients will pass the stock check trivially.)
  await http(`/api/dishes/${dish.id}`, {
    method: "PUT",
    body: JSON.stringify({
      ingredients: [{ ingredient_id: ing.id, quantity: 50, unit: "g" }],
    }),
  })

  // 4. Place order with client-supplied low price; server must ignore it.
  const key = uuid()
  const order1 = (await http("/api/orders", {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify({
      items: [{ dish_id: dish.id, quantity: 1, price: 0.01 }],
      payment_method: "cash",
      cashier_id: "smoke",
    }),
  })).data
  assert(order1.total === 12.5, `server-computed total is 12.5 (got ${order1.total})`)
  assert(order1.status === "pending", "new order status is 'pending'")

  // 5. Re-posting same key returns the same order.
  const order2 = (await http("/api/orders", {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify({
      items: [{ dish_id: dish.id, quantity: 1, price: 0.01 }],
      payment_method: "cash",
      cashier_id: "smoke",
    }),
  })).data
  assert(order2.id === order1.id, "duplicate Idempotency-Key returns same order")

  // 6. An order that exceeds stock is rejected with 409.
  try {
    await http("/api/orders", {
      method: "POST",
      headers: { "Idempotency-Key": uuid() },
      body: JSON.stringify({
        // 100g of flour in stock, dish uses 50g, so 3 = 150g fails
        items: [{ dish_id: dish.id, quantity: 3, price: 0.01 }],
        payment_method: "cash",
        cashier_id: "smoke",
      }),
    })
    assert(false, "over-stock order was rejected")
  } catch (e) {
    assert(e.status === 409, `over-stock order returned 409 (got ${e.status})`)
  }

  log("All checks passed.", true)
}

main().catch((e) => {
  console.error("smoke test failed:", e.message)
  process.exit(1)
})
