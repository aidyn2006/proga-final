LATE = "(o.order_delivered_customer_date > o.order_estimated_delivery_date)"

QUERIES = {
    1: ("Monthly revenue with month-over-month growth (CTE + LAG)", """
WITH monthly AS (
    SELECT substr(o.order_purchase_timestamp, 1, 7) AS month,
           COUNT(DISTINCT o.order_id)               AS orders,
           ROUND(SUM(oi.price), 2)                  AS revenue
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY month
)
SELECT month, orders, revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
             / LAG(revenue) OVER (ORDER BY month), 1) AS mom_growth_pct
FROM monthly
ORDER BY month
"""),
    2: ("Top product categories by revenue (4-table JOIN + RANK)", """
SELECT RANK() OVER (ORDER BY SUM(oi.price) DESC) AS revenue_rank,
       pc.category_name_en                       AS category,
       COUNT(*)                                  AS items_sold,
       ROUND(SUM(oi.price), 2)                   AS revenue,
       ROUND(AVG(oi.price), 2)                   AS avg_price
FROM order_items oi
JOIN orders o              ON o.order_id = oi.order_id
JOIN products p            ON p.product_id = oi.product_id
JOIN product_categories pc ON pc.category_name = p.category_name
WHERE o.order_status = 'delivered'
GROUP BY pc.category_name_en
ORDER BY revenue_rank
LIMIT 20
"""),
    3: ("Delivery delays by customer state (JOIN + GROUP BY/HAVING)", f"""
SELECT z.state                                                       AS customer_state,
       COUNT(*)                                                      AS delivered_orders,
       ROUND(AVG(julianday(o.order_delivered_customer_date)
                 - julianday(o.order_estimated_delivery_date)), 4)   AS avg_delay_days,
       ROUND(100.0 * SUM({LATE}) / COUNT(*), 2)                      AS late_share_pct
FROM orders o
JOIN customers c   ON c.customer_id = o.customer_id
JOIN zip_codes z   ON z.zip_prefix = c.zip_prefix
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY z.state
HAVING COUNT(*) >= 100
ORDER BY late_share_pct DESC
"""),
    4: ("Seller performance with quartiles (CTEs + NTILE + RANK)", f"""
WITH order_review AS (
    SELECT order_id, AVG(review_score) AS score FROM order_reviews GROUP BY order_id
),
seller_orders AS (
    SELECT oi.seller_id, o.order_id,
           SUM(oi.price) AS revenue,
           CASE WHEN {LATE} THEN 1 ELSE 0 END AS is_late,
           r.score
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id
    LEFT JOIN order_review r ON r.order_id = o.order_id
    WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
    GROUP BY oi.seller_id, o.order_id
),
seller_stats AS (
    SELECT seller_id,
           COUNT(*)                          AS orders,
           ROUND(SUM(revenue), 2)            AS revenue,
           ROUND(100.0 * AVG(is_late), 2)    AS late_share_pct,
           ROUND(AVG(score), 2)              AS avg_review
    FROM seller_orders
    GROUP BY seller_id
    HAVING COUNT(*) >= 30
)
SELECT seller_id, orders, revenue, late_share_pct, avg_review,
       RANK()  OVER (ORDER BY revenue DESC) AS revenue_rank,
       NTILE(4) OVER (ORDER BY avg_review DESC) AS review_quartile
FROM seller_stats
ORDER BY revenue_rank
LIMIT 50
"""),
    5: ("Top-3 sellers per state (ROW_NUMBER partitioned)", """
WITH seller_rev AS (
    SELECT s.seller_id, z.state AS seller_state, SUM(oi.price) AS revenue,
           COUNT(DISTINCT oi.order_id) AS orders
    FROM order_items oi
    JOIN sellers s   ON s.seller_id = oi.seller_id
    JOIN zip_codes z ON z.zip_prefix = s.zip_prefix
    JOIN orders o    ON o.order_id = oi.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY s.seller_id, z.state
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY seller_state ORDER BY revenue DESC) AS rn
    FROM seller_rev
)
SELECT seller_state, rn AS rank_in_state, seller_id, orders, ROUND(revenue, 2) AS revenue
FROM ranked
WHERE rn <= 3
ORDER BY seller_state, rn
"""),
    6: ("Customer cohort retention by month (CTEs + FIRST_VALUE)", """
WITH purchases AS (
    SELECT DISTINCT c.customer_unique_id AS cu,
           substr(o.order_purchase_timestamp, 1, 7) AS ym
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
),
first_purchase AS (
    SELECT cu, MIN(ym) AS cohort FROM purchases GROUP BY cu
),
activity AS (
    SELECT f.cohort,
           (CAST(substr(p.ym, 1, 4) AS INTEGER) * 12 + CAST(substr(p.ym, 6, 2) AS INTEGER))
         - (CAST(substr(f.cohort, 1, 4) AS INTEGER) * 12 + CAST(substr(f.cohort, 6, 2) AS INTEGER))
           AS month_offset,
           COUNT(DISTINCT p.cu) AS active_customers
    FROM purchases p
    JOIN first_purchase f ON f.cu = p.cu
    GROUP BY f.cohort, month_offset
)
SELECT cohort, month_offset, active_customers,
       ROUND(100.0 * active_customers /
             FIRST_VALUE(active_customers) OVER (PARTITION BY cohort ORDER BY month_offset), 2)
           AS retention_pct
FROM activity
WHERE month_offset BETWEEN 0 AND 12
ORDER BY cohort, month_offset
"""),
    7: ("Repeat vs one-time customers (subquery in FROM)", """
SELECT CASE WHEN n_orders = 1 THEN '1 order'
            WHEN n_orders = 2 THEN '2 orders'
            ELSE '3+ orders' END AS segment,
       COUNT(*)                                          AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct,
       ROUND(AVG(total_spent), 2)                        AS avg_lifetime_value
FROM (
    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS n_orders, SUM(oi.price) AS total_spent
    FROM customers c
    JOIN orders o       ON o.customer_id = c.customer_id
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
) t
GROUP BY segment
ORDER BY customers DESC
"""),
    8: ("Payment methods share (window SUM OVER)", """
SELECT payment_type,
       COUNT(*)                                            AS payments,
       ROUND(AVG(payment_installments), 2)                 AS avg_installments,
       ROUND(AVG(payment_value), 2)                        AS avg_value,
       ROUND(SUM(payment_value), 2)                        AS total_value,
       ROUND(100.0 * SUM(payment_value) / SUM(SUM(payment_value)) OVER (), 2) AS value_share_pct
FROM order_payments
GROUP BY payment_type
ORDER BY total_value DESC
"""),
    9: ("Review score vs delivery delay bucket (CASE + JOIN)", f"""
SELECT CASE
         WHEN delay <= -7 THEN '1: 7+ days early'
         WHEN delay <= 0  THEN '2: on time (0-7 days early)'
         WHEN delay <= 3  THEN '3: 1-3 days late'
         WHEN delay <= 7  THEN '4: 4-7 days late'
         ELSE '5: 7+ days late' END AS delivery_bucket,
       COUNT(*)                     AS reviews,
       ROUND(AVG(review_score), 3)  AS avg_score,
       ROUND(100.0 * AVG(review_score <= 2), 2) AS negative_share_pct
FROM (
    SELECT r.review_score,
           julianday(o.order_delivered_customer_date) - julianday(o.order_estimated_delivery_date) AS delay
    FROM order_reviews r
    JOIN orders o ON o.order_id = r.order_id
    WHERE o.order_delivered_customer_date IS NOT NULL
)
GROUP BY delivery_bucket
ORDER BY delivery_bucket
"""),
    10: ("Daily orders with 7-day moving average (window frame)", """
WITH daily AS (
    SELECT substr(order_purchase_timestamp, 1, 10) AS day, COUNT(*) AS orders
    FROM orders
    GROUP BY day
)
SELECT day, orders,
       ROUND(AVG(orders) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS orders_ma7
FROM daily
ORDER BY day
"""),
    11: ("Sellers with late share above the marketplace average (scalar subquery)", f"""
SELECT oi.seller_id,
       COUNT(DISTINCT o.order_id) AS orders,
       ROUND(100.0 * SUM({LATE}) / COUNT(*), 2) AS late_share_pct
FROM order_items oi
JOIN orders o ON o.order_id = oi.order_id
WHERE o.order_delivered_customer_date IS NOT NULL
GROUP BY oi.seller_id
HAVING COUNT(DISTINCT o.order_id) >= 50
   AND 1.0 * SUM({LATE}) / COUNT(*) >
       (SELECT AVG({LATE.replace('o.', 'o2.')})
        FROM orders o2 WHERE o2.order_delivered_customer_date IS NOT NULL)
ORDER BY late_share_pct DESC
"""),
}

