# Employee synchronization architecture — proposal

Status: design only. No source database, Management AIOS database, or Inventory AIOS database was contacted. No synchronization connection, job, endpoint, table, grant or schedule is implemented. Inventory AIOS remains on fictional employee preview data; the existing employee registration endpoint remains disabled.

## Requirement boundary and source of truth

The original requirements PDF R-05 requires employee onboarding information and asset links, R-06 requires transfer/promotion updates with complete history, and R-07 requires inactive/left status, return of all assigned assets before exit completion, and retained history. R-04/R-08/R-13/R-14/R-15/R-16 use employee identity for allocation, returns, dashboards, search, reports and mobile employee updates. The PDF does not say that Inventory AIOS must be the system where staff create employee master records. The new project direction is to synchronize those records from an existing authoritative employee system. This changes the proposed input mechanism, not the required data or asset/exit obligations.

Potential source identified earlier: database `ledsone`, schema `employee_management`, table `staff`. Potential Management AIOS reference: database `order_management_copy`, schema `management_aios`, table `staff_dashboard_records`. These names are **unverified leads**, not current connection targets or approved schemas. If management confirms `ledsone` as the authoritative source and authorizes access, prefer a direct one-way feed from it. Use the Management AIOS dataset only to compare mapping and behavior after separate authorization; a derived dashboard copy is not assumed to be authoritative.

The PDF R-16 explicitly asks users to update employee information from mobile devices. Routing source-owned employee edits to the authoritative system may conflict with that expectation unless management confirms that a mobile hand-off to that system satisfies R-16 or identifies local-only employee data that Inventory AIOS may edit. This decision is pending. R-07 also requires a decision on how a source employment-status change interacts with local return clearance. Do not equate a source departure signal with a completed Inventory AIOS exit.

## Proposed data flow

1. A separately configured source reader uses a read-only account and a narrowly scoped query or approved view. It reads only needed fields in bounded batches with a stable source key and change cursor or snapshot boundary. It never writes to the source.
2. A synchronization service validates identity, field types, required values, organization codes, status mapping and source version. It reports missing/ambiguous mappings for review; it never guesses from names, email or row order.
3. The destination writer uses a separate authorized Inventory AIOS connection and a transaction per bounded batch. It locks mapping/current rows as needed, upserts by the stable source identity, retains the existing local `employees.id` UUID, adds organization history and audit events, and records a committed checkpoint or processed source version in that same destination transaction.
4. Only a committed batch advances the cursor. Retry uses source key plus version/fingerprint to avoid duplicate onboarding/history/audit effects. A failure rolls back the batch, records a sanitized failure outside the failed transaction if authorized, and leaves the prior committed checkpoint available for recovery.
5. An authorized operator can review conflicts, freshness and run history. Scheduling and any manual Sync action remain disabled until source authority, roles, permissions, monitoring and recovery are approved and integration tested.

No cross-database transaction is assumed. The reader and writer use separate pools and credentials. The destination must tolerate source changes between pages by using a verified source snapshot/cursor contract, followed by a reconciliation pass. Do not use an unverified timestamp alone as a deletion or completion signal.

## Mapping contract to verify

| Destination | Required source evidence and rule |
| --- | --- |
| Proposed `employee_source_links(source_system, source_employee_id, employee_id, source_version)` | Confirm an immutable, non-recycled source key. Unique source-system/key and unique local employee link. Preserve local UUID for all existing allocations, history and user links. No match by name or mutable email. |
| `employees.employee_number` | Confirm source staff/employee number, uniqueness, reuse and correction policy. It may be displayed as a code but is not assumed to be the immutable source key. |
| `first_name`, `last_name` | Confirm source fields, splitting of full names, Unicode normalization and handling of missing parts. Never invent a value silently. |
| `department_id`, `team_id`, `designation_id` | Approved source-code-to-local-reference maps; confirm team belongs to department and effective dates. Missing/ambiguous mappings enter a conflict queue rather than creating arbitrary masters. |
| `joining_date` | Confirm date meaning, timezone/date-only semantics and handling of unknown historical values. |
| `status`, `exit_date` | Approve exact source-to-local vocabulary and effective-date mapping. Preserve a distinction between source employment status and local asset-clearance state; the current single `status` field is insufficient to represent both safely without a reviewed contract. |
| `users.employee_id` | Preserve existing local user association; synchronize employee master data only. External authentication identity/provider mapping remains a separate approved boundary. |

