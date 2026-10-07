from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from checkout.config import Settings
from checkout.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(str(tmp_path / "store.db"), 2, 10))) as client:
        yield client


def cart(client, items=None):
    cart_id = client.post("/api/carts").json()["id"]
    for product, quantity in items or [("coffee", 1)]:
        assert (
            client.post(
                f"/api/carts/{cart_id}/items", json={"product_id": product, "quantity": quantity}
            ).status_code
            == 201
        )
    return cart_id


def checkout(client, cart_id, key, coupon=None):
    return client.post(
        f"/api/carts/{cart_id}/checkout",
        json={"coupon_code": coupon},
        headers={"Idempotency-Key": key},
    )


def race(operations):
    barrier = Barrier(len(operations))

    def run(operation):
        barrier.wait(timeout=10)
        return operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return list(pool.map(run, operations))


def earn_coupon(client):
    for number in range(2):
        assert checkout(client, cart(client), f"earn-{number}").status_code == 201
    return client.post("/api/admin/coupons").json()["code"]


def test_concurrent_retries_create_one_order_and_survive_restart(client):
    cart_id = cart(client)
    results = race([lambda: checkout(client, cart_id, "same") for _ in range(8)])
    assert sorted(response.status_code for response in results) == [200] * 7 + [201]
    assert len({response.json()["id"] for response in results}) == 1
    assert client.get("/api/admin/report").json()["total_orders"] == 1
    settings = client.app.state.store.database.settings
    with TestClient(create_app(settings)) as restarted:
        replay = checkout(restarted, cart_id, "same")
        assert replay.status_code == 200
        assert replay.json() == results[0].json()
        assert (
            next(p for p in restarted.get("/api/products").json() if p["id"] == "coffee")[
                "inventory"
            ]
            == 99
        )


def test_same_cart_different_keys_and_key_payload_conflict(client):
    cart_id = cart(client)
    results = race([lambda key=key: checkout(client, cart_id, key) for key in ("one", "two")])
    assert sorted(response.status_code for response in results) == [201, 409]
    winner = "one" if results[0].status_code == 201 else "two"
    assert (
        checkout(client, cart_id, winner, "different").json()["error"]["code"]
        == "IDEMPOTENCY_CONFLICT"
    )
    other = cart(client)
    assert checkout(client, other, winner).status_code == 409


def test_competing_carts_cannot_oversell(client):
    carts = [cart(client, [("grinder", 1)]) for _ in range(6)]
    results = race([lambda cid=cid: checkout(client, cid, cid) for cid in carts])
    assert sorted(response.status_code for response in results) == [201, 201, 409, 409, 409, 409]
    grinder = next(p for p in client.get("/api/products").json() if p["id"] == "grinder")
    assert grinder["inventory"] == 0


def test_only_one_competing_checkout_redeems_coupon(client):
    coupon = earn_coupon(client)
    carts = [cart(client) for _ in range(5)]
    results = race([lambda cid=cid: checkout(client, cid, cid, coupon) for cid in carts])
    assert sorted(response.status_code for response in results) == [201, 409, 409, 409, 409]
    assert client.get("/api/admin/report").json()["coupons"] == {
        "generated": 1,
        "available": 0,
        "redeemed": 1,
    }


def test_failure_rolls_back_prior_inventory_updates_and_preserves_coupon(client):
    coupon = earn_coupon(client)
    cart_id = cart(client, [("coffee", 3), ("grinder", 3)])
    before = client.get("/api/products").json()
    report = client.get("/api/admin/report").json()
    failed = checkout(client, cart_id, "retryable", coupon)
    assert failed.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"
    assert client.get("/api/products").json() == before
    assert client.get("/api/admin/report").json() == report
    client.put(f"/api/carts/{cart_id}/items/grinder", json={"quantity": 1})
    assert checkout(client, cart_id, "retryable", coupon).status_code == 201


def test_database_failure_after_inventory_change_rolls_back_everything(client):
    coupon = earn_coupon(client)
    cart_id = cart(client)
    database = client.app.state.store.database
    with database.transaction(write=True) as connection:
        connection.execute(
            "CREATE TRIGGER reject_order BEFORE INSERT ON orders "
            "BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
        )
    before = client.get("/api/products").json()
    with TestClient(client.app, raise_server_exceptions=False) as failing_client:
        assert checkout(failing_client, cart_id, "crash", coupon).status_code == 500
    assert client.get("/api/products").json() == before
    assert client.get("/api/admin/coupons").json()[0]["status"] == "AVAILABLE"
    with database.transaction(write=True) as connection:
        connection.execute("DROP TRIGGER reject_order")
    assert checkout(client, cart_id, "crash", coupon).status_code == 201


