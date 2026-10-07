from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response

from checkout import schemas
from checkout.service import Store

router = APIRouter(prefix="/api")


def get_store(request: Request):
    return request.app.state.store


StoreDep = Annotated[Store, Depends(get_store)]
Key = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[!-~]+$")
]


@router.get("/products", tags=["Products"])
def products(store: StoreDep) -> list[schemas.Product]:
    return store.products()


@router.post("/carts", status_code=201, tags=["Carts"])
def create_cart(store: StoreDep) -> schemas.Cart:
    return store.create_cart()


@router.get("/carts/{cart_id}", tags=["Carts"])
def get_cart(cart_id: str, store: StoreDep) -> schemas.Cart:
    return store.get_cart(cart_id)


@router.post("/carts/{cart_id}/items", status_code=201, tags=["Carts"])
def add_item(cart_id: str, body: schemas.ItemInput, store: StoreDep) -> schemas.Cart:
    return store.set_item(cart_id, body.product_id, body.quantity, adding=True)


@router.put("/carts/{cart_id}/items/{product_id}", tags=["Carts"])
def update_item(
    cart_id: str, product_id: str, body: schemas.QuantityInput, store: StoreDep
) -> schemas.Cart:
    return store.set_item(cart_id, product_id, body.quantity)


@router.delete("/carts/{cart_id}/items/{product_id}", status_code=204, tags=["Carts"])
def remove_item(cart_id: str, product_id: str, store: StoreDep):
    store.remove_item(cart_id, product_id)
    return Response(status_code=204)


@router.post(
    "/carts/{cart_id}/checkout",
    status_code=201,
    tags=["Checkout"],
    responses={200: {"model": schemas.Order, "description": "Successful replay"}},
)
def checkout(
    cart_id: str,
    body: schemas.CheckoutInput,
    store: StoreDep,
    idempotency_key: Key,
    response: Response,
) -> schemas.Order:
    order, replayed = store.checkout(cart_id, idempotency_key, body.coupon_code)
    response.status_code = 200 if replayed else 201
    response.headers["Idempotency-Replayed"] = str(replayed).lower()
    response.headers["Location"] = f"/api/orders/{order['id']}"
    return order


@router.get("/orders/{order_id}", tags=["Orders"])
def get_order(order_id: str, store: StoreDep) -> schemas.Order:
    return store.get_order(order_id)


@router.post("/admin/coupons", status_code=201, tags=["Administration"])
def generate_coupon(store: StoreDep) -> schemas.Coupon:
    return store.generate_coupon()


@router.get("/admin/coupons", tags=["Administration"])
def coupons(store: StoreDep) -> list[schemas.Coupon]:
    return store.coupons()


@router.get("/admin/report", tags=["Administration"])
def report(store: StoreDep) -> schemas.Report:
    return store.report()


@router.patch("/admin/products/{product_id}", tags=["Administration"])
def update_product(
    product_id: str, body: schemas.ProductUpdate, store: StoreDep
) -> schemas.Product:
    return store.update_product(product_id, body.model_dump(exclude_unset=True))
