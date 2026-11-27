# Phased Implementation Roadmap

## Planning principles

This roadmap is documentation only. Each phase ends with a review checkpoint and test evidence before the next phase starts. It assumes confirmed requirements from the PDF and keeps proposals/decisions visible. No production migration, external connection, or deployment is implied.

## Phase 0 — Decisions, baseline, and acceptance contract

**Scope:** confirm role/approval authority, asset numbering, tracking-mode rules, disposal, notifications, document storage, data retention, report definitions, and organization scope. Convert R-01–R-17 into testable acceptance examples.

**Outputs:** decision register, glossary, approved role matrix, state-transition table, API contract conventions, threat model, backup/restore objectives.

**Verification checkpoint:** requirements review signs off all 17 sections; unresolved decisions are explicitly accepted as backlog items or resolved; no proposal is mislabeled as confirmed.

## Phase 1 — Platform and identity foundation

**Scope:** project configuration, FastAPI route foundation, React shell, responsive layout system, provider-independent authentication and authorization foundation, user/role model, and PostgreSQL/Alembic baseline. The selected initial authentication direction is individual local administrator accounts; shared SSO is optional future work and operational login remains disabled pending policy approval.

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

## Phase 10 — Authentication, authorization, and integration readiness

This roadmap records a proposed sequence, not company security approval. The initial development direction is two individually assigned Inventory AIOS administrator accounts and separately authorized read-only summary access. No operational authentication or summary access is enabled. Preserve stable local user IDs, deny-by-default backend policy, independent employee synchronization, and independent Management AIOS deployment/database boundaries. Database migration execution, account provisioning, external identity access, and Management AIOS changes require their own explicit approvals.

### Task 10C — Provider-independent backend security hardening

- **Objective:** Review and harden the existing verifier, principal mapping, authorization dependencies, error behavior, and service boundaries without selecting a credential provider.
- **Expected files:** `backend/app/core/` authentication/authorization modules, protected route dependencies, focused unit tests, and security architecture notes only if findings require correction.
- **Dependencies/approvals:** Offline; no identity provider or database required. Preserve fail-closed policy and current disabled routes.
- **Acceptance/tests:** Missing, invalid, inactive, expired, and unavailable identities deny access; role changes are observed according to the implemented policy; no sensitive values appear in errors/logging; permission checks are enforced server-side.
- **Safeguards:** No bypass, default identity, role grant, account provisioning, or change to employee registration availability.

**Task 10C status:** Completed as offline provider-independent hardening. The full backend non-integration suite passed 145 tests; 41 PostgreSQL integration tests were deselected. Ruff and Python compilation passed. No database or external service was accessed. This evidence covers fake verifiers, policies, and mocked database failures only; it does not activate authentication or prove operational/production security.

**Task 10D output:** a detailed credential/session schema and lifecycle contract is documented. Team Leader technical approval for offline two-table model and migration-draft work is reported for Task 10E. AUTH-01–AUTH-15 operational decisions remain pending; they gate activation and provisioning according to the [authentication approval gates](../architecture/authentication.md), not the offline schema slice. No login endpoint or account provisioning is authorized by this design output.

### Task 10D — Administrator credential and session contract

- **Objective:** Define local password credential and server-side session data/lifecycle contracts while keeping company policy choices explicit and pending.
- **Expected files:** `docs/architecture/authentication.md`, `docs/database/schema-plan.md`, `docs/architecture/roles-permissions.md`, and this roadmap; no models or migration files.
- **Dependencies/approvals:** Read-only review of existing users/roles/audit relationships and Task 10A–10C findings. Approval is not required to document alternatives; approval is required before Task 10E freezes model fields or operational settings.
- **Acceptance/tests:** Contract defines credential/session columns, indexes, FK behavior, normalization, hashing, expiry/revocation, provisioning/recovery, browser security, migration gates, and offline/database/browser test plans. AUTH-01–AUTH-15 remain pending where unapproved; no existing identity or R-11 requirement is weakened.
- **Safeguards:** No credentials, endpoints, cookies, schema, accounts, permission grants, or authentication behavior implemented.

**Task 10D status:** Documentation contract prepared for review. No application tests are required or run for this documentation-only task; `git diff --check` is required.

### Task 10E — Authentication models and migration preparation

