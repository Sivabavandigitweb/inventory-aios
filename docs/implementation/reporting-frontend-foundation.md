# Reports and Analytics frontend foundation

## Scope and requirement traceability

This is a local fictional preview, not an operational reporting service. The source PDF's R-15 explicitly names asset summary, employee-wise, department-wise, allocation, return, damaged, purchase history, employee exit asset, and audit trail reports. R-17 prefers Excel/PDF export; this preview keeps those controls disabled. R-13 dashboard metrics are implemented separately.

The page also offers quantity inventory and approval examples as proposed previews because shared fictional records exist. They are not represented as additional explicit R-15 report mandates. Missing asset information is identified in R-12 as a notification category, but a report requires approved completeness semantics.

## Implemented report categories

Available from shared typed providers:

- Individual asset inventory (R-15 asset summary): current fictional asset identity, category, location, lifecycle status.
- Quantity inventory (proposed): each lot displays physical, reserved, and physical-minus-reserved counts. It does not combine lots or products because units are unresolved.
- Employee-wise and department-wise assets (R-15): summaries derived from fictional allocations and employee organization mapping.
- Allocations (R-15): shared allocation examples.
- Returns (R-15): shared historical return examples; preview does not prove verification or current custody.
- Damaged assets (R-15): individual assets whose fictional current status is Damaged.
- Employee exit assets (R-15): partial clearance cases with visible outstanding individual allocations; readiness remains unknown.
- Approval examples (proposed): R-10 request scenarios only, not submitted requests or decisions.

Explicitly unavailable:

- Purchase history (R-15): the shared preview has receipt examples but no approved purchase date, supplier, cost, currency or purchase-record contract.
- Audit trail (R-15): authorized audit history is not connected; R-11 remains partially implemented.
- Missing asset information: required completeness rules and validated live records are unavailable. Optional nulls are not classified as violations.

## Filtering and calculations

Search is applied to report reference, subject, details, category, location, status, employee and department. Category/location/status/department/employee and date filters appear only where the selected preview has values. Matching totals are computed before pagination. The asset summary includes a small accessible status distribution with numeric labels.

Preview rows use the existing asset/product/lot, employee, workflow, repair, clearance and approval providers. Shared allocation, return, exit, approval and repair references are validated before display. Provider failures show an error state and never fall back to a second dataset.

Historical return examples do not mutate asset status. Quantity stock is per lot with illustrative whole-number counts only; quantity units are not approved. Missing/unknown data remains unavailable rather than being treated as zero. Partial fixtures are not complete inventory or reproducible as-of reports.

## Security, exports and future integration

The current role/permission matrix is proposed; reports must eventually be protected by server-side authentication and authorization. Management must approve report-specific permissions and any department/location scope. Sensitive employee, procurement and audit information requires field-level access decisions. Export access must be authorized and audited, and large reports require server-side pagination/filtering and a reproducible as-of snapshot.

Excel/PDF are preferred by R-17, not generated here. No operational export, scheduled report, email delivery, or backend request is implemented.

Future Grok-generated reports must call authorized backend reporting services. Grok must not receive unrestricted database access, bypass report permissions, or invent unavailable report values.

## Pending decisions and deferred work

- Report definitions, filter sets, as-of semantics, metric definitions and user scopes.
- Approved role/department/location access boundaries and sensitive fields.
- Export formats beyond the Excel/PDF preference, export auditing, and retention.
- Purchase history source and data contract.
- Missing-information rules and optional-vs-required field semantics.
- Authorized audit history, previous/updated values, redaction and retention remain R-11 gaps.
- Operational report APIs, snapshots, export generation and delivery.

## Preview

Run from frontend with npm run dev, then open http://localhost:5173/reports.
