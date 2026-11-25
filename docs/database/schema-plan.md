# PostgreSQL Schema Plan

## Task 8B offline model status

The independent `public.inventory_products` catalog and `public.receipts` header are now registered in SQLAlchemy metadata only. No migration or operational workflow is implemented. Receipt lines, assets and lots remain deferred rather than represented by incomplete models. The shared idempotency core was implemented offline in Task 8D; see the Task 8D status below. See [scope and migration preparation](../implementation/asset-model-foundation.md).

## Design status

This is a normalized planning model for PostgreSQL with SQLAlchemy 2 and Alembic. It preserves current state and history without treating the PDF’s missing policies as settled. It supports both individually tracked assets and quantity-based inventory.

PostgreSQL is the authoritative operational store. Grok, the frontend, document storage, and notification providers access it only through authorized FastAPI services or adapters.

## Task 8A asset design refinement (proposed)

The [asset foundation design](asset-foundation-design.md) is the detailed review draft for asset columns, constraints, numbering, quantity journal/balances, registration history and future relationships. Its asset-specific contracts supersede conflicting shorthand below: product tracking mode derives from the existing category; procurement facts stay on receipt lines; lots have separate location balances; serial uniqueness is undecided; quantity allocations can have multiple partial returns. The conceptual overview is not an implemented schema. No new model or migration is authorized yet. See the [asset implementation plan](../implementation/asset-foundation-plan.md) for API, permission, migration and test gates.

## Core tables

Types below are conceptual PostgreSQL types; exact SQLAlchemy mappings and naming conventions are implementation work.

| Table | Key columns | Relationships and purpose |
|---|---|---|
| `users` | `id uuid PK`, `username`, `email`, `display_name`, `status`, `employee_id FK`, timestamps | Authenticated application identities; optionally linked to an employee. Unique normalized email/username. |
| `roles` | `id`, `code UNIQUE`, `name`, `description` | Proposed RBAC role catalog. |
| `user_roles` | `user_id FK`, `role_id FK`, `valid_from`, `valid_to` | Many-to-many role assignments with history; composite PK. |
| `departments` | `id`, `code UNIQUE`, `name`, `active` | Organization reference data. |
| `teams` | `id`, `department_id FK`, `code`, `name`, `active` | Team belongs to a department; unique `(department_id, code)`. |
| `designations` | `id`, `code UNIQUE`, `name`, `active` | Employee designation reference data. |
| `employees` | `id uuid PK`, `employee_number UNIQUE`, name fields, `department_id`, `team_id`, `designation_id`, `joining_date`, `status`, `exit_date` | Current employee profile. Status values include active, inactive, left_company; final policy is pending. |
| `employee_history` | `id`, `employee_id FK`, old/new org fields, change_type, effective_at, changed_by FK, reason | Immutable transfer, promotion, onboarding, and exit history. |
| `asset_categories` | `id`, `code UNIQUE`, `name`, `tracking_mode`, `active` | Supports individually tracked and quantity-based categories. “Other” preserves source descriptions. |
| `suppliers` | `id`, name, contact fields, active | Supplier/service-provider directory; service providers may be typed or separated later. |
| `locations` | `id`, `code UNIQUE`, `name`, parent/location type, active | Receipt and current asset/storage location. |
| `inventory_products` | `id`, category FK, `sku`, brand, model, specifications, tracking_mode | Normalized product/model data for repeated quantity items and tracked assets. Unique SKU policy is pending. |
| `receipts` | `id`, receipt_number, received_at, received_by FK, location_id FK, status, notes | Header for a new asset receiving event. Receipt approval policy pending. |
| `receipt_lines` | `id`, receipt_id FK, product_id FK, quantity, unit_cost, purchase_date, supplier_id FK, warranty fields, specifications | Quantity and procurement details; check quantity > 0 and money non-negative. |
| `assets` | `id uuid PK`, `asset_number UNIQUE`, product_id FK, serial_number, status, purchase_date, supplier_id, warranty fields, purchase_cost, current_location_id, source_receipt_line_id | One row per individually tracked unit; serial uniqueness scope pending approval; disposed rows are retained. |
| `inventory_lots` | `id`, product_id FK, location_id FK, source_receipt_line_id FK, quantity_on_hand, quantity_reserved | Quantity-based stock; checks non-negative and transactionally updated. |
| `asset_documents` | `id`, asset_id/receipt_id/repair_id/return_id FK nullable, storage_key, checksum, media_type, size_bytes, uploaded_by FK | Metadata only; binary content stays behind a private document adapter. At least one parent reference required. |
| `allocations` | `id`, employee_id FK, asset_id FK nullable, lot_id FK nullable, quantity, allocation_date, assigned_by FK, condition, status | Asset-to-employee assignment. Exactly one of asset or lot is required; tracked assets cannot have overlapping active allocations. |
| `returns` | `id`, allocation_id FK, returned_at, returned_by FK, verified_by FK, condition, remarks, status | Return evidence and verification; one active return per allocation. |
| `repairs` | `id`, asset_id FK, reported_at, reported_by FK, repair_date, repair_cost, service_provider_id FK, status, notes | Damage/repair history; asset status transition is service-controlled. |
| `disposals` | `id`, asset_id/lot_id FK, requested_by FK, approved_by FK, disposal_date, method, reason, status, evidence | Retained disposal record; no hard delete of asset history. Disposal policy and methods are pending. |
| `approvals` | `id`, subject_type, subject_id, workflow_type, status, requested_by FK, decided_by FK, decided_at, comment | Generic approval request linked to registration, allocation, return, or disposal; concrete FK strategy must be chosen during implementation. |
| `audit_events` | `id uuid PK`, nullable `actor_user_id FK` (required for user source), action, entity_type, entity_id uuid, occurred_at, change_source, metadata jsonb | Append-only event envelope for R-11. Metadata allowlist excludes before/after values pending approved confidentiality/redaction policy. See `docs/architecture/audit-logging.md`. |
| `notifications` | `id`, recipient_user_id/role, event_type, subject_type/id, status, channel, scheduled_at, sent_at, failure_reason | In-app/outbox record for reminders and delivery tracking. |
| `warranty_alerts` | `id`, asset_id FK, due_at, status, generated_at, notification_id FK | Prevent duplicate warranty reminders; exact lead time is pending. |
| `report_exports` | `id`, report_type, requested_by FK, filters jsonb, status, storage_key, created_at, expires_at | Asynchronous report/export tracking; expiration policy pending. |