Source column names, key stability, update semantics and permissions have not been inspected. A mapping specification and representative sanitized samples require source-owner review before a schema change or import. Legacy Inventory AIOS employees require a reviewed one-time matching plan with duplicate/collision reports before any link is created.

## Lifecycle and conflict rules

- **New source employee:** create one local profile only after required mappings validate; allocate a new local UUID once, keep the source link, and record onboarding provenance. A repeated source record creates no second employee.
- **Existing employee:** update only approved source-owned fields when the source version changes. Retain historical organization and allocation context; do not rewrite old allocation facts or delete history. Use effective dates from the source only when verified.
- **Source departure or disappearance:** never delete a local employee or cascade asset references. A missing row is a discrepancy for review, not an automatic exit. A departure signal must not mark Inventory AIOS exit complete while assigned assets lack verified returns. The exact visible status, allocation block and notification policy are pending.
- **Conflicts:** duplicate source keys, recycled employee numbers, source-key changes, competing local matches, ambiguous organization values, out-of-order versions and invalid dates/statuses stop affected records and create reviewable, sanitized conflict entries. Unaffected records may proceed only under an approved batch policy. No silent overwrite or merge.
- **Idempotency and recovery:** source key/version plus reviewed fingerprint identifies an already applied change. Use uniqueness and row locks in the destination, with checkpoint and audit changes in one transaction. After interruption, resume from the last committed checkpoint and reconcile. Test concurrent runs, reruns, out-of-order changes and rollback against an isolated database before activation.

## Security, audit and operations

Source access must be read-only and scoped to approved employee fields. Source and destination credentials live in separate secured configuration, never in frontend code, chat, logs or command arguments. The sync worker has no migration/owner privileges. Destination permissions must be demonstrated from the actual SQL statements and approved separately. Network/TLS, source-owner approval, PII minimization, retention, operator authorization and monitoring need review. The frontend must never connect directly to either database.

Synchronization logs should record run ID, source version/cursor, start/end, counts of created/updated/unchanged/conflicted records, sanitized error categories and checkpoint status, without raw employee payloads. Audit/history must distinguish a system-initiated sync from a human change in the source. If the source supplies a verifiable human actor, define a reviewed mapping; otherwise do not attribute the change to an arbitrary local user. R-11 before/after values and redaction remain incomplete, so synchronization cannot claim full audit compliance. Audit events, employee changes, history and checkpoint must share the destination transaction; permanent audit write grants remain pending.

## Pending decisions and implementation stages

1. Confirm authoritative source owner/system, access path, immutable key, source change feed/snapshot semantics and whether Management AIOS is reference only.
2. Approve source-to-local field, organization, status and legacy-link mappings; resolve unknown data, conflicting identities and effective dates.
3. Confirm R-16 mobile update path, R-07 source departure versus local clearance, allocation-block behavior, operator authority and conflict workflow.
4. Approve authentication/service identity, PII scope, audit attribution/redaction, sync schedule, freshness alerts, logs/retention and recovery expectations.
5. After approval, design additive source-link/run/conflict metadata and an internal sync service; review migration, least-privilege connections and rollback plan. Keep the public registration endpoint fail-closed, then decide whether to remove it or replace it with a separately authorized internal command.
6. Test with sanitized source fixtures and disposable destination database: initial import, update, duplicate, missing employee, status/exit conflict, referential history, idempotent rerun, concurrent runs, interrupted batches, source outage, privilege denial and audit atomicity. Enable scheduling/manual action only after those gates pass.

Existing backend registration models, migration, route, service and tests are retained in this task. Future changes must revise their contracts and tests without weakening the current fail-closed behavior.
