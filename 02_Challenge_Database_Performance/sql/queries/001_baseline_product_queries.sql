-- Q1: Monthly sales by product category
EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
SELECT
    DATE_TRUNC('month', o.order_purchase_timestamp)::date AS sales_month,
    COALESCE(
        t.product_category_name_english,
        p.product_category_name,
        'uncategorized'
    ) AS category,
    ROUND(SUM(oi.price), 2) AS total_sales,
    COUNT(DISTINCT oi.order_id) AS unique_orders,
    ROUND(
        SUM(oi.price) / NULLIF(COUNT(DISTINCT oi.order_id), 0),
        2
    ) AS average_order_value
FROM olist.order_items oi
JOIN olist.orders o ON o.order_id = oi.order_id
JOIN olist.products p ON p.product_id = oi.product_id
LEFT JOIN olist.product_category_translation t
    ON t.product_category_name = p.product_category_name
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1, 2
ORDER BY 1, 2;


-- Q2: Delayed delivery rate by state and month
EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
SELECT
    DATE_TRUNC('month', o.order_purchase_timestamp)::date AS order_month,
    c.customer_state,
    COUNT(*) AS delivered_orders,
    COUNT(*) FILTER (
        WHERE o.order_delivered_customer_date >
              o.order_estimated_delivery_date
    ) AS delayed_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE o.order_delivered_customer_date >
                  o.order_estimated_delivery_date
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS delayed_percentage
FROM olist.orders o
JOIN olist.customers c ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2;


-- Q3: Relationship between delivery delay and review score
EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
WITH delivery_reviews AS (
    SELECT
        r.review_score,
        EXTRACT(
            EPOCH FROM (
                o.order_delivered_customer_date -
                o.order_estimated_delivery_date
            )
        ) AS delay_seconds
    FROM olist.orders o
    JOIN olist.order_reviews r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
)
SELECT
    CASE
        WHEN delay_seconds < -86400 THEN '01 - Early > 1 day'
        WHEN delay_seconds < 0 THEN '02 - Early <= 1 day'
        WHEN delay_seconds = 0 THEN '03 - On time'
        WHEN delay_seconds <= 604800 THEN '04 - Late <= 7 days'
        ELSE '05 - Late > 7 days'
    END AS delay_group,
    review_score,
    COUNT(*) AS review_count,
    ROUND(AVG(delay_seconds)::numeric / 86400, 2) AS average_delay_days
FROM delivery_reviews
GROUP BY 1, 2
ORDER BY 1, 2;


-- Q4: Top 20 sellers by revenue and performance
EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
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
FROM seller_order so
JOIN olist.orders o ON o.order_id = so.order_id
JOIN olist.sellers s ON s.seller_id = so.seller_id
LEFT JOIN review_by_order r ON r.order_id = so.order_id
GROUP BY s.seller_id, s.seller_state, s.seller_city
ORDER BY total_revenue DESC
LIMIT 20;


-- Q5: Payment distribution and relationship with order value
EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
WITH order_values AS (
    SELECT
        order_id,
        SUM(payment_value) AS order_value,
        MAX(payment_installments) AS max_installments
    FROM olist.order_payments
    GROUP BY order_id
),
payment_correlation AS (
    SELECT
        CORR(
            max_installments::double precision,
            order_value::double precision
        ) AS installment_order_value_correlation
    FROM order_values
)
SELECT
    p.payment_type,
    p.payment_installments,
    COUNT(*) AS payment_records,
    COUNT(DISTINCT p.order_id) AS unique_orders,
    ROUND(SUM(p.payment_value), 2) AS total_payment_value,
    ROUND(AVG(p.payment_value), 2) AS average_payment_value,
    ROUND(
        pc.installment_order_value_correlation::numeric,
        4
    ) AS installment_order_value_correlation
FROM olist.order_payments p
CROSS JOIN payment_correlation pc
GROUP BY
    p.payment_type,
    p.payment_installments,
    pc.installment_order_value_correlation
ORDER BY p.payment_type, p.payment_installments;