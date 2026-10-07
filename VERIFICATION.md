# Verification record

## Executed locally

- Python 3.12: 17 backend tests passed.
- Ruff: backend source and tests passed lint and formatting checks.
- Tests use temporary file-backed SQLite databases and HTTP clients. Concurrent requests start behind a thread barrier.

The backend cases cover duplicate checkout, reused keys with different payloads, competing carts for two units of stock, competing coupon redemptions, concurrent milestone issuance, rollback after an earlier stock update, injected database failure, replay after restart, exact rounding, live price changes, report reconciliation, invalid quantities, cart lifecycle and lock timeout.

## Verified in GitHub Actions

[Verification run 1](https://github.com/iitian-gopu/neustackapp_assignment/actions/runs/37629649639) passed on commit `6187c467a65cd33243b83da1338356d18ca4fc4a`.

| Check | Result |
| --- | --- |
| Backend installation, Ruff lint and formatting | Passed |
| Backend HTTP and concurrency suite | 17 tests passed |

The Python integration suite exercises concurrent connections in one process. Production load, multi-host deployment and real payments were not tested.

## Hosted HTTP verification

The Render checkout service served all five seeded products and the Swagger UI. The hosted demo created five orders, issued the eligible coupon, and placed a sixth order with a 10% discount. Repeating checkout returned the same order. The report reconciled to six orders, gross 7794 cents, discounts 130 cents, net 7664 cents, and one generated/redeemed coupon. The demo's request timeout is configurable for slower hosted connections.

Hosted verification covers HTTP flows; it does not include a manual visual browser review. See `DEPLOYMENT.md` for the free-hosting persistence and cold-start limitations. Hosting setup and these checks are additional to the initial implementation time estimate below.

## Scope and time

Approximately one hour of active work covered the initial implementation, setup and CI verification. Hosting configuration and live HTTP checks were completed separately. This estimate excludes personal review and interview preparation.

Authentication, real payments, production database migrations and reporting pagination remain deliberately deferred as described in the decision documents.
