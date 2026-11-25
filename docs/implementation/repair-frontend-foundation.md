# Repair frontend foundation — Task 9E

## Scope and requirement trace

The page is a local, fictional, partial preview. It is not a repair service, database integration, or operational record. The original requirements matrix maps section 9 to R-09: maintain reported date, reported by, repair date, repair cost, service provider, and current status for damaged or repaired assets. R-02 confirms asset lifecycle values Available, Allocated, Repair, Damaged, and Disposed. R-10 separately confirms approval workflows for registration, allocation, return, and disposal; it does not establish repair approval authority.

The reviewed R-09 requirement does not specify repair progress states, repair outcomes, internal/external classifications, deadlines, service intervals, cost approval, or authority. “Open example” and “Historical example” are fixture group labels only. The UI never changes an asset lifecycle state and does not fabricate costs, provider records, documents, verification, or approvals.

## Implemented preview

- Responsive repair directory with fictional/partial notice, summaries calculated from fixture rows, search, grouping filter, pagination, details, loading, empty, and safe error states.
- New Repair preview allows selecting a fictional individual asset and entering issue/date locally; submit remains disabled. Selection does not mean the asset is eligible, and reporter identity is not inferred from a client field.
- Details show the linked asset's current mock lifecycle state and identify unavailable assessment, provider, costs, documents, completion, outcome, approval, and audit details.
- Two open examples reference the two mock assets already marked Repair and not in current custody. Four dated historical examples are labeled fictional; they do not change present asset status. All examples reference existing mock assets.
- Asset details link to repairs with an asset search query; the dashboard offers repair preview navigation. No backend requests occur.

## Maintenance finding

No preventive-maintenance schedule, interval, or reminder is specified by the reviewed requirement section or matrix. Preventive maintenance is a possible future enhancement, not an implemented workflow. No servicing interval or notification schedule is assumed.

## Decisions and future work

Management/business review is needed for progress and outcome vocabulary, internal versus external responsibility, repair eligibility, approvals, cost/currency and provider handling, evidence, completion verification, and which asset lifecycle transitions follow repair. Condition vocabulary and broader asset decisions remain pending. The PDF's current-status field does not settle these transitions.

Operational implementation needs approved backend schemas and authorization, authenticated reporter identity, transactional asset/repair updates, immutable audit coverage (including previous/updated values under R-11), idempotency, and PostgreSQL tests for concurrent repair cases, rollback, duplicate reports, and approved transitions. No database model, migration, or runtime permission was changed here. Preventive maintenance requires a separate requirement or management approval.

Local preview route: /repairs (frontend dev server, normally http://localhost:5173/repairs).
