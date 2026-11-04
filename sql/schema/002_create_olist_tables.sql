CREATE SCHEMA IF NOT EXISTS olist;

-- 1. Customers
CREATE TABLE IF NOT EXISTS olist.customers (
    customer_id VARCHAR(32) PRIMARY KEY,
    customer_unique_id VARCHAR(32) NOT NULL,
    customer_zip_code_prefix VARCHAR(5) NOT NULL,
    customer_city TEXT NOT NULL,
    customer_state CHAR(2) NOT NULL
);

-- 2. Geolocation
CREATE TABLE IF NOT EXISTS olist.geolocation (
    geolocation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    geolocation_zip_code_prefix VARCHAR(5) NOT NULL,
    geolocation_lat DOUBLE PRECISION NOT NULL,
    geolocation_lng DOUBLE PRECISION NOT NULL,
    geolocation_city TEXT NOT NULL,
    geolocation_state CHAR(2) NOT NULL
);

-- 3. Product Category Translation
CREATE TABLE IF NOT EXISTS olist.product_category_translation (
    product_category_name TEXT PRIMARY KEY,
    product_category_name_english TEXT
);

-- Preserve the two untranslated categories
INSERT INTO olist.product_category_translation
    (product_category_name, product_category_name_english)
VALUES
    ('pc_gamer', NULL),
    ('portateis_cozinha_e_preparadores_de_alimentos', NULL)
ON CONFLICT (product_category_name) DO NOTHING;

-- 4. Products
CREATE TABLE IF NOT EXISTS olist.products (
    product_id VARCHAR(32) PRIMARY KEY,
    product_category_name TEXT
        REFERENCES olist.product_category_translation(product_category_name),
    product_name_lenght INTEGER,
    product_description_lenght INTEGER,
    product_photos_qty INTEGER,
    product_weight_g INTEGER,
    product_length_cm INTEGER,
    product_height_cm INTEGER,
    product_width_cm INTEGER
);

-- 5. Sellers
CREATE TABLE IF NOT EXISTS olist.sellers (
    seller_id VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(5) NOT NULL,
    seller_city TEXT NOT NULL,
    seller_state CHAR(2) NOT NULL
);

-- 6. Orders
CREATE TABLE IF NOT EXISTS olist.orders (
    order_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL
        REFERENCES olist.customers(customer_id),
    order_status VARCHAR(30) NOT NULL,
    order_purchase_timestamp TIMESTAMP NOT NULL,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP NOT NULL
);

-- 7. Order Items
CREATE TABLE IF NOT EXISTS olist.order_items (
    order_id VARCHAR(32) NOT NULL
        REFERENCES olist.orders(order_id),
    order_item_id SMALLINT NOT NULL,
    product_id VARCHAR(32) NOT NULL
        REFERENCES olist.products(product_id),
    seller_id VARCHAR(32) NOT NULL
        REFERENCES olist.sellers(seller_id),
    shipping_limit_date TIMESTAMP NOT NULL,
    price NUMERIC(12,2) NOT NULL,
    freight_value NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

-- 8. Order Payments
CREATE TABLE IF NOT EXISTS olist.order_payments (
    order_id VARCHAR(32) NOT NULL
        REFERENCES olist.orders(order_id),
    payment_sequential SMALLINT NOT NULL,
    payment_type VARCHAR(30) NOT NULL,
    payment_installments SMALLINT NOT NULL,
    payment_value NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

-- 9. Order Reviews
CREATE TABLE IF NOT EXISTS olist.order_reviews (
    review_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_id VARCHAR(32) NOT NULL,
    order_id VARCHAR(32) NOT NULL
        REFERENCES olist.orders(order_id),
    review_score SMALLINT NOT NULL
        CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP NOT NULL,
    review_answer_timestamp TIMESTAMP NOT NULL
);