## Relationships and normalization

- A department has many teams and employees; an employee’s changing organization is recorded in `employee_history` rather than overwriting history.
- A product/category describes common attributes; an `asset` represents a serializable, individually tracked unit; an `inventory_lot` represents quantity-based stock.
- A receipt has many lines; a line can create one or more assets or a quantity lot. Receipt evidence is preserved.
- An employee can have many allocations over time. A tracked asset can have many historical allocations but at most one active allocation.
- Returns, repairs, disposals, approvals, and audit events reference the relevant lifecycle record and remain retained.
- Documents use metadata plus a storage key so PostgreSQL remains authoritative for ownership and references without storing large binaries by default.

## Constraints and indexes

### Integrity constraints

- Primary keys use UUIDs for externally exposed records where practical; human-readable asset and receipt numbers are separate unique identifiers.
- `employee_number`, `asset_number`, category codes, location codes, and role codes are unique after normalization.
- Status fields use PostgreSQL enums or constrained lookup tables with explicit migration review.
- `quantity > 0`, `quantity_on_hand >= 0`, `quantity_reserved >= 0`, and `quantity_reserved <= quantity_on_hand`.
- Monetary values are non-negative `numeric` values with an agreed currency policy.
- Asset allocation requires exactly one of `asset_id` or `lot_id`; tracked allocation quantity is one.
- A tracked asset cannot have two active allocations; enforce with a partial unique index or equivalent transaction-safe service check.
- `returns.verified_by` is required when a return is finalized; a fully verified returned asset cannot remain actively allocated; quantity returns may be partial.
- Disposal finalization requires approval and evidence fields according to the approved policy.
- Audit events are append-only to the application role; corrections are compensating events, not updates.