BENCH_SQL = QUERIES[3][1]

ML_FEATURES_SQL = """
WITH item_agg AS (
    SELECT oi.order_id,
           COUNT(*)              AS n_items,
           SUM(oi.price)         AS price_sum,
           SUM(oi.freight_value) AS freight_sum,
           SUM(p.weight_g)       AS weight_g,
           SUM(COALESCE(p.length_cm, 0) * COALESCE(p.height_cm, 0) * COALESCE(p.width_cm, 0)) AS volume_cm3,
           MIN(oi.seller_id)     AS seller_id,
           MIN(pc.category_name_en) AS category
    FROM order_items oi
    LEFT JOIN products p            ON p.product_id = oi.product_id
    LEFT JOIN product_categories pc ON pc.category_name = p.category_name
    GROUP BY oi.order_id
),
pay AS (
    SELECT order_id, MAX(payment_installments) AS installments, MIN(payment_type) AS payment_type
    FROM order_payments GROUP BY order_id
)
SELECT o.order_id,
       o.order_purchase_timestamp AS purchase_ts,
       CAST((julianday(o.order_estimated_delivery_date) - julianday(o.order_purchase_timestamp)) AS REAL) AS promised_days,
       CAST(strftime('%H', o.order_purchase_timestamp) AS INTEGER) AS purchase_hour,
       CAST(strftime('%w', o.order_purchase_timestamp) AS INTEGER) AS purchase_dow,
       CAST(strftime('%m', o.order_purchase_timestamp) AS INTEGER) AS purchase_month,
       a.n_items, a.price_sum, a.freight_sum, a.weight_g, a.volume_cm3, a.category,
       pay.installments, pay.payment_type,
       zc.state AS customer_state, zs.state AS seller_state,
       CASE WHEN zc.state = zs.state THEN 1 ELSE 0 END AS same_state,
       CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END AS is_late
FROM orders o
JOIN item_agg a      ON a.order_id = o.order_id
JOIN customers c     ON c.customer_id = o.customer_id
JOIN zip_codes zc    ON zc.zip_prefix = c.zip_prefix
JOIN sellers s       ON s.seller_id = a.seller_id
JOIN zip_codes zs    ON zs.zip_prefix = s.zip_prefix
LEFT JOIN pay        ON pay.order_id = o.order_id
WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
ORDER BY o.order_purchase_timestamp
"""
