# Candidate Permission Access Matrix

## Status

This matrix expresses a proposed design only. It does not authorize role creation, account provisioning, permission grants, operational access, or Management AIOS integration. Every cell marked “candidate” remains subject to named approval and resource/business checks. Original PDF sources are R-01–R-17; section numbers equal R numbers and page references are in the requirements matrix.

## Access categories

- **Admin candidate:** individually identified Inventory AIOS administrator. A capability requires a separate explicit grant; the role name is not an all-access rule.
- **Summary viewer candidate:** individually authorized human viewer; limited to an approved aggregate response, not operational endpoints.
- **Approver:** separately named authority for a specific approval type, separate from requester/create permissions.
- **Restricted operator:** separately appointed account, role, security, audit, integration, or system operator.
- **Management service:** future server-side service identity scoped only to a fixed summary API. It is not a human user or role.
- **Deny:** no access under this design unless management approves a specific exception and corresponding authorization.

## Role-to-capability matrix

| Module / operation | Admin candidate | Summary viewer | Approver | Restricted operator | Management service | Requirement / notes |
| --- | --- | --- | --- | --- | --- | --- |
| Dashboard: approved aggregate summary | Candidate `summary:read:approved`, only if explicitly granted | Candidate explicit summary permission only | Deny unless separately approved | No implied access | Candidate `summary:service:read` only | R-13; fields/freshness/scope AUTH-09/10 |
| Dashboard: detailed employee/asset/repair/approval records | Per-capability grant and resource scope | Deny | Only records in own approval scope | No automatic access | Deny | R-04–R-15; not the summary contract |
| Assets: read detail | Per-action candidate grant | Deny | Only data required for assigned decision | Deny by default | Deny | R-02, R-14; serial/cost/supplier fields restricted |
| Assets: create/register | Per-action candidate grant; required R-10 approval remains separate | Deny | Decision only; no create right implied | Deny | Deny | R-01, R-02, R-10 |
| Assets: update/status | Per-action candidate grant; workflow validation | Deny | No general update right | Deny | Deny | R-02, R-11 |
| Product catalog: read | Candidate per-action grant | Deny unless approved aggregate only | Deny | Optional designated master-data operator | Deny | R-01, R-02 |
| Product catalog: create/update | Candidate only with separate reference-data grant | Deny | Deny | Designated operator only | Deny | R-01, R-02; historical references retained |
| Receiving: read/create | Candidate per-operation grants, scoped by location | Deny | May decide if assigned; no request right | No implied access | Deny | R-03, R-10 |
| Receipt-to-asset registration | Candidate per-operation grant after approval | Deny | Approve/reject only | Deny | Deny | R-01, R-03, R-10 |
| Quantity inventory: read | Candidate per-operation grant | Only approved aggregate grouped by compatible unit | Deny | No implied access | Only approved summary projection | R-03, R-13; never combine incomparable units |
| Quantity inventory: adjust | Candidate only if separately approved | Deny | No adjustment implied | Deny | Deny | R-03, R-11; reason, transaction, audit required |
| Employees: detailed read | Existing `employees:read:all` is a guard identifier, not a viewer grant; any future grant must be filtered | Deny | Only minimum fields needed for assigned decision | No automatic access | Deny | R-05–R-07, R-14; AUTH-10 scope/fields |
| Employees: manual create/update | Deny until workflow/source ownership is approved; `employees:create` is not auto-granted | Deny | Deny | Deny | Deny | R-05, R-06, R-16; sync does not provision accounts |
| Employee sync: configure/run/review | Candidate only for explicitly assigned sync operator after source-owner approval | Deny | Deny | Designated sync operator/service only | Deny | R-05–R-07, R-11; disconnected |
| Allocations: read/create/update/cancel | Separate capability per operation; scope by employee, asset, location and current custody | Deny | Assigned decision only; does not create | Deny | Deny | R-04, R-10; availability and business checks still required |
| Returns: read/record | Separate per-operation grant | Deny | Assigned decision only | Deny | Deny | R-07, R-08, R-10; recorded is not verified |
| Returns: verify | Separate verifier authority | Deny | Only if approved as distinct authority; self-review unresolved | Deny | Deny | R-07, R-08, R-11; AUTH-08 |
| Repairs: read/report/update/close | Separate per-operation grants; notes/cost/provider may need additional field scope | Approved aggregate only | Deny unless an assigned workflow explicitly requires a decision | Deny | Deny | R-09, R-11 |
| Exit clearance: read/start/complete | Separate grants; completion requires appointed authority and required verified returns | Deny | Only an explicitly appointed clearance authority | Deny | Deny | R-07, R-11; no exception policy inferred |
| Approvals: read | Only approved workflow/scope | Deny | Assigned requests only | Deny | Deny | R-10 |
| Approvals: approve/reject | Deny unless account separately holds the specific authority | Deny | Candidate per workflow type; self-approval/delegation pending | Deny | Deny | R-10, R-11; AUTH-08 |
| Disposal: request/finalize | Request and finalization are separate candidate capabilities; finalization follows approval | Deny | Decision only if named | Deny | Deny | R-10, R-11; method/evidence/reversibility unresolved |
| Notifications: read/manage/configure | Separate operational capabilities; no delivery configuration by role name | Deny | Deny | Designated operator only after policy approval | Deny | R-12; recipient/channel/schedule unresolved |
| Reports: read | Per-report grant and organizational/data scope | Only approved aggregate report projection | Assigned approval data only | No implied access | Approved summary endpoint only | R-15; employee-wise/detail reports restricted |
| Reports: export | Separate explicit per-report export grant | Deny by default | Deny unless separately authorized | No implied access | Deny | R-15, R-17; AUTH-13 where audit data; retention/redaction pending |
| Settings: read/configure | Read and each change separately granted; sensitive values remain hidden | Deny | Deny | Designated system operator only | Deny | R-17; no operational values invented |
| User/account: provision/deactivate/recover | Deny by default, including to administrator role | Deny | Deny | AUTH-02/AUTH-05 appointed operator only | Deny | R-17; attribution and session revocation required |
| Role/permission administration | Deny by default, including to administrator role | Deny | Deny | Separate security authority with review and audit | Deny | R-17; no wildcard; AUTH-07 |
| Audit: read/filter/export | Deny unless separate reader/export capabilities are approved | Deny | No implied access | Separate auditor/operator only if approved | Deny | R-11, R-15; R-11 remains partial; AUTH-13 |
| Backup/recovery administration | Deny by default | Deny | Deny | Separate database/operations authority, not application admin | Deny | Not a permission inferred from R-17; separate operational approval |
| AI: invoke/read | Only within caller’s already-approved read capabilities | Only approved aggregate subset | No decision authority delegated to AI | No special AI rights | No direct AI access | R-17 does not specify AI; provider disconnected |
| AI: propose/execute write | Candidate request still passes caller permission, scope, business rules, approval and required human confirmation | Deny | AI may not decide | Deny | Deny | AI-generated input is untrusted; no model-specific grant |
| Management AIOS embedded summary | Not applicable | User must be explicitly authorized in Management and viewer access separately approved in Inventory | Deny | Integration operator only | Fixed summary API scope only | AUTH-12/14; independent auth/backends/databases |
| Open Inventory Administration link | Administrator authenticates independently to Inventory | No implied admin access | No implied access | No token sharing | Deny | AUTH-14; no bearer in URL/cookie sharing |

