# Design decisions

This submission contains the checkout and rewards backend.

[The backend decision document](be/DECISIONS.md) covers the system invariants, eight material decisions, alternatives, transaction and idempotency strategy, money calculations, coupon semantics, error handling, production evolution and priorities for further work.

The main correctness boundary is one SQLite write transaction: inventory changes, order creation, coupon redemption and the successful retry record commit together. Order snapshots provide the source of truth for receipts and reporting.

[VERIFICATION.md](VERIFICATION.md) records executed checks. [DEPLOYMENT.md](DEPLOYMENT.md) explains the hosted demo's storage limitations.
