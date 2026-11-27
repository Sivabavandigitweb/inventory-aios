# Candidate Permission Catalog

## Status and source boundary

This is a design catalog, not a grant list or approved company access policy. The source PDF states operational requirements and, in section 17 (PDF page 6), web access from authorized devices and preferred login/role-based permissions. It does not define application roles, named approvers, viewer populations, organizational scopes, or per-operation grants. R-11 (section 11, PDF page 4) remains only partially satisfied; this catalog does not claim otherwise. All capabilities below are **candidate, ungranted** identifiers.

Requirement notation uses the requirement section and PDF page: R-01 through R-17 map to sections 1–17. Detailed source text is in the [requirements matrix](../requirements/requirements-matrix.md).

## Candidate access categories

| Category | Intended identity | Boundary |
| --- | --- | --- |
| `inventory_admin` (candidate human role) | Individually authenticated Inventory AIOS account; two named initial account holders are the selected development direction | No wildcard or role-wide bypass. Each capability is separately approved and assigned. This role does not itself imply approval, account administration, audit export, or system administration. |
| `inventory_summary_reader` (candidate human role) | Individually authorized viewer if management approves standalone viewer accounts | Read only dedicated approved aggregate responses. No operational record access or writes. Viewer identity and organizational scope are pending. |
| Approval authority (candidate capability assignments, not a default role) | Named approver(s) for an approved workflow type | Separate from submit/create permissions; scope, delegation, stages, and self-approval are pending. |
| Restricted security/system operator (candidate capabilities, not a default role) | Individually appointed and attributable operator | Provisioning, recovery, role assignment, policy administration, audit access, integration configuration, and backup controls each require separate approval. |
| `management_inventory_summary` (future service identity, not a human role) | Management AIOS backend only, after separate integration approval | Narrow service authentication limited to approved summary endpoints. No raw records, administrator APIs, browser token forwarding, or database access. |

The two administrator accounts must remain separate local `users.id` identities, credentials, sessions, activation state, and audit actors. The schema must not cap the lifetime account count at two. Employee records, Management AIOS users, Inventory AIOS users, and service identities are separate identity classes. Employee synchronization must never provision accounts or assign permissions.

## Catalog conventions

- Capability IDs are proposed names, except the existing `employees:read:all` and `employees:create` identifiers and the `receipts:create` string used by idempotency tests. A name found in code or a test is not an approved grant.
- `Per-action grant` means a narrowly assigned capability only after authorization approval; it never means that every administrator receives it.
- Required scope is checked by backend services for each resource. A capability alone does not prove employee, department, location, custody, or approval ownership.
- State-changing operations must pass workflow validation and record required audit events transactionally before activation.
- Status describes the reviewed backend, not frontend previews: `Guard only` is enforcement without an operational grant; `Test reference` is not a route grant; `Design` means no operational capability implementation was verified.

## Candidate capability catalog

