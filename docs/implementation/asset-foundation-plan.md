# Asset foundation implementation plan — Task 8A

## Task 8C?8D sequencing update

Read the [management decision register](../requirements/asset-business-decisions.md) and [receiving/idempotency contract](../database/asset-receiving-contract.md). Requirements already explicit in the PDF are not reopened for approval. The following supersedes broader early slice recommendations where they would implement unsettled rules.

| Readiness | Models/work | Next gate |
|---|---|---|
| Independent, already implemented | InventoryProduct and Receipt, unchanged | Existing offline maintenance can proceed; no operational enablement. |
| Offline foundation implemented in Task 8D | Shared IdempotencyRequest model, canonical fingerprinting, pure replay decision | No migration or database runner. ABD-13 still blocks retention/cleanup; PostgreSQL concurrency and permissions need separate review. |
| Management decisions required | receipt_lines and product unit metadata | ABD-01/02/04/05 for classification/units/procurement; ABD-03 for receiving identity/service responsibility. Quantity precision or field nullability must not be guessed. |
| Management and dependent models required | assets | Receipt lines plus ABD-07/08/09/10 for numbers/serials/condition/approval. ABD-11 additionally blocks legacy import. |
| Management and receiving enforcement required | inventory_lots | Receipt lines, ABD-01/02/12 and reviewed source-line locking/equality checks. |
| Future workflow design required | balances, movements, registration provenance, allocation/return/repair/disposal | Reconciliation, custody/outflow rules, approval authority and audit integration; no partial placeholders. |

Task 8D implemented the shared core offline. The next technical task is review of its future migration and PostgreSQL command runner/concurrency test design; execution still requires separate authorization. Management must resolve ABD-01?05 for receipt lines and ABD-13 for retry retention/cleanup. No operational endpoint, cleanup scheduler or durable failure/lease behavior is enabled.

Registration and stock activation additionally require the previously pending identity mapping, authorization and audit approvals. There is no new migration, grant, database access or runtime write in this update.

## Task 8B conditional implementation

Only the independent product catalog and receipt header models were implemented under subsequent conditional approval. The remaining slices below still require decisions and review. See [Task 8B scope, tests and migration preparation](asset-model-foundation.md); no migration, database access or operational writes occurred.

Status: design for review only. No new models/migrations/endpoints/grants are authorized by this document. The [asset foundation design](../database/asset-foundation-design.md) supplies the proposed column contracts and distinguishes confirmed PDF requirements from technical proposals. Existing uncommitted security/audit work is preserved.

## Review gates and delivery slices

1. Review the proposed product/receipt/individual-asset/quantity-lot split, procurement inheritance, registration history, required-versus-unknown information, tracking classification and numbering decisions. Confirm the application-controlled audit and authentication boundaries separately; this design does not approve them.
2. After explicit model approval, implement a small offline SQLAlchemy/Pydantic foundation slice using existing masters: inventory_products, receipts, receipt_lines and assets plus the shared idempotency/provenance contract needed by registration. Add metadata tests without database connections or enabled routes. Review unresolved visible-number uniqueness before defining its final constraint. If unresolved, implement only the independent product/receipt subset, not an invented numbering policy.
3. Separately implement/review lot, balance and journal model metadata and enforcement design. Prove cross-table tracking mode, integral-unit checks, registration-count consistency and stock reconciliation before enabling writes. A privileged administrator's ability to bypass constraints is outside runtime guarantees; direct runtime SQL must still be tested.
4. Only after schema and enforcement review, prepare new Alembic revisions extending 7d4a9c2e1b60. Do not edit either existing revision, invent a new current database revision or run migrations automatically. Inspect the actual target revision in a separately authorized preflight; a database behind audit head requires its own approved prerequisite migration.
5. Rehearse those reviewed revisions only on an explicitly authorized disposable target with checksum-verified backup, schema/row/ACL baseline, migration-role authentication and owner assumption. Keep runtime grants separate and fail closed if inherited/PUBLIC privileges differ from the plan. No development-database changes are authorized now.
6. Implement transactional command services and API contracts behind unconfigured/deny-by-default dependencies. Enable operational endpoints only after approved authentication, identity mapping, role permissions, R-10 authority, numbering, idempotency, audit policy and tested minimal database grants are in place. Employee registration stays disabled.

