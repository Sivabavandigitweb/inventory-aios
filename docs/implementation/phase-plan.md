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

**Scope:** employee onboarding, organizational history, allocation, return, employee exit, condition capture, and R-04–R-08.

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