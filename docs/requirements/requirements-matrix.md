# Requirements Traceability Matrix

## Source and analysis rules

**Authoritative source:** `docs/requirements/Inventory & Asset Management Automation System.pdf` (six pages, 17 numbered sections).

The numbered requirements below are extracted from the PDF. Statements marked **Confirmed** are source requirements. Items marked **Proposed** are implementation choices made to give the requirements a buildable shape. Items marked **Decision needed** require company confirmation and must not be treated as policy.

The system remains independent from Management AIOS. PostgreSQL is the operational source of truth, and all state changes must pass through FastAPI authorization, validation, and transaction handling.

## Context from the PDF

- **Objective — Confirmed:** centralize asset tracking, allocation, return, and monitoring; reduce manual work; provide complete audit visibility.
- **Current challenges — Confirmed:** records are maintained manually in Google Sheets; updates may be delayed or forgotten; ownership and allocation history are time-consuming to track; audit and management review require manual effort.
- **Expected outcome — Confirmed:** visibility into assets, employee allocations, asset movement history, and audit records while reducing manual effort and dependence on Google Sheets.

## Traceability matrix

| ID | PDF section and confirmed requirement | Modules | Priority | Acceptance criteria |
|---|---|---|---|---|
| R-01 | **1. Asset Registration Module:** register every newly purchased or received asset immediately; support desktops, laptops, monitors, accessories, furniture, CCTV, pen drives, external hard drives, networking equipment, printers, UPS devices, mobile devices, and other company-owned assets. | Receiving, catalog, asset registry | Must | A user can record a received item in the supported categories; the record is available for subsequent search and lifecycle actions; unsupported categories can be represented as an approved “other” category without losing the original description. |
| R-02 | **2. Asset Information Management:** maintain auto-generated Asset ID, category, brand, model, serial number, specifications, purchase date, supplier details, warranty information, purchase cost, and status (Available, Allocated, Repair, Damaged, Disposed). | Asset registry, suppliers, warranty, audit | Must | A tracked asset cannot be saved without a unique Asset ID and required identity fields; status changes are validated; prior values remain auditable. |
| R-03 | **3. New Asset Receiving Process:** record received date, received by, quantity, location, technical specifications, and optional supporting documents. | Receiving, locations, documents | Must | A receipt records the actor, date, quantity, location, and specifications; optional documents can be attached; receipt and asset creation are linked and transactionally consistent. |
| R-04 | **4. Asset Allocation Management:** record employee name/ID, department, team, designation, allocation date, assigned by, and asset condition when assigning an asset. | Allocation, employees, organization history | Must | An allocation identifies one employee, one asset or quantity line, date, assigning actor, and condition; unavailable or already allocated tracked assets cannot be allocated. |
| R-05 | **5. Employee Onboarding Management:** record employee name, ID, department, team, designation, and joining date; link allocated assets to the employee profile. | Employees, organization, allocation | Must | An employee profile stores the required onboarding fields; linked allocations are visible from the profile and preserve their history. |
| R-06 | **6. Employee Transfer & Promotion Management:** when team, department, or promotion changes, update the employee’s asset records while maintaining complete historical records. | Employees, organization history, allocations, audit | Must | A transfer or promotion records the effective change and actor; current ownership references the current employee profile; prior organization and allocation context remains queryable. |
| R-07 | **7. Employee Exit Management:** set employee status to Inactive or Left Company; identify all assigned assets; require returns before exit completion; record return date, verifier, condition, and remarks; retain complete history. | Employee exit, returns, approvals, audit | Must | Exit cannot be completed while required assigned assets remain unresolved; each return has the required fields; historical allocations and returns remain available for audit. |
| R-08 | **8. Asset Return Management:** record return date, returned by, verified by, condition, and remarks whenever an asset is returned. | Returns, assets, employee history | Must | A return references the allocation or asset, records all required return fields, changes the asset’s lifecycle state appropriately, and is auditable. |
| R-09 | **9. Repair & Damaged Asset Management:** maintain reported date, reported by, repair date, repair cost, service provider, and current status for damaged or repaired assets. | Repairs, suppliers/service providers, assets | Must | A repair case records reporter and dates; repair cost and service provider can be recorded; status transitions distinguish damaged, repair, and available/disposed outcomes. |
| R-10 | **10. Approval Workflow:** support approval workflows for new asset registration, asset allocation, asset return, and asset disposal. | Approvals, receiving, allocation, returns, disposal | Must | Each configured approval request has a subject, requester, status, decision actor/time, and audit trail; an unapproved action cannot be finalized where approval is required. Authority configuration is a decision needed. |
| R-11 | **11. Audit Trail:** record user, date/time, previous value, and updated value for changes; make history available for audit and management review. | Audit, reporting, authorization | Must | State-changing operations produce immutable audit events with actor, timestamp, entity, old value, and new value; authorized users can filter and review them. Retention policy is a decision needed. |
| R-12 | **12. Notifications & Reminders:** notify responsible personnel about pending registration, pending return, warranty expiration, pending approvals, and missing information. | Notifications, scheduled jobs, approvals, warranty | Should | Each trigger creates a traceable notification or reminder for an identified recipient or role; delivery status is visible; channels, timing, and escalation are decisions needed. |
| R-13 | **13. Dashboard:** show total, allocated, available, damaged, under-repair assets; newly joined employees; employees who left; pending returns; pending approvals. | Dashboard, reporting, read models | Should | Authorized dashboard users see each listed metric with a defined as-of time and drill-down or filter path; metric definitions are agreed before release. |
| R-14 | **14. Search & Filter:** search by Asset ID, employee name/ID, department, team, and serial number. | Search, asset registry, employees | Must | Authorized users can search each listed field; results respect permissions and return current status plus relevant owner/location context. |
| R-15 | **15. Reports:** generate asset summary, employee-wise, department-wise, allocation, return, damaged, purchase history, employee exit asset, and audit trail reports. | Reporting, export | Should | Each listed report has a documented filter set, permission check, reproducible as-of time, and export format; Excel/PDF export is preferred under R-17. |
| R-16 | **16. Mobile Entry & Accessibility:** provide mobile-friendly, tablet, and desktop access; quick forms for registration, allocation, employee updates, returns, and document upload at any time. | Responsive frontend, forms, documents | Must | Core forms are usable at mobile, tablet, and desktop breakpoints; keyboard and accessible-label checks pass; upload and save feedback handles offline/interruption safely. “At any time” still depends on authorized access and service availability. |
| R-17 | **17. System Requirements:** web-based access from authorized devices; preferred login/role permissions, responsive design, QR/barcode tracking, approval workflow, automated notifications, dashboard analytics, and Excel/PDF export. | Platform, auth, all modules | Must for web/auth/responsive; preferred for QR, notifications, analytics, exports | Authorized users can log in and access permitted modules; API is versioned and secure; preferred capabilities are separately tracked and prioritized rather than assumed mandatory. |