def test_milestone_generation_is_atomic_and_backlog_is_not_lost(client):
    assert client.post("/api/admin/coupons").status_code == 409
    for number in range(6):
        checkout(client, cart(client), f"order-{number}")
    results = race([lambda: client.post("/api/admin/coupons") for _ in range(8)])
    assert sorted(response.status_code for response in results) == [201] * 3 + [409] * 5
    assert sorted(
        response.json()["milestone"] for response in results if response.status_code == 201
    ) == [2, 4, 6]


def test_price_snapshot_rounding_and_report_reconciliation(client):
    coupon = earn_coupon(client)
    cart_id = cart(client, [("tea", 3)])
    client.patch("/api/admin/products/tea", json={"unit_price_minor": 105})
    assert client.get(f"/api/carts/{cart_id}").json()["subtotal_minor"] == 315
    order = checkout(client, cart_id, "discount", coupon).json()
    assert (order["subtotal_minor"], order["discount_minor"], order["total_minor"]) == (
        315,
        32,
        283,
    )
    client.patch("/api/admin/products/tea", json={"unit_price_minor": 999})
    assert client.get(f"/api/orders/{order['id']}").json() == order
    report = client.get("/api/admin/report").json()
    assert report == client.get("/api/admin/report").json()
    assert (report["gross_minor"], report["discounts_minor"], report["net_minor"]) == (
        2913,
        32,
        2881,
    )
    assert (
        next(p for p in report["products"] if p["product_id"] == "tea")["purchased_quantity"] == 3
    )


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True, 10001])
def test_invalid_quantities_are_rejected(client, quantity):
    cart_id = client.post("/api/carts").json()["id"]
    assert (
        client.post(
            f"/api/carts/{cart_id}/items", json={"product_id": "coffee", "quantity": quantity}
        ).status_code
        == 422
    )
    assert client.get(f"/api/carts/{cart_id}").json()["items"] == []


def test_cart_lifecycle_validation_and_invalid_coupon(client):
    cart_id = client.post("/api/carts").json()["id"]
    assert checkout(client, cart_id, "empty").json()["error"]["code"] == "EMPTY_CART"
    assert (
        client.post(
            f"/api/carts/{cart_id}/items", json={"product_id": "missing", "quantity": 1}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/carts/{cart_id}/items", json={"product_id": "coffee", "quantity": 1}
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/carts/{cart_id}/items", json={"product_id": "coffee", "quantity": 1}
        ).status_code
        == 409
    )
    assert checkout(client, cart_id, "bad", "UNKNOWN").status_code == 422
    assert client.post(f"/api/carts/{cart_id}/checkout", json={}).status_code == 422
    assert client.put(f"/api/carts/{cart_id}/items/coffee", json={"quantity": 2}).status_code == 200
    assert client.delete(f"/api/carts/{cart_id}/items/coffee").status_code == 204
    assert client.delete(f"/api/carts/{cart_id}/items/coffee").status_code == 204
    client.post(f"/api/carts/{cart_id}/items", json={"product_id": "coffee", "quantity": 1})
    assert checkout(client, cart_id, "valid").status_code == 201
    assert client.delete(f"/api/carts/{cart_id}/items/coffee").status_code == 409


def test_busy_database_is_retryable_and_does_not_change_state(client):
    cart_id = cart(client)
    database = client.app.state.store.database
    quick_app = create_app(Settings(database.settings.database_path, 2, 10, 1))
    with TestClient(quick_app) as quick:
        with database.transaction(write=True):
            response = checkout(quick, cart_id, "busy")
            assert response.status_code == 503
            assert response.headers["Retry-After"] == "1"
        assert checkout(quick, cart_id, "busy").status_code == 201


def test_full_discount_and_policy_mismatch(tmp_path):
    path = str(tmp_path / "full.db")
    with TestClient(create_app(Settings(path, 1, 100))) as client:
        checkout(client, cart(client), "first")
        coupon = client.post("/api/admin/coupons").json()["code"]
        order = checkout(client, cart(client), "second", coupon).json()
        assert order["total_minor"] == 0
    with pytest.raises(ValueError, match="Reward policy differs"):
        with TestClient(create_app(Settings(path, 2, 100))):
            pass
