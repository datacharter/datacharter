-- Net revenue by customer region (QA accounts excluded).
SELECT c.region, sum(o.amount) AS net_revenue
FROM sales o
JOIN crm c USING (customer_id)
WHERE o.refunded = false AND c.tier <> 'internal'
GROUP BY 1 ORDER BY 2 DESC;