## Task 9A.2 employee synchronization direction (proposed implementation)

The project direction is to receive employee master data from the company's authoritative employee system rather than create it manually in Inventory AIOS. This is an implementation decision, not a statement in the original PDF. It does not remove R-05 onboarding fields and asset links, R-06 organizational history, R-07 mandatory asset return before exit completion, R-11 audit, R-14 search, or R-16 mobile accessibility. No synchronization service or connection is implemented. See [employee synchronization architecture](../architecture/employee-synchronization.md).

| Requirement | Effect of proposed synchronization | Open confirmation |
| --- | --- | --- |
| R-05 | Import and update employee identity, name, organization and joining date from the approved source; preserve local UUID and asset links. | Confirm authoritative source, stable key, field quality and legacy matching. |
| R-06 | Reflect source transfers/promotions in current profile while retaining prior organization and allocation history. | Confirm effective dates, change feed and conflict ownership. |
| R-07 | A source departure must not complete local asset exit until verified returns clear all assignments; never delete a missing source employee. | Approve source-status vocabulary, local clearance state and allocation-block policy. |
| R-11 | Sync history and audit must be transactional and attributable to the service/source event without inventing a human actor. | Approve attribution, previous/updated values, redaction and retention. |
| R-14/R-15 | Search and reporting continue to use linked local employee identity and authorized organization data. | Confirm freshness and report as-of semantics. |
| R-16 | The PDF asks for mobile employee updates; source-owned fields may need a hand-off to the authoritative system instead of local edits. | Management must confirm whether that path satisfies R-16 and whether any local-only employee fields remain editable. |

## Task 10 authentication and summary access direction (proposed implementation)

R-17 (section 17, PDF page 6) identifies login and role-based permissions as preferred system features and requires authorized-device web access; it does not prescribe local passwords, SSO, a fixed account count, role names, or summary-reader scope. R-11 (section 11, PDF page 4) continues to require the user, date/time, previous value, and updated value, and remains only partially implemented. A two-individual-administrator initial direction, dedicated read-only summary access, and later Management AIOS integration are project design proposals pending company approval. The proposed 15-character password-only minimum, Argon2id, cookie/session settings, and account/session table structures are technical policy proposals, not requirements stated by the PDF. They do not weaken R-11 or approve any access grants. Employee synchronization must not provision application accounts. See [authentication and authorization](../architecture/authentication.md), [roles and permissions](../architecture/roles-permissions.md), and the Phase 10 roadmap.

The exact summary fields, viewer population, account-provisioning authority, password/MFA/session policy, administrator capabilities, approval authority, audit trust/redaction/retention, and Management AIOS service identity remain **Pending Approval**. No operational authentication, summary endpoint, role grant, or audit writer is enabled.