- **Objective:** Reuse local `users`, `roles`, and `user_roles`; implement the approved `user_password_credentials` and `auth_sessions` schema, then prepare an additive migration for separate review.
- **Expected files:** SQLAlchemy user/session models, model exports/tests, Alembic revision, migration documentation, and schema permission review.
- **Dependencies/approvals:** Team Leader technical design and offline implementation scope is reported as confirmed for the two-table contract. Operational AUTH-01–AUTH-15 decisions remain pending; username canonicalization and existing-name collision checks are required before password login/provisioning, not to store a credential FK. Migration execution requires separate database-change approval, backup, exact target guard, owner/ACL/default-privilege baseline, and disposable-database rehearsal.
- **Acceptance/tests:** PostgreSQL dialect DDL and named constraints/indexes are reviewed; stable local user UUID and audit FKs are preserved; no username duplication, exactly-two constraint, default account/password, plaintext credentials, MFA factor, cleanup job, or public registration. Offline model and migration tests distinguish compilation from PostgreSQL enforcement.
- **Safeguards:** Do not connect to databases or execute the revision until separately authorized; no credential values in fixtures or migration text.

**Task 10E status:** Offline models and additive migration draft `0ea2d9c71b45` prepared. Full backend non-integration suite: 151 passed, 41 integration tests deselected, with one existing Starlette/httpx deprecation warning. Focused model/auth/migration suite: 46 passed with the same warning. Ruff, Python compilation, Alembic history and offline upgrade/downgrade SQL generation passed. `git diff --check` reported no whitespace errors (only existing line-ending normalization warnings). Operational policies, database ownership/default ACL verification, migration execution, account provisioning, authentication, grants, and audit writing remain disabled or pending.

### Task 10F — Secure password verification and session lifecycle

- **Objective:** Implement approved Argon2id verification and backend-managed opaque session lifecycle, including login, logout, restoration, password change/reset, rotation, and revocation.
- **Expected files:** Password/session service, auth routes/schemas, settings, approved dependency declaration, cookie/CSRF middleware, and unit/API tests.
- **Dependencies/approvals:** Approved credential/session technical schema (Task 10E); offline Argon2id adapter completed under the separate Task 10F.1A authorization. Offline orchestration/session components and fake-repository unit tests can proceed without provisioning or a live database. Operational password, MFA, rate-limit, recovery, session, and cookie/CSRF policies are required before activation. Applying the migration, provisioning accounts, and database-backed/browser activation tests each require separate approval and controlled setup.
- **Acceptance/tests:** Generic credential failures; rate limiting; secure token hashing and cookies; session expiry/revocation; inactive-user denial; CSRF and origin tests; no localStorage token; failure closed.
- **Safeguards:** No public registration/recovery, default credentials, secret logging, or uncontrolled reset endpoint.

#### Task 10F.1 — Offline hashing boundary

- **Objective:** Define the provider-neutral password hashing interface, safe error contract, and tests without selecting or enabling a cryptographic provider.
- **Expected files:** `backend/app/core/password_hashing.py`, fake-provider tests, and authentication documentation.
- **Dependencies/approvals:** Offline scope only; no dependency or operational-policy approval was needed for the interface. The Argon2 adapter was separately authorized and is documented in Task 10F.1A below.
- **Acceptance/tests:** Hash/verify/rehash behavior is expressed behind an injected backend; bad hashes fail as invalid credentials; backend failures become generic service errors; exact password text is passed without normalization or truncation; no authentication dependency is wired.
- **Safeguards:** Fake providers do not claim cryptographic assurance; no accounts, endpoints, persistence, logs, or fallback authentication.

**Task 10F.1 status:** Provider-neutral service and 13 fake-provider tests remain implemented. Task 10F.1A then added the dependency and concrete adapter under separate developer authorization; see its status below.

#### Task 10F.1A — Approved Argon2id adapter

- **Objective:** Implement the bounded Argon2id adapter using the authorized `argon2-cffi` range and test its real cryptographic behavior.
- **Dependencies/approvals:** Dependency and offline adapter/testing were expressly authorized. Hash costs and input caps used by tests are not approved operational settings. No login routes, persistence or active authentication.
- **Acceptance/tests:** Fake-provider coverage remains; actual hash/verify/mismatch, distinct random salts, malformed/unsupported/unreasonable encoded parameters, rehash detection, long/exact password handling, and sanitized provider failures are covered with bounded test-only costs.
- **Safeguards:** No actual account credentials, expensive load tests, or trust in unbounded stored costs. Authentication remains disabled pending AUTH policies and deployment approvals.

