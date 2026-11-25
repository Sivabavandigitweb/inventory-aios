# Asset Management frontend foundation — Task 9B

Status: preview only. Route: `/assets`. Run `cd frontend` then `npm run dev`; open `http://localhost:5173/assets`. No asset or receiving API is called.

## Implemented

The Assets page keeps the existing shell and provides four responsive sections: individual assets, quantity inventory, product catalog and receiving. It includes separate summary totals for individual units and illustrative physical/available quantity stock, search and filters, pagination, a keyboard accessible details dialog, and explicit loading, empty and error states. Buttons for product creation and receipt submission are disabled. No mutation or asset-number generation is available.

`frontend/src/assets/types.ts` defines **proposed preview types**, not finalized backend response contracts. The separate `mockAssetProvider` contains fictional DEMO records only. An injected provider failure displays an error; it never silently substitutes mock records for a production API. The five lifecycle statuses are the exact R-02 values: Available, Allocated, Repair, Damaged and Disposed. Asset identifiers are DEMO labels, not LED numbers. Condition text, lot references and illustrative quantities are preview data, not approved vocabularies, numbering or unit rules.

Product catalog columns follow implemented `InventoryProduct` fields (name, category, optional SKU/brand/model, specifications and active flag). The receiving view uses R-03 date, receiver, quantity, location, specifications and optional documents. Only the `Receipt` header model currently exists. Receipt lines, assets, lots, stock balances and operational APIs have not been implemented.

## Boundaries and future integration

The original requirements PDF sections R-01–R-03, R-09, R-13–R-14 and R-16 motivate this view. R-02 supplies lifecycle states; R-03 supplies receiving fields. Planned allocation, repair, return, transfer and audit history are marked unavailable and contain no fabricated operational records.

All 13 management decisions in `docs/requirements/asset-business-decisions.md` remain pending. ABD-01/02/12 control item versus pooled stock classification, units and quantity semantics. ABD-03–06 control receiver, procurement completeness, costs and discrepancies. ABD-07–11 control LED numbering, serials, condition, approval and legacy imports. ABD-13 governs retry retention. The UI does not select any option.

Future work needs approved business decisions, SQLAlchemy models and a reviewed migration for receipt lines/assets/lots, authorized versioned API response schemas, real permission checks, transactional receiving and idempotency, audit integration, allocation and repair workflows, and PostgreSQL integration tests. Replace the explicit mock provider only after those prerequisites. Keep individual asset totals separate from quantity balances. Do not enable stock writes, employee synchronization, registration or receiving from this preview.
