# Employee Exit and Asset Clearance frontend foundation - Task 9F

## Confirmed requirements

R-07 (PDF section 7) requires the employee status to be updated to Inactive or Left Company when an employee leaves; all assigned assets must be identified and returned before exit completion; return date, verifier, condition and remarks must be recorded; and complete asset history must remain available. R-08 specifies return fields. The requirements matrix's additional clearance invariants are proposed technical acceptance criteria: no completion with unresolved tracked/quantity obligations or returns lacking required verification, with current locked state and transactional completion. They do not approve exceptions or an authority matrix.

## Responsibility boundary

The authoritative employee system is intended to own employee master information; its source and synchronization remain unconnected. External employment status, local employee master status, and Inventory AIOS inventory clearance are separate. An inactive employee is not inferred to be departing or cleared; a missing source record never deletes an employee or completes clearance. This page does not edit employment status or create actual exit cases.

## Preview features and data

The /exit-clearance page uses existing fictional employee, asset, allocation and return providers plus a separate fictional review-reference provider. Six DEMO review examples reference existing employees. Two have visible current allocations without a related return. Historical allocation returns remain linked. The source connection is shown as not connected; no departure dates, synchronization events, approvals or operational case records are asserted.

Directory search, department and review filters, pagination, summary counts, details, responsive table behavior, loading/empty/error states and navigation links are implemented. The fictional employee master status is displayed separately from the unknown external employment status. A recorded fictional return is not treated as independently verified. Zero visible outstanding assets remain Unknown because data coverage is partial, return verification is not established, and quantity-stock obligations are unavailable. Clearance controls remain disabled.

Details show linked allocations, visible outstanding assets, related return references, verifier text from the fixture with an explicit unknown-verification statement, and a proposed checklist. Asset, allocation and return links preserve their preview routes. Employee details and dashboard link to clearance review.

## Existing proposed lifecycle and safeguards

The database schema plan already records a proposed (not approved) sequence: DRAFT -> OPEN -> AWAITING_RETURNS -> READY_FOR_CLEARANCE -> CLEARED -> COMPLETED, with CANCELLED before clearance. This frontend adds no competing state machine and does not display those states as operational. All preview readiness remains unknown. R-07's mandatory return-before-completion rule is preserved; no exception, penalty, deadline, replacement cost, approval authority or completion is invented.

## Pending decisions and future implementation

Management must confirm the clearance authority and any exception policy. Source owner, stable identity mapping, employment-status mapping, event timing and handling source changes remain pending. Quantity inventory needs an approved custody and partial-return contract. Return verification evidence, approval flow, audit completeness/actor attribution under R-11, retention and idempotency behavior also remain unresolved.

Operational work requires authenticated authorization, employee/source integration, persisted exit and exit-item records, locked current allocation rechecks, atomic return/clearance/employee updates, audit events, idempotent retries, rollback/recovery behavior, and PostgreSQL tests for outstanding, unverified, partial quantity, stale snapshots, concurrency, interruption and duplicate requests. No backend contract, model, migration, permission or workflow was changed here.

Local preview route: /exit-clearance (normally http://localhost:5173/exit-clearance).
