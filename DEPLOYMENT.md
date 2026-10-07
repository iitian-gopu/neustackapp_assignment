# Hosted assignment demo

The checkout API is deployed on Render from the Python package in `be/`.

## Services

| Service | Host | Configuration |
| --- | --- | --- |
| Checkout API | Render | Python 3.12, repository root, build `python -m pip install ./be`, start `python -m uvicorn checkout.main:app --host 0.0.0.0 --port $PORT` |

## Demo limitations

The Render service uses the free plan. It may sleep when idle, so the first request can take longer. The checkout database is `/tmp/neustack-checkout.db` and is discarded when the service restarts or redeploys. Its transactional guarantees hold while that database exists; this deployment does not demonstrate durable recovery across host restarts.

All hosted data is disposable. No customer data, private credentials or real payments belong in this service. Administrative checkout endpoints have no authentication, as allowed by the assignment.

For a persistent checkout deployment, use one Render instance with a persistent disk, set `DATABASE_PATH` to a path on that mount, and retain the existing single-process transaction strategy. Multiple hosts require the production database design described in `be/DECISIONS.md`.

## API links

- Checkout Swagger: https://neustack-checkout-api.onrender.com/docs
- Checkout products: https://neustack-checkout-api.onrender.com/api/products

Deployment URLs are not verification results. Confirm each deployment is live and exercise its HTTP endpoints before including it in a submission.

To exercise coupon issuance and a repeated checkout against the hosted Python API:

```bash
BASE_URL=https://neustack-checkout-api.onrender.com/api REQUEST_TIMEOUT=60 python be/scripts/demo.py
```

Run this from the repository root. It creates disposable orders and prints the resulting report. On PowerShell, set `$env:BASE_URL` and `$env:REQUEST_TIMEOUT` before running `python be/scripts/demo.py`.
