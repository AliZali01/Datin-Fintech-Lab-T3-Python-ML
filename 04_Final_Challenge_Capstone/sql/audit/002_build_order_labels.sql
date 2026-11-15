CREATE SCHEMA IF NOT EXISTS capstone;

CREATE TABLE IF NOT EXISTS capstone.order_labels (
    order_id TEXT PRIMARY KEY,
    approved_at TIMESTAMP NOT NULL,
    target SMALLINT NOT NULL CHECK (target IN (0,1)),
    post_approval_review_count INTEGER NOT NULL,
    negative_review_count INTEGER NOT NULL,
    nonnegative_review_count INTEGER NOT NULL,
    unscored_review_count INTEGER NOT NULL,
    first_review_date DATE NOT NULL,
    last_review_date DATE NOT NULL
);

WITH future_reviews AS (
    SELECT
        o.order_id,
        o.order_approved_at,
        r.review_score,
        r.review_creation_date::date AS review_date
    FROM olist.orders o
    JOIN olist.order_reviews r USING (order_id)
    WHERE o.order_approved_at IS NOT NULL
      AND r.review_creation_date::date >
          o.order_approved_at::date
),
aggregated AS (
    SELECT
        order_id,
        order_approved_at,
        COUNT(*) AS review_count,
        COUNT(*) FILTER (
            WHERE review_score IN (1,2)
        ) AS negative_count,
        COUNT(*) FILTER (
            WHERE review_score BETWEEN 3 AND 5
        ) AS nonnegative_count,
        COUNT(*) FILTER (
            WHERE review_score IS NULL
               OR review_score NOT BETWEEN 1 AND 5
        ) AS unscored_count,
        MIN(review_date) AS first_review,
        MAX(review_date) AS last_review
    FROM future_reviews
    GROUP BY order_id, order_approved_at
    HAVING COUNT(*) FILTER (
        WHERE review_score BETWEEN 1 AND 5
    ) > 0
)
INSERT INTO capstone.order_labels (
    order_id,
    approved_at,
    target,
    post_approval_review_count,
    negative_review_count,
    nonnegative_review_count,
    unscored_review_count,
    first_review_date,
    last_review_date
)
SELECT
    order_id,
    order_approved_at,
    CASE WHEN negative_count > 0 THEN 1 ELSE 0 END,
    review_count,
    negative_count,
    nonnegative_count,
    unscored_count,
    first_review,
    last_review
FROM aggregated
ON CONFLICT (order_id) DO UPDATE SET
    approved_at = EXCLUDED.approved_at,
    target = EXCLUDED.target,
    post_approval_review_count =
        EXCLUDED.post_approval_review_count,
    negative_review_count = EXCLUDED.negative_review_count,
    nonnegative_review_count = EXCLUDED.nonnegative_review_count,
    unscored_review_count = EXCLUDED.unscored_review_count,
    first_review_date = EXCLUDED.first_review_date,
    last_review_date = EXCLUDED.last_review_date;

SELECT target, COUNT(*) AS orders
FROM capstone.order_labels
GROUP BY target
ORDER BY target;

SELECT
    COUNT(*) AS labeled_orders,
    COUNT(*) FILTER (
        WHERE negative_review_count > 0
          AND nonnegative_review_count > 0
    ) AS conflicting_orders
FROM capstone.order_labels;