# API contract

Local base URL: `http://127.0.0.1:8000/api`.

Hosted base URL: `https://neustack-checkout-api.onrender.com/api`.

Open [the live Swagger UI](https://neustack-checkout-api.onrender.com/docs) to inspect schemas and execute requests. Bodies are JSON. `/openapi.json` provides the machine-readable contract. All `/admin/*` endpoints are administrative; authentication is outside this assignment's scope.

## Endpoints

| Method and path | Request | Success | Important failure cases |
| --- | --- | --- | --- |
| `GET /products` | None | `200`, product array | `503` database busy |
| `POST /carts` | None | `201`, cart | `503` database busy |
| `GET /carts/{id}` | None | `200`, cart | `404` unknown cart |
| `POST /carts/{id}/items` | `{"product_id":"coffee","quantity":2}` | `201`, updated cart | `404` cart/product missing; `409` duplicate item or closed cart; `422` invalid quantity |
| `PUT /carts/{id}/items/{product_id}` | `{"quantity":3}` | `200`, updated cart | `404` missing cart/product/item; `409` closed cart; `422` invalid quantity |
| `DELETE /carts/{id}/items/{product_id}` | None | `204`, empty body | `404` cart missing; `409` closed cart |
| `POST /carts/{id}/checkout` | `{}` or `{"coupon_code":"CODE"}`; required `Idempotency-Key` header | `201`, order; `200` for replay | `404` cart missing; `409` empty/closed cart, inventory/coupon/key conflict; `422` invalid coupon or request |
| `GET /orders/{id}` | None | `200`, order | `404` unknown order |
| `POST /admin/coupons` | None | `201`, newly generated coupon | `409` no eligible milestone |
| `GET /admin/coupons` | None | `200`, coupon array | `503` database busy |
| `GET /admin/report` | None | `200`, report | `503` database busy |
| `PATCH /admin/products/{id}` | `{"unit_price_minor":1599,"inventory":4}`; either or both | `200`, product | `404` missing product; `422` invalid or empty changes |

`PATCH` sets the absolute current inventory; it is not an increment. It exists to exercise price and availability changes. Product names and IDs cannot be changed through this API.

Deleting an already absent item is a successful no-op for an existing open cart. Adding an existing item is a conflict, not an implicit increment; use PUT to set the quantity. Integers must be JSON integers: strings, booleans, fractions, zero and negative quantities are rejected. Quantity limit: 10,000 per product. Price limit: 100,000,000 minor units. Inventory limit: 1,000,000. Unknown input properties and explicit null product updates are rejected.

## Response examples

A product:

```json
{"id":"coffee","name":"House Coffee","unit_price_minor":1299,"inventory":100}
```

A cart with one item:

```json
{
  "id":"cart-uuid",
  "created_at":"2026-10-07T13:00:00+00:00",
  "currency":"USD",
  "status":"OPEN",
  "order_id":null,
  "items":[{
    "product_id":"coffee","name":"House Coffee","unit_price_minor":1299,
    "quantity":2,"inventory":100,"line_total_minor":2598
  }],
  "subtotal_minor":2598
}
```

Cart totals are live estimates, including after checkout. The `order_id` points to the authoritative purchased snapshot. Cart stock is informational; other carts can contain the same product.

An order using a 10% coupon:

```json
{
  "id":"order-uuid","cart_id":"cart-uuid","coupon_code":"CODE",
  "discount_percent":10,"subtotal_minor":2598,"discount_minor":260,"total_minor":2338,
  "created_at":"2026-10-07T13:01:00+00:00","currency":"USD",
  "items":[{
    "product_id":"coffee","name":"House Coffee","unit_price_minor":1299,
    "quantity":2,"line_total_minor":2598
  }]
}
```

Checkout responses include `Location: /api/orders/{id}` and `Idempotency-Replayed: true|false`.

A coupon:

```json
{
  "code":"A9E83973310049F8A304C9C08D817AD6","milestone":5,"discount_percent":10,
  "created_at":"2026-10-07T13:02:00+00:00","status":"AVAILABLE","order_id":null
}
```

On redemption, status is `REDEEMED` and `order_id` identifies the consuming order. Coupon codes are exact and case-sensitive. Coupons never expire, are not customer-bound, and cannot stack. Eligibility is store-wide, not per customer. Admin generation issues one oldest eligible milestone per request. Repeated generation with multiple eligible milestones intentionally issues different coupons.

A report on a new database:

```json
{
  "currency":"USD","total_orders":0,"gross_minor":0,"discounts_minor":0,"net_minor":0,
  "products":[
    {"product_id":"coffee","purchased_quantity":0},
    {"product_id":"filter","purchased_quantity":0},
    {"product_id":"grinder","purchased_quantity":0},
    {"product_id":"mug","purchased_quantity":0},
    {"product_id":"tea","purchased_quantity":0}
  ],
  "coupons":{"generated":0,"available":0,"redeemed":0}
}
```

The report uses order snapshots, never current product prices. Products with no sales appear with quantity zero. `gross_minor - discounts_minor = net_minor`; `available + redeemed = generated`. The response is one database snapshot and has no side effects.

## Retry contract

Use a unique printable ASCII `Idempotency-Key` of 1–128 characters per checkout intent. Keys are global in this unauthenticated demo. Successful requests retain their key indefinitely. The same key, cart and coupon returns the stored order even after product updates or restart. Omitting the coupon and passing null are equivalent. Changing cart or coupon with an already successful key returns `IDEMPOTENCY_CONFLICT`. Cart contents are not part of the key payload: successful checkout closes the cart; after a failed attempt the caller may edit the cart and retry.

Validation and failed transactions do not reserve a key. A failed checkout can be corrected and retried with that key. For uncertain outcomes, retry the same request before starting a new intent. Database contention returns `503` and `Retry-After: 1`; use bounded retries with jitter. A retry after an internal error is also safe with the same key.

## Error envelope

```json
{
  "error":{
    "code":"INSUFFICIENT_INVENTORY",
    "message":"Requested quantity is no longer available",
    "details":{"product_id":"grinder","available":2,"requested":3}
  }
}
```

| Code | Status | Client response |
| --- | --- | --- |
| `NOT_FOUND`, `ITEM_NOT_FOUND` | 404 | Check resource identifiers |
| `ITEM_EXISTS` | 409 | Update with PUT |
| `CART_CHECKED_OUT` | 409 | Use `details.order_id` to retrieve the existing order |
| `EMPTY_CART` | 409 | Add an item |
| `INSUFFICIENT_INVENTORY` | 409 | Refresh cart and reduce requested quantity |
| `COUPON_REDEEMED` | 409 | Select another coupon or deliberately remove it |
| `IDEMPOTENCY_CONFLICT` | 409 | Resolve the original intent; do not blindly retry with a new key |
| `NO_ELIGIBLE_MILESTONE` | 409 | Wait for more successful orders |
| `INVALID_COUPON` | 422 | Check the exact coupon code |
| `VALIDATION_ERROR` | 422 | Correct fields listed in `details.issues` |
| `DATABASE_BUSY` | 503 | Retry after the indicated delay |
| `INTERNAL_ERROR` | 500 | Retry checkout with the same key; investigate server logs |

The first detected business error is returned. Checkout checks an existing key, cart state, empty cart, coupon validity, then stock. Clients should branch on codes, not message text. Framework-level unknown-route or unsupported-method responses retain FastAPI's normal `detail` format; the envelope above applies to declared endpoint processing.
