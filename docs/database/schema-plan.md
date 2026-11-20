# PostgreSQL Schema Plan

## Design status

This is a normalized planning model for PostgreSQL with SQLAlchemy 2 and Alembic. It preserves current state and history without treating the PDF’s missing policies as settled. It supports both individually tracked assets and quantity-based inventory.

PostgreSQL is the authoritative operational store. Grok, the frontend, document storage, and notification providers access it only through authorized FastAPI services or adapters.

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
| `assets` | `id uuid PK`, `asset_number UNIQUE`, product_id FK, serial_number, status, purchase_date, supplier_id, warranty fields, purchase_cost, current_location_id, source_receipt_line_id | One row per individually tracked unit; serial uniqueness when present; disposed rows are retained. |
| `inventory_lots` | `id`, product_id FK, location_id FK, source_receipt_line_id FK, quantity_on_hand, quantity_reserved | Quantity-based stock; checks non-negative and transactionally updated. |
| `asset_documents` | `id`, asset_id/receipt_id/repair_id/return_id FK nullable, storage_key, checksum, media_type, size_bytes, uploaded_by FK | Metadata only; binary content stays behind a private document adapter. At least one parent reference required. |
| `allocations` | `id`, employee_id FK, asset_id FK nullable, lot_id FK nullable, quantity, allocation_date, assigned_by FK, condition, status | Asset-to-employee assignment. Exactly one of asset or lot is required; tracked assets cannot have overlapping active allocations. |
| `returns` | `id`, allocation_id FK, returned_at, returned_by FK, verified_by FK, condition, remarks, status | Return evidence and verification; one active return per allocation. |
| `repairs` | `id`, asset_id FK, reported_at, reported_by FK, repair_date, repair_cost, service_provider_id FK, status, notes | Damage/repair history; asset status transition is service-controlled. |
| `disposals` | `id`, asset_id/lot_id FK, requested_by FK, approved_by FK, disposal_date, method, reason, status, evidence | Retained disposal record; no hard delete of asset history. Disposal policy and methods are pending. |
| `approvals` | `id`, subject_type, subject_id, workflow_type, status, requested_by FK, decided_by FK, decided_at, comment | Generic approval request linked to registration, allocation, return, or disposal; concrete FK strategy must be chosen during implementation. |
| `audit_events` | `id`, actor_user_id FK, occurred_at, entity_type, entity_id, action, previous_value jsonb, new_value jsonb, request_id | Append-only audit record for R-11; sensitive-field redaction policy pending. |
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
- `returns.verified_by` is required when a return is finalized; a returned asset cannot remain actively allocated.
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

## Architectural gap resolution: request idempotency (proposed design)

Idempotency is a technical safety control, not a business approval policy. It prevents retries from creating duplicate receiving, allocation, return, approval, disposal, or exit effects.

### Proposed table

| Table | Key columns | Purpose |
|---|---|---|
| `idempotency_requests` | `id uuid PK`, `principal_id FK`, `operation_scope`, `idempotency_key`, `request_fingerprint`, `status`, `response_status`, `response_body jsonb nullable`, `resource_type nullable`, `resource_id nullable`, `created_at`, `updated_at`, `completed_at nullable`, `expires_at`, `error_code nullable` | Stores the request claim, canonical payload fingerprint, processing/result state, replayable response, and retention deadline. |

### Key and fingerprint rules

- The unique scope is `(principal_id, operation_scope, idempotency_key)`. `operation_scope` includes HTTP method, normalized route family, and any resource identifier that changes the command meaning.
- The client supplies the key in an `Idempotency-Key` header for important commands. The backend canonicalizes the validated request body and relevant command parameters, then stores a cryptographic fingerprint.
- A repeated key with the same scope and identical fingerprint replays the stored successful or permanent-failure response without repeating the business operation.
- A repeated key with a different fingerprint is rejected as a conflict; it cannot mutate or reuse the original request.
- A request still marked `PROCESSING` returns a deterministic in-progress response or waits under a bounded policy. It never starts a second business transaction.

### Transaction, crash, and failure behavior

- The idempotency claim and the business write share one database transaction for each command. A unique-key conflict loads the existing row and compares the fingerprint.
- The first request inserts `PROCESSING`, performs authorization and validation, executes the business transaction, records audit events, stores the response/resource reference, and commits as `SUCCEEDED`.
- A permanent client error can commit as `FAILED` with its safe response and no business mutation; the same key replays that error. A corrected request uses a new key.
- A transient server/database failure rolls back the business write and the idempotency claim together, allowing a retry with the same key. Recovery of an orphaned `PROCESSING` row uses `expires_at` and a bounded reconciliation rule; it must never blindly replay a partially committed business effect.
- If the server crashes after commit but before responding, the retry finds `SUCCEEDED` and returns the stored response/resource reference.
- Response bodies must exclude secrets and sensitive data not already authorized for the principal.

### Retention and expiry

`expires_at`, response retention, cleanup method, and whether audit references outlive idempotency rows are configurable decisions. Until decided, rows must not be deleted while a request can still be retried by an active client, and cleanup must be read-only verified and auditable.

### Required command coverage

The strategy applies to receiving, allocation, return, approval decision, disposal request/finalization, and employee-exit commands. Each command must define its operation scope, canonical fingerprint inputs, replay response, and transaction boundary before implementation.
## Core safeguard implementation status

The unapplied initial revision `36368303c6c6` implements the following technical safeguards for the core tables:

- UUID primary keys retain SQLAlchemy `uuid.uuid4` defaults and add PostgreSQL `gen_random_uuid()` server defaults. The database function is used without adding an extension in this baseline; the supported PostgreSQL version must provide it.
- `updated_at` keeps SQLAlchemy `onupdate` behavior and receives PostgreSQL `BEFORE UPDATE` triggers for database-side maintenance.
- `employee_history` has a PostgreSQL trigger that rejects updates and deletes. Corrections are represented as new compensating history events, subject to authorization and audit rules; no exception path is enabled by this migration.
- `employee_history.change_source` distinguishes `user`, `system`, and `import` technical sources. User-originated events require `changed_by_id`; system and import events may use a null actor only when the application records the source and reason. This is a provenance mechanism, not an approval policy.

These safeguards are implemented in model metadata and migration text but have not been executed against the database. Trigger behavior remains pending integration testing after explicit migration approval.

## Proposed status values and transitions

Status values remain application-level proposals and are not constrained by this initial migration:

- Employee: proposed `active`, `inactive`, and `left_company`; normal transitions are `active -> inactive` or `active -> left_company` only through approved lifecycle workflows, while reactivation and other transitions require a management decision.
- User: proposed `active`, `inactive`, and `suspended`; authentication and role-revocation behavior remains subject to the approved identity policy.

The database deliberately does not enforce these values or transitions yet. Management must confirm the final vocabulary, transition authority, reactivation rules, and treatment of imported or legacy records before status constraints are added.
## Authentication schema gap (proposed; not migrated)

The current core schema does not store passwords, external identity subjects, login sessions, or revoked-session state. The recommended approach is company-managed OIDC without application-managed passwords, plus stable external identity mapping and hashed opaque session tokens if immediate application logout/revocation is required. Proposed additions are `user_identities` (unique issuer/subject mapped to `users.id`) and `auth_sessions` (user, token hash, timestamps, expiry, revocation, minimal client metadata). These proposals require identity/security approval and an Alembic review before implementation. No schema change has been made. Existing `user_roles.valid_from`/`valid_to` records support assignment validity only; they are not authentication sessions.