## Future API contract proposal

All paths are beneath /api/v1; names and permission strings are proposed, not active authorization grants.

| Endpoint family | Purpose and authorization boundary |
|---|---|
| GET /asset-categories, /suppliers, /locations, /inventory-products | Reuse reference data with approved scope; minimal fields. Master-data writes require separate management permissions. |
| POST /receipts and POST /receipts/{id}/lines | Capture receipt facts with Idempotency-Key, authenticated recorder and permitted location scope. Distinguish physical receiver from authenticated actor. |
| POST /receipts/{id}/register | Atomically register selected lines/units, provenance and audit; never accept a client-trusted actor, generated number or timestamp. Approval timing remains undecided. |
| GET /assets, GET /assets/{id} | Paginated inventory read, authorized location/org scope; filter visible identifier, category via product, status and serial. Employee/org filtering joins allocations when implemented. |
| GET /assets/{id}/history | Authorized domain history; does not silently expose audit_events or imply full R-11 completion. |
| GET /inventory-lots, GET /inventory-balances | Report lot provenance and stock quantities; distinguish individual-unit counts from lot counts. |
| POST /allocations, /returns, /repairs, /disposals; POST /assets/{id}/transfers; POST /inventory-transfers | Reserved future workflow contracts; require approval/condition/verification rules before implementation. No unrestricted PATCH status or balance endpoint. |

Mutating commands use the shared idempotency scope, payload fingerprint and atomic replay contract. Return 409 for conflicting key payloads, duplicate business identifiers and stale-state conflicts; use an agreed safe response for in-progress commands. Unknown/missing required information receives explicit validation/completeness handling, not fabricated values. Existing authentication remains unconfigured and audit trust decisions remain pending. Future Grok calls can only use ordinary authorized backend workflows, never database credentials or independently trusted actor IDs.

## Proposed database privilege map (not executable grants)

| Workflow | Future minimum privileges to derive and test |
|---|---|
| Read/search | SELECT only the approved columns of assets, receipt lines, products/categories, suppliers and locations required by scoped queries. Sensitive purchase costs, supplier contacts and documents require explicit visibility policy. PostgreSQL table grants alone do not enforce organization scope. |
| Receipt capture | INSERT on client/business fields of receipts/lines; generated UUID/timestamp RETURNING needs narrowly tested SELECT. Draft edits need only explicitly chosen UPDATE columns and approval before granting them. No master-data INSERT/UPDATE simply to simplify fixtures. |
| Individual registration | INSERT on approved assets and asset_registration_events fields; reads of locked source/master references. Number generation privileges depend on the selected scheme. Row locking and ORM UPDATE/RETURNING requirements must be measured with the actual service; do not guess or grant ALL. |
| Quantity receiving/movements | INSERT on lots, initial balances and journal business fields; balance mutation privileges depend on the reviewed SECURITY INVOKER trigger/guard design. Direct arbitrary balance UPDATE must be rejected; this is a gate, not permission to enable free quantity writes. |
| Idempotency | INSERT plus narrowly scoped UPDATE of processing/result columns and necessary SELECT for replay/locking. Restrict request access by authenticated principal; no blanket cleanup DELETE until retention is approved. |
| Audit | Only the separately approved seven-column INSERT, SELECT(occurred_at) and metadata-validator EXECUTE from the current audit proposal. This task grants none. |

No runtime ownership, CREATE/DDL, TRIGGER, REFERENCES, DELETE/TRUNCATE on retained records, owner/migrator membership, or unconditional PUBLIC execution is needed. Functions must use reviewed search paths and explicit execute privileges. Existing sequence privileges are not a reason to grant access to a future numbering sequence. Schema USAGE/connectivity must remain restricted and verified. The current app's four SELECT grants are not sufficient for this future module, and are not expanded by this task.

## Audit and provenance integration

