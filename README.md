# Checkout and rewards service

[Architecture in Excalidraw](https://excalidraw.com/#json=Lb3qHileMl3fii9RTK84d,ubIOay4MK6tkc_r70Vn-VA) · [Live Swagger UI](https://neustack-checkout-api.onrender.com/docs)

Python, FastAPI and SQLite implementation of the backend assignment. The service provides carts, atomic checkout, inventory protection, retry-safe orders, milestone coupons and administrative reports.

## Run locally

Requires Python 3.11 or newer. Start with [the backend README](be/README.md) for installation, configuration and examples. The database and five products are created on startup.

```bash
cd be
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
uvicorn checkout.main:app --reload
```

On Windows PowerShell, use `.\.venv\Scripts\Activate.ps1` to activate the environment. Open http://127.0.0.1:8000/docs to exercise the API.

## Documentation

- [API endpoints, examples and errors](be/docs/API.md)
- [High-level design](be/docs/HLD.md)
- [Low-level design](be/docs/LLD.md)
- [Design decisions](be/DECISIONS.md)
- [Verification results](VERIFICATION.md)
- [Deployment configuration and limitations](DEPLOYMENT.md)

## Checks

From `be/` with the environment activated:

```bash
pytest -q
ruff check src tests scripts
ruff format --check src tests scripts
```

The suite includes 17 tests covering retries, competing stock and coupon purchases, rollback, rounding and report reconciliation. GitHub Actions runs the same checks.

## Live API

[Checkout API documentation](https://neustack-checkout-api.onrender.com/docs)

[Review the service in a few minutes](REVIEW.md): a Swagger walkthrough covering checkout, replay protection and reporting, with an optional coupon demo.

The free demo can take longer to respond after an idle period. Its database resets on host restart or redeployment; local file-backed storage persists across application restarts.

## Time spent

Approximately one hour covered the initial implementation, setup and verification. Hosting setup and live checks were completed separately. Personal review time is excluded.