### Indexes

- Assets: unique `asset_number`, unique non-null `serial_number` where company policy requires it, `(status, category_id)`, `(current_location_id, status)`, and `product_id`.
- Employees: unique `employee_number`, normalized searchable name, `(department_id, team_id, status)`.
- Allocations: `(employee_id, status)`, `(asset_id, status)`, `(allocation_date)`.
- Receipts and approvals: `(status, received_at)`, `(workflow_type, status)`, `(requested_by, status)`.
- Audit: `(entity_type, entity_id, occurred_at)`, `(actor_user_id, occurred_at)`.
- Notifications: `(recipient, status, scheduled_at)` and `(event_type, status)`.
- Search may use PostgreSQL `pg_trgm` or a dedicated search strategy only after scale and operational needs are confirmed.

## Transactions and migrations

- Receiving, allocation, return, exit completion, repair status changes, and disposal finalization are transaction boundaries.
- Lock or otherwise serialize the asset/lot row when allocating or returning to prevent double allocation.
- Use Alembic migrations with reviewed forward/backward plans, data backfills, constraints added after cleanup, and explicit backup/restore checks.
- Never run migrations or connect to production without explicit approval. Production backup frequency, retention, restore objectives, and migration window are unresolved decisions.
- Destructive changes require read-only verification, a named approval, and a recoverable backup; prefer status transitions and archival records over deletion.
## Architectural gap resolution: employee exit clearance (proposed design)

The PDF requirement is confirmed: assigned assets must be identified and returned before employee exit completion (R-07). The entities, states, and concurrency controls below are proposed technical design decisions; they do not authorize management exceptions.

### Proposed tables

| Table | Key columns | Relationships and purpose |
|---|---|---|
| `employee_exits` | `id uuid PK`, `employee_id FK`, `status`, `initiated_by FK`, `initiated_at`, `target_exit_date`, `cleared_by FK nullable`, `cleared_at nullable`, `completed_at nullable`, `cancelled_at nullable`, `reason` | One exit case per employee at a time. Holds the workflow state and clearance decision while the employee record retains current status. |
| `employee_exit_items` | `id uuid PK`, `exit_id FK`, `allocation_id FK`, `asset_id FK nullable`, `lot_id FK nullable`, `quantity_expected`, `quantity_returned`, `return_id FK nullable`, `status`, `identified_at`, `resolved_at nullable`, `notes` | Snapshot of every active assignment identified for this exit. A row references the source allocation and either an individual asset or quantity lot. |

Relationships:

- `employee_exits.employee_id` references `employees`; `employee_exits.initiated_by` and `cleared_by` reference `users`.
- `employee_exit_items.exit_id` references `employee_exits`; `allocation_id` references the historical allocation that caused the item to be outstanding.
- `employee_exit_items.return_id` references `returns` when the item is returned. The original allocation remains retained; the return is not a replacement for it.
- Exit and exit-item changes emit `audit_events` with `entity_type`/`entity_id` pointing to the exit or item and the actor/timestamp/old/new values. If concrete foreign keys are preferred, nullable `employee_exit_id` and `employee_exit_item_id` may be added after the audit model review.

### Proposed exit states and transitions

These are workflow states, not company policy:

```text
DRAFT -> OPEN -> AWAITING_RETURNS -> READY_FOR_CLEARANCE -> CLEARED -> COMPLETED
  |       |            |                    |
  +-------+------------+--------------------+--> CANCELLED (before clearance only)
```

- `DRAFT`: case created but not submitted for operational clearance.
- `OPEN`: exit case submitted; active allocations are being identified.
- `AWAITING_RETURNS`: one or more exit items are unresolved.
- `READY_FOR_CLEARANCE`: all identified items have verified returns and zero outstanding quantity.
- `CLEARED`: authorized clearance check succeeded; employee exit may be finalized.
- `COMPLETED`: employee status is changed to the approved inactive/left status in the same final transaction.
- `CANCELLED`: case stopped before clearance; cancellation actor and reason are audited.

