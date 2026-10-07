# Checkout and rewards

A small Python service with persistent carts, atomic checkout, milestone coupons and a reconciled admin report. FastAPI handles HTTP validation; SQLite owns the transaction boundary.

## Run locally

Requires Python 3.11 or newer. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
uvicorn checkout.main:app --reload
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead. The remaining commands are the same.

Open http://127.0.0.1:8000/docs for the interactive API, or http://127.0.0.1:8000/openapi.json for the generated contract. The database and five products are created on startup. Restarting never resets inventory or orders. The hand grinder starts with two units.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_PATH` | `checkout.db` | SQLite file, relative to the working directory |
| `REWARD_EVERY` | `5` | Successful orders per coupon milestone |
| `DISCOUNT_PERCENT` | `10` | Whole-number percentage, 1 through 100 |

Set environment variables before starting the service. Once a database exists, its reward policy is fixed. A different policy at startup fails clearly rather than reinterpreting existing milestones. For a disposable fresh run, stop the service and choose a new database path.

All amounts are integer USD cents. For example, `1299` means $12.99. Carts use current prices and do not reserve inventory. Checkout validates stock again and freezes the purchased names, prices, quantities and totals in the order.

## Try it

With the server running, use a second terminal:

```bash
python scripts/demo.py
```

This creates five orders, requests a coupon, redeems it, repeats that checkout with the same key, and checks that the replay returns the same order. Run it against a fresh database with the default policy. It prints the resulting admin report.

For a single cart:

```bash
curl -X POST http://127.0.0.1:8000/api/carts
curl -X POST http://127.0.0.1:8000/api/carts/CART_ID/items \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"coffee","quantity":2}'
curl -X POST http://127.0.0.1:8000/api/carts/CART_ID/checkout \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: checkout-example-1' \
  -d '{}'
```

Replace `CART_ID` with the returned ID. Retry checkout with the same key and body if the response is lost. A different key cannot check out a completed cart again.

## Tests

```bash
pytest -q
ruff check src tests
ruff format --check src tests
```

The tests use temporary database files. They cover overlapping retries, competing stock and coupon purchases, milestone generation races, restart recovery, rollback after partial inventory changes, injected database failure, rounding and report reconciliation. They run through the HTTP interface rather than only calling service methods.

## Project map

| Path | Responsibility |
| --- | --- |
| `src/checkout/api.py` | HTTP routes and dependencies |
| `src/checkout/schemas.py` | Request and response contracts |
| `src/checkout/service.py` | Cart, checkout, coupon and reporting operations |
| `src/checkout/database.py` | Connections, transaction scope and seeding |
| `src/checkout/schema.sql` | Tables and database constraints |
| `tests/` | Failure and concurrency tests |
| `docs/API.md` | Endpoint examples, status codes and errors |
| `docs/HLD.md` | System boundaries and production evolution |
| `docs/LLD.md` | Data model, transaction order and invariants |
| `DECISIONS.md` | Choices, alternatives and deferred work |

Authentication is intentionally absent. Every `/api/admin/*` operation is administrative and must be protected before deploying this service. No external payment call is made; committing checkout represents payment success.
