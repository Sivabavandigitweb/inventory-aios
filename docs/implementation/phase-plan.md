# Phased Implementation Roadmap

## Planning principles

This roadmap is documentation only. Each phase ends with a review checkpoint and test evidence before the next phase starts. It assumes confirmed requirements from the PDF and keeps proposals/decisions visible. No production migration, external connection, or deployment is implied.

## Phase 0 — Decisions, baseline, and acceptance contract

**Scope:** confirm role/approval authority, asset numbering, tracking-mode rules, disposal, notifications, document storage, data retention, report definitions, and organization scope. Convert R-01–R-17 into testable acceptance examples.

**Outputs:** decision register, glossary, approved role matrix, state-transition table, API contract conventions, threat model, backup/restore objectives.

**Verification checkpoint:** requirements review signs off all 17 sections; unresolved decisions are explicitly accepted as backlog items or resolved; no proposal is mislabeled as confirmed.

## Phase 1 — Platform and identity foundation

**Scope:** project configuration, FastAPI route foundation, React shell, responsive layout system, authentication integration, user/role model, authorization dependency pattern, PostgreSQL/Alembic baseline.

**Tests:** API authentication, role denial, session/token expiry, secure error responses, responsive smoke checks, migration upgrade/downgrade in an isolated database.

**Checkpoint:** authorized users can reach only permitted placeholder boundaries; no production connection; database migration review passes.

## Phase 2 — Reference data, receiving, and asset registry

**Scope:** categories, products, suppliers, locations, receipts, optional supporting-document metadata, individually tracked assets, quantity lots, asset search/filter, and R-01–R-03/R-14 foundations.

**Tests:** required-field validation, duplicate asset/serial prevention, receipt-to-asset consistency, quantity invariants, document authorization, interrupted receipt rollback, mobile quick-entry flow.

**Checkpoint:** a received asset or quantity item is traceable from receipt to current inventory, with audit history and no partial committed state.

## Phase 3 — Employees, allocation, return, and exit

**Scope:** employee onboarding data through an approved authoritative-source synchronization, organizational history, allocation, return, employee exit, condition capture, and R-04–R-08. Manual employee creation in Inventory AIOS is no longer the proposed workflow.

**Tests:** allocation availability, concurrent allocation conflict, required return before exit completion, return verification, transfer/promotion history, rollback after an interrupted multi-step operation, employee access isolation.

**Checkpoint:** complete happy-path and failure-path lifecycle walkthrough is accepted for tracked and quantity-based inventory.

## Phase 4 — Repairs, approvals, disposal, and audit

**Scope:** repair/damage records, approval engine for registration/allocation/return/disposal, disposal records, immutable audit events, and R-09–R-11.

**Tests:** approval permissions, self-approval policy once decided, invalid state transitions, append-only audit checks, disposal evidence, transaction rollback, recovery after approval interruption.

**Checkpoint:** reviewers can reconstruct who changed what and when; no approved action bypasses authorization or validation.

## Phase 5 — Dashboard, notifications, reports, and documents

**Scope:** R-12–R-15 and document/report delivery: dashboard metrics, pending queues, warranty and missing-information reminders, reports, export jobs, and notification adapter.

**Tests:** metric definitions against fixtures, permission-filtered reports, export access/expiry, duplicate notification prevention, retry and failure status, reminder timing using a controllable clock.

**Checkpoint:** management, auditors, and operations roles see only their approved views; each report has a reproducible filter/as-of definition.

## Phase 6 — Mobile hardening, preferred features, and readiness

**Scope:** R-16–R-17 hardening, accessibility, QR/barcode tracking if approved, Excel/PDF export if approved, performance, observability, backup/restore rehearsal, and operational runbooks.

**Tests:** keyboard/screen-reader-oriented checks, mobile/tablet/desktop regression, barcode workflow, load and pagination checks, security review, restore rehearsal, migration rehearsal, and end-to-end workflow suite.

