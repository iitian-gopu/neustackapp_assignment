# Design decisions

The main risk is a checkout that looks successful to one part of the system and failed to another. Inventory, the order, its coupon and its retry record therefore commit together. There is no queue or cache in this implementation.

## Invariants

- Inventory never becomes negative through checkout.
- A cart has at most one order. Checked-out carts cannot be edited.
- A successful checkout key identifies exactly one cart, coupon and order.
- Each milestone has at most one coupon, and each coupon has at most one consuming order.
- Failed checkout leaves stock, coupons, orders and retry records unchanged.
- Order totals equal the frozen line totals minus the recorded discount.
- Reports aggregate committed orders and read all counters from one snapshot.

These are enforced in both the write path and database constraints where practical. `UNIQUE(cart_id)`, `UNIQUE(coupon_code)`, `UNIQUE(milestone)` and nonnegative inventory checks are the final safeguards. Cross-row sums remain a service invariant, verified by tests; arbitrary direct SQL can bypass that part of the model.

## Decision: SQLite with one explicit transaction per operation

**Context:** Two requests can both observe the same stock or coupon as available.

**Options considered:** An in-memory dictionary with a process lock; SQLite; PostgreSQL with row locks.

**Choice:** A file-backed SQLite database, WAL mode, foreign keys, and `BEGIN IMMEDIATE` for writes.

**Why:** It demonstrates durable atomicity and overlapping request handling without another service to install. The writer lock is acquired before checking eligibility or stock, so decisions are made against the state that can actually be committed. Reads use ordinary transactions and can continue against a consistent snapshot.

**Consequences:** Writes serialize across connections and local processes. This is a deliberate throughput limit, not a distributed architecture. Connections wait up to five seconds, then return a retryable 503. No network calls or user interaction occur inside the transaction. Rollback covers every exception, including exceptions after earlier rows have been changed.

## Decision: Persist successful checkout intent

**Context:** A client may miss a response after the transaction commits.

**Options considered:** Deduplicate only by cart; store every request including failures; persist successful keys with their request identity.

**Choice:** Require a global idempotency key and store its cart, optional coupon and order in the checkout transaction. Also make cart ID unique on orders.

**Why:** Retrying the same intent returns the same snapshot after a process restart. Reusing a successful key for another payload is an explicit conflict. The cart constraint separately protects callers that accidentally use a new key.

**Consequences:** Failed attempts do not bind the key and can be corrected. A lost response is resolved by retrying the same key, never by inventing a new one. Omitting a coupon and sending null are equivalent. Keys have no expiration in this exercise. Production keys would be scoped to the authenticated customer and given an explicit retention contract.

## Decision: Live cart prices, immutable orders

**Context:** Price and availability can change while a cart is open.

**Options considered:** Reserve inventory and price at add time; store a quote version and reject changes; reprice at checkout.

**Choice:** Carts are nonbinding estimates. Checkout uses current database prices and stock. Orders copy product ID, name, unit price, quantity and line total.

**Why:** Reservations need expiry and abandoned-cart handling. Repricing is a coherent smaller contract, with no hidden promise about holding stock. A client must show that prices may change before purchase.

**Consequences:** A cart can contain more units than are currently in stock, but checkout fails atomically. A completed cart still displays live estimates; its linked order is the receipt. A real storefront should add quote acknowledgement before charging if a price changed.

## Decision: Store-wide milestone coupons issued on demand

**Context:** The prompt does not specify customer ownership, expiry, backlog or whether the nth order consumes its own reward.

**Options considered:** Per-customer loyalty counters; automatic issuance; admin-triggered global issuance.

**Choice:** Every `n` committed orders makes one milestone eligible. Each admin request issues the oldest unrewarded milestone. Coupons are transferable bearer codes, do not expire and apply to one later order. Discounted orders also count toward future milestones. One coupon per checkout, no stacking.

**Why:** There is no customer identity in the brief. Separating eligibility from issuance gives the admin endpoint a meaningful role. Generating one coupon per request makes backlog behavior easy to inspect.

**Consequences:** A request after three unclaimed milestones issues only one; two more requests issue the remaining two. Generation retries may issue the next eligible milestone, which is intentional and different from checkout idempotency. Unique milestone numbers prevent duplicate rewards. Policy values are stored on first startup and must match on restart; changing the campaign requires an explicit migration or new database.

## Decision: Derive redemption from the order

**Context:** A standalone `consumed` flag could be set before checkout fails or drift away from orders.

**Options considered:** A coupon status flag; a redemption table; a unique nullable coupon reference on orders.

