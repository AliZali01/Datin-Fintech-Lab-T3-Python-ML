BEGIN;

DROP TABLE IF EXISTS capstone.order_features;

CREATE TABLE capstone.order_features AS

WITH

-- 1. Labeled orders and decision timestamps
base AS MATERIALIZED (
    SELECT
        l.order_id,
        l.approved_at,
        l.target,
        o.customer_id,
        o.order_purchase_timestamp,
        o.order_estimated_delivery_date,
        c.customer_state,
        c.customer_zip_code_prefix
    FROM capstone.order_labels l
    JOIN olist.orders o
        ON o.order_id = l.order_id
    LEFT JOIN olist.customers c
        ON c.customer_id = o.customer_id
    WHERE l.approved_at IS NOT NULL
),

-- 2. ZIP-level geographic centroids
geo_zip AS MATERIALIZED (
    SELECT
        geolocation_zip_code_prefix AS zip_code,
        AVG(geolocation_lat) AS latitude,
        AVG(geolocation_lng) AS longitude
    FROM olist.geolocation
    WHERE geolocation_zip_code_prefix IS NOT NULL
      AND geolocation_lat IS NOT NULL
      AND geolocation_lng IS NOT NULL
    GROUP BY geolocation_zip_code_prefix
),

-- 3. Unique seller/order relationships
order_sellers AS MATERIALIZED (
    SELECT DISTINCT
        order_id,
        seller_id
    FROM olist.order_items
    WHERE seller_id IS NOT NULL
),

-- 4. Order item aggregates
item_agg AS (
    SELECT
        oi.order_id,
        COUNT(*)::integer AS item_count,
        COUNT(DISTINCT oi.product_id)::integer AS unique_product_count,
        COUNT(DISTINCT oi.seller_id)::integer AS unique_seller_count,
        SUM(oi.price) AS total_item_price,
        SUM(oi.freight_value) AS total_freight_value,
        AVG(oi.price) AS avg_item_price
    FROM olist.order_items oi
    JOIN base b ON b.order_id = oi.order_id
    GROUP BY oi.order_id
),

-- 5. Product attributes
product_agg AS (
    SELECT
        oi.order_id,
        COUNT(DISTINCT p.product_category_name)::integer
            AS product_category_count,
        AVG(p.product_weight_g::numeric)
            AS avg_product_weight_g,
        AVG(p.product_photos_qty::numeric)
            AS avg_product_photos_qty,
        AVG(p.product_description_lenght::numeric)
            AS avg_product_description_length,
        AVG(
            p.product_length_cm::numeric
            * p.product_width_cm
            * p.product_height_cm
        ) AS avg_product_volume_cm3
    FROM olist.order_items oi
    JOIN base b ON b.order_id = oi.order_id
    LEFT JOIN olist.products p
        ON p.product_id = oi.product_id
    GROUP BY oi.order_id
),

-- 6. Payment aggregates
payment_agg AS (
    SELECT
        op.order_id,
        COUNT(*)::integer AS payment_record_count,
        COUNT(DISTINCT op.payment_type)::integer
            AS payment_type_count,
        SUM(op.payment_value) AS payment_total_value,
        AVG(op.payment_installments::numeric)
            AS avg_payment_installments,
        MAX(op.payment_installments)
            AS max_payment_installments
    FROM olist.order_payments op
    JOIN base b ON b.order_id = op.order_id
    GROUP BY op.order_id
),

-- 7. Current seller geography
seller_agg AS (
    SELECT
        os.order_id,
        COUNT(DISTINCT os.seller_id)::integer
            AS seller_count,
        COUNT(DISTINCT s.seller_state)::integer
            AS seller_state_count,
        AVG(g.latitude) AS avg_seller_latitude,
        AVG(g.longitude) AS avg_seller_longitude,
        AVG(
            CASE
                WHEN s.seller_state IS NULL
                  OR b.customer_state IS NULL THEN NULL
                WHEN s.seller_state = b.customer_state THEN 1.0
                ELSE 0.0
            END
        ) AS same_state_seller_share
    FROM order_sellers os
    JOIN base b ON b.order_id = os.order_id
    LEFT JOIN olist.sellers s
        ON s.seller_id = os.seller_id
    LEFT JOIN geo_zip g
        ON g.zip_code = s.seller_zip_code_prefix
    GROUP BY os.order_id
),