**Task 10F.1A status:** `argon2-cffi>=25.1,<26` declared and installed in the existing backend venv (25.1.0; bindings 26.2.0, cffi 2.1.1, pycparser 3.12). The explicit-config Argon2id adapter is not wired to operational authentication. Focused password/auth/model/migration tests: 67 passed with one existing Starlette/httpx deprecation warning. Full backend non-integration suite: 182 passed, 41 integration tests deselected, with the same warning. Ruff, compilation, dependency consistency, and `git diff --check` results are recorded in the Task 10F.1A completion report; no PostgreSQL integration tests were run.

#### Task 10F.2 — Offline credential verification orchestration

- **Objective:** Build a provider-independent offline authentication service that coordinates a fake/injected credential repository with the password service, with equal generic denial behavior for unknown, inactive and incorrect-password cases and a bounded dummy-hash path for unknown accounts.
- **Expected files:** A narrowly scoped service module and fake-repository/unit tests; authentication design documentation only as needed.
- **Dependencies/approvals:** Requires review of Task 10F.1A adapter behavior and a dummy-hash configuration contract. Must not require live username normalization policy, an actual account, database persistence, session storage, route exposure or operational timing commitments. AUTH policy and deployment approval remain necessary before activation.
- **Acceptance/tests:** Known-user success/failure, unmapped/inactive denial, safe hashing/provider failure propagation, consistent public rejection message, stable local user UUID return for future attribution, timing-path invocation contract, and no persistence/side effects are tested offline. Tests do not claim constant-time behavior or prevent enumeration by themselves.
- **Safeguards:** No login endpoint, account lookup against the database, session creation, credential update, throttling service, role grant, audit write, or activation. Preserve the default unconfigured production verifier.

**Task 10F.2 status:** Offline credential orchestration and fake-repository tests are implemented. Focused password, credential, auth, model, and migration tests: 97 passed with one existing Starlette/httpx deprecation warning. Full backend non-integration suite: 212 passed, 41 integration tests deselected, with the same warning. Usernames, statuses, credentials, and dummy hashes in tests are fictional. No production repository, canonicalizer, route, session, MFA, permission, or audit integration is configured. Credential verification remains separate from authentication and authorization.

#### Task 10F.3 — Offline secure session lifecycle

- **Objective:** Implement injectable session issuance, validation, activity tracking, individual revocation, and an internal user-wide revocation contract.
- **Expected files:** Session lifecycle service, fake-repository tests, authentication documentation, and this plan.
- **Dependencies/approvals:** The prepared AuthSession schema and Task 10F.2 VerifiedCredential contract. Use explicit test policy and fake clock/repositories; no database or operational policy approval is implied.
- **Acceptance/tests:** Canonical 32-byte CSPRNG token format, SHA-256 digest-only persistence, stale account/credential rejection, exact expiry boundaries, activity throttling and conditional updates, idempotent revocation, sanitized failures, and no auth-route wiring.
- **Safeguards:** No database implementation, cookies, login/logout endpoints, MFA, authorization, audit writing, cleanup, or activation.

**Task 10F.3 status:** Offline session service and fake repository tests: 39 passed. Combined authentication/model/migration regression set: 136 passed. Full backend non-integration suite: 251 passed, 41 integration tests deselected. Each suite reported the existing Starlette/httpx deprecation warning. Ruff, compilation, dependency consistency, and `git diff --check` are validated for this task; no PostgreSQL integration or concurrency guarantees are claimed.

#### Task 10F.4 — Login and logout orchestration readiness

- **Objective:** Coordinate credential verification and session lifecycle in an application-level login/logout service; initially keep orchestration injectable and offline.
- **Dependencies/approvals:** Review the Task 10F.3 service contract; approve AUTH-02/03/04/05/06 decisions covering username rules, password/MFA, throttling, recovery, session duration/activity/revocation, and deployment cookie/CSRF/CORS settings before activation. A tested atomic database repository and separately authorized migration rehearsal are required before operational endpoints.
- **Acceptance/tests:** Generic failure mapping, MFA gate before issuance, fresh account/credential revalidation, session issuance only after successful verification and approved factor completion, idempotent logout, no token persistence in the browser, and fake-port failure tests. HTTP/cookie integration and PostgreSQL atomicity are separate approved stages.
- **Safeguards:** Do not wire to the production verifier, enable routes, provision accounts, or activate authentication until the applicable policies and deployment controls are approved.

