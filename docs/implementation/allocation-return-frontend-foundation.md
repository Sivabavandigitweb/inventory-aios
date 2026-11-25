# Allocation and return frontend foundation — Task 9D

Status: fictional, partial preview only. Routes: `/allocations` and `/returns`. Run `cd frontend`, `npm run dev`, then open `http://localhost:5173/allocations` or `http://localhost:5173/returns`. No operational API, database or employee source is contacted.

## Confirmed requirements and implemented preview

The [original PDF](../requirements/Inventory%20%26%20Asset%20Management%20Automation%20System.pdf) requires employee identity and organization, allocation date, assigner and asset condition on assignment (R-04/R-05); retained organization history (R-06); assigned-asset return before employee exit completion (R-07); return date, returner, verifier, condition and remarks (R-07/R-08); approval workflows for allocation/return (R-10); complete audit history (R-11); search and mobile access (R-14/R-16). The PDF does not define approval authority, deadlines, eligibility criteria, condition vocabulary or post-return lifecycle transitions.

The Allocation page has a searchable, department-filtered and paginated directory, partial-example counts, details dialog and New Allocation preview. Its selectable employees and individual assets come from existing providers. It shows assignment date, assigner requirement and condition observation but cannot submit. A selection is not authorization or eligibility. No quantity-stock allocation is shown.

The Returns page has searchable, department/location-filtered and paginated examples, counts, details and Record Return preview. A return references one fictional allocation. The form shows confirmed return fields plus a receiving location labeled as a proposal. It presents only fictional current-custody examples for selection. Return verification, approval, documents, lifecycle change and exit clearance remain unavailable. No deadline, overdue flag or approved workflow state is fabricated.

## Shared data boundary

The separate typed `mockWorkflowProvider` holds **partial** DEMO allocation and return examples. `useWorkflowPreview` loads it together with the existing typed employee and asset providers; failures display an error without mock fallback. A validation function rejects missing employee/asset/allocation links, duplicate references, duplicate current custody and overlapping fictional custody intervals. The two current-custody examples reference the two existing mock assets whose lifecycle status is Allocated; historical returns reference available example assets and do not alter their current status. Directory summary counts come from these records, not a claimed complete inventory.

Employee and Asset details link to the filtered fictional allocation preview while retaining their separate unavailable operational-history messages. A historical allocation may link to its fictional return example. Links and status labels explicitly say preview/example.

## Pending rules and integration

All 13 asset business decisions remain pending, especially ABD-01/02/12 for tracked versus pooled stock, ABD-09 for condition vocabulary, ABD-10 for approval, and ABD-13 for retry retention. Allocation/return authorization, employee source identity mapping and exit-clearance interaction also require approval. Existing audit permission, before/after value capture and R-11 redaction remain incomplete. Do not infer a return deadline or post-return Available transition.

Before activation, implement reviewed allocation/return models and migrations, authorized versioned APIs, row locking and exclusivity, approval policy, employee and asset eligibility checks, quantity stock accounting if approved, transactional audit and idempotency, return verification, exit-clearance invariants, and PostgreSQL integration tests for concurrency, rollback and retries. The current forms make no writes and cannot satisfy those gates.
