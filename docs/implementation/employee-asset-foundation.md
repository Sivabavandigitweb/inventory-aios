# Employee and asset foundation — accelerated Task B

## Implemented offline foundation

- Employee synchronization accepts an injected read-only source, explicit source key and organization mapping. It checks duplicate external IDs and employee numbers, rejects conflicting local mappings, preserves local employee IDs, and never deletes absent rows or completes exit clearance. The PostgreSQL source adapter validates configured identifiers and marks its transaction read-only; it has not been configured or connected.
- The SQLAlchemy synchronization repository supports atomic upsert preparation, dry runs, identity mapping, history and audit callback requirements. Persistent synchronization is fail-closed unless explicit write and complete-audit gates are supplied. The API execution route remains unavailable until the source owner confirms schema, stable identity, mappings and audit controls.
- Added product, receiving, receipt-line, individually tracked asset, quantity lot, unit-scoped balance, movement, registration-event, employee-source-identity and synchronization-run metadata.
- Added protected read APIs for product catalog, individual asset directory, quantity balances, receipt history, employee summary and sync status. Existing capability checks remain deny-by-default. There are no operational product/receiving/asset write routes.
- Authenticated React workspace pages use same-origin API providers and do not fall back to fictional data. The unauthenticated preview remains explicitly fictional. Quantity values are displayed by unit; unlike units are not added together.

## Migration and activation boundary

Additive Alembic revision `4b6f10a2c903` follows `0ea2d9c71b45`. It creates new tables only, uses explicit `public` references, has no seed records or grants, and refuses downgrade while any new table contains data. PostgreSQL SQL was compiled offline. No migration was executed and no database was accessed.

Operational writes remain disabled because approval authority, asset numbering, authoritative employee mapping, and complete R-11 audit attribution/value-delta support are not ready. Existing authentication remains fail-closed and no roles are granted. Receipt lines default to pending; tracked asset lifecycle state requires an explicit value and does not default to available.

## Required next gates

1. Source owner confirms the read-only source target/schema, stable unique external identifier, field mappings, organization-code mapping, refresh behavior and data handling.
2. Management approves write and approval boundaries, unit vocabulary, asset-number policy, audit fields/retention and the employee status mapping.
3. Approve and rehearse migration plus least-privilege ownership/runtime grants on the disposable PostgreSQL restore target; verify backup/restore first.
4. Implement and run PostgreSQL transaction/concurrency tests for receipt posting, balance updates, idempotency, synchronization conflicts and audit atomicity.
5. Complete authentication, CSRF, provisioning, authorization grants and browser/deployment gates before operational activation.

Allocation, return, repair, disposal and exit-clearance workflows still require separate transactional services, resource authorization, approvals and audit recording. This foundation does not claim those workflows or inventory writes are operational.

### Accelerated Task C+D.2 continuation

Added an authenticated asset operations panel for product creation, receiving, individual and quantity registration requests, approval decisions, and posting approved registration. The panel uses typed same-origin cookie requests with CSRF and idempotency headers, reports only confirmed results, and refreshes after success. New product/receiving/registration paths remain available only through the auth and inventory-evidence router builder; the operational API router is unchanged.

Added single-line allocation and return transaction services, schemas, endpoints in the same isolated write-router factory, and authenticated allocation/return forms. Allocation request, independent approval, issue, return record and independent verification are separately authorized; row locks, current employee/asset/balance checks, idempotency and same-transaction audit callbacks are used. Partial and complete quantity returns are supported for `good` condition. Other quantity-return conditions remain blocked because the current inventory balance schema has no quarantine/disposition bucket. PostgreSQL concurrency and transaction guarantees still require the approved database rehearsal; no route, role, or write was activated.

## Combined accelerated Task C+D checkpoint

Added an additive workflow schema draft in `9c81e247a610` after `4b6f10a2c903` for allocation headers/lines, returns, repair cases, disposal requests, exit clearances, approval decisions and notification records. The schema separates individual assets from unit-scoped quantity lines and includes guarded state values, idempotency references, active-asset/open-clearance uniqueness, and restrictive foreign keys. Added allowlisted before/after audit value fields and validation for selected non-sensitive workflow fields. Existing audit metadata and append-only behavior remain in place.

Offline workflow helpers currently cover locked individual-asset lifecycle transitions and exit-clearance completion. They require injected authorization and independent approval decisions, write audit events in the same transaction scope, and are not connected to API routes. A database-backed aggregate summary provider is prepared; department scopes fail closed because no approved employee-to-location scope mapping exists. Small category/location groups are suppressed using a mandatory injected threshold. The summary router remains isolated.

The authenticated dashboard, workflow, approval, and reporting routes continue to show an unavailable state instead of fictional preview data. Public preview routes remain fictional. Added transactional catalog creation, receipt creation, registration request/approval/finalization services, idempotency handling, same-transaction audit calls, and an explicitly constructed write-router factory. Revision `a1c7e3052b94` adds registration request tables, request idempotency references, and database-side audit-value validation; it follows `9c81e247a610` and has only been compiled offline by the migration test. The write router is not registered in the operational router, and no frontend write form calls it.

These additions cover only the initial catalog/receiving/registration path at the service and isolated API-adapter level. Allocation and return mutations, repair/disposal operations, exit-clearance creation, approval APIs beyond registration, dashboard/report/notification operational APIs, exports, and authenticated workflow write UI remain incomplete. No operational write is enabled. R-11 remains partial; PostgreSQL execution, privileges, transaction/concurrency behavior, and runtime audit operation require a separately approved rehearsal.