Use the existing caller-transaction audit writer. Domain write, registration history, stock journal, idempotency response and audit event must succeed or roll back together. Authenticated/authorized backend context supplies the actor; timestamps come from PostgreSQL. Audit failure must prevent a successful business commit. Never work around unavailable permissions by omitting audit or committing business data first. R-11 remains partial: metadata allows request_id, changed_fields and outcome only, and cannot hold arbitrary old/new snapshots. Previous/updated values require a separately reviewed redaction/schema design; do not weaken the existing validator. Append-only records do not independently verify human identity. SELECT(occurred_at) exposes audit timestamps across rows; existing pending management decisions remain unchanged.

## Migration and import strategy

Prefer additive reviewable revisions: shared request/product/receipt structures first, then asset/provenance and quantity projections/journal with their integrity triggers. Create indexes/constraints in dependency order; never add a non-null or unique rule to legacy data without validation/backfill review. Give all new objects to inventory_aios_owner through the existing migrator SET ROLE configuration; review default PUBLIC function EXECUTE and keep runtime grants separate. Use transactional DDL where supported and call out any future nontransactional index operation explicitly. An empty-foundation downgrade may be prepared for review, but reject downgrade once business/history rows exist rather than silently deleting them. Recovery/forward-fix decisions require separate approval.

Legacy import is a separate staged workflow: acquire an approved read-only export, preserve originals, classify individual versus quantity items, review duplicate labels/serials, map masters, verify procurement completeness, and approve numbering namespaces before import. Use source-system/record keys for repeatable import; do not invent opening stock or sequence high-water values. Reconcile source-to-target counts and quantities. No source export or database access occurred in Task 8A.

## Testing strategy before activation

- Offline metadata/schema tests: typed columns/nullability, PK/FK RESTRICT behavior, unique source-line/unit keys, lifecycle/JSON/money/quantity checks, category-mode derivation and correct indexes; no duplicate masters.
- Unit command tests: validation, authorization and organization scope, unknown procurement facts, proposed lifecycle rules only after approval, audit fail-closed behavior and disabled endpoints.
- PostgreSQL tests on an explicitly authorized disposable database: invalid foreign keys, allowed/invalid states, negatives/reservations, individual-versus-quantity mismatch, integral-unit validation, receipt over-registration, provenance immutability and direct-SQL bypass attempts. Verify SQLSTATE/constraint identities.
- Concurrency tests with separate real connections: same visible number, same source unit, same idempotency key, changed payload replay, oversubscription, balanced location transfer, registration finalization versus receipt edit, and category reclassification race. Locks/unique constraints must prove correctness, not just sequential tests.
- Transaction tests: business/audit/stock failures and process interruption roll back all effects; crash-after-commit replay creates no duplicates; reservation and partial verified return math reconcile. No permanent synthetic data.
- Permissions tests as the actual runtime login: minimum INSERT/SELECT/UPDATE for concrete ORM statements, forbidden timestamp writes, mutations/history tampering, DDL, trigger changes and role escalation. Owner tests cannot prove runtime privileges.
- Numbering/import tests only after decisions: normalization collisions, namespace ambiguity, sequence gaps, transfer stability, existing-label reservation and idempotent source mapping.
- Offline Alembic rendering and metadata diff review, then separately approved migration rehearsal with before/after schema, counts, row totals and ACL verification. Do not run the existing PostgreSQL integration suite during this design-only task.

## Decisions needed from management and technical review

Management: LED format/scope/immutability/starting data; serial/SKU normalization and uniqueness; category tracking classification, units and fractional quantities; immediate registration versus approval; missing/not-applicable purchase/warranty/serial policy; currency/cost rules; condition vocabulary; allocation/return/repair/disposal and damaged-item transitions; numbering gaps and import mapping; report quantity definitions; audit/identity/provider/retention/access policies already pending.

Technical review: confirm normalized procurement inheritance and lot/location balances; approve ledger enforcement and transaction lock order; define idempotency expiry/replay privacy; choose exact implementation slices and prove minimal runtime privileges. These are proposals requiring review, not assumed company policies.

Recommended next task: approve the schema and resolve numbering/tracking/approval blockers, then implement only the approved offline model-and-test slice. Do not create migration files or enable writes as part of Task 8A.