Permitted transitions are explicit. No transition from `AWAITING_RETURNS` to `CLEARED` is allowed while any required item is unresolved. A reopened or superseded exit process requires a new proposed state transition and management decision; it is not silently inferred.

### Outstanding-asset rules

At exit opening, the service locks the employee and reads all active allocations. It creates one exit item per tracked asset and one item per quantity allocation (with `quantity_expected` equal to the outstanding assigned quantity). The service must re-query current active allocations during clearance rather than trusting only the initial snapshot.

An exit item is resolved only when:

- a tracked asset has a verified return linked through `return_id`; or
- a quantity allocation has verified returns whose total quantity equals `quantity_expected`.

Outstanding means any active allocation for the employee, any exit item with remaining quantity, any return missing required verification, or any asset/lot whose return transaction has not completed. The mandatory default is that every outstanding item blocks clearance.

### Transaction and concurrency rules

- Opening an exit and snapshotting active allocations occurs in one transaction and locks the employee row before allocation rows.
- Allocation creation for an employee must lock the same employee row and reject new allocations when an exit is `OPEN`, `AWAITING_RETURNS`, or `READY_FOR_CLEARANCE`, unless a future management-approved policy explicitly permits it.
- Final clearance locks the employee row, the exit row, all active allocations, and relevant asset/lot rows in a consistent order; it then re-queries active allocations and item quantities.
- The final clearance check, audit event, employee status change, and `COMPLETED` transition commit atomically. A conflict or interruption rolls back all of them.
- A returned tracked asset cannot be reallocated until its return transaction commits. Quantity stock is adjusted atomically and cannot become negative.

### Exceptions

No exception path is enabled by the confirmed PDF requirement. If management later requires an exception workflow, the proposed shape is `EXCEPTION_REQUESTED -> EXCEPTION_APPROVED` or `EXCEPTION_REJECTED`, with a named approver, reason, evidence, affected item, and audit event. `EXCEPTION_APPROVED` would be the only proposed state allowed to resolve an item without a normal verified return, and it must remain disabled until management explicitly approves the policy and authority.

## Shared idempotency foundation ? Task 8D offline status

The [Task 8D implementation note](../implementation/idempotency-foundation.md) records the model, pure fingerprinting and replay decision components. The management [decision register](../requirements/asset-business-decisions.md) keeps ABD-13 retention pending. This foundation is not migrated, granted or enabled. Its mechanics are technical proposals derived from R-01/R-03/R-10/R-11/R-16, not separate requirements stated by the PDF.

`public.idempotency_requests` has `id uuid PK`, `principal_id uuid FK users ON DELETE RESTRICT`, `operation_scope varchar(200)`, `idempotency_key varchar(200)`, `request_fingerprint varchar(64)`, `status varchar(20)`, `response_status smallint nullable`, `resource_type varchar(80) nullable`, `resource_id uuid nullable`, `completed_at timestamptz nullable`, and standard created/updated timestamps. It stores no request body, full response, authentication token, password, error cache, expiry date or cleanup schedule. Unique `(principal_id,operation_scope,idempotency_key)` scopes claims to a local authenticated user and versioned command. Named CHECKs require nonblank scope/key, lowercase SHA-256 syntax, processing/succeeded status, a complete successful result, and paired resource reference fields. PostgreSQL enforcement awaits a future migration and integration tests.

The caller's business change, audit event, claim and minimal success result must share one transaction. A failed command rolls back all of them. No independent commit is allowed and a durable processing row is an integrity incident, not an automatic lease to recover. The pure service only decides execute/replay/conflict from a caller-supplied snapshot after injected current authorization checks; it makes no database claim and proves no concurrency guarantee. A future runner must handle unique-key races, bounded waits, rollback and post-commit replay with real PostgreSQL connections. A repeated key with changed content is a conflict; business uniqueness/approval checks still apply when a different key is used. Replay returns only the minimal status/resource reference after current operation and resource authorization are checked.

