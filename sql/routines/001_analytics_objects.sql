
\timing on

-- ==========================================
-- Q1: Monthly Category Sales Snapshot
-- ==========================================

CREATE MATERIALIZED VIEW IF NOT EXISTS
olist.monthly_category_sales_snapshot AS

SELECT
    DATE_TRUNC('month', o.order_purchase_timestamp)::date
        AS sales_month,

    COALESCE(
        t.product_category_name_english,
        p.product_category_name,
        'uncategorized'
    ) AS category,

    ROUND(SUM(oi.price), 2) AS total_sales,

    COUNT(DISTINCT oi.order_id) AS unique_orders,

    ROUND(
        SUM(oi.price) /
        NULLIF(COUNT(DISTINCT oi.order_id), 0),
        2
    ) AS average_order_value

FROM olist.order_items oi
JOIN olist.orders o ON o.order_id = oi.order_id
JOIN olist.products p ON p.product_id = oi.product_id
LEFT JOIN olist.product_category_translation t
    ON t.product_category_name = p.product_category_name

WHERE o.order_status NOT IN ('canceled', 'unavailable')

GROUP BY 1, 2;

CREATE UNIQUE INDEX IF NOT EXISTS
idx_monthly_category_snapshot
ON olist.monthly_category_sales_snapshot
(sales_month, category);


-- ==========================================
-- Q5: Payment Distribution Snapshot
-- ==========================================

CREATE MATERIALIZED VIEW IF NOT EXISTS
olist.payment_distribution_snapshot AS

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
    pc.installment_order_value_correlation;


CREATE UNIQUE INDEX IF NOT EXISTS
idx_payment_distribution_snapshot
ON olist.payment_distribution_snapshot
(payment_type, payment_installments);


-- ==========================================
-- ANALYTICAL VIEWS
-- ==========================================

CREATE OR REPLACE VIEW olist.v_seller_performance AS
SELECT *
FROM olist.seller_performance_snapshot;


CREATE OR REPLACE VIEW olist.v_monthly_category_sales AS
SELECT *
FROM olist.monthly_category_sales_snapshot;


CREATE OR REPLACE VIEW olist.v_payment_distribution AS
SELECT *
FROM olist.payment_distribution_snapshot;


-- ==========================================
-- FUNCTION 1: Top Sellers
-- ==========================================

CREATE OR REPLACE FUNCTION olist.get_top_sellers(
    p_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    seller_id TEXT,
    seller_state TEXT,
    seller_city TEXT,
    total_revenue NUMERIC,
    seller_orders BIGINT,
    average_preparation_hours NUMERIC,
    average_review_score NUMERIC
)
LANGUAGE plpgsql
STABLE
AS $$

BEGIN

    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 3095 THEN
        RAISE EXCEPTION 'Invalid seller limit: %', p_limit;
    END IF;

    RETURN QUERY

    SELECT
        s.seller_id::text,
        s.seller_state::text,
        s.seller_city::text,
        s.total_revenue,
        s.seller_orders,
        s.average_preparation_hours,
        s.average_review_score

    FROM olist.v_seller_performance s

    ORDER BY s.total_revenue DESC
    LIMIT p_limit;

END;
$$;


-- ==========================================
-- FUNCTION 2: Monthly Category Sales
-- ==========================================

CREATE OR REPLACE FUNCTION olist.get_category_sales(
    p_start DATE DEFAULT NULL,
    p_end DATE DEFAULT NULL
)
RETURNS TABLE (
    sales_month DATE,
    category TEXT,
    total_sales NUMERIC,
    unique_orders BIGINT,
    average_order_value NUMERIC
)
LANGUAGE sql
STABLE
AS $$

    SELECT
        v.sales_month,
        v.category::text,
        v.total_sales,
        v.unique_orders,
        v.average_order_value

    FROM olist.v_monthly_category_sales v

    WHERE (p_start IS NULL OR v.sales_month >= p_start)
      AND (p_end IS NULL OR v.sales_month <= p_end)

    ORDER BY v.sales_month, v.category;

