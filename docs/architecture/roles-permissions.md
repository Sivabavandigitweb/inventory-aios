# Roles and Permissions

## Status

The PDF requires login and role-based permissions as a preferred system feature (R-17), approval workflows (R-10), auditability (R-11), and access from authorized devices. It does not define role names or authority boundaries. The matrix below is therefore a **Proposed baseline**, pending company approval.

## Proposed roles

| Role | Intended scope |
|---|---|
| Administrator | User/role configuration, reference data, system configuration, and exceptional support. Should not automatically imply approval of one’s own business actions. |
| Inventory Officer | Receiving, asset records, allocations, returns, repairs, documents, and operational reports within assigned scope. |
| Approver | Review and approve/reject configured registration, allocation, return, and disposal requests. Exact authority is unresolved. |
| Employee | View own profile and assigned assets; submit or acknowledge allowed requests; no broad inventory mutation by default. |
| Auditor | Read-only access to asset, employee, workflow, report, and audit history. No state-changing permission. |
| Management | Dashboard, reports, and review access; whether management can approve or edit is unresolved. |

## Permission matrix

Legend: **C** = create/submit, **R** = read, **U** = update, **A** = approve/reject, **X** = no access by default, **S** = configuration/support. Scope and approval authority remain subject to decision.

| Capability | Administrator | Inventory Officer | Approver | Employee | Auditor | Management |
|---|---:|---:|---:|---:|---:|---:|
| Authenticate and view own profile | R/S | R | R | R | R | R |
| Manage users and roles | S | X | X | X | X | X |
| Manage categories, locations, suppliers | S | C/U | X | X | R | R |
| Register/receive assets | C/U/S | C/U | R/A | X | R | R |
| View asset registry and history | R/S | R/U | R | R (assigned only) | R | R |
| Allocate assets | C/U/S | C/U | R/A | R (own) | R | R or A if approved |
| Return assets | C/U/S | C/U | R/A | C (own acknowledgement) | R | R |
| Onboard/update employee profile | S | C/U | R | X | R | R |
| Transfer/promotion history | S | C/U | R/A if required | R (own) | R | R |
| Exit processing | S | C/U | R/A if required | R (own status) | R | R/A if approved |
| Repair/damage records | C/U/S | C/U | R | C (report) | R | R |
| Dispose assets | S/C | C | R/A | X | R | R/A if policy grants |
| Reports and dashboard | R/S | R | R | R (limited) | R | R |
| Audit trail | R/S | R (operational scope) | R (decision scope) | R (own events if allowed) | R | R |
| Notifications | S | R/U operational | R/U decision queue | R/U own | R | R/U own |
| Document upload/download | S | C/R | R | C/R own | R | R |

## Authorization rules to implement

1. Enforce permissions in FastAPI services and routes; frontend visibility is not authorization.
2. Apply object-level scope to assets, employees, documents, reports, approvals, and audit records.
3. Prevent self-approval where the configured policy disallows it; this is a decision needed, not an assumed rule.
4. Preserve separation of duties for registration, allocation, return, and disposal where management requires it.
5. Keep employee access limited to their own profile and assigned-asset context unless approved otherwise.
6. Make audit and management access read-only by default; any mutation must be explicitly authorized.
7. Deny by default for new roles, endpoints, and data fields until a permission is assigned and tested.

## Decisions required

- Which people or organizational roles may approve each of the four workflow types?
- Are approvals single-step or multi-step, and can an approver delegate?
- Can Administrator, Management, or Inventory Officer approve actions they initiated?
- What organizational scope applies to each Inventory Officer and Approver?
- What may an Employee edit or acknowledge?
- Which reports and documents contain restricted information?
- How are inactive users, role changes, and revoked sessions handled?
## Exit-clearance permissions (proposed)

The PDF confirms that assigned assets must be returned before exit completion; it does not assign authority for initiating or clearing an exit. The following is a technical baseline only:

| Capability | Administrator | Inventory Officer | Approver | Employee | Auditor | Management |
|---|---:|---:|---:|---:|---:|---:|
| Initiate employee exit case | S | C/U | R | X or C only if later approved | R | R |
| View assigned exit items | R/S | R/U | R | R (own) | R | R |
| Record/verify returns | S | C/U | R/A if configured | C (own acknowledgement) | R | R |
| Perform final clearance | S | C (subject to policy) | A | X | R | A only if explicitly authorized |
| Request a future exception | S | C with reason/evidence | R/A only under approved policy | X | R | A only if explicitly authorized |

No role receives an automatic exception or bypass. Final clearance must re-check all outstanding tracked assets and quantity assignments in the same transaction that completes the exit.

## Idempotency permission boundary

Idempotency protects authorized commands; it does not grant authorization. The original request’s principal, object scope, role checks, and validation are applied before a stored result is replayed. A different principal cannot use another principal’s key to retrieve or mutate a result. Stored responses must be filtered to the requesting principal and must not expose secrets.

The important command families requiring idempotency coverage are receiving, allocation, return, approval, disposal, and employee exit. These controls are proposed technical behavior and do not settle which roles may approve or clear an exit.
## Authentication foundation status (technical proposal)

The backend now has a provider-neutral credential-verifier interface, an active-user check, and request-time filtering of currently valid `user_roles`. The default verifier is unconfigured and the default role-permission policy grants no permissions; protected employee endpoints therefore remain closed. No role assignments or grants have been approved or seeded. See [authentication design](authentication.md) for the recommended OIDC/session design, proposed schema additions, and decisions requiring approval.