**Checkpoint:** release-readiness review confirms acceptance coverage, unresolved risk acceptance, backup/restore evidence, secure configuration, and rollback plan.

## Cross-phase quality gates

- Every state-changing endpoint has authorization, validation, transaction, audit, and error-path tests.
- Every database change has an Alembic review and isolated upgrade test; destructive operations have read-only verification first.
- Frontend changes include Vitest coverage for meaningful interaction and permission states.
- Backend and workflow changes include Pytest unit/integration coverage and interruption/rollback cases.
- Traceability matrix links each delivered capability to its requirement ID and acceptance evidence.
- Security checks cover secrets, document/report access, object-level authorization, and safe error handling.

## Recommended next development task

Resolve Phase 0 decisions with company stakeholders, then create the approved domain glossary, state-transition rules, role/approval policy, and API contract outline. Only after that approval should implementation begin with the platform and identity foundation.
## Gap-resolution checkpoints

### Phase 3 exit-clearance verification

Before employee exit implementation is accepted, verify the proposed `employee_exits` and `employee_exit_items` model, permitted transitions, tracked-asset and quantity-item accounting, and the mandatory final clearance invariant. Pytest coverage must include missing returns, partial quantity returns, unverified returns, stale snapshots, concurrent allocation during an active exit, concurrent clearance, rollback after interruption, and audit completeness.

### Phase 2–4 idempotency verification

Before each important write command is released, define its operation scope, canonical fingerprint, response replay, and transaction boundary. Pytest integration coverage must include receiving, allocation, return, approval, disposal, and employee exit. Test identical retries, key/payload mismatch, concurrent identical requests, permanent validation failure, transient rollback/retry, and crash-after-commit replay. Vitest coverage should verify safe retry and in-progress feedback for mobile quick-entry forms.

## Additional quality gates

- No employee exit endpoint can complete without a locked, current outstanding-allocation check.
- No exception transition is enabled until management explicitly approves the policy and authority.
- No important write endpoint is released without idempotency behavior and a duplicate-effect test.
- Idempotency cleanup and employee-exit exception handling remain configurable decisions and must be documented before operational deployment.

## Task 8A asset foundation review checkpoint

The security/audit foundation has technical rehearsal evidence supplied by the user; audit grants and identity/provider policy remain pending, and operational employee writes remain disabled; authoritative-source synchronization is now the proposed direction. Asset work can proceed independently as offline design and, after explicit approval, model development. Task 8A itself creates no models, migrations, permissions or enabled workflows.

Review the [detailed asset schema](../database/asset-foundation-design.md) and [asset implementation plan](asset-foundation-plan.md). They refine Phase 2 and future Phase 3/4 interfaces, reuse existing masters, distinguish individual assets from quantity lots/balances, and identify numbering and policy blockers. The next asset task is review/approval of those contracts, followed by the approved offline model/test slice. Database migrations and runtime activation require subsequent authorization; R-11 remains partial and no audit/authentication policy is changed.

## Task 9A.2 employee synchronization checkpoint

The [employee synchronization architecture](../architecture/employee-synchronization.md) is a design proposal only. The Employees frontend keeps its fictional directory and details but removes manual registration controls and displays a disabled sync action. The existing backend POST registration route remains fail-closed and unchanged; its future removal or replacement with an internal sync command needs a separate decision and test revision. No source connection, destination migration, permission, audit write or scheduled job is enabled.

Before implementing a sync adapter, verify source authority/schema/key and obtain source-owner access approval; approve source-to-local field, organization and status mappings, legacy identity matching, R-16 mobile update path and R-07 exit/clearance behavior. Then design least-privilege separate connections, durable source links and run logs, transactional history/audit/checkpoints, conflict review and idempotent recovery. Test sanitized source fixtures and disposable destination data for duplicate, out-of-order, missing, concurrent and interrupted records before enabling a schedule or manual action. Retain all local UUIDs, allocations and history; never auto-delete a missing source employee or clear exit while assets remain outstanding.