| Capability ID | Module / operation | Access and sensitivity | Candidate access category | Requirement | Existing implementation status | Additional rules, audit, and approvals | Grant |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `dashboard:read:operational` | Operational dashboard | Read; mixed sensitivity | Individually approved per-action grant; summary viewers use only the separate summary contract | R-13 | Design; live operational aggregates not implemented | Must distinguish unknown/unavailable values and source freshness; audit read is not implied | None |
| `summary:read:approved` | Read the approved inventory summary schema | Read; aggregate, potentially sensitive for small groups | Explicit summary viewer; future summary service only under its separate scope | R-13, R-17 | Design; endpoint not implemented | AUTH-09/10 define fields, units, small-cell rules, freshness, population, and scope | None |
| `assets:read` | Read asset records | Read; serial, custody, purchase and supplier fields are sensitive | Per-action grant; summary readers denied | R-02, R-14 | Domain previews exist; endpoint permission not verified | Field-level and department/location scope; audit access separate | None |
| `assets:create` | Register a tracked asset | Write; asset identity and procurement data | Per-action grant; approval may be required | R-01, R-02, R-10 | Design; no operational route grant verified | Unique ID policy, receiving linkage, validation, audit and R-10 workflow | None |
| `assets:update` | Update asset details/status | Write; before/after values may be sensitive | Per-action grant | R-02, R-11 | Design | Allowed fields and lifecycle transitions; transactional audit; no direct status bypass | None |
| `products:read` | Read product/catalog reference data | Read; low to moderate sensitivity | Per-action grant | R-01, R-02 | Design | Separate product/reference data from individual assets | None |
| `products:manage` | Create/update/deactivate catalog entries | Write; master-data integrity | Separately approved reference-data operator | R-01, R-02 | Design | No deletion where historical records depend on the item; audit changes | None |
| `receipts:read` | Read receiving records | Read; supplier, arrival and document metadata | Per-action grant; summary readers denied | R-03 | Design | Scope by approved location/organization; restrict document access | None |
| `receipts:create` | Record a receipt | Write; supplier and receiving detail | Per-action grant; receiving workflow authority separately approved | R-03, R-10 | Referenced in idempotency tests only; no operational grant verified | Actor, receipt date, quantity, location, specs, documents, idempotency and audit | None |
| `receipts:register_asset` | Convert an approved receipt into tracked asset records | Write; asset/procurement detail | Per-action grant plus required registration approval | R-01, R-03, R-10 | Design | Must prevent duplicate/partial registration and reconcile quantity with tracked units | None |
| `inventory:quantity:read` | Read quantity inventory balances | Read; operational availability | Per-action grant; summary only through separately approved aggregates | R-03, R-13 | Design | Preserve unit-of-measure boundaries; do not mix with individual asset counts | None |
| `inventory:quantity:adjust` | Adjust quantity stock | Write; stock integrity | Per-action grant and any separately approved review | R-03, R-11 | Design | Reason/evidence, concurrency-safe balance update, transaction and audit | None |
| `employees:read:all` | Read employee records using existing broad capability identifier | Read; high personal-data sensitivity | No summary-viewer grant; any future grant needs field and resource filters | R-05, R-06, R-07, R-14 | **Guard only** on protected employee routes; no production verifier or grant | “All” must not bypass field-level, department, or purpose limits; consider narrower replacement before activation | None |
| `employees:create` | Manually create employee records using existing identifier | Write; high personal-data sensitivity | Denied/disabled pending workflow decision; never auto-granted | R-05, R-11, R-16 | Guard exists; route remains unavailable without audit-writer dependency; employee source is intended master | Revised source-sync direction does not authorize manual registration; preserve failure closed | None |
| `employees:update` | Change employee-owned profile fields | Write; high personal-data sensitivity | Denied unless approved field ownership/workflow exists | R-05, R-06, R-16 | Design | Source-owned fields must not be overwritten; retain history and audit | None |
| `employee_sync:configure` | Configure source mapping/connection/schedule | Read/write configuration; critical integration sensitivity | Restricted operator only after source-owner approval | R-05–R-07, R-11 | Disconnected design | No credentials in UI/logs; least privilege, mapping review, audit and recovery | None |
| `employee_sync:run` | Start an approved synchronization | State changing; employee data | Separately approved sync operator/service | R-05–R-07, R-11 | Disconnected; not implemented | No account provisioning, preserve UUID/history, idempotency, conflict handling and audit | None |
| `employee_sync:review` | Review synchronization conflicts/errors | Read/write resolution; personal data | Explicitly designated reviewer | R-05–R-07 | Design | Resolution authority and source-of-truth rules pending | None |
| `allocations:read` | Read allocation and custody history | Read; employee/asset relationship | Per-action grant; summary readers denied | R-04, R-07, R-14 | Preview only; endpoint grant not verified | Enforce user/employee, org, location and asset custody scope | None |
| `allocations:create` | Assign an available asset/quantity to an employee | Write; personal and asset custody data | Per-action grant plus R-10 approval if configured | R-04, R-10 | Preview only | Recheck availability, current custody, quantity, employee status, approval and audit in transaction | None |
| `allocations:update` | Correct/change an allocation | Write; high historical impact | Separately approved per-action grant | R-04, R-06, R-11 | Design | Prefer explicit history-preserving events; prevent silent reassignment | None |
| `allocations:cancel` | Cancel an allocation | Write; custody and history | Separately approved per-action grant | R-04, R-11 | Design | Define allowed states and consequences; audit | None |
| `returns:read` | Read return records | Read; employee, condition and remarks | Per-action grant; summary readers denied | R-07, R-08 | Preview only | Resource scope and field filtering; distinguish recorded from verified return | None |
| `returns:record` | Record returned asset/quantity | Write; custody and condition | Per-action grant | R-07, R-08, R-10 | Preview only | Capture required actor/date/condition/remarks; a record alone is not verification | None |
| `returns:verify` | Verify return/condition | Write/attestation; high business significance | Separately appointed verifier; approver role is not inferred | R-07, R-08, R-10, R-11 | Design | AUTH-08 must settle authority and self-review; audit actor/evidence | None |
| `repairs:read` | Read repair cases | Read; notes/provider/cost sensitive | Per-action grant; summary viewers only approved aggregates | R-09 | Preview only | Notes, provider and cost restricted by approved fields/scope | None |
| `repairs:report` | Report damage or open a repair case | Write; asset condition | Per-action grant | R-09, R-11 | Preview only | Validate asset custody/state; audit and evidence | None |
| `repairs:update` | Update repair state/cost/provider | Write; procurement and service data | Separately approved per-action grant | R-09, R-11 | Design | Valid transitions; restrict cost/provider fields; transactional audit | None |
| `exit_clearance:read` | Read exit clearance | Read; sensitive employee/asset detail | Explicitly scoped role; summary viewers denied | R-07, R-11 | Preview only; readiness may remain unknown | Limit to assigned organizational scope and necessary fields | None |
| `exit_clearance:complete` | Complete employee inventory clearance | Sensitive state transition | Separately appointed clearance authority | R-07, R-11 | Not implemented | Block completion until all required returns are verified; define authority/exception policy | None |
| `approvals:read` | Read approval requests | Read; sensitive request/evidence | Explicitly scoped operational reader | R-10 | Preview only | Scope by workflow and organization; does not grant decision rights | None |
| `approvals:decide:asset_registration` | Approve/reject asset registration | Write/decision | Named authority for this workflow only | R-01, R-10, R-11 | Not implemented | AUTH-08: stages, delegation, evidence, self-approval and separation of duties | None |
| `approvals:decide:allocation` | Approve/reject allocation | Write/decision | Named authority for this workflow only | R-04, R-10, R-11 | Not implemented | Revalidate availability and requester/approver separation | None |
| `approvals:decide:return` | Approve/reject return | Write/decision | Named authority for this workflow only | R-08, R-10, R-11 | Not implemented | Preserve distinction between returned and verified | None |
| `approvals:decide:disposal` | Approve/reject disposal | Write/decision | Named authority for this workflow only | R-10, R-11 | Not implemented | Disposal method, evidence, authority and reversibility need decisions | None |
| `disposals:request` | Request asset disposal | Write; lifecycle and procurement history | Per-action request capability | R-10, R-11 | Design | Does not confer approval or finalization | None |
| `disposals:finalize` | Record an approved disposal | High-impact write | Separate executor after required approval | R-10, R-11 | Design | Check approved request and immutable history; audit transaction | None |
| `notifications:read` | Read notification status/history | Read; potentially personal | Explicit operational grant | R-12 | Preview only; delivery disabled | Recipient visibility and retention require approval | None |
| `notifications:manage` | Configure or retry notification delivery | Operational write/configuration | Restricted operator after delivery policy approval | R-12 | Not implemented | Channels, recipients, timing, retries and escalation unresolved | None |
| `reports:read` | View approved reports | Read; varies by report | Per-report grant and data scope | R-15 | Preview only | Report fields, as-of semantics and restricted columns pending | None |
| `reports:export` | Export a report | Data extraction; high disclosure risk | Separate grant per report/data scope | R-15, R-17 | Export unavailable/disabled | File handling, redaction, retention and audit; no blanket export | None |
| `settings:read` | Read non-sensitive configuration | Read; some settings sensitive | Per-action grant | R-17 | Preview only | Secrets and security configuration remain backend-only | None |
| `settings:configure` | Change application settings | Critical operational write | Restricted operator, each setting separately approved | R-17 | Not implemented | Changes need validation, audit, rollback and approval as applicable | None |
| `users:provision` / `users:deactivate` | Provision/deactivate local application accounts | Critical identity administration | AUTH-02 authorized operator only | R-17 | Not implemented | Separate from employee sync; individual attribution and session revocation | None |
| `credentials:recover` | Reset/recover a credential | Critical security operation | AUTH-02/AUTH-05 approved recovery operator | R-17 | Not implemented | Never expose old password; revoke sessions/increment credential version; audit without secrets | None |
| `roles:assign` | Assign/remove time-bounded role assignments | Critical authorization administration | Separately approved role operator | R-17 | `user_roles` model supports validity periods; no grants enabled | Dual control/review and audit policy pending; current assignments rechecked each request | None |
| `permissions:admin` | Change role-to-capability policy | Critical security boundary | Separate security authority; not ordinary admin | R-17 | No production mapping; default deny-all | No wildcard; code/review/change control, audit and rollback | None |
| `audit:read` | View/filter audit history | High sensitivity | Explicit authorized auditor/reader | R-11, R-15 | Audit history query not implemented | Actor/entity scope, field redaction, retention and access review pending | None |
| `audit:export` | Export audit events | Very high disclosure risk | Separate explicit authority | R-11, R-15 | Not implemented | AUTH-13 approval, immutable export log, redaction and retention | None |
| `ai:invoke` | Request AI assistance | Potentially sensitive data transfer | Caller must have the underlying requested read capability | R-17 (AI is not specified in the original PDF) | Grok disconnected | AI has no permissions of its own; payload minimization and human confirmation required | None |
| `summary:service:read` | Future Management backend reads dedicated summary projection | Aggregate service access | Dedicated service identity only; not a human role | R-13, R-17 | Not implemented; AUTH-12/14 pending | Fixed endpoint allowlist, audience/scope, rotation/revocation, rate limits and freshness policy | None |