**Task 10F.4 status:** Offline `LoginLogoutOrchestrator` composes credential verification with session issuance/revocation using injected attempt-protection and authentication-completion policies. Login bounds inputs, fails closed on denied/unavailable policy, records verification outcome/releases attempt capacity, and returns a result only after successful session persistence. Logout revokes only the presented session and separately reports whether server revocation was certain while always allowing a future adapter to clear its local cookie. Tests use fake repositories and policies plus one bounded real Argon2id/session lifecycle path. No routes, cookies, persistent repositories, MFA, rate limiter, account provisioning, permission grants, or operational authentication are enabled. All AUTH-01–AUTH-15 remain Pending Approval. Actual database atomicity, uncertain-commit orphan handling, distributed attempt protection, and browser CSRF/CORS/cookie behavior require separately approved integration work.

**Task 10F.4 validation:** focused authentication/session regression set: 164 passed. Full backend non-integration suite: 279 passed, 41 integration tests deselected. Ruff and `pip check` passed; Python compilation and `git diff --check` passed. The full suite reports one existing Starlette/httpx deprecation warning from FastAPI's TestClient import. PostgreSQL integration tests were not run.

#### Task 10F.5 — Isolated authentication HTTP and browser security adapter

- **Objective:** Prepare login, logout, and session-status HTTP contracts with secure cookie scope, strict request validation, exact Origin checks, a fail-closed CSRF port, and sanitized responses.
- **Expected files:** Isolated versioned authentication router factory, adapter tests, small session validation activity option, authentication architecture and phase-plan updates.
- **Dependencies/approvals:** Existing offline 10F.4 orchestration/session contracts. Explicit test-only policies and HTTPS test URL are used. No operational router registration, production CSRF policy, CORS change, migration execution, or deployment approval is included.
- **Acceptance/tests:** Login JSON is strict and body-limited; CSRF/Origin checks precede credential work; only a Secure/HttpOnly/host-only `__Host-` cookie receives the token; status reads only that cookie and does not extend activity; logout clears with matching scope and distinguishes uncertain revocation; all responses are no-store; operational router remains unchanged.
- **Safeguards:** The CSRF validator is mandatory and injected; a test comparator is not a production mechanism. No permissive default, database repository, HTTP registration, fake operational credentials, or frontend token storage.

**Task 10F.5 status:** adapter prepared in `backend/app/api/v1/routes/authentication.py` and mounted only by in-process tests. Routes are `/api/v1/auth/login`, `/api/v1/auth/logout`, and `/api/v1/auth/session`. Exact Origin allowlisting is separate from CORS. CSRF enforcement is a fail-closed injected boundary; complete synchronizer/signed session-bound token issuance remains deferred. Session status validates without activity updates. Operational `api_router` does not expose the prepared paths. The React frontend, operational CORS and production auth configuration are unchanged.

**Task 10F.5 validation:** authentication HTTP adapter tests: 52 passed. Focused authentication/HTTP/session regression set: 217 passed. Full backend non-integration suite: 332 passed, 41 PostgreSQL integration tests deselected. Ruff, `pip check`, Python compilation, and `git diff --check` passed. The suites report one existing Starlette/httpx deprecation warning from FastAPI's TestClient import. Complete-suite commands ran from a neutral temporary directory with `.env` and `.test.env` absent; isolated focused runs do not import environment-backed app configuration. No database or external service was contacted. Test CSRF behavior is fake-only and does not establish production CSRF protection or browser cookie behavior.

### Task 10G — Administrator and read-only summary permission enforcement

- **Objective:** Implement approved capability permissions for administrator operations and a dedicated aggregate-only summary API.
- **Expected files:** Permission definitions/dependencies, summary service and response schemas/routes, policy documentation, and backend tests.
- **Dependencies/approvals:** Approved role/capability matrix, approval/self-approval rules, summary field/viewer scope, and required database privileges. No implicit administrator approval authority.
- **Acceptance/tests:** Deny-by-default endpoint tests; summary excludes restricted details; reader cannot call operations or access employee/audit/procurement details; unknown data remains distinct from zero; role visibility is not enforced only in UI.
- **Safeguards:** No public summary, unrestricted ORM serialization, blanket role grants, or direct Management database access.

