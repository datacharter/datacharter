# End-to-end example workspace

A copy-paste template showing every DataCharter governance surface in one
place: **PII masking**, **agent access**, **row filters**, **guides** (agent
context), **tests** (CI assertions), and a **metric**.

```sh
datacharter serve examples/ecommerce     # explore in the browser
datacharter test  examples/ecommerce     # run the data assertions
datacharter mcp   examples/ecommerce     # governed MCP server (guides ride
                                         # the initialize `instructions`)
```

What to try:
- Ask the agent "what's revenue by region?" — the guide steers it to net
  revenue and away from QA accounts.
- Flip **Agent view** on a query touching `crm` — name/email come back `•••`.
- The agent only ever sees un-refunded orders (`row_filters`).

Copy this directory, replace the CSVs with your sources, and keep the shape.