## Enforcement invariants

1. Authentication identifies a stable local `users.id`; it does not grant permissions.
2. The current `RolePermissionPolicy` is deny-all. Unknown roles/capabilities, missing grants, inactive users, expired/removed assignments, invalid results, and policy/repository failures must deny on each protected request.
3. `user_roles` has a validity interval (`valid_from`, nullable `valid_to`); assignment removal/expiry must apply to the next authorization check. Role names do not imply rights. Multiple-role combination semantics remain a policy decision; no conflicting/deny-override semantics are assumed here.
4. No wildcard, administrator bypass, frontend-only gate, permission snapshot in a session, employee-sync provisioning, or Management AIOS token forwarding is allowed.
5. Capability authorization is followed by resource-scope checks and business-workflow validation. Audit writes are a separate transactional requirement, not a substitute for authorization.

## Offline enforcement preparation (Task A.1)

The backend has a closed capability identifier catalog and rejects unknown capability values and wildcard permission results. This catalog is an identifier allowlist, not a role-to-capability grant map. The production role policy remains deny-all. Resource authorization is an injected server-side boundary and must be followed by business-workflow checks. Candidate mappings in this document remain design proposals and are not active grants.

The restricted summary response/service and router factory are prepared with an explicit summary capability and injected organizational scope/provider. The router is isolated and unregistered; no operational summary data provider exists. Authentication persistence adapters and secure browser composition are also prepared, but authentication configuration defaults disabled and the composition path requires explicit release evidence. No database connection, migration, grant, account provisioning, audit write, or operational route activation occurred in Task A.1.

## Approval dependencies

AUTH-07 governs administrator capability/account-role boundaries; AUTH-08 governs decision authorities and self-approval; AUTH-09 governs summary fields, grouping, units and freshness; AUTH-10 governs viewer eligibility and organizational scope; AUTH-11 governs a standalone viewer channel; AUTH-12 and AUTH-14 govern service authentication and Management AIOS integration; AUTH-13 governs audit readers/export and attribution. AUTH-01/02 govern administrator identity and account/role operators. AUTH-04, AUTH-06, and AUTH-15 remain relevant to authentication activation, sessions, and optional SSO. All remain **Pending Approval** unless separately documented as approved.
