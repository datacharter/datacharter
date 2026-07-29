# Analytics guide

- **Net revenue** means `sum(amount)` over orders where `refunded = false`.
  Never report gross when someone says "revenue".
- **Exclude QA accounts** from customer counts: `tier = 'internal'`
  (their region is `ZZ`).
- `order_date` is when the order was placed. There is no shipping date in
  this dataset — do not invent one.