### Task 10H — Frontend login, protected navigation, and summary interface

- **Objective:** Replace preview-only access with approved login/session states and a dedicated summary experience while preserving independent administration UI boundaries.
- **Expected files:** React auth/session client, login/logout and protected-route components, permission-aware navigation, summary page, and frontend tests/styles.
- **Dependencies/approvals:** Stable auth API contract, approved cookie deployment arrangement, approved summary fields and access scopes. Backend endpoints must be available in an authorized test environment.
- **Acceptance/tests:** Direct-route denial, session restoration/expiry, logout, 401/403/service unavailable states, accessible keyboard behavior, no credential/token localStorage, no mocked successful writes.
- **Safeguards:** UI hiding is not authorization; no secrets or external calls in browser.

### Task 10I — Authentication and authorization integration testing

- **Objective:** Verify real auth/session/role behavior end to end, including transactional audit attribution and database least privilege.
- **Expected files:** Isolated PostgreSQL/API integration fixtures and browser/API security tests; no production configuration files.
- **Dependencies/approvals:** Explicit disposable database target, approved test account provisioning, applied reviewed migration, and identity/deployment test arrangements. Any Management service credential test is separately approved.
- **Acceptance/tests:** Individual admin attribution, reader scope, session revocation, account deactivation, CSRF/CORS, permission denials, audit rollback/atomicity, database denied DDL and data access, failure recovery.
- **Safeguards:** Test only approved isolated systems; rollback synthetic data; never use production accounts or credentials in output.

### Task 10J — Security readiness review

- **Objective:** Independent evidence-based review of threat model, authentication, role policy, audit, recovery, deployment, monitoring, and unresolved risk acceptance.
- **Expected files:** Security readiness report and remediation/approval register.
- **Dependencies/approvals:** Tasks 10C–10I evidence; company security and operational owners must approve outstanding policies. No release is implied.
- **Acceptance/tests:** Findings have owners and dispositions; no open critical/high issue is represented as accepted without named approval; operational enablement remains blocked until explicit release authorization.
- **Safeguards:** Do not claim production readiness from preview or offline test evidence.

### Separate future task — Management AIOS integration

After Task 10J and separate approval, design and implement the two entry points: Management AIOS renders an authorized summary using a narrowly scoped server-to-server Inventory summary credential; administrators open the independent Inventory application and authenticate with individual Inventory credentials. Require allowlisted endpoints, timeouts, rate limits, data freshness/cache policy, credential rotation/revocation, and unavailable-service behavior. Do not forward Management bearer tokens, auto-grant Inventory access, merge repositories, share databases, or grant Management direct database access. Any Management AIOS changes belong to its separately authorized repository task. Future SSO is optional and requires an approved identity provider and trust contract.

## Recommended next task

Proceed with **Task 10F.6 — Combined offline authentication contract and security review**. Exercise credential verification, session lifecycle, orchestration, and the isolated HTTP adapter together; review status/error/cookie semantics and ensure no route is wired operationally. Keep the CSRF validator explicitly test-only and record it as an activation blocker until a complete mechanism is approved and implemented. Do not register routes, provision accounts, or activate sessions. Any later operational API stage must wait for relevant AUTH approvals, an approved deployment/cookie/CSRF arrangement, database-backed repositories with atomic account/version checks, and separately authorized migration rehearsal.

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

## Task 9I Settings and Administration frontend checkpoint

The [Settings frontend foundation](settings-frontend-foundation.md) adds a read-only, eight-section configuration preview. Existing fictional asset and employee providers supply category, location, and organization examples; supplier data and operational configuration remain unavailable. Role concepts are proposed, source synchronization is disconnected, notification settings are unresolved, Grok is not connected, runtime audit is not enabled, and production backup/recovery health is not represented. No API, database, or external service is called and all administrative operations remain disabled. This completes the independent frontend preview route set, not operational functionality or production readiness. See the [frontend completion inventory](frontend-completion-inventory.md) for remaining unavailable areas and combined review steps.

## Task 10F.6 combined offline authentication review checkpoint

