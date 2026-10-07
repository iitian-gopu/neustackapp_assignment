from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Quantity = Annotated[int, Field(strict=True, ge=1, le=10000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemInput(Input):
    product_id: str = Field(min_length=1, max_length=100)
    quantity: Quantity


class QuantityInput(Input):
    quantity: Quantity


class CheckoutInput(Input):
    coupon_code: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^\S+$")


class ProductUpdate(Input):
    unit_price_minor: Annotated[int, Field(strict=True, ge=0, le=100000000)] | None = None
    inventory: Annotated[int, Field(strict=True, ge=0, le=1000000)] | None = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("Provide at least one non-null field")
        return self


class Product(BaseModel):
    id: str
    name: str
    unit_price_minor: int
    inventory: int


class OrderItem(BaseModel):
    product_id: str
    name: str
    unit_price_minor: int
    quantity: int
    line_total_minor: int


class CartItem(OrderItem):
    inventory: int


class Cart(BaseModel):
    id: str
    created_at: str
    currency: Literal["USD"]
    status: Literal["OPEN", "CHECKED_OUT"]
    order_id: str | None
    items: list[CartItem]
    subtotal_minor: int


class Order(BaseModel):
    id: str
    cart_id: str
    coupon_code: str | None
    discount_percent: int
    subtotal_minor: int
    discount_minor: int
    total_minor: int
    created_at: str
    currency: Literal["USD"]
    items: list[OrderItem]


class Coupon(BaseModel):
    code: str
    milestone: int
    discount_percent: int
    created_at: str
    status: Literal["AVAILABLE", "REDEEMED"]
    order_id: str | None


class ProductQuantity(BaseModel):
    product_id: str
    purchased_quantity: int


class CouponCounts(BaseModel):
    generated: int
    available: int
    redeemed: int


class Report(BaseModel):
    currency: Literal["USD"]
    total_orders: int
    gross_minor: int
    discounts_minor: int
    net_minor: int
    products: list[ProductQuantity]
    coupons: CouponCounts


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict


class ErrorResponse(BaseModel):
    error: ErrorDetail