-- 8. Customer event history
customer_events AS (
    SELECT
        o.customer_id,
        o.order_approved_at::date AS event_date,
        COUNT(*)::bigint AS approved_orders,
        0::bigint AS reviewed_orders,
        0::bigint AS negative_orders
    FROM olist.orders o
    WHERE o.order_approved_at IS NOT NULL
    GROUP BY o.customer_id, o.order_approved_at::date

    UNION ALL

    SELECT
        o.customer_id,
        l.last_review_date AS event_date,
        0::bigint,
        COUNT(*)::bigint,
        COUNT(*) FILTER (WHERE l.target = 1)::bigint
    FROM capstone.order_labels l
    JOIN olist.orders o
        ON o.order_id = l.order_id
    WHERE l.last_review_date IS NOT NULL
      AND l.last_review_date > l.approved_at::date
    GROUP BY o.customer_id, l.last_review_date
),

customer_daily AS (
    SELECT
        customer_id,
        event_date,
        SUM(approved_orders) AS approved_orders,
        SUM(reviewed_orders) AS reviewed_orders,
        SUM(negative_orders) AS negative_orders
    FROM customer_events
    GROUP BY customer_id, event_date
),

-- Only strictly earlier calendar days are included
customer_cumulative AS (
    SELECT
        customer_id,
        event_date,

        COALESCE(
            SUM(approved_orders) OVER (
                PARTITION BY customer_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_approved_orders,

        MAX(event_date) FILTER (
            WHERE approved_orders > 0
        ) OVER (
            PARTITION BY customer_id
            ORDER BY event_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS previous_order_date,

        COALESCE(
            SUM(reviewed_orders) OVER (
                PARTITION BY customer_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_reviewed_orders,

        COALESCE(
            SUM(negative_orders) OVER (
                PARTITION BY customer_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_negative_orders

    FROM customer_daily
),

customer_history AS (
    SELECT
        b.order_id,
        ch.prior_approved_orders,
        ch.previous_order_date,
        ch.prior_reviewed_orders,
        ch.prior_negative_orders
    FROM base b
    LEFT JOIN customer_cumulative ch
        ON ch.customer_id = b.customer_id
       AND ch.event_date = b.approved_at::date
),

-- 9. Seller historical order and review events
seller_events AS (
    SELECT
        os.seller_id,
        o.order_approved_at::date AS event_date,
        COUNT(DISTINCT os.order_id)::bigint AS approved_orders,
        0::bigint AS review_count,
        0::numeric AS review_score_sum
    FROM order_sellers os
    JOIN olist.orders o
        ON o.order_id = os.order_id
    WHERE o.order_approved_at IS NOT NULL
    GROUP BY os.seller_id, o.order_approved_at::date

    UNION ALL

    SELECT
        os.seller_id,
        r.review_creation_date::date,
        0::bigint,
        COUNT(*)::bigint,
        COALESCE(SUM(r.review_score), 0)::numeric
    FROM order_sellers os
    JOIN olist.order_reviews r
        ON r.order_id = os.order_id
    JOIN olist.orders ro
        ON ro.order_id = r.order_id
    WHERE r.review_score IS NOT NULL
      AND r.review_creation_date IS NOT NULL
      AND ro.order_approved_at IS NOT NULL
      AND r.review_creation_date::date > ro.order_approved_at::date
    GROUP BY os.seller_id, r.review_creation_date::date
),

seller_daily AS (
    SELECT
        seller_id,
        event_date,
        SUM(approved_orders) AS approved_orders,
        SUM(review_count) AS review_count,
        SUM(review_score_sum) AS review_score_sum
    FROM seller_events
    GROUP BY seller_id, event_date
),

seller_cumulative AS (
    SELECT
        seller_id,
        event_date,

        COALESCE(
            SUM(approved_orders) OVER (
                PARTITION BY seller_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_approved_orders,

        COALESCE(
            SUM(review_count) OVER (
                PARTITION BY seller_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_review_count,

        COALESCE(
            SUM(review_score_sum) OVER (
                PARTITION BY seller_id
                ORDER BY event_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ), 0
        ) AS prior_review_score_sum

    FROM seller_daily
),

seller_history AS (
    SELECT
        os.order_id,

        AVG(
            COALESCE(sc.prior_approved_orders, 0)::numeric
        ) AS avg_prior_seller_orders,

        MAX(
            COALESCE(sc.prior_approved_orders, 0)
        ) AS max_prior_seller_orders,

        SUM(
            COALESCE(sc.prior_review_count, 0)
        ) AS prior_seller_review_count,

        SUM(
            COALESCE(sc.prior_review_score_sum, 0)
        ) / NULLIF(
            SUM(COALESCE(sc.prior_review_count, 0)), 0
        ) AS prior_seller_avg_review_score

    FROM order_sellers os
    JOIN base b ON b.order_id = os.order_id
    LEFT JOIN seller_cumulative sc
        ON sc.seller_id = os.seller_id
       AND sc.event_date = b.approved_at::date
    GROUP BY os.order_id
),

-- 10. Combine current and historical features
joined AS (
    SELECT
        b.order_id,
        b.approved_at,
        b.target,
        b.customer_state,

        EXTRACT(
            EPOCH FROM (
                b.approved_at - b.order_purchase_timestamp
            )
        ) / 60.0 AS purchase_to_approval_minutes,

        EXTRACT(
            EPOCH FROM (
                b.order_estimated_delivery_date - b.approved_at
            )
        ) / 86400.0 AS estimated_delivery_days_from_approval,

        cg.latitude AS customer_latitude,
        cg.longitude AS customer_longitude,

        COALESCE(ia.item_count, 0) AS item_count,
        COALESCE(ia.unique_product_count, 0)
            AS unique_product_count,
        COALESCE(ia.unique_seller_count, 0)
            AS unique_seller_count,

        COALESCE(ia.total_item_price, 0)
            AS total_item_price,
        COALESCE(ia.total_freight_value, 0)
            AS total_freight_value,
        ia.avg_item_price,

        COALESCE(pa.payment_record_count, 0)
            AS payment_record_count,
        COALESCE(pa.payment_type_count, 0)
            AS payment_type_count,
        COALESCE(pa.payment_total_value, 0)
            AS payment_total_value,
        pa.avg_payment_installments,
        pa.max_payment_installments,

        COALESCE(pr.product_category_count, 0)
            AS product_category_count,
        pr.avg_product_weight_g,
        pr.avg_product_photos_qty,
        pr.avg_product_description_length,
        pr.avg_product_volume_cm3,

        COALESCE(sa.seller_state_count, 0)
            AS seller_state_count,
        sa.avg_seller_latitude,
        sa.avg_seller_longitude,
        sa.same_state_seller_share,

        COALESCE(ch.prior_approved_orders, 0)
            AS customer_prior_approved_order_count,

        CASE
            WHEN ch.previous_order_date IS NOT NULL
            THEN (
                b.approved_at::date - ch.previous_order_date
            )::integer
        END AS customer_days_since_previous_order,

        ch.previous_order_date AS customer_previous_order_date,

        COALESCE(ch.prior_reviewed_orders, 0)
            AS customer_prior_reviewed_order_count,

        CASE
            WHEN COALESCE(ch.prior_reviewed_orders, 0) > 0
            THEN ch.prior_negative_orders::numeric
                 / ch.prior_reviewed_orders
        END AS customer_prior_negative_review_rate,

        COALESCE(sh.avg_prior_seller_orders, 0)
            AS avg_prior_seller_orders,
        COALESCE(sh.max_prior_seller_orders, 0)
            AS max_prior_seller_orders,
        COALESCE(sh.prior_seller_review_count, 0)
            AS prior_seller_review_count,
        sh.prior_seller_avg_review_score

    FROM base b

    LEFT JOIN geo_zip cg
        ON cg.zip_code = b.customer_zip_code_prefix

    LEFT JOIN item_agg ia
        ON ia.order_id = b.order_id

    LEFT JOIN product_agg pr
        ON pr.order_id = b.order_id

    LEFT JOIN payment_agg pa
        ON pa.order_id = b.order_id

    LEFT JOIN seller_agg sa
        ON sa.order_id = b.order_id

    LEFT JOIN customer_history ch
        ON ch.order_id = b.order_id

    LEFT JOIN seller_history sh
        ON sh.order_id = b.order_id
)

SELECT
    j.*,

    CASE
        WHEN j.customer_latitude IS NOT NULL
         AND j.avg_seller_latitude IS NOT NULL
        THEN
            6371.0 * 2 * ASIN(
                SQRT(
                    LEAST(
                        1.0,
                        POWER(
                            SIN(
                                RADIANS(
                                    j.avg_seller_latitude
                                    - j.customer_latitude
                                ) / 2.0
                            ), 2
                        )
                        +
                        COS(RADIANS(j.customer_latitude))
                        * COS(RADIANS(j.avg_seller_latitude))
                        * POWER(
                            SIN(
                                RADIANS(
                                    j.avg_seller_longitude
                                    - j.customer_longitude
                                ) / 2.0
                            ), 2
                        )
                    )
                )
            )
    END AS customer_seller_distance_km,

    j.total_freight_value
        / NULLIF(j.total_item_price, 0)
        AS freight_to_price_ratio,

    j.payment_total_value
        / NULLIF(
            j.total_item_price + j.total_freight_value, 0
        ) AS payment_to_order_value_ratio

FROM joined j;

-- 11. Indexes
CREATE UNIQUE INDEX order_features_order_id_idx
    ON capstone.order_features(order_id);

CREATE INDEX order_features_approved_at_idx
    ON capstone.order_features(approved_at);

ANALYZE capstone.order_features;

COMMIT;

-- 12. Validation
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT order_id) AS unique_orders,
    COUNT(*) FILTER (WHERE target = 1) AS negative_orders,
    COUNT(*) FILTER (WHERE target = 0) AS nonnegative_orders,
    COUNT(*) FILTER (
        WHERE customer_latitude IS NULL
    ) AS missing_customer_coordinates,
    COUNT(*) FILTER (
        WHERE customer_seller_distance_km IS NULL
    ) AS missing_distance
FROM capstone.order_features;

-- Temporal integrity checks
SELECT
    COUNT(*) FILTER (
        WHERE customer_previous_order_date >= approved_at::date
    ) AS invalid_customer_history,

    COUNT(*) FILTER (
        WHERE customer_days_since_previous_order < 0
    ) AS negative_history_days,

    COUNT(*) FILTER (
        WHERE purchase_to_approval_minutes < 0
    ) AS negative_approval_intervals,

    COUNT(*) FILTER (
        WHERE customer_prior_negative_review_rate < 0
           OR customer_prior_negative_review_rate > 1
    ) AS invalid_customer_review_rates

FROM capstone.order_features;

-- Feature query execution plan
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    approved_at,
    target,
    purchase_to_approval_minutes,
    item_count,
    payment_total_value,
    customer_prior_negative_review_rate,
    prior_seller_avg_review_score,
    customer_seller_distance_km
FROM capstone.order_features
WHERE approved_at < TIMESTAMP '2018-01-01'
ORDER BY approved_at
LIMIT 1000;