The [authentication offline review](authentication-offline-review.md) consolidates password verification, credential lookup, session lifecycle, login/logout orchestration, and the isolated HTTP adapter. Duplicate JSON keys, duplicate authentication-cookie values, and ambiguous Content-Length/Transfer-Encoding framing are rejected before authentication processing. Component and combined HTTP tests use fictional data, fake repositories, deterministic clocks, and explicit test policies. Task 10F.6 validation: focused auth components **222 passed**; full backend non-integration suite **337 passed, 41 integration tests deselected**; HTTP adapter **57 passed**; pip check, Ruff, Python compilation, and `git diff --check` passed. One existing Starlette/httpx TestClient deprecation warning remains.

The prepared router remains unregistered and production authentication remains fail-closed. Production CSRF, real browser behavior, PostgreSQL persistence/concurrency/privilege rehearsal, provisioning, MFA/rate limiting, audit writing, and AUTH-01–AUTH-15 approvals remain blockers to operational activation. R-11 is partial. Recommended next task: Task 10G offline administrator and summary-viewer capability design/enforcement tests; do not grant roles or activate authentication.


## Task 9J combined frontend quality review checkpoint

All ten frontend routes have route-level and shared-provider review. Shell metadata now identifies preview/authentication state accurately; Dashboard test timing warnings were corrected without suppression. Static responsive review was performed because browser tooling was unavailable. No external calls or backend operations were added. The full frontend suite (94 tests), TypeScript typecheck, ESLint, production build, and diff checks passed before the local Git checkpoint; production readiness and operational activation remain outstanding. See [frontend quality review](frontend-quality-review.md).

## Accelerated Task A.1 offline implementation checkpoint

Added an explicit capability identifier catalog with unknown-capability and wildcard denial, a fail-closed resource authorization interface, a typed restricted summary service with an isolated router, SQLAlchemy authentication repository adapters, and explicit authentication activation evidence/configuration. The prepared HMAC double-submit CSRF boundary supports login tokens and session-bound state-change tokens; apply `require_authenticated_csrf` alongside authentication, capability, resource, and workflow checks on future mutating routes. No candidate role mapping or operational permission grant was added. The authentication and summary routers remain outside operational router registration. Focused validation: 178 tests passed across permission, summary, repository-contract, runtime-config, CSRF, auth, session, orchestration, and isolated HTTP suites. One Starlette/httpx TestClient deprecation warning remains.

Operational activation remains blocked pending management approvals (including AUTH-01–AUTH-15), PostgreSQL migration rehearsal and ownership/runtime-privilege verification, approved account provisioning and role assignments, distributed login protection and MFA decision, audit-writer verification, deployment-origin/proxy settings, and real-browser CSRF/cookie validation. No migration, database grant, account, permission, or authentication route was activated. R-11 remains partial. Next: obtain required decisions and run separately approved PostgreSQL and browser release gates before considering activation.

## Accelerated Task A.2 integration preparation

Added a per-request database authentication service dependency, a cookie-session Principal dependency that revalidates session and reloads current roles, an unregistered authentication composition path, and the React login/protected-workspace shell. Existing module pages remain labeled as previews; the backend auth routes are still not mounted. Frontend focused tests: 18 passed; backend focused tests: 183 passed. The target-guarded PostgreSQL auth tests and least-privilege grant/verification scripts are prepared but unexecuted. See the authentication architecture and database rehearsal README. The same-origin proxy/deployment path, approvals, username normalization, provisioning authority, production MFA and distributed throttling, migration, grants, and browser verification remain activation requirements.

## Task 10G.1 permission catalog and access matrix

Task 10G.1 is a documentation-only candidate design. The [permission catalog](../architecture/permission-catalog.md) and [access matrix](../architecture/permission-access-matrix.md) separate operational capabilities, summary viewing, workflow-specific approval, and restricted administration. No role mapping or grant is implemented. The [authorization development plan](authorization-development-plan.md) defines the next offline deny-by-default contract/testing scope and the approval gates before any production mapping or access activation. AUTH-01–AUTH-15 remain pending and R-11 remains partial.

## Accelerated Task B — employee and asset foundation