**Choice:** An order's unique `coupon_code` is the redemption record. There is no separate mutable flag.

**Why:** There cannot be a committed redemption without an order. Rollback naturally releases the coupon. The unique reference prevents a second consuming order even if application checks regress.

**Consequences:** Reports and coupon status use the same source. Refunds and coupon reinstatement are outside scope and would need a separate policy and event history.

## Decision: Integer minor units and one rounding point

**Context:** Binary floats cannot represent many decimal prices exactly.

**Options considered:** Decimal prices throughout; integer cents; floating-point numbers rounded at the end.

**Choice:** Integer USD cents and integer percentage discounts. Line totals are `price * quantity`. Discount is `(subtotal * percent + 50) // 100`, rounded half up once on the full subtotal. Net is subtotal minus discount.

**Why:** This keeps all stored and reported arithmetic exact and avoids disagreement caused by per-line rounding. For a subtotal of 315 cents and 10%, discount is 32 cents and net is 283. A 100% discount produces zero, never a negative total.

**Consequences:** Fractional percentages, currencies with different minor-unit scales, taxes and shipping are deferred. Input caps keep a single seeded-catalog order comfortably inside SQLite's integer range. Aggregated reporting would need limits or a wider numeric type at extreme lifetime volumes.

## Decision: Direct SQL and a small service layer

**Context:** The evaluator needs to locate the transaction and see the conditions that protect it.

**Options considered:** ORM repositories and units of work; direct SQL hidden in route handlers; direct SQL in an application service.

**Choice:** Thin HTTP routes, Pydantic contracts, a service module and a database transaction helper.

**Why:** An ORM adds little for eight small tables. Keeping checkout in one readable method makes the atomic boundary visible. SQL values are bound parameters; the few dynamic identifiers come only from internal table names and validated update fields.

**Consequences:** SQL portability is manual. SQLite startup DDL is idempotent but is not a versioned migration system. PostgreSQL adoption requires deliberate query and schema changes.

## Decision: Treat successful commit as payment success

**Context:** Real payment and database transactions cannot be atomically committed together.

**Options considered:** A fake payment interface; a real external integration; no external payment call.

**Choice:** The assignment's permitted simplification: successful checkout is payment success.

**Why:** A fake that always succeeds would add an abstraction without testing a meaningful external failure. Database rollback is exercised instead, including a trigger that fails after inventory updates.

**Consequences:** There is no claim of real payment correctness. A future integration needs pending orders, bounded stock reservations, provider idempotency keys, webhook deduplication, an outbox and explicit compensation when payment and inventory disagree.

## Errors and reporting

Errors distinguish not found, invalid input, state conflict, contention and unexpected failure. Stable machine-readable codes drive client recovery; messages remain short. Business failures do not expose database errors. Unexpected exceptions are logged and become a generic 500. Infrastructure and framework errors are not all forced into a custom envelope; the precise scope is in the API guide.

The report runs multiple SELECTs inside one read transaction. Independent reads could straddle a checkout. The explicit snapshot preserves reconciliation. It sums order snapshots and derives redemption from orders rather than updating a second set of counters.

## Production evolution and deferred work

Several app instances on one host can share the same local SQLite file, subject to its single-writer limit. Containers on different hosts must not share it through a network filesystem. Move to PostgreSQL, lock the cart, coupon and product rows in a fixed order, retain the unique constraints, and retry deadlocks at the transaction boundary. Allocate milestone eligibility using a locked counter or transactional reward ledger; copying SQLite's `COUNT`/`MAX` algorithm without equivalent serialization would race.

Authentication, authorization, real payments, customer-bound keys, migration tooling, pagination, structured tracing, load benchmarks, backups and retention jobs are deferred. So are cancellation, refunds and changes to reward policy. These omissions do not remove any requested checkout operation, but they prevent calling this production-ready.

## AI assistance and validation

ChatGPT/Codex helped draft the implementation, tests and documentation. The initial draft covered both assignment briefs. The submission was narrowed to the checkout backend, and the unrelated UI, mock API, deployment references and CI job were removed. The database transaction boundary and persisted retry records were retained and verified against competing HTTP requests and failure injection.

Validation covers concurrent HTTP requests, replay after restart, injected database failures and report reconciliation. Results and the limits of those checks are recorded in [VERIFICATION.md](../VERIFICATION.md).

## Another two hours

First inspect multi-process contention with a real server and collect lock-wait latency. Then add a property-based test that reconciles stock deltas, orders, coupon uniqueness and revenue across randomized failures. For a payment-bearing deployment, price acknowledgement and payment state transitions would take priority over more endpoints.
