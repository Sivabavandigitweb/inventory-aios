# Inventory dashboard frontend foundation — Task 9C

Status: fictional local preview only. Route: `/dashboard`. Run `cd frontend`, then `npm run dev`; open `http://localhost:5173/dashboard`. No database, backend API or employee source connection is used.

## Implemented

The responsive dashboard shows individual asset summary cards; accessible numeric bar displays for the five R-02 lifecycle statuses, categories and locations; per-lot quantity stock availability; employee overview; employee source status; and working links to asset directory, quantity inventory, product catalog and employee directory. Loading, empty and provider-error states are explicit. No mock fallback is used when a provider fails.

The dashboard calls the existing typed `mockAssetProvider.load()` and `mockEmployeeProvider.getSummary()`. `buildDashboardSummary` derives individual asset totals, status/category/location counts and per-lot available quantity (`physical - reserved`). Status, category and location counts each reconcile to the individual asset count. Employee counts are the same provider summary used by the Employees page. Stock lots are not added to the individual asset count. The stock chart keeps each lot separate; units and aggregation across products remain unapproved under ABD-02/12. Illustrative quantities are whole counts only and are not production balances.

Quick navigation uses existing router destinations. The Assets page accepts only `assets`, `quantity`, `products` and `receiving` as optional `section` query values; unknown values default to the individual directory. Tabs still work by click and keyboard.

## Asset page refinements

Lifecycle badges use green Available, blue Allocated, amber Repair, red Damaged and neutral Disposed. The directory uses a short neutral condition label, with one visible note that the condition vocabulary awaits approval. The details close control matches the Employee Management dialog. Table row contrast, catalog search hint and tab focus styling were refined. No mock status, quantity calculation or business rule changed.

## Requirements and deferred work

R-13 requests total/allocated/available/damaged/repair assets, new and departed employees, pending returns and approvals. Preview asset status counts are displayed. New joiners, departures, approvals, overdue returns, active repair workflows, recent inventory transactions and exit clearance are **unavailable**, rather than shown as fabricated records or zero counts. R-12 notifications, R-14 search and R-16 responsive access remain future operational integration topics. Employee synchronization is not connected and has no last-success timestamp.

The dashboard is not an authorized operational report. Production integration needs approved data contracts and permissions, real asset/lot/employee synchronization services, as-of and metric definitions, business decisions ABD-01–13, audit requirements and integration tests. Reuse the same backend read models across dashboard and directories; enforce authorization in backend services. Do not activate receiving, registration, stock changes, employee synchronization or Grok from this UI.
