BEGIN;

ALTER TABLE capstone.order_features
    ADD COLUMN IF NOT EXISTS customer_history_available SMALLINT;

ALTER TABLE capstone.order_features
    ADD COLUMN IF NOT EXISTS customer_review_history_available SMALLINT;

ALTER TABLE capstone.order_features
    ADD COLUMN IF NOT EXISTS seller_review_history_available SMALLINT;

-- Build customer events using the stable customer identity
WITH customer_events AS (

    SELECT
        c.customer_unique_id,
        o.order_approved_at::date AS event_date,
        COUNT(*)::bigint AS approved_orders,
        0::bigint AS reviewed_orders,
        0::bigint AS negative_orders
    FROM olist.orders o
    JOIN olist.customers c
        ON c.customer_id = o.customer_id
    WHERE o.order_approved_at IS NOT NULL
    GROUP BY c.customer_unique_id, o.order_approved_at::date

    UNION ALL

    SELECT
        c.customer_unique_id,
        l.last_review_date AS event_date,
        0::bigint,
        COUNT(*)::bigint,
        COUNT(*) FILTER (WHERE l.target = 1)::bigint
    FROM capstone.order_labels l
    JOIN olist.orders o
        ON o.order_id = l.order_id
    JOIN olist.customers c
        ON c.customer_id = o.customer_id
    WHERE l.last_review_date IS NOT NULL
      AND l.last_review_date > l.approved_at::date
    GROUP BY c.customer_unique_id, l.last_review_date
),

customer_daily AS (
    SELECT
        customer_unique_id,
        event_date,
        SUM(approved_orders) AS approved_orders,
        SUM(reviewed_orders) AS reviewed_orders,
        SUM(negative_orders) AS negative_orders
    FROM customer_events
    GROUP BY customer_unique_id, event_date
),

customer_cumulative AS (
    SELECT
        customer_unique_id,
        event_date,

        COALESCE(
            SUM(approved_orders) OVER (
                PARTITION BY customer_unique_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_approved_orders,

        MAX(event_date) FILTER (
            WHERE approved_orders > 0
        ) OVER (
            PARTITION BY customer_unique_id
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS previous_order_date,

        COALESCE(
            SUM(reviewed_orders) OVER (
                PARTITION BY customer_unique_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_reviewed_orders,

        COALESCE(
            SUM(negative_orders) OVER (
                PARTITION BY customer_unique_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_negative_orders

    FROM customer_daily
),

history AS (
    SELECT
        f.order_id,
        COALESCE(h.prior_approved_orders, 0) AS prior_orders,
        h.previous_order_date,
        COALESCE(h.prior_reviewed_orders, 0) AS prior_reviews,
        COALESCE(h.prior_negative_orders, 0) AS prior_negative
    FROM capstone.order_features f
    JOIN olist.orders o
        ON o.order_id = f.order_id
    JOIN olist.customers c
        ON c.customer_id = o.customer_id
    LEFT JOIN customer_cumulative h
        ON h.customer_unique_id = c.customer_unique_id
       AND h.event_date = f.approved_at::date
)

UPDATE capstone.order_features f
SET
    customer_prior_approved_order_count = h.prior_orders,

    customer_previous_order_date = h.previous_order_date,

    customer_days_since_previous_order =
        CASE
            WHEN h.previous_order_date IS NOT NULL
            THEN (f.approved_at::date - h.previous_order_date)::integer
        END,

    customer_prior_reviewed_order_count = h.prior_reviews,

    customer_prior_negative_review_rate =
        h.prior_negative::numeric / NULLIF(h.prior_reviews, 0),

    customer_history_available =
        CASE WHEN h.prior_orders > 0 THEN 1 ELSE 0 END,

    customer_review_history_available =
        CASE WHEN h.prior_reviews > 0 THEN 1 ELSE 0 END

FROM history h
WHERE f.order_id = h.order_id;

-- Seller history availability indicator
UPDATE capstone.order_features
SET seller_review_history_available =
    CASE
        WHEN prior_seller_review_count > 0 THEN 1
        ELSE 0
    END;

ANALYZE capstone.order_features;

COMMIT;

-- Customer history validation
SELECT
    COUNT(*) AS total_orders,

    COUNT(*) FILTER (
        WHERE customer_prior_approved_order_count > 0
    ) AS orders_with_customer_history,

    COUNT(*) FILTER (
        WHERE customer_prior_reviewed_order_count > 0
    ) AS orders_with_customer_review_history,

    COUNT(*) FILTER (
        WHERE customer_history_available = 1
    ) AS history_indicator_positive,

    COUNT(*) FILTER (
        WHERE customer_review_history_available = 1
    ) AS review_history_indicator_positive

FROM capstone.order_features;

-- Seller history validation
SELECT
    COUNT(*) FILTER (
        WHERE seller_review_history_available = 1
    ) AS orders_with_seller_review_history,

    COUNT(*) FILTER (
        WHERE seller_review_history_available = 0
    ) AS orders_without_seller_review_history,

    COUNT(*) FILTER (
        WHERE prior_seller_review_count > 0
          AND prior_seller_avg_review_score IS NULL
    ) AS inconsistent_seller_history

FROM capstone.order_features;

-- Orders with no item records
SELECT
    o.order_status,
    COUNT(*) AS orders,
    SUM(f.target) AS negative_orders
FROM capstone.order_features f
JOIN olist.orders o USING (order_id)
WHERE f.item_count = 0
GROUP BY o.order_status
ORDER BY orders DESC;

-- Orders with no payment records
SELECT
    f.order_id,
    o.order_status,
    f.approved_at,
    f.target,
    f.item_count
FROM capstone.order_features f
JOIN olist.orders o USING (order_id)
WHERE f.payment_record_count = 0;

-- Product missing values
SELECT
    COUNT(*) FILTER (WHERE avg_product_weight_g IS NULL)
        AS missing_weight,
    COUNT(*) FILTER (WHERE avg_product_photos_qty IS NULL)
        AS missing_photos,
    COUNT(*) FILTER (WHERE avg_product_volume_cm3 IS NULL)
        AS missing_volume,
    COUNT(*) FILTER (WHERE customer_seller_distance_km IS NULL)
        AS missing_distance
FROM capstone.order_features;