## Task 9C dashboard preview checkpoint

The [Inventory dashboard frontend foundation](inventory-dashboard-foundation.md) reuses the fictional asset and employee providers. It shows calculated individual-asset lifecycle, category and location distributions, per-lot quantity availability, employee overview and navigation into the existing preview pages. Operational approval, return, repair, transaction and exit metrics remain unavailable; source synchronization is not connected. The asset directory received visual-only status, condition-label, dialog, table and focus refinements. This does not complete Phase 5 reporting or enable any Phase 2–4 write workflow. Live metric definitions, approved units, source connections, authorization and integration tests remain future gates.

## Task 9D allocation and return preview checkpoint

The [allocation and return frontend foundation](allocation-return-frontend-foundation.md) replaces both placeholders with fictional, partial linked previews. Directories, details, search, filters, pagination and selectable forms are available; submission remains disabled. Shared employee and asset mock providers supply identities, and a separate workflow preview provider supplies only consistent example links. Employee and Asset details can navigate to the related fictional preview. This does not implement Phase 3 allocation, return or exit-clearance workflows, Phase 4 approvals/audit completion, or operational dashboard pending counts. Authorization, approval/condition decisions, migrations, transactional writes, idempotency and PostgreSQL concurrency tests remain gates before activation.

## Task 9E repair frontend checkpoint

The [repair frontend foundation](repair-frontend-foundation.md) adds a fictional partial R-09 preview with linked asset examples, directory search/filter/pagination, details and a disabled new-repair form. Repair group labels are illustrative only; there are no operational status transitions, provider/cost/document/approval records, database calls or maintenance schedules. Preventive maintenance was not found in the reviewed R-09 requirement. Backend repair records, approval/authority decisions, lifecycle transition rules, audit completeness, idempotent transactions and PostgreSQL integration tests remain Phase 4 gates.

## Task 9F employee exit and asset clearance preview checkpoint

The [employee exit frontend foundation](employee-exit-frontend-foundation.md) adds a fictional partial inventory-clearance review at /exit-clearance. It reuses employee, asset, allocation and return previews, marks return verification and final readiness unknown, and keeps completion disabled. The external employee source remains unconnected; employment status, departure and inventory clearance are separate. No exit state machine is introduced beyond documenting the schema plan's existing unapproved proposal. Operational R-07 implementation remains a Phase 3 gate requiring approved authority/exception policy, quantity obligations, authenticated source mapping, transactions, audit, idempotency and PostgreSQL concurrency/recovery tests.

## Task 9G approvals and notifications preview checkpoint

The [approval and notification frontend foundation](approval-notification-frontend-foundation.md) adds fictional examples for the four R-10 approval workflow types and five R-12 reminder categories. Requests are not submitted or pending operational work; reminder scenarios are not delivered messages. Decision controls remain disabled, authority and delivery are unavailable, and dashboard metrics were not represented as live zero counts. Phase 4 approval processing and Phase 5 notification delivery still require approved role/authority, separation-of-duties, evidence, timing, recipient, transaction, audit, idempotency, access-control and retry policies, followed by backend and PostgreSQL integration tests. Future Grok remains advisory and cannot decide or bypass backend authorization.
## Task 9H reporting and analytics preview checkpoint

The [reporting frontend foundation](reporting-frontend-foundation.md) provides partial, fictional reports derived from shared asset, employee, workflow, repair, clearance and approval providers. It implements R-15 asset summary, employee-wise, department-wise, allocation, return, damaged and employee-exit previews; purchase history and audit trail are explicitly unavailable without data/services. Quantity and approval previews are proposed; missing-information reporting is withheld pending completeness rules. Excel/PDF controls remain disabled despite R-17 preference. Authorization, report definitions, as-of semantics, exports, retention and audit access remain future decisions. This does not implement operational reporting or close Phase 5 reporting.
