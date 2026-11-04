SET work_mem = '64MB';
SET jit = off;

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


