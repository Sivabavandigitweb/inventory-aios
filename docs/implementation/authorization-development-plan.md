# Authorization Development Plan

## Status

Task 10G.1 is a documentation/design checkpoint. No permissions are granted and no authorization code changes are made here. The production `RolePermissionPolicy` remains deny-all. The existing authentication HTTP router is still unregistered. R-11 remains partially implemented.

## Authentication and access layers

Keep four independent checks visible in designs and tests:

1. **Authentication:** validate a credential/session and identify the stable local `users.id`; employee records and Management AIOS identities are not substitutes.
2. **Capability authorization:** evaluate a narrow backend capability against current valid local role assignments. Unknown capabilities, roles, missing assignments, invalid policy results, inactive accounts, and infrastructure failures deny.
3. **Resource authorization:** verify the requested employee, asset, location, department, allocation, approval, report, or audit record is within the actor’s approved scope. Do not use a capability name such as `employees:read:all` as proof of every object/field entitlement.
4. **Business workflow validation:** verify the state transition and rules (for example, asset availability, verified returns before exit clearance, approval state, duplicate/idempotent command handling). A permission never bypasses workflow invariants.

The existing `require_permission()` and employee read/create dependencies can be reused. Current guards protect employee routes only. `employees:create` is not an approved operational workflow under the source-sync direction and remains unavailable through its fail-closed audit-writer dependency. The `receipts:create` string appears in idempotency tests but is not evidence of a protected receiving endpoint. No production capability mapping has been verified.

## Candidate Task 10G sequence

| Task | Objective and bounded scope | Dependencies / approvals | Acceptance evidence |
| --- | --- | --- | --- |
| **10G.1 — Permission catalog and access matrix (this task)** | Document candidate roles/categories, operation-level capability identifiers, scopes, sensitivity, audit/approval dependencies, and pending AUTH decisions. | Requirements and architecture review only. No company grant approval needed for a clearly labeled proposal. | PDF section references and exact current implementation status; no grant or source change. |
| **10G.2 — Deny-by-default policy contract and offline enforcement tests** | Reuse `RolePermissionPolicy`/`require_permission`; define a typed capability decision boundary and test explicit allow/deny, unknown IDs, malformed policy results, absent role, inactive user, expiry/removal, and outage. Use fake policies only for positive candidate cases. Keep production policy deny-all and do not seed/map operational roles. | Can proceed offline. Management approval is required before activating any production role-to-capability mapping or assigning a role. | Offline tests prove authorization occurs at backend boundary and removed/expired grants deny on later checks; no actual grants. |
| **10G.3 — Resource-scope authorization contract** | Design and test injected scope checks for department/location, custody, report, approval, and exit-clearance resources using fictional records. | Can define/test interface offline. Management must approve actual scopes and data classes before production policy. | Out-of-scope access is denied; scope and workflow checks are separate. No database query changes until separately reviewed. |
| **10G.4 — Summary response schema and offline service** | Define a dedicated aggregate projection and unknown/freshness semantics; never expose ORM/operational records. Test individual asset counts separately from compatible quantity units and small-group suppression only after a decision. | Schema structure can be prototyped offline. AUTH-09 fields/grouping/freshness and AUTH-10 viewer identities/scope must be approved before exposing results. | Response whitelist tests; no API registration, grants, database access, or external calls before a separate task. |
| **10G.5 — Approval and restricted-administration capability contracts** | Model request/decision separation and distinct account, role, permission, audit, sync, and system-configuration capabilities without assigning them to administrator by default. | Offline contract tests may proceed; AUTH-02, AUTH-07, AUTH-08, and AUTH-13 decisions required before operating the workflows. | Submitter cannot gain decision right implicitly; self-approval behavior follows an approved rule, otherwise decision is unavailable. |
| **10G.6 — Management summary service boundary (future, separately authorized)** | Keep independent app/backend/database; specify a fixed summary-only server-to-server API and Management user gate. Administration remains a separate Inventory login. | AUTH-10, AUTH-11, AUTH-12, AUTH-14 and both application owners’ security/deployment approvals. No Management repository work in this phase. | Service identity cannot call operational routes; user-level gate and revocation behavior documented and tested offline. |