Canonical request fingerprinting includes a versioned scope, sorts object keys, preserves list order, distinguishes types, normalizes finite decimals and aware datetimes, and rejects unsupported data or sensitive field names with generic errors. SHA-256 does not hide low-entropy input; keep fingerprints internal and access-controlled. Retention and safe cleanup are pending ABD-13, so no expiry default or deletion behavior was implemented. Inventory receiving, allocation, return, approval, disposal and employee-exit commands must define their own scope, authorized result visibility and transaction boundary before activation. AI-suggested operations must traverse the same backend rules.

## Core safeguard implementation status

The repository initial revision `36368303c6c6` implements the following technical safeguards for the core tables:

- UUID primary keys retain SQLAlchemy `uuid.uuid4` defaults and add PostgreSQL `gen_random_uuid()` server defaults. The database function is used without adding an extension in this baseline; the supported PostgreSQL version must provide it.
- `updated_at` keeps SQLAlchemy `onupdate` behavior and receives PostgreSQL `BEFORE UPDATE` triggers for database-side maintenance.
- `employee_history` has a PostgreSQL trigger that rejects updates and deletes. Corrections are represented as new compensating history events, subject to authorization and audit rules; no exception path is enabled by this migration.
- `employee_history.change_source` distinguishes `user`, `system`, and `import` technical sources. User-originated events require `changed_by_id`; system and import events may use a null actor only when the application records the source and reason. This is a provenance mechanism, not an approval policy.

These safeguards are implemented in model metadata and migration text. The user reports the disposable rehearsal at revision `7d4a9c2e1b60`; Task 8A performed no database access and does not reverify the state of either database. Trigger behavior remains pending integration testing after explicit migration approval.

## Proposed status values and transitions

Status values remain application-level proposals and are not constrained by this initial migration:

- Employee: proposed `active`, `inactive`, and `left_company`; normal transitions are `active -> inactive` or `active -> left_company` only through approved lifecycle workflows, while reactivation and other transitions require a management decision.
- User: proposed `active`, `inactive`, and `suspended`; authentication and role-revocation behavior remains subject to the approved identity policy.

The database deliberately does not enforce these values or transitions yet. Management must confirm the final vocabulary, transition authority, reactivation rules, and treatment of imported or legacy records before status constraints are added.
## Authentication schema gap (proposed; not migrated)

The current core schema does not store passwords, external identity subjects, login sessions, or revoked-session state. The recommended approach is company-managed OIDC without application-managed passwords, plus stable external identity mapping and hashed opaque session tokens if immediate application logout/revocation is required. Proposed additions are `user_identities` (unique issuer/subject mapped to `users.id`) and `auth_sessions` (user, token hash, timestamps, expiry, revocation, minimal client metadata). These proposals require identity/security approval and an Alembic review before implementation. No schema change has been made. Existing `user_roles.valid_from`/`valid_to` records support assignment validity only; they are not authentication sessions.


## Audit event foundation

The ORM and proposed migration define `public.audit_events` with actor attribution, event/entity identifiers, database timestamp, source, and JSONB metadata checked by a schema-qualified immutable database function against the same allowlist as the application. Append-only triggers reject update, delete, and truncate. The event writer joins the caller transaction and never commits independently. Before/after business values remain unresolved because R-11 needs them but no safe field-level redaction policy has been approved. The migration downgrade refuses to drop non-empty audit history. See `docs/architecture/audit-logging.md`.


## Database role separation preparation (Task 7D.1E.1)

No role, ownership, or grant changes have been executed. The following is a review plan for a later approved rehearsal on `inventory_aios_restore_check`; it is not execution authorization. PostgreSQL roles and role memberships are cluster-wide. Database CONNECT grants, schema grants, object ownership, object ACLs, and default privileges are database-scoped (default privileges are per creating role and optionally schema).

### Existing role handling and membership

`inventory_aios_app` already exists. Inspect its attributes, memberships, ownership, and grants; do not recreate it. Review whether the proposed owner and migrator names already exist before any cluster-wide role statement. `inventory_aios_owner` should be `NOLOGIN`. The migrator should have no superuser, database creation, role creation, replication, or row-security bypass capability. Configure its membership explicitly with `INHERIT FALSE` and `SET TRUE` (PostgreSQL versions supporting membership options):