$$;


-- ==========================================
-- FUNCTION 3: Payment Distribution
-- ==========================================

CREATE OR REPLACE FUNCTION olist.get_payment_distribution(
    p_payment_type TEXT DEFAULT NULL
)
RETURNS TABLE (
    payment_type TEXT,
    payment_installments INTEGER,
    payment_records BIGINT,
    unique_orders BIGINT,
    total_payment_value NUMERIC,
    average_payment_value NUMERIC,
    installment_order_value_correlation NUMERIC
)
LANGUAGE sql
STABLE
AS $$

    SELECT
        v.payment_type::text,
        v.payment_installments::integer,
        v.payment_records,
        v.unique_orders,
        v.total_payment_value,
        v.average_payment_value,
        v.installment_order_value_correlation

    FROM olist.v_payment_distribution v

    WHERE p_payment_type IS NULL
       OR v.payment_type = p_payment_type

    ORDER BY v.payment_type, v.payment_installments;

$$;


-- ==========================================
-- REFRESH AUDIT TABLE
-- ==========================================

CREATE TABLE IF NOT EXISTS olist.snapshot_refresh_log (
    refresh_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    duration_ms NUMERIC(14,3) NOT NULL,
    row_count BIGINT NOT NULL,
    refreshed_by TEXT NOT NULL
);


-- ==========================================
-- STORED PROCEDURE
-- ==========================================

CREATE OR REPLACE PROCEDURE
olist.refresh_analytics_snapshots()

LANGUAGE plpgsql
AS $$

DECLARE
    v_started TIMESTAMPTZ;
    v_finished TIMESTAMPTZ;
    v_rows BIGINT;

BEGIN

    -- Seller snapshot
    v_started := clock_timestamp();

    REFRESH MATERIALIZED VIEW
        olist.seller_performance_snapshot;

    v_finished := clock_timestamp();

    SELECT COUNT(*) INTO v_rows
    FROM olist.seller_performance_snapshot;

    INSERT INTO olist.snapshot_refresh_log
    VALUES (
        DEFAULT,
        'seller_performance_snapshot',
        v_started,
        v_finished,
        ROUND(
            (EXTRACT(EPOCH FROM (v_finished-v_started))*1000)::numeric,
            3
        ),
        v_rows,
        SESSION_USER
    );


    -- Monthly sales snapshot
    v_started := clock_timestamp();

    REFRESH MATERIALIZED VIEW
        olist.monthly_category_sales_snapshot;

    v_finished := clock_timestamp();

    SELECT COUNT(*) INTO v_rows
    FROM olist.monthly_category_sales_snapshot;

    INSERT INTO olist.snapshot_refresh_log
    VALUES (
        DEFAULT,
        'monthly_category_sales_snapshot',
        v_started,
        v_finished,
        ROUND(
            (EXTRACT(EPOCH FROM (v_finished-v_started))*1000)::numeric,
            3
        ),
        v_rows,
        SESSION_USER
    );


    -- Payment snapshot
    v_started := clock_timestamp();

    REFRESH MATERIALIZED VIEW
        olist.payment_distribution_snapshot;

    v_finished := clock_timestamp();

    SELECT COUNT(*) INTO v_rows
    FROM olist.payment_distribution_snapshot;

    INSERT INTO olist.snapshot_refresh_log
    VALUES (
        DEFAULT,
        'payment_distribution_snapshot',
        v_started,
        v_finished,
        ROUND(
            (EXTRACT(EPOCH FROM (v_finished-v_started))*1000)::numeric,
            3
        ),
        v_rows,
        SESSION_USER
    );

END;
$$;


-- Update planner statistics
ANALYZE olist.monthly_category_sales_snapshot;
ANALYZE olist.payment_distribution_snapshot;
ANALYZE olist.seller_performance_snapshot;