Prepared the provider-independent employee synchronization service, source identity and run metadata, inventory catalog/receipt/asset/quantity metadata, protected read APIs and authenticated-workspace API providers. Source mapping and persistent synchronization remain gated; inventory write APIs are not enabled because required audit, approval and numbering decisions remain unresolved. Additive migration `4b6f10a2c903` follows `0ea2d9c71b45` and has only been compiled offline. See [employee and asset foundation](employee-asset-foundation.md). No migration, database grant, source connection or operational inventory write was performed.

## Combined accelerated Task C+D — workflow, summary, reporting and notification foundation

Added workflow persistence contracts and draft migration `9c81e247a610` after `4b6f10a2c903`, plus safe audit-value validation, fail-closed lifecycle/clearance helpers, and an aggregate-only database summary provider. Authenticated dashboard/workflow/report routes now avoid fictional data and state that their operational providers are unavailable. Product/receiving writes, complete allocation/return/repair/disposal/approval workflows, notifications, report exports and authenticated frontend providers are not complete. No route activation, migration, permission grant, audit enablement, database connection or source import occurred. See [employee and asset foundation](employee-asset-foundation.md). Task C+D remains **PARTIAL**.

### Accelerated Task C+D.2 continuation

Added the authenticated asset operations panel for catalog creation, receipt entry, individual/quantity registration submission, registration decisions and approved posting. Added allocation/return transaction services, schemas and protected handlers inside the existing evidence-gated isolated write router. Authenticated allocation/return routes now use same-origin API-only forms with CSRF/idempotency headers, confirmed-success refresh and no preview fallback. Services require explicit capabilities, active employees/current stock, independent approval, row locks, idempotency and same-transaction audit callbacks. Offline focused validation is reported in the Task C+D.2 completion report; database concurrency, deployment activation and policy approval remain unverified.

### Task C+D.1 implementation continuation

Added an isolated transactional service path for product creation, receipt creation, asset and quantity registration requests, registration decisions, and approved registration finalization. Service policies fail closed; writes use idempotency records, lock relevant category/product/location/receipt rows, keep stock unchanged until approved registration finalization, and stage allowlisted audit events in the caller transaction. Migration draft `a1c7e3052b94` extends the prior workflow revision with registration request records and database-side audit-value validation. The API factory is deliberately not included in `api_router`; operational writes and UI submission remain unavailable. Focused validation: 59 passed across inventory write/schema/model/workflow and offline migration suites; Ruff and Python compilation passed. PostgreSQL tests were not run. Allocations, returns, repairs, disposal, exit-clearance operations, dashboards, reports, notifications, exports, and operational frontend workflow forms remain implementation gaps. Task C+D.1 is **PARTIAL**.

### Task F.1C.1 consolidated application activation checkpoint

Management decisions supplied for two individually attributable administrators (`super_admin`, `system_admin`), lowercase ASCII usernames, `super_admin` as account-provisioning authority, separate explicit approval capabilities with no self-approval, disposal reason codes, quarantine-first damaged quantity handling, independent exit-clearance approval, and session maxima of 8 hours absolute / 30 minutes idle are recorded in [authentication and authorization](../architecture/authentication.md). Confirmed values were connected to username canonicalization, session-setting validation, and disposal reason validation. AUTH-04 MFA is custom but its exact policy is not supplied; repair-cost currency codes and explicit role-to-capability assignments are also absent. The default role policy remains deny-all. No administrators were provisioned, no operational permissions or persistent database grants were applied, and auth/write routers remain behind their activation gates. Task F.1C.1 remains **PARTIAL** pending the exact configuration, least-privilege grants, shared distributed login protection, approved MFA, account bootstrap/audit attribution, and browser/deployment verification.

### Task F.1C.2 final consolidated application integration checkpoint

Added explicit role capability mappings, approved repair currency validation, configurable self-approval behavior, and a PostgreSQL-backed account/IP login-attempt protection adapter with additive migration draft `c4e2b7a91d60`. Added conditional self-approval checks to existing workflow operations, a gated database policy/composition path, and frontend currency/approval text updates. The new migration and prepared least-privilege grant/revocation scripts remain unexecuted. Authentication and inventory-write routers remain unregistered in the operational application; no accounts, role assignments, or persistent grants were created. The revised self-approval policy is test-configurable only until management confirms it supersedes the prior independent-approval decision. Focused validation and database/environment limitations are recorded in the Task F.1C.2 completion report. Status: **PARTIAL**.
