BEGIN;

-- Preserve incomplete item/payment records as missing,
-- rather than exposing zero values as potential leakage.

SELECT
    COUNT(*) AS orders_without_items
FROM capstone.order_features
WHERE item_count = 0;

SELECT
    COUNT(*) AS orders_without_payments
FROM capstone.order_features
WHERE payment_record_count = 0;

-- Missing item records
UPDATE capstone.order_features
SET
    item_count = NULL,
    unique_product_count = NULL,
    unique_seller_count = NULL,
    total_item_price = NULL,
    total_freight_value = NULL,
    avg_item_price = NULL,
    product_category_count = NULL,
    avg_product_weight_g = NULL,
    avg_product_photos_qty = NULL,
    avg_product_description_length = NULL,
    avg_product_volume_cm3 = NULL,
    seller_state_count = NULL,
    avg_seller_latitude = NULL,
    avg_seller_longitude = NULL,
    same_state_seller_share = NULL,
    avg_prior_seller_orders = NULL,
    max_prior_seller_orders = NULL,
    prior_seller_review_count = NULL,
    prior_seller_avg_review_score = NULL,
    seller_review_history_available = NULL,
    customer_seller_distance_km = NULL,
    freight_to_price_ratio = NULL,
    payment_to_order_value_ratio = NULL
WHERE item_count = 0;

-- Missing payment record
UPDATE capstone.order_features
SET
    payment_record_count = NULL,
    payment_type_count = NULL,
    payment_total_value = NULL,
    avg_payment_installments = NULL,
    max_payment_installments = NULL,
    payment_to_order_value_ratio = NULL
WHERE payment_record_count = 0;

-- Calculate fixed temporal boundaries
DROP TABLE IF EXISTS capstone.modeling_dataset;

CREATE TABLE capstone.modeling_dataset AS

WITH cutoffs AS (
    SELECT
        percentile_disc(0.70)
            WITHIN GROUP (ORDER BY approved_at) AS train_end,

        percentile_disc(0.85)
            WITHIN GROUP (ORDER BY approved_at) AS validation_end

    FROM capstone.order_features
),

candidates AS (
    SELECT
        CASE
            WHEN f.approved_at < c.train_end
                THEN 'train'
            WHEN f.approved_at < c.validation_end
                THEN 'validation'
            ELSE 'test'
        END AS split,

        f.order_id,
        f.approved_at,
        f.target,
        l.last_review_date,

        f.customer_state,

        f.purchase_to_approval_minutes,
        f.estimated_delivery_days_from_approval,

        f.customer_latitude,
        f.customer_longitude,

        f.item_count,
        f.unique_product_count,
        f.unique_seller_count,
        f.total_item_price,
        f.total_freight_value,
        f.avg_item_price,

        f.payment_record_count,
        f.payment_type_count,
        f.payment_total_value,
        f.avg_payment_installments,
        f.max_payment_installments,

        f.product_category_count,
        f.avg_product_weight_g,
        f.avg_product_photos_qty,
        f.avg_product_description_length,
        f.avg_product_volume_cm3,

        f.seller_state_count,
        f.avg_seller_latitude,
        f.avg_seller_longitude,
        f.same_state_seller_share,

        f.customer_prior_approved_order_count,
        f.customer_days_since_previous_order,
        f.customer_prior_reviewed_order_count,
        f.customer_prior_negative_review_rate,
        f.customer_history_available,
        f.customer_review_history_available,

        f.avg_prior_seller_orders,
        f.max_prior_seller_orders,
        f.prior_seller_review_count,
        f.prior_seller_avg_review_score,
        f.seller_review_history_available,

        f.customer_seller_distance_km,
        f.freight_to_price_ratio,
        f.payment_to_order_value_ratio,

        CASE
            WHEN f.approved_at < c.train_end
                THEN l.last_review_date < c.train_end::date

            WHEN f.approved_at < c.validation_end
                THEN l.last_review_date < c.validation_end::date

            ELSE l.last_review_date IS NOT NULL
        END AS label_mature

    FROM capstone.order_features f

    JOIN capstone.order_labels l
        ON l.order_id = f.order_id

    CROSS JOIN cutoffs c
)

SELECT
    split,
    order_id,
    approved_at,
    target,

    customer_state,

    purchase_to_approval_minutes,
    estimated_delivery_days_from_approval,

    customer_latitude,
    customer_longitude,

    item_count,
    unique_product_count,
    unique_seller_count,
    total_item_price,
    total_freight_value,
    avg_item_price,

    payment_record_count,
    payment_type_count,
    payment_total_value,
    avg_payment_installments,
    max_payment_installments,

    product_category_count,
    avg_product_weight_g,
    avg_product_photos_qty,
    avg_product_description_length,
    avg_product_volume_cm3,

    seller_state_count,
    avg_seller_latitude,
    avg_seller_longitude,
    same_state_seller_share,

    customer_prior_approved_order_count,
    customer_days_since_previous_order,
    customer_prior_reviewed_order_count,
    customer_prior_negative_review_rate,
    customer_history_available,
    customer_review_history_available,

    avg_prior_seller_orders,
    max_prior_seller_orders,
    prior_seller_review_count,
    prior_seller_avg_review_score,
    seller_review_history_available,

    customer_seller_distance_km,
    freight_to_price_ratio,
    payment_to_order_value_ratio

FROM candidates
WHERE label_mature IS TRUE;

CREATE UNIQUE INDEX modeling_dataset_order_id_idx
    ON capstone.modeling_dataset(order_id);

CREATE INDEX modeling_dataset_split_idx
    ON capstone.modeling_dataset(split);

ANALYZE capstone.modeling_dataset;

COMMIT;

-- Split validation
SELECT
    split,
    COUNT(*) AS records,
    SUM(target) AS positive,
    COUNT(*) - SUM(target) AS negative,
    ROUND(100.0 * AVG(target), 2) AS positive_rate,
    MIN(approved_at) AS first_approval,
    MAX(approved_at) AS last_approval

FROM capstone.modeling_dataset
GROUP BY split

ORDER BY CASE split
    WHEN 'train' THEN 1
    WHEN 'validation' THEN 2
    ELSE 3
END;

-- Missing values after data-quality correction
SELECT
    COUNT(*) FILTER (WHERE item_count IS NULL)
        AS missing_item_count,

    COUNT(*) FILTER (WHERE payment_record_count IS NULL)
        AS missing_payment_count,

    COUNT(*) FILTER (WHERE customer_seller_distance_km IS NULL)
        AS missing_distance,

    COUNT(*) FILTER (WHERE customer_prior_negative_review_rate IS NULL)
        AS missing_customer_history,

    COUNT(*) FILTER (WHERE prior_seller_avg_review_score IS NULL)
        AS missing_seller_history

FROM capstone.modeling_dataset;

-- Target integrity
SELECT
    COUNT(*) AS total_records,
    COUNT(DISTINCT order_id) AS unique_orders,
    COUNT(*) FILTER (WHERE target NOT IN (0,1))
        AS invalid_targets
FROM capstone.modeling_dataset;
