-- Candidate rewrites for the live Olist dashboard queries.
-- Run in the Challenge 02 folder against the existing PostgreSQL container.
-- Existing baseline queries and indexes are intentionally left unchanged.
--
-- Keep the same session settings for repeatable comparisons.
SET work_mem = '64MB';
SET jit = off;

-- ============================================================
-- Q1: Monthly sales by category
-- Rewrite COUNT(DISTINCT order_id) as two-stage aggregation.
-- The first stage produces one row per month/category/order.
-- ============================================================

EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
WITH order_category_sales AS MATERIALIZED (
    SELECT
        DATE_TRUNC('month', o.order_purchase_timestamp)::date AS sales_month,
        COALESCE(
            t.product_category_name_english,
            p.product_category_name,
            'uncategorized'
        ) AS category,
        oi.order_id,
        SUM(oi.price) AS order_category_sales
    FROM olist.order_items AS oi
    JOIN olist.orders AS o
        ON o.order_id = oi.order_id
    JOIN olist.products AS p
        ON p.product_id = oi.product_id
    LEFT JOIN olist.product_category_translation AS t
        ON t.product_category_name = p.product_category_name
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY
        DATE_TRUNC('month', o.order_purchase_timestamp)::date,
        COALESCE(
            t.product_category_name_english,
            p.product_category_name,
            'uncategorized'
        ),
        oi.order_id
)
SELECT
    sales_month,
    category,
    ROUND(SUM(order_category_sales), 2) AS total_sales,
    COUNT(*) AS unique_orders,
    ROUND(
        SUM(order_category_sales) / NULLIF(COUNT(*), 0),
        2
    ) AS average_order_value
FROM order_category_sales
GROUP BY sales_month, category
ORDER BY sales_month, category;


-- ============================================================
-- Q4: Top 20 sellers
-- Find the top 20 from revenue first. Then retrieve order and
-- review metrics only for those sellers, using existing
-- (seller_id, order_id) and order_reviews(order_id) indexes.
-- ============================================================

EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
WITH top_sellers AS MATERIALIZED (
    SELECT
        oi.seller_id,
        SUM(oi.price) AS total_revenue
    FROM olist.order_items AS oi
    GROUP BY oi.seller_id
    ORDER BY SUM(oi.price) DESC
    LIMIT 20
),
top_seller_orders AS MATERIALIZED (
    SELECT
        ts.seller_id,
        seller_orders.order_id
    FROM top_sellers AS ts
    JOIN LATERAL (
        SELECT oi.order_id
        FROM olist.order_items AS oi
        WHERE oi.seller_id = ts.seller_id
        GROUP BY oi.order_id
    ) AS seller_orders
        ON TRUE
),
top_seller_order_ids AS MATERIALIZED (
    SELECT DISTINCT order_id
    FROM top_seller_orders
),
review_by_order AS MATERIALIZED (
    SELECT
        r.order_id,
        AVG(r.review_score::numeric) AS average_review
    FROM top_seller_order_ids AS ids
    JOIN olist.order_reviews AS r
        ON r.order_id = ids.order_id
    GROUP BY r.order_id
),
seller_metrics AS (
    SELECT
        tso.seller_id,
        COUNT(*) AS seller_orders,
        ROUND(
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        o.order_delivered_carrier_date -
                        o.order_approved_at
                    )
                ) / 3600
            )::numeric,
            2
        ) AS average_preparation_hours,
        ROUND(AVG(r.average_review), 2) AS average_review_score
    FROM top_seller_orders AS tso
    JOIN olist.orders AS o
        ON o.order_id = tso.order_id
    LEFT JOIN review_by_order AS r
        ON r.order_id = tso.order_id
    GROUP BY tso.seller_id
)
SELECT
    ts.seller_id,
    s.seller_state,
    s.seller_city,
    ROUND(ts.total_revenue, 2) AS total_revenue,
    sm.seller_orders,
    sm.average_preparation_hours,
    sm.average_review_score
FROM top_sellers AS ts
JOIN olist.sellers AS s
    ON s.seller_id = ts.seller_id
JOIN seller_metrics AS sm
    ON sm.seller_id = ts.seller_id
ORDER BY ts.total_revenue DESC;


-- ============================================================
-- Q5: Payment distribution and order-value correlation
-- GROUPING SETS computes order-level, payment-group-level,
-- and payment-group/order-level aggregates from one table scan.
-- No new index or precomputed snapshot is used.
-- ============================================================

EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
WITH payment_rollup AS MATERIALIZED (
    SELECT
        payment_type,
        payment_installments,
        order_id,
        GROUPING(
            payment_type,
            payment_installments,
            order_id
        ) AS grouping_level,
        COUNT(*) AS payment_records,
        SUM(payment_value) AS total_payment_value,
        AVG(payment_value) AS average_payment_value,
        MAX(payment_installments) AS max_installments
    FROM olist.order_payments
    GROUP BY GROUPING SETS (
        (order_id),
        (payment_type, payment_installments),
        (payment_type, payment_installments, order_id)
    )
),
order_correlation AS (
    SELECT
        CORR(
            max_installments::double precision,
            total_payment_value::double precision
        ) AS installment_order_value_correlation
    FROM payment_rollup
    WHERE grouping_level = 6
),
payment_distribution AS (
    SELECT
        payment_type,
        payment_installments,
        MAX(payment_records)
            FILTER (WHERE grouping_level = 1) AS payment_records,
        COUNT(*)
            FILTER (WHERE grouping_level = 0) AS unique_orders,
        MAX(total_payment_value)
            FILTER (WHERE grouping_level = 1) AS total_payment_value,
        MAX(average_payment_value)
            FILTER (WHERE grouping_level = 1) AS average_payment_value
    FROM payment_rollup
    WHERE grouping_level IN (0, 1)
    GROUP BY payment_type, payment_installments
)
SELECT
    d.payment_type,
    d.payment_installments,
    d.payment_records,
    d.unique_orders,
    ROUND(d.total_payment_value, 2) AS total_payment_value,
    ROUND(d.average_payment_value, 2) AS average_payment_value,
    ROUND(
        c.installment_order_value_correlation::numeric,
        4
    ) AS installment_order_value_correlation
FROM payment_distribution AS d
CROSS JOIN order_correlation AS c
ORDER BY d.payment_type, d.payment_installments;
