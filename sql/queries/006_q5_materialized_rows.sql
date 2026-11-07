-- Q5 candidate v2: materialize the raw payment rows once, then aggregate
-- independently at order level and payment-type/installment/order level.
-- Semantics match the original query:
--   * payment_records = raw payment rows
--   * unique_orders = distinct orders per payment type/installment pair
--   * correlation = CORR(max installments per order, total payment value per order)
-- This remains a live query; no snapshot or new index is used.

SET work_mem = '128MB';
SET jit = off;

EXPLAIN (ANALYZE, BUFFERS, SUMMARY)
WITH payments AS MATERIALIZED (
    SELECT
        order_id,
        payment_type,
        payment_installments,
        payment_value
    FROM olist.order_payments
),
order_values AS MATERIALIZED (
    SELECT
        order_id,
        SUM(payment_value) AS order_value,
        MAX(payment_installments) AS max_installments
    FROM payments
    GROUP BY order_id
),
payment_group_order AS MATERIALIZED (
    SELECT
        payment_type,
        payment_installments,
        order_id,
        COUNT(*)::bigint AS payment_records,
        SUM(payment_value) AS group_payment_value
    FROM payments
    GROUP BY
        payment_type,
        payment_installments,
        order_id
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
    FROM payment_group_order
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
