PRAGMA foreign_keys = ON;

CREATE TABLE zip_codes (
    zip_prefix INTEGER PRIMARY KEY,
    city       TEXT,
    state      TEXT,
    lat        REAL,
    lng        REAL
);

CREATE TABLE customers (
    customer_id        TEXT PRIMARY KEY,
    customer_unique_id TEXT NOT NULL,
    zip_prefix         INTEGER NOT NULL REFERENCES zip_codes(zip_prefix)
);

CREATE TABLE sellers (
    seller_id  TEXT PRIMARY KEY,
    zip_prefix INTEGER NOT NULL REFERENCES zip_codes(zip_prefix)
);

CREATE TABLE product_categories (
    category_name    TEXT PRIMARY KEY,
    category_name_en TEXT
);

CREATE TABLE products (
    product_id    TEXT PRIMARY KEY,
    category_name TEXT REFERENCES product_categories(category_name),
    name_length   INTEGER,
    description_length INTEGER,
    photos_qty    INTEGER,
    weight_g      REAL,
    length_cm     REAL,
    height_cm     REAL,
    width_cm      REAL
);

CREATE TABLE orders (
    order_id                      TEXT PRIMARY KEY,
    customer_id                   TEXT NOT NULL REFERENCES customers(customer_id),
    order_status                  TEXT NOT NULL,
    order_purchase_timestamp      TEXT NOT NULL,
    order_approved_at             TEXT,
    order_delivered_carrier_date  TEXT,
    order_delivered_customer_date TEXT,
    order_estimated_delivery_date TEXT
);

CREATE TABLE order_items (
    order_id            TEXT    NOT NULL REFERENCES orders(order_id),
    order_item_id       INTEGER NOT NULL,
    product_id          TEXT    NOT NULL REFERENCES products(product_id),
    seller_id           TEXT    NOT NULL REFERENCES sellers(seller_id),
    shipping_limit_date TEXT,
    price               REAL    NOT NULL,
    freight_value       REAL    NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE order_payments (
    order_id             TEXT    NOT NULL REFERENCES orders(order_id),
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT    NOT NULL,
    payment_installments INTEGER,
    payment_value        REAL    NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE order_reviews (
    review_pk               INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id               TEXT NOT NULL,
    order_id                TEXT NOT NULL REFERENCES orders(order_id),
    review_score            INTEGER NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title    TEXT,
    review_comment_message  TEXT,
    review_creation_date    TEXT,
    review_answer_timestamp TEXT
);

CREATE INDEX idx_orders_customer  ON orders(customer_id);
CREATE INDEX idx_orders_purchase  ON orders(order_purchase_timestamp);
CREATE INDEX idx_items_product    ON order_items(product_id);
CREATE INDEX idx_items_seller     ON order_items(seller_id);
CREATE INDEX idx_reviews_order    ON order_reviews(order_id);
CREATE INDEX idx_customers_unique ON customers(customer_unique_id);
