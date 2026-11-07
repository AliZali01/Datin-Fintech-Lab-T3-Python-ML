
-- Q1: Product category analysis
CREATE INDEX IF NOT EXISTS idx_order_items_product_cover
ON olist.order_items (product_id)
INCLUDE (order_id, price);

-- Q4: Seller revenue and order aggregation
CREATE INDEX IF NOT EXISTS idx_order_items_seller_order_cover
ON olist.order_items (seller_id, order_id)
INCLUDE (price);

-- Q3 and Q4: Review aggregation and joins
CREATE INDEX IF NOT EXISTS idx_order_reviews_order_cover
ON olist.order_reviews (order_id)
INCLUDE (review_score);

-- Q5: Payment aggregation
CREATE INDEX IF NOT EXISTS idx_order_payments_order_cover
ON olist.order_payments (order_id)
INCLUDE (payment_type, payment_installments, payment_value);

ANALYZE olist.order_items;
ANALYZE olist.order_reviews;
ANALYZE olist.order_payments;
ANALYZE olist.products;
ANALYZE olist.orders;
ANALYZE olist.sellers;
