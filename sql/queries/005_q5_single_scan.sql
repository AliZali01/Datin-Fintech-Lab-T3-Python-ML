-- Q5 alternative: one source scan, shared order-level/payment-group aggregate.
-- This is a LIVE query: it reads olist.order_payments at execution time.
-- Compare its EXPLAIN ANALYZE with Q5 baseline and the previous GROUPING SETS attempt.

SET work_mem = '128MB';
SET jit = off;

EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
WITH payment_by_order_group AS MATERIALIZED (
    SELECT
        payment_type,
        payment_installments,
        order_id,
        COUNT(*) AS payment_records,
        SUM(payment_value) AS group_payment_value
    FROM olist.order_payments
    GROUP BY
        payment_type,
        payment_installments,
        order_id
),
order_values AS (
    SELECT
        order_id,
        SUM(group_payment_value) AS order_value,
        MAX(payment_installments) AS max_installments
    FROM payment_by_order_group
    GROUP BY order_id
),
payment_correlation AS (
    SELECT
        CORR(
            max_installments::double precision,
            order_value::double precision
        ) AS installment_order_value_correlation
    FROM order_values
),
payment_distribution AS (
    SELECT
        payment_type,
        payment_installments,
        SUM(payment_records)::bigint AS payment_records,
        COUNT(*)::bigint AS unique_orders,
        SUM(group_payment_value) AS total_payment_value,
        SUM(group_payment_value)
            / NULLIF(SUM(payment_records), 0) AS average_payment_value
    FROM payment_by_order_group
    GROUP BY
        payment_type,
        payment_installments
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
CROSS JOIN payment_correlation AS c
ORDER BY
    d.payment_type,
    d.payment_installments;
