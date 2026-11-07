-- 1. Single-table view
CREATE OR REPLACE VIEW olist.v_delivered_orders AS
SELECT
    order_id,
    customer_id,
    order_purchase_timestamp,
    order_delivered_customer_date,
    order_estimated_delivery_date
FROM olist.orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL;


-- 2. Multi-table analytical view
CREATE OR REPLACE VIEW olist.v_seller_performance_live AS
WITH seller_order AS (
    SELECT
        seller_id,
        order_id,
        SUM(price) AS order_revenue
    FROM olist.order_items
    GROUP BY seller_id, order_id
),
review_by_order AS (
    SELECT
        order_id,
        AVG(review_score::numeric) AS average_review
    FROM olist.order_reviews
    GROUP BY order_id
)
SELECT
    s.seller_id,
    s.seller_state,
    s.seller_city,
    ROUND(SUM(so.order_revenue), 2) AS total_revenue,
    COUNT(*) AS seller_orders,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (
            o.order_delivered_carrier_date - o.order_approved_at
        )) / 3600)::numeric, 2
    ) AS average_preparation_hours,
    ROUND(AVG(r.average_review), 2) AS average_review_score
FROM seller_order so
JOIN olist.orders o ON o.order_id = so.order_id
JOIN olist.sellers s ON s.seller_id = so.seller_id
LEFT JOIN review_by_order r ON r.order_id = so.order_id
GROUP BY s.seller_id, s.seller_state, s.seller_city;


-- 3. Monthly snapshot storage
CREATE TABLE IF NOT EXISTS olist.monthly_sales_cache (
    sales_month DATE NOT NULL,
    category TEXT NOT NULL,
    total_sales NUMERIC(14,2) NOT NULL,
    unique_orders BIGINT NOT NULL,
    average_order_value NUMERIC(14,2),
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sales_month, category),
    CHECK (total_sales >= 0),
    CHECK (unique_orders >= 0)
);


-- 4. Idempotent monthly procedure
CREATE OR REPLACE PROCEDURE olist.refresh_monthly_sales(
    p_month DATE
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_month DATE;
BEGIN
    IF p_month IS NULL THEN
        RAISE EXCEPTION 'Month cannot be NULL';
    END IF;

    v_month := DATE_TRUNC('month', p_month)::DATE;

    DELETE FROM olist.monthly_sales_cache
    WHERE sales_month = v_month;

    INSERT INTO olist.monthly_sales_cache (
        sales_month,
        category,
        total_sales,
        unique_orders,
        average_order_value,
        refreshed_at
    )
    SELECT
        v_month,
        COALESCE(
            t.product_category_name_english,
            p.product_category_name,
            'uncategorized'
        ),
        ROUND(SUM(oi.price), 2),
        COUNT(DISTINCT oi.order_id),
        ROUND(
            SUM(oi.price) /
            NULLIF(COUNT(DISTINCT oi.order_id), 0),
            2
        ),
        NOW()
    FROM olist.order_items oi
    JOIN olist.orders o ON o.order_id = oi.order_id
    JOIN olist.products p ON p.product_id = oi.product_id
    LEFT JOIN olist.product_category_translation t
        ON t.product_category_name = p.product_category_name
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= v_month
      AND o.order_purchase_timestamp < v_month + INTERVAL '1 month'
    GROUP BY 1, 2;
END;
$$;