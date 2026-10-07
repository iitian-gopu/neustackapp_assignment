CREATE TABLE IF NOT EXISTS reward_policy (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    reward_every INTEGER NOT NULL CHECK (reward_every > 0),
    discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 1 AND 100)
);
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor BETWEEN 0 AND 100000000),
    inventory INTEGER NOT NULL CHECK (inventory BETWEEN 0 AND 1000000)
);
CREATE TABLE IF NOT EXISTS carts (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cart_items (
    cart_id TEXT NOT NULL REFERENCES carts(id),
    product_id TEXT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 10000),
    PRIMARY KEY (cart_id, product_id)
);
CREATE TABLE IF NOT EXISTS coupons (
    code TEXT PRIMARY KEY,
    milestone INTEGER NOT NULL UNIQUE CHECK (milestone > 0),
    discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 1 AND 100),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    cart_id TEXT NOT NULL UNIQUE REFERENCES carts(id),
    coupon_code TEXT UNIQUE REFERENCES coupons(code),
    discount_percent INTEGER NOT NULL CHECK (discount_percent BETWEEN 0 AND 100),
    subtotal_minor INTEGER NOT NULL CHECK (subtotal_minor >= 0),
    discount_minor INTEGER NOT NULL CHECK (discount_minor BETWEEN 0 AND subtotal_minor),
    total_minor INTEGER NOT NULL CHECK (total_minor = subtotal_minor - discount_minor),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    order_id TEXT NOT NULL REFERENCES orders(id),
    product_id TEXT NOT NULL REFERENCES products(id),
    name TEXT NOT NULL,
    unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_total_minor INTEGER NOT NULL CHECK (line_total_minor = unit_price_minor * quantity),
    PRIMARY KEY (order_id, product_id)
);
CREATE TABLE IF NOT EXISTS checkout_requests (
    key TEXT PRIMARY KEY,
    cart_id TEXT NOT NULL REFERENCES carts(id),
    coupon_code TEXT,
    order_id TEXT NOT NULL UNIQUE REFERENCES orders(id)
);