```sql
-- Cluster-wide; administrator action after conflict and dependency review.
GRANT inventory_aios_owner TO inventory_aios_migrator WITH INHERIT FALSE, SET TRUE;
```

This permits an explicit `SET ROLE` while preventing automatic privilege inheritance. Verify role attributes and membership options from `pg_roles` and `pg_auth_members` after any approved change. Do not grant owner membership to the application login.

### Ownership and privilege inventory

Before proposing any transfer, inventory the target database owner, `public` schema owner, application tables, partitioned tables, sequences, views, materialized views, types, and functions (including signatures), plus ACLs and dependencies. Review ownership of the database and schema separately: do not transfer the shared `public` schema or database owner by default. Transfer only confirmed application objects to `inventory_aios_owner`; ownership changes are not equivalent to grants and can affect other users, dependencies, and operational tooling. Avoid broad `REASSIGN OWNED` unless a complete cluster-wide impact review approves it.

Inspect existing PUBLIC grants and inherited role grants. PostgreSQL commonly grants PUBLIC function EXECUTE by default. For functions created by `inventory_aios_owner`, remove that global default explicitly (no `IN SCHEMA` clause), since per-schema default privilege revokes cannot cancel a global default grant; then add narrowly scoped schema defaults only if approved. Revoke existing PUBLIC EXECUTE from the reviewed application functions individually or with a carefully reviewed schema-scoped statement. Review other database/schema/table PUBLIC grants rather than applying blanket revocations that could break unrelated users.

```sql
-- Database-specific default privileges for future objects created as owner.
ALTER DEFAULT PRIVILEGES FOR ROLE inventory_aios_owner
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE inventory_aios_owner IN SCHEMA public
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE inventory_aios_owner IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM PUBLIC;
```

Default privileges do not change existing objects. Enumerate and adjust current ACLs separately.

### Runtime least privilege

Derive grants from active application service queries and writes, not from test convenience. Current employee registration is disabled; when enabled, its database work requires reads of user/organization references and inserts into employees, employee_history, and audit_events. Read access for actual list/get workflows must be mapped table by table. Grant only the required SELECT and INSERT on those tables; grant no runtime UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER, schema CREATE, ownership, or ability to assume the owner. Existing sequence use must be verified before granting sequence privileges; the core migration uses UUID server defaults. Future audit_events access is pending the later migration and approved workflow.

The runtime process loads only `.env`. Alembic loads its migration URL from the separate ignored `.migration.env`; the integration harness loads runtime and owner test URLs from ignored `.test.env`. The checked-in `.env.example`, `.migration.env.example`, and `.test.env.example` contain placeholders only. Keep the actual migrator secret out of the runtime service environment.

`employee_history` must remain append-only: runtime has at most SELECT and INSERT, while UPDATE, DELETE, and TRUNCATE are denied by ACL and its trigger. Runtime cannot own the table, alter/disable triggers, or replace trigger functions. Owner-level trigger tests use the separately configured migration identity to assume owner; runtime permission tests use only `inventory_aios_app`. Do not widen runtime grants to make owner-level fixtures pass.

### Rehearsal and recovery boundaries

Use only the disposable `inventory_aios_restore_check` database for a future approved rehearsal. Confirm its backup, revision, object inventory, and schema comparison first. Role creation and membership are cluster-wide even during this rehearsal; all grants and ownership transfers must target only that database's confirmed application objects. Test runtime and migration connections independently, verify denied DDL and history mutation as runtime, and verify approved migration object ownership after explicit owner assumption. Never execute these proposed statements against `inventory_aios_dev` as part of rehearsal.

Before any later rollout, retain a verified pre-change backup and catalog inventory. Recovery should restore the database backup or explicitly restore reviewed database-specific owners and ACLs; do not use `DROP OWNED` or delete cluster roles until all database dependencies, memberships, and owned objects are reviewed.
