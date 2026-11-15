CREATE SCHEMA IF NOT EXISTS capstone;

CREATE TABLE IF NOT EXISTS capstone.temporal_column_audit (
    source_schema TEXT NOT NULL DEFAULT 'olist',
    source_table TEXT NOT NULL,
    source_column TEXT NOT NULL,
    availability_status TEXT NOT NULL,
    model_feature_allowed BOOLEAN NOT NULL,
    historical_aggregate_allowed BOOLEAN NOT NULL,
    planned_use TEXT NOT NULL,
    temporal_rule TEXT NOT NULL,
    evidence TEXT NOT NULL,
    PRIMARY KEY (source_schema, source_table, source_column)
);

INSERT INTO capstone.temporal_column_audit (
    source_table, source_column, availability_status,
    model_feature_allowed, historical_aggregate_allowed,
    planned_use, temporal_rule, evidence
)
VALUES

-- ORDERS
('orders','order_id','available_at_creation',FALSE,TRUE,'join_key','Identifier only','Olist order primary key'),
('orders','customer_id','available_at_creation',FALSE,TRUE,'customer_history_join','Join customer history only','Olist order foreign key'),
('orders','order_status','post_decision',FALSE,FALSE,'excluded','Never use current final status','Status evolves after approval'),
('orders','order_purchase_timestamp','available_at_purchase',TRUE,TRUE,'derived_features','Use purchase time and prior-event cutoffs','Purchase event timestamp'),
('orders','order_approved_at','decision_time',FALSE,TRUE,'decision_cutoff','Use as prediction timestamp and historical cutoff only','Challenge decision definition'),
('orders','order_delivered_carrier_date','post_decision',FALSE,FALSE,'excluded','Never use','Carrier handover occurs later'),
('orders','order_delivered_customer_date','post_decision',FALSE,FALSE,'excluded','Never use','Actual delivery occurs later'),
('orders','order_estimated_delivery_date','available_at_purchase',TRUE,FALSE,'derived_features','Use only the estimate communicated at purchase','Olist data dictionary'),

-- CUSTOMERS
('customers','customer_id','available_at_creation',FALSE,TRUE,'join_key','Join to order only','Order customer key'),
('customers','customer_unique_id','available_at_creation',FALSE,TRUE,'customer_history_key','Historical aggregates must use prior orders only','Customer identity key'),
('customers','customer_zip_code_prefix','available_at_purchase',TRUE,FALSE,'geography_feature','Use order-associated customer address','Customer order location'),
('customers','customer_city','available_at_purchase',FALSE,FALSE,'excluded_high_cardinality','Not used directly','Customer location text'),
('customers','customer_state','available_at_purchase',TRUE,FALSE,'geography_feature','Use order-associated customer state','Customer order location'),

-- ORDER ITEMS
('order_items','order_id','available_at_creation',FALSE,TRUE,'join_key','Join to order','Order foreign key'),
('order_items','order_item_id','available_at_purchase',TRUE,FALSE,'item_aggregation','Aggregate item count by order','Item sequence'),
('order_items','product_id','available_at_purchase',FALSE,FALSE,'product_join','Use catalog attributes, not raw identifier','Product foreign key'),
('order_items','seller_id','available_at_purchase',FALSE,TRUE,'seller_history_join','Historical seller data must precede decision','Seller foreign key'),
('order_items','shipping_limit_date','conditional_unverified',FALSE,FALSE,'excluded_pending_evidence','Exclude until creation time is verified','No event timestamp in source'),
('order_items','price','available_at_purchase',TRUE,FALSE,'item_aggregation','Aggregate order prices','Transaction item price'),
('order_items','freight_value','available_at_purchase',TRUE,FALSE,'item_aggregation','Aggregate order freight','Transaction freight value'),

-- PAYMENTS
('order_payments','order_id','available_at_creation',FALSE,TRUE,'join_key','Join to order','Order foreign key'),
('order_payments','payment_sequential','conditional_unverified',FALSE,FALSE,'excluded_pending_evidence','Do not use until payment event timing is established','No event timestamp in source'),
('order_payments','payment_type','available_by_approval',TRUE,FALSE,'payment_feature','Payment method selected by approval','Checkout transaction attribute'),
('order_payments','payment_installments','available_by_approval',TRUE,FALSE,'payment_feature','Installments selected by approval','Checkout transaction attribute'),
('order_payments','payment_value','available_by_approval',TRUE,FALSE,'payment_feature','Aggregate payment values','Checkout transaction amount'),

-- PRODUCTS
('products','product_id','static_catalog_assumption',FALSE,TRUE,'product_join','Join catalog only','Product identifier'),
('products','product_category_name','static_catalog_assumption',TRUE,FALSE,'product_feature','Assume catalog category stable for historical period','Static catalog snapshot'),
('products','product_name_lenght','static_catalog_assumption',TRUE,FALSE,'product_feature','Assume catalog snapshot stable','Static catalog attribute'),
('products','product_description_lenght','static_catalog_assumption',TRUE,FALSE,'product_feature','Assume catalog snapshot stable','Static catalog attribute'),
('products','product_photos_qty','static_catalog_assumption',TRUE,FALSE,'product_feature','Assume catalog snapshot stable','Static catalog attribute'),
('products','product_weight_g','static_catalog_assumption',TRUE,FALSE,'product_feature','Assume catalog snapshot stable','Static catalog attribute'),
('products','product_length_cm','static_catalog_assumption',TRUE,FALSE,'product_feature','Assume catalog snapshot stable','Static catalog attribute'),
('products','product_height_cm','static_catalog_assumption',TRUE,FALSE,'product_feature','Assume catalog snapshot stable','Static catalog attribute'),
('products','product_width_cm','static_catalog_assumption',TRUE,FALSE,'product_feature','Assume catalog snapshot stable','Static catalog attribute'),