## Evaluation rules to decide before enforcement

1. Resolve only currently valid `user_roles` assignments on every protected request. Inactive users and expired/removed assignments deny on the next check.
2. Unknown role/capability, missing policy, malformed policy result, or repository/policy outage denies safely. No wildcard or default allow.
3. Do not persist a complete permission snapshot in a session. Stable local user ID identifies the actor; current authorization is resolved separately.
4. Multiple-role combination, conflicting grants/denials, delegation, and emergency access have not been approved. Do not invent union, precedence, or deny-override behavior until management chooses a rule.
5. A successful capability check does not satisfy resource-level authorization or workflow validation. For example, an allocation still requires an available asset and valid employee/custody state.

## Pending approval mapping

| Decision | Existing AUTH item | Blocks neutral offline contract/enforcement tests? | Blocks a production mapping/grant or activation? |
| --- | --- | --- | --- |
| Initial administrator identities and provisioning authority | AUTH-01/02 | No | Yes, before provisioning |
| Administrator and sensitive capability boundaries | AUTH-07 | No | Yes, before any role mapping/grant |
| Approval authorities, stages, delegation, self-approval | AUTH-08 | No | Yes, before approval decisions |
| Summary fields, aggregation, units, freshness and small groups | AUTH-09 | No | Yes, before summary response is exposed |
| Viewer identity and organization scope | AUTH-10 | No | Yes, before viewer access |
| Standalone viewer access or Management-only channel | AUTH-11 | No | Yes, before access channel is activated |
| Service identity and scope | AUTH-12 | No | Yes, before Management service access |
| Audit actor, values/redaction, readers, exports and retention | AUTH-13 | No | Yes, before audit access/export/write activation |
| Future Management integration and user gate | AUTH-14 | No | Yes, before integration |
| Optional SSO | AUTH-15 | No | Yes, only if SSO is selected |
| MFA/session/password/recovery policies | AUTH-02–AUTH-06 | No | Yes, before operational authentication |