## Traceability by artifact

| Requirement IDs | Primary design artifact |
|---|---|
| R-01–R-03, R-09, R-14 | `docs/architecture/overview.md`, `docs/database/schema-plan.md` |
| R-04–R-08 | `docs/architecture/overview.md`, `docs/architecture/roles-permissions.md`, `docs/database/schema-plan.md` |
| R-05–R-07, R-16 | `docs/architecture/employee-synchronization.md`, `docs/implementation/employee-frontend-foundation.md` |
| R-10–R-12 | `docs/architecture/overview.md`, `docs/architecture/roles-permissions.md` |
| R-13–R-15 | `docs/architecture/overview.md`, `docs/implementation/phase-plan.md` |
| R-16–R-17 | `docs/architecture/overview.md`, `docs/implementation/phase-plan.md` |

## Missing business decisions

- Approval authorities, number of approval stages, delegation, and self-approval rules.
- Asset numbering format, prefix, uniqueness scope, and whether IDs are immutable.
- Disposal authorities, evidence, methods, and whether disposal is reversible.
- Notification channels, recipient resolution, timing, retries, escalation, and quiet hours.
- Required fields by asset category, serial-number policy, currency, warranty lead times, retention, backups, document limits, and report definitions.

The PDF confirms business capabilities and data capture. It does not settle these policies; they must remain visible as decisions rather than being implemented as assumptions.
## Gap-resolution acceptance criteria and negative cases

The following are **proposed technical acceptance criteria** that make confirmed R-07 and safe-write behavior testable. They do not create management-approved exceptions.

### Employee exit clearance

- An exit case identifies every active tracked allocation and quantity allocation for the employee.
- An exit cannot enter `CLEARED` or `COMPLETED` while any required tracked asset is not returned and verified, any quantity remains outstanding, or any return lacks required verification.
- Final clearance re-reads and locks the employee, exit, allocation, and asset/lot rows; a concurrent allocation or return conflict causes a safe retry/failure, not partial completion.
- A successful final clearance changes the employee exit state, employee status, and audit records atomically; interruption leaves the exit incomplete and recoverable.
- Historical allocations, exit items, returns, and audit events remain queryable after completion.
- Negative tests cover: missing return, partial quantity return, unverified return, allocation attempted during clearance, concurrent clearance, stale exit snapshot, and an attempted exception without explicit approved policy.

### Idempotent write commands

- Receiving, allocation, return, approval decision, disposal, and employee-exit commands require a scoped idempotency key.
- Repeating an identical request returns the original result without a duplicate business record or audit effect.
- Reusing a key with a different payload is rejected without mutation.
- Concurrent identical requests produce one business effect; the other receives a replay or bounded in-progress response.
- Permanent validation failure is safely replayable; transient failure rolls back and can be retried with the same key.
- A crash after commit and before response is recovered by replaying the committed result.
- Negative tests cover duplicate receipt, duplicate allocation, duplicate return, repeated approval/disposal, repeated exit command, fingerprint mismatch, and recovery from an interrupted request.

## Additional unresolved decisions

- Which role or named authority may perform final employee exit clearance?
- Is any exception to mandatory return permitted, and if so, what management-approved evidence, authority, and audit rules apply?
- What are the idempotency retention period, expiration behavior, cleanup schedule, and client retry window?
- Which operation scopes are shared across route aliases or versions, and what response data may be replayed?

## Task 10G.1 permission traceability clarification

The permission catalog and access matrix are proposals linked to source requirements; they do not add requirements or assign access. In the original PDF, sections 1–9 (R-01–R-09, PDF pages 1–4) specify asset, employee, allocation, return, repair, and exit data/workflows but do not name authorized roles or per-operation restrictions. Section 10 (R-10, page 4) requires approval workflows for registration, allocation, return, and disposal but does not identify approvers, stages, or self-approval rules. Section 11 (R-11, page 4) requires user, date/time, previous value, and updated value to be available for audit/management review; current implementation remains partial. Section 12 (R-12, pages 4–5) specifies notification topics but not recipients or configuration authorities. Sections 13–15 (R-13–R-15, page 5) specify dashboard, search, and reports but not viewer eligibility or data scopes. Section 16 (R-16, page 6) requires mobile entry/accessibility, not a role model. Section 17 (R-17, page 6) requires web access from authorized devices and lists login and role-based permissions as preferred features; it defines no roles or grants. The two-individual-administrator direction, summary-viewer category, capability names, resource scopes, and Management AIOS service boundary are proposed architecture and remain subject to AUTH-01–AUTH-15 approvals. See the [permission catalog](../architecture/permission-catalog.md) and [access matrix](../architecture/permission-access-matrix.md).
