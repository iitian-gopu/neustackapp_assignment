import json
import os
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8000/api")
TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "30"))


def request(method, path, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    data = json.dumps(body).encode() if body is not None else None
    with urlopen(
        Request(BASE + path, data=data, headers=headers, method=method), timeout=TIMEOUT
    ) as response:
        return json.load(response)


def make_cart():
    cart = request("POST", "/carts")
    request("POST", f"/carts/{cart['id']}/items", {"product_id": "coffee", "quantity": 1})
    return cart["id"]


for _ in range(5):
    cart_id = make_cart()
    request("POST", f"/carts/{cart_id}/checkout", {}, str(uuid4()))
coupon = request("POST", "/admin/coupons")
cart_id = make_cart()
key = str(uuid4())
body = {"coupon_code": coupon["code"]}
order = request("POST", f"/carts/{cart_id}/checkout", body, key)
replay = request("POST", f"/carts/{cart_id}/checkout", body, key)
assert order == replay
print(json.dumps({"order": order, "report": request("GET", "/admin/report")}, indent=2))