-- SELLERS
('sellers','seller_id','available_at_creation',FALSE,TRUE,'seller_history_key','Use for prior seller aggregates','Seller identifier'),
('sellers','seller_zip_code_prefix','static_seller_assumption',TRUE,FALSE,'seller_geography','Assume seller location stable','Seller reference data'),
('sellers','seller_city','static_seller_assumption',FALSE,FALSE,'excluded_high_cardinality','Not used directly','Seller reference data'),
('sellers','seller_state','static_seller_assumption',TRUE,FALSE,'seller_geography','Assume seller location stable','Seller reference data'),

-- GEOLOCATION
('geolocation','geolocation_id','static_lookup_assumption',FALSE,FALSE,'excluded_identifier','Never use identifier','Lookup row identifier'),
('geolocation','geolocation_zip_code_prefix','static_lookup_assumption',FALSE,TRUE,'geography_join','Aggregate coordinates by ZIP prefix','Geolocation lookup key'),
('geolocation','geolocation_lat','static_lookup_assumption',TRUE,FALSE,'geography_feature','Use ZIP centroid, not arbitrary row','Static geolocation reference'),
('geolocation','geolocation_lng','static_lookup_assumption',TRUE,FALSE,'geography_feature','Use ZIP centroid, not arbitrary row','Static geolocation reference'),
('geolocation','geolocation_city','static_lookup_assumption',FALSE,FALSE,'excluded_reference','Not used directly','Static geolocation reference'),
('geolocation','geolocation_state','static_lookup_assumption',FALSE,FALSE,'excluded_reference','Not used directly','Static geolocation reference'),

-- REVIEWS
('order_reviews','review_record_id','post_outcome',FALSE,FALSE,'excluded_identifier','Never use as predictor','Review record identifier'),
('order_reviews','review_id','post_outcome',FALSE,FALSE,'excluded_identifier','Never use as predictor','Review identifier'),
('order_reviews','order_id','post_outcome',FALSE,TRUE,'label_and_history_join','Only for label construction and prior history','Review order foreign key'),
('order_reviews','review_score','post_outcome',FALSE,TRUE,'label_and_prior_history','Current order: label only; history: strictly prior review dates','Review is observed after order approval'),
('order_reviews','review_comment_title','post_outcome',FALSE,FALSE,'excluded','Never use','Customer review content'),
('order_reviews','review_comment_message','post_outcome',FALSE,FALSE,'excluded','Never use','Customer review content'),
('order_reviews','review_creation_date','historical_event_time',FALSE,TRUE,'historical_review_cutoff','Prior history only when review date is strictly before current approval date','Review event date'),
('order_reviews','review_answer_timestamp','post_outcome',FALSE,FALSE,'excluded','Never use','Review response occurs later'),

-- CATEGORY TRANSLATION
('product_category_translation','product_category_name','static_lookup_assumption',FALSE,TRUE,'category_join','Lookup only','Static translation dictionary'),
('product_category_translation','product_category_name_english','static_lookup_assumption',TRUE,FALSE,'category_feature','Use as category mapping','Static translation dictionary')

ON CONFLICT (source_schema, source_table, source_column)
DO UPDATE SET
    availability_status = EXCLUDED.availability_status,
    model_feature_allowed = EXCLUDED.model_feature_allowed,
    historical_aggregate_allowed = EXCLUDED.historical_aggregate_allowed,
    planned_use = EXCLUDED.planned_use,
    temporal_rule = EXCLUDED.temporal_rule,
    evidence = EXCLUDED.evidence;

-- Completeness check
WITH source_columns AS (
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'olist'
      AND table_name IN (
        'orders',
        'customers',
        'order_items',
        'order_payments',
        'order_reviews',
        'products',
        'sellers',
        'geolocation',
        'product_category_translation'
      )
)
SELECT
    COUNT(*) AS source_columns,
    COUNT(a.source_column) AS audited_columns,
    COUNT(*) FILTER (
        WHERE a.source_column IS NULL
    ) AS missing_audit_entries
FROM source_columns s
LEFT JOIN capstone.temporal_column_audit a
    ON a.source_schema = 'olist'
   AND a.source_table = s.table_name
   AND a.source_column = s.column_name;

-- List columns allowed as engineered feature sources
SELECT
    source_table,
    source_column,
    availability_status,
    planned_use
FROM capstone.temporal_column_audit
WHERE model_feature_allowed = TRUE
ORDER BY source_table, source_column;

-- Explicitly excluded tempting columns
SELECT
    source_table,
    source_column,
    availability_status,
    temporal_rule
FROM capstone.temporal_column_audit
WHERE availability_status IN (
    'post_decision',
    'post_outcome',
    'conditional_unverified'
)
ORDER BY source_table, source_column;