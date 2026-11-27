# Roles and Permissions

## Status and requirements

This is a proposed access model, not an approved company permission policy. R-17 (section 17, page 6) prefers login and role-based permissions but defines neither role names nor grants. R-10 (section 10, page 4) requires approval workflows for asset registration, allocation, return, and disposal but does not name approvers. No operational role grants are enabled.

The selected development direction is two individual administrator accounts for initial operations, plus read-only inventory summary access for other authorized company users. Two accounts are not enforced as a database limit. No shared administrator login, public registration, default account, or automatic grant to Management AIOS users is permitted by this design.

## Initial access classes (proposed)

| Access class | Intended access | Boundaries |
|---|---|---|
| `inventory_admin` | Approved Inventory AIOS operational and configuration capabilities for individually identified accounts | Must use explicit backend permissions; does not bypass authorization, audit, validation, transactions, approval workflow, or separation-of-duties rules. Role does not automatically confer approval authority. |
| `inventory_summary_reader` | Read only the approved aggregate summary schemas/endpoints | No detailed operational records, individual assignments, audit history, settings mutation, or write endpoints. Viewer population and scopes require approval. |
| `management_inventory_summary` (service identity, not a human role) | Future Management AIOS backend reads of approved summary endpoints | Dedicated server-side credential, summary-only scope and audience; never has administrator access or direct database access. Integration requires separate approval. |

The two initial human accounts may receive the same `inventory_admin` role after company approval, but each has its own `users.id`, username, password, active/inactive status, session revocation, and audit attribution. The `inventory_summary_reader` access class may be realized as an approved local role or via a Management AIOS service integration. No standalone viewer accounts or shared viewer credentials are created without approval.

The current backend remains deny-all. On each protected request it validates the active local user and reloads role assignments whose `valid_from` is not in the future and whose `valid_to` is null or in the future. Removal or expiry therefore affects the next authorization check. Invalid permission-policy results, wildcard capability values, and recognized policy outages fail closed; no administrative bypass or role grant is enabled. Task 10C verifies these contracts with offline fakes and mocks only.

## Capability permissions

Keep capability permissions as the backend enforcement unit even if the user-facing model has two access classes. The identifiers below are examples for the policy contract; grants and object scopes remain **Pending Approval**.

| Capability area | Capabilities to define separately |
|---|---|
| Dashboard and summaries | Read dashboard; read only approved summary projections |
| Assets and catalog | Read asset detail; create/update asset; read/manage products and categories |
| Receiving and quantity inventory | Read/submit receipts; receive/adjust stock only under approved workflows; read permitted stock summaries |
| Employees and synchronization | Read permitted employee fields; initiate/review sync and conflicts; employee master synchronization must not provision app users |
| Allocations and returns | Read, create/record, verify, and any approval decisions as separate capabilities |
| Repairs and exit clearance | Read, report/update repairs, verify returns, initiate/complete clearance; enforce R-07 return-before-exit completion |
| Approvals | Read requests and decide by workflow type under approved authority; not implied by administrator role |
| Notifications and reports | Read/manage notifications separately; read reports and export separately with data scopes |
| Settings and user access | Read settings; manage reference data, accounts, roles, and permissions as distinct capabilities |
| Audit | Write through trusted service code in the business transaction; read/filter/export separately under approved scopes |
| AI-assisted operations | Use only the caller’s already-authorized capabilities; no model-specific privilege or direct database access |

`RolePermissionPolicy` must map only approved role codes to capabilities and deny unknown roles, permissions, and scopes. A route should require the narrowest permission for its operation. Services must perform object-level and organizational-scope checks; frontend visibility is not authorization. The UI must never be the only control for read-only access.

An administrator is not a PostgreSQL owner or superuser. Administrative app permissions cannot disable triggers, bypass audit, change security boundaries, or execute arbitrary SQL. Account provisioning and role assignment must use an approved, attributable process. Any emergency support capability requires a separate approved and audited design.

## Read-only summary boundary

Use dedicated response schemas and endpoints (for example `GET /api/v1/summary`) rather than granting summary users access to operational API models. Enforce authentication and an explicit `summary:read`-equivalent capability in FastAPI. Return only company-approved aggregate fields, with data-as-of/freshness metadata and explicit unknown/unavailable states.

Candidate aggregates include lifecycle counts for individually tracked assets; category, location, and department counts; compatible quantity availability grouped by unit; and explicitly approved operational indicators. Do not combine individual-asset counts with quantity totals or combine incompatible units. Do not provide employee names, individual asset assignments, serial numbers, procurement cost, detailed repair/exit notes, audit history, credentials, or internal configuration by default. The company must approve summary fields, viewer identities, scopes, caching/freshness, and whether a standalone viewer login is required.

For future Management AIOS embedding, Management AIOS must authenticate its own user and explicitly authorize that user for the summary before its backend calls Inventory AIOS with a dedicated summary-only service identity. Inventory AIOS must not accept forwarded Management bearer tokens or arbitrary user identity headers as proof. A user-delegated assertion would require a separately approved issuer, audience, signature, and trust contract.

## Approval and separation of duties

Do not grant both administrators approval rights simply because they share the administrator role. Keep R-10 decision capabilities separate from operational create/update capabilities. The company must identify approvers for registration, allocation, return, and disposal, decide single/multi-step review and delegation, and decide whether initiators may approve their own operations. Until approved, no approval authority is configured. Preserve R-07: exit completion must not bypass outstanding asset returns or verified clearance.

## Employee and account identity boundary

Employee master records are synchronized from a separately approved authoritative employee source. Synchronization never creates or activates `users`, sets credentials, assigns roles, or deactivates application accounts. An optional local user-to-employee relationship is not the authentication identity. Management AIOS users and service identities are also distinct from Inventory AIOS users and synchronized employees.

## Audit and idempotency boundaries

Every user-originated audit event derives its actor from the authenticated local `users.id`, never from request payload, client, Management AIOS, or Grok. Record the operation, entity, server time, and approved before/after values in the same transaction as the business change. Redact credentials and session/service secrets. Audit history is read-only for explicitly authorized readers; export and retention require separate approval. Current R-11 implementation remains partial and runtime grants remain disabled; see [audit logging](audit-logging.md).

Idempotency protects an already-authorized command; it does not confer permission. Before replay, revalidate current principal, role, object scope, and operation authorization. A different principal cannot use a stored key/result to access another user's operation. See the [database schema plan](../database/schema-plan.md).

## Required decisions

- Which two people receive the initial administrator accounts, and who is authorized to provision, reset, deactivate, and assign roles?
- What administrator and summary-reader capabilities and data scopes are approved?
- Who may approve each R-10 operation; what are self-approval and separation-of-duties rules?
- Which summary fields, freshness guarantees, organizational filters, and viewer populations are approved?
- Will standalone summary users exist before Management AIOS integration?
- What audit reader/export scope, before/after redaction, retention, and service-actor policy is approved?
- What session, MFA, password reset, and account deactivation policies are approved?

See the [authentication design and decision checklist](authentication.md). All role grants, summary fields, and approval authority remain pending; the present matrix is not authorization to seed users, apply grants, or enable operational endpoints.

## Task 10G.1 permission catalog and matrix

The [candidate permission catalog](permission-catalog.md) defines proposed operation-level capability IDs, sensitivity, scope, current backend evidence, and approval/audit dependencies. The [candidate access matrix](permission-access-matrix.md) separates individually granted administrator capabilities, summary-only viewer access, workflow-specific approvers, restricted operators, and the future summary service identity. Neither document is a grant list. Current production policy remains deny-all, and every operational permission remains unassigned pending the applicable AUTH approval.
