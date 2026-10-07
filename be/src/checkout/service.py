from datetime import datetime, timezone
from uuid import uuid4

from checkout.database import Database
from checkout.errors import DomainError


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def require_row(connection, table, identifier):
    row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (identifier,)).fetchone()
    if row is None:
        raise DomainError(404, "NOT_FOUND", f"{table.rstrip('s').capitalize()} not found")
    return row


def ensure_open(connection, cart_id):
    require_row(connection, "carts", cart_id)
    order = connection.execute("SELECT id FROM orders WHERE cart_id = ?", (cart_id,)).fetchone()
    if order:
        raise DomainError(409, "CART_CHECKED_OUT", "Cart already checked out", order_id=order["id"])


def cart_view(connection, cart_id):
    cart = require_row(connection, "carts", cart_id)
    items = [
        dict(row)
        for row in connection.execute(
            "SELECT p.id AS product_id, p.name, p.unit_price_minor, p.inventory, ci.quantity, "
            "p.unit_price_minor * ci.quantity AS line_total_minor "
            "FROM cart_items ci JOIN products p ON p.id = ci.product_id "
            "WHERE ci.cart_id = ? ORDER BY p.id",
            (cart_id,),
        )
    ]
    order = connection.execute("SELECT id FROM orders WHERE cart_id = ?", (cart_id,)).fetchone()
    return {
        "id": cart_id,
        "created_at": cart["created_at"],
        "currency": "USD",
        "status": "CHECKED_OUT" if order else "OPEN",
        "order_id": order["id"] if order else None,
        "items": items,
        "subtotal_minor": sum(item["line_total_minor"] for item in items),
    }


def order_view(connection, order_id):
    order = dict(require_row(connection, "orders", order_id))
    order["currency"] = "USD"
    order["items"] = [
        dict(row)
        for row in connection.execute(
            "SELECT product_id, name, unit_price_minor, quantity, line_total_minor "
            "FROM order_items WHERE order_id = ? ORDER BY product_id",
            (order_id,),
        )
    ]
    return order