## Proposed access evaluation semantics (not activated)

- Retrieve current active user and current role assignments on each protected operation; apply `valid_from` and `valid_to` using server UTC time. Removed or expired assignments must not be cached as authorization.
- Resolve each permission through an explicit allowlist. Unknown capability or role means deny. Policy/store failure means sanitized unavailable/deny; no fallback policy.
- Never interpret administrator role as a shortcut around capability checks. Never grant an administrator account/session based on successful login alone.
- Keep permissions out of long-lived session snapshots. A validated identity supplies a stable user ID; current capabilities are re-evaluated.
- Defer multiple-role conflict semantics, delegated authority, emergency access, and whether a principal may hold both submitter and approver assignments until a written decision. Until then, affected operations cannot be activated.
- Frontend navigation may reflect authorization for usability but is not enforcement. All protected reads/writes and exports must be checked in backend routes/services.

## Resource scope and workflow checks

Potential resource constraints include department/location visibility, employee-specific assignments, asset custody, allocation owner, receipt location, approver’s workflow type, assigned exit-clearance responsibility, report filters, and sensitive serial/cost/repair/audit fields. Database filtering must be performed server-side and must not rely on client-supplied organization identifiers. Define whether the local administrator scope is organization-wide only after approval. Keep unknown or incomplete scope as denial or explicit unavailable state, not a silent all-records result.

An `allocations:create` capability cannot allocate an unavailable asset; `exit_clearance:complete` cannot override outstanding/unverified returns; `approvals:decide:*` cannot be inferred from `inventory_admin`; `reports:export` is separate from viewing. These are validation boundaries, not newly approved company workflows.

## Candidate inventory summary contract

The summary is separate from the administrator operational dashboard and must use an allowlisted response schema. Candidate fields for AUTH-09 review:

- individually tracked asset totals by approved lifecycle status (available, allocated, repair, damaged, disposed), category, and location;
- quantity inventory availability grouped by product/location **and compatible unit**, never added to individual-asset counts or unlike units;
- explicitly approved operational counts only where source data is complete and current;
- `as_of`/refresh status with `unknown` or `unavailable` when not established.

Default exclusions: employee names/IDs and individual assignments, serial numbers and sensitive asset identifiers, purchase cost and detailed supplier data, repair notes/costs, exit-clearance details, approvals with personal/evidence data, audit history, credentials, configuration, and unrestricted ORM rows. Small aggregate groups can re-identify a person or location; threshold/suppression rules and organizational scope require AUTH-09/10 decisions. No standalone viewer access or Management integration is activated.

## Audit requirements

When state-changing permissions are eventually activated, derive the actor from the authenticated local user ID; record action, server timestamp, affected entity and approved before/after values in the same transaction. Apply field-level redaction, preserve append-only history, and make audit read/export separate capabilities. Audit inability must fail the relevant write according to the approved transaction contract. The current audit writer/permission rehearsal is not full R-11: previous/updated values, authorized query/export, retention and permanent runtime grants remain outstanding.

## Management approval gates

Keep AUTH-01–AUTH-15 as recorded in `authentication.md`. Permission-specific gates:

- **Before a production role mapping or grant:** AUTH-01/02 account/operator authority and AUTH-07 capability boundaries.
- **Before approval workflow access:** AUTH-08 named authorities, workflow scope, delegation, separation of duties and self-approval.
- **Before summary exposure:** AUTH-09 exact fields, units, grouping/small-group rules and freshness; AUTH-10 authorized viewers and department/location scope; AUTH-11 standalone versus integrated channel.
- **Before audit access/export:** AUTH-13 readers, data values/redaction, retention and actor trust.
- **Before Management AIOS integration:** AUTH-12 service authentication and AUTH-14 independent user-level summary gate; AUTH-15 only if future SSO is selected.
- **Before authentication activation:** applicable AUTH-02–AUTH-06 password/MFA/recovery/session policies, production CSRF and deployment/browser/database prerequisites documented in the authentication review.

Technical development may continue with interface contracts, deny-all defaults, fictional fakes and isolated tests. None of that grants operational approval.