class Store:
    def __init__(self, database: Database):
        self.database = database

    def products(self):
        with self.database.transaction() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM products ORDER BY id")]

    def create_cart(self):
        with self.database.transaction(write=True) as connection:
            cart_id = str(uuid4())
            connection.execute("INSERT INTO carts VALUES (?, ?)", (cart_id, timestamp()))
            return cart_view(connection, cart_id)

    def get_cart(self, cart_id):
        with self.database.transaction() as connection:
            return cart_view(connection, cart_id)

    def set_item(self, cart_id, product_id, quantity, *, adding=False):
        with self.database.transaction(write=True) as connection:
            ensure_open(connection, cart_id)
            require_row(connection, "products", product_id)
            previous = connection.execute(
                "SELECT quantity FROM cart_items WHERE cart_id = ? AND product_id = ?",
                (cart_id, product_id),
            ).fetchone()
            if adding and previous:
                raise DomainError(409, "ITEM_EXISTS", "Use PUT to change the existing quantity")
            if not adding and not previous:
                raise DomainError(404, "ITEM_NOT_FOUND", "Item is not in this cart")
            connection.execute(
                "INSERT INTO cart_items VALUES (?, ?, ?) "
                "ON CONFLICT(cart_id, product_id) DO UPDATE SET quantity = excluded.quantity",
                (cart_id, product_id, quantity),
            )
            return cart_view(connection, cart_id)

    def remove_item(self, cart_id, product_id):
        with self.database.transaction(write=True) as connection:
            ensure_open(connection, cart_id)
            connection.execute(
                "DELETE FROM cart_items WHERE cart_id = ? AND product_id = ?", (cart_id, product_id)
            )

    def checkout(self, cart_id, key, coupon_code):
        with self.database.transaction(write=True) as connection:
            previous = connection.execute(
                "SELECT * FROM checkout_requests WHERE key = ?", (key,)
            ).fetchone()
            if previous:
                if (previous["cart_id"], previous["coupon_code"]) != (cart_id, coupon_code):
                    raise DomainError(
                        409, "IDEMPOTENCY_CONFLICT", "Key was used for another request"
                    )
                return order_view(connection, previous["order_id"]), True
            ensure_open(connection, cart_id)
            cart = cart_view(connection, cart_id)
            if not cart["items"]:
                raise DomainError(409, "EMPTY_CART", "Add at least one item before checkout")
            percent = 0
            if coupon_code is not None:
                coupon = connection.execute(
                    "SELECT * FROM coupons WHERE code = ?", (coupon_code,)
                ).fetchone()
                if coupon is None:
                    raise DomainError(422, "INVALID_COUPON", "Coupon does not exist")
                redeemed = connection.execute(
                    "SELECT id FROM orders WHERE coupon_code = ?", (coupon_code,)
                ).fetchone()
                if redeemed:
                    raise DomainError(409, "COUPON_REDEEMED", "Coupon has already been redeemed")
                percent = coupon["discount_percent"]
            for item in cart["items"]:
                changed = connection.execute(
                    "UPDATE products SET inventory = inventory - ? WHERE id = ? AND inventory >= ?",
                    (item["quantity"], item["product_id"], item["quantity"]),
                ).rowcount
                if not changed:
                    raise DomainError(
                        409,
                        "INSUFFICIENT_INVENTORY",
                        "Requested quantity is no longer available",
                        product_id=item["product_id"],
                        available=item["inventory"],
                        requested=item["quantity"],
                    )
            subtotal = cart["subtotal_minor"]
            discount = (subtotal * percent + 50) // 100
            order_id = str(uuid4())
            connection.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_id,
                    cart_id,
                    coupon_code,
                    percent,
                    subtotal,
                    discount,
                    subtotal - discount,
                    timestamp(),
                ),
            )
            connection.executemany(
                "INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        order_id,
                        item["product_id"],
                        item["name"],
                        item["unit_price_minor"],
                        item["quantity"],
                        item["line_total_minor"],
                    )
                    for item in cart["items"]
                ],
            )
            connection.execute(
                "INSERT INTO checkout_requests VALUES (?, ?, ?, ?)",
                (key, cart_id, coupon_code, order_id),
            )
            return order_view(connection, order_id), False

    def get_order(self, order_id):
        with self.database.transaction() as connection:
            return order_view(connection, order_id)

    def generate_coupon(self):
        with self.database.transaction(write=True) as connection:
            count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            last = connection.execute("SELECT COALESCE(MAX(milestone), 0) FROM coupons").fetchone()[
                0
            ]
            milestone = last + self.database.settings.reward_every
            if milestone > count:
                raise DomainError(
                    409, "NO_ELIGIBLE_MILESTONE", "No unrewarded milestone is eligible"
                )
            coupon = {
                "code": uuid4().hex.upper(),
                "milestone": milestone,
                "discount_percent": self.database.settings.discount_percent,
                "created_at": timestamp(),
            }
            connection.execute("INSERT INTO coupons VALUES (?, ?, ?, ?)", tuple(coupon.values()))
            return {**coupon, "status": "AVAILABLE", "order_id": None}

    def coupons(self):
        with self.database.transaction() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT c.*, o.id AS order_id, CASE WHEN o.id IS NULL THEN 'AVAILABLE' "
                    "ELSE 'REDEEMED' END AS status FROM coupons c "
                    "LEFT JOIN orders o ON o.coupon_code = c.code ORDER BY c.milestone"
                )
            ]

    def report(self):
        with self.database.transaction() as connection:
            totals = dict(
                connection.execute(
                    "SELECT COUNT(*) AS total_orders, "
                    "COALESCE(SUM(subtotal_minor), 0) AS gross_minor, "
                    "COALESCE(SUM(discount_minor), 0) AS discounts_minor, "
                    "COALESCE(SUM(total_minor), 0) AS net_minor FROM orders"
                ).fetchone()
            )
            generated = connection.execute("SELECT COUNT(*) FROM coupons").fetchone()[0]
            redeemed = connection.execute(
                "SELECT COUNT(*) FROM orders WHERE coupon_code IS NOT NULL"
            ).fetchone()[0]
            quantities = [
                dict(row)
                for row in connection.execute(
                    "SELECT p.id AS product_id, "
                    "COALESCE(SUM(oi.quantity), 0) AS purchased_quantity "
                    "FROM products p LEFT JOIN order_items oi ON oi.product_id = p.id "
                    "GROUP BY p.id ORDER BY p.id"
                )
            ]
            return {
                "currency": "USD",
                **totals,
                "products": quantities,
                "coupons": {
                    "generated": generated,
                    "available": generated - redeemed,
                    "redeemed": redeemed,
                },
            }

    def update_product(self, product_id, changes):
        with self.database.transaction(write=True) as connection:
            require_row(connection, "products", product_id)
            for field, value in changes.items():
                connection.execute(
                    f"UPDATE products SET {field} = ? WHERE id = ?", (value, product_id)
                )
            return dict(require_row(connection, "products", product_id))
