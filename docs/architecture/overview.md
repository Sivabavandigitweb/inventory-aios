# Inventory AIOS Architecture Overview

## Status and boundaries

This is a planning design derived from the six-page requirements PDF. PDF requirements are marked **Confirmed** in the requirements matrix; architecture choices below are **Proposed** unless explicitly identified as a decision needed.

Inventory AIOS is an independent system. It does not share an operational database with Management AIOS and does not permit Grok or the browser to connect directly to PostgreSQL.

## Proposed logical architecture

```text
Authorized browser (initially two individually assigned administrators)
        |
        | HTTPS, secure application session, responsive React UI
        v
React + TypeScript + Vite frontend
        |
        | versioned REST API
        v
FastAPI application
  - authentication and RBAC
  - Pydantic validation
  - lifecycle services and approval policy
  - audit/event recording
  - notification orchestration
        |
        +<------------------ Management AIOS backend (future, approved)
        |                     Management user authorization first;
        |                     summary-only service identity to this API
        |
        +---------------------> Grok API (server-side, scoped prompts only)
        |
        +---------------------> Document storage adapter
        |                         (provider to be decided)
        |
        +---------------------> Notification adapter
        |                         (email/in-app/channel to be decided)
        v
PostgreSQL + SQLAlchemy 2 + Alembic
  authoritative operational state and history
```

## Components

### Frontend

- React, TypeScript, and Vite.
- Feature areas: dashboard, receiving, asset registry, allocation, returns, employee lifecycle, repairs, approvals, reports, audit, and administration.
- Reusable form, table, filter, status, approval, document-upload, and audit-history components.
- Responsive layouts for desktop, tablet, and mobile, with quick-entry paths for the R-16 workflows.
- The frontend calls only versioned FastAPI endpoints. It never contains the authoritative authorization or business-rule decision.

### FastAPI backend

Proposed internal layers:

1. **API routes** — versioned HTTP contracts, authentication dependencies, status codes.
2. **Pydantic schemas** — input/output validation and explicit serialization.
3. **Services** — lifecycle rules, approval checks, duplicate prevention, and transaction orchestration.
4. **Repositories/data access** — SQLAlchemy 2 queries and unit-of-work boundaries.
5. **Adapters** — Grok, document storage, notifications, and export generation.
6. **Audit publisher** — records actor, timestamp, entity, previous value, and new value for state changes.

All writes must pass through authorization, validation, and a database transaction. Service errors should be safe and actionable without exposing internals, secrets, or raw database details.

### PostgreSQL

PostgreSQL is the authoritative operational database. It stores current state and historical records for employees, assets, receipts, allocations, returns, repairs, approvals, notifications, and audit events. Schema details and constraints are in `docs/database/schema-plan.md`.

### Grok API

Grok is an optional future server-side assistant integration through FastAPI. It must never receive administrator passwords, session credentials, service credentials, or direct PostgreSQL access. Backend services must apply the authenticated administrator's own Inventory AIOS permissions and business/approval rules to every AI-assisted operation. Generated text is advisory; sensitive changes require the approved human confirmation and ordinary authorized API workflow, and are attributed to the responsible local user. Read-only AI requests may use only approved summary schemas. Prompt/data-retention policy and enabled use cases require management decisions.

### Future Management AIOS integration

Inventory AIOS remains an independent application, repository, deployment, backend, and database. The future Management AIOS navigation presents two distinct paths: **Inventory Summary** and **Open Inventory Administration**. Summary access requires Management AIOS authentication plus an explicit Management-side summary authorization, followed by a server-to-server call from the Management backend to dedicated Inventory summary endpoints using a narrowly scoped, rotatable/revocable integration identity. That identity cannot access Inventory administrator operations. Apply timeouts, rate limits, bounded caching, data freshness metadata, and a clear unavailable state. Never expose service credentials to the browser, forward Management bearer tokens as Inventory credentials, or permit the Management backend to act as an unrestricted proxy.

Open Inventory Administration is a link to the independent Inventory deployment. The administrator authenticates with their own individual Inventory AIOS credentials. A Management AIOS login or administrator status does not create an Inventory account or grant Inventory permissions. No direct Management AIOS database access is allowed. The existing Management AIOS DigitDisplay link uses a separate application login and is navigation only; it is not a reusable SSO mechanism. Management AIOS is not modified by this design. Optional company OIDC may later provide SSO, but each application keeps its own client, local session, explicit access grant, and authorization policy.

### Document storage

Supporting documents are required as optional attachments for receiving and later evidence workflows. Proposed design: store file metadata, ownership, checksum, media type, size, and object key in PostgreSQL; store binary content behind a private document-storage adapter. Downloads use short-lived authorized URLs or a streaming API after FastAPI permission checks. Provider, retention, virus scanning, maximum size, and allowed file types are decisions needed.

### Notifications

Notifications are created by domain events such as pending registration, pending return, warranty expiration, pending approval, and missing information. Proposed design: persist an in-app notification/outbox record first, then deliver through an adapter and record delivery status. Channel, recipient resolution, schedule, retries, escalation, and quiet hours are decisions needed. Notification failures must not silently roll back an otherwise valid inventory transaction unless the business decides delivery is mandatory.

## Security and data-flow rules

- Require authentication for authorized-device access and enforce role permissions in FastAPI.
- Initial local authentication is a proposed direction only: two individually assigned administrator accounts, private password provisioning, and backend-managed opaque sessions. MFA, password, and session rules require company approval; no operational login is enabled.
- Other users receive only company-approved aggregate summaries through dedicated schemas/endpoints and explicit authorization. No public or anonymous summary access is permitted.
- Scope every read and write by the authenticated user’s role and permitted organizational context once that policy is decided.
- Validate all input at the API and service layers; use database constraints as a second line of defense.
- Use least-privilege credentials for the application and separate credentials for migrations/operations.
- Keep secrets in environment/configuration management; never store them in the repository or send them to the frontend.
- Record audit events in the same transaction as the business change where possible.
- Treat documents and exported reports as sensitive; authorize each download and record important access if required by policy.
- Use read-only verification before destructive operations; disposal is an approval-controlled lifecycle action, not a hard delete.

## Proposed REST API modules

The following route shapes are proposed and require schema/permission review before implementation. All are under `/api/v1`.

| Module | Representative endpoints |
|---|---|
| Auth and users (proposed) | `POST /auth/login`, `POST /auth/logout`, `GET /auth/session`, `POST /auth/password/change`, `GET /me`; restricted administrative provisioning/reset operations are not public |
| Read-only summary (proposed) | `GET /summary` and approved aggregate breakdowns with dedicated response schemas; never expose unrestricted operational models |
| Dashboard | `GET /dashboard/summary`, `GET /dashboard/trends` |
| Catalog and assets | `GET /assets`, `POST /assets`, `GET /assets/{id}`, `PATCH /assets/{id}`, `GET /assets/{id}/history` |
| Receiving | `POST /receipts`, `GET /receipts`, `GET /receipts/{id}`, `POST /receipts/{id}/documents`, `POST /receipts/{id}/submit` |
| Employees | `GET /employees`, `POST /employees`, `GET /employees/{id}`, `PATCH /employees/{id}`, `POST /employees/{id}/transfers`, `POST /employees/{id}/exit` |
| Allocation and return | `POST /allocations`, `GET /allocations`, `POST /allocations/{id}/return`, `GET /returns` |
| Repairs and disposal | `POST /repairs`, `PATCH /repairs/{id}`, `POST /assets/{id}/dispose`, `GET /disposals` |
| Approvals | `GET /approvals`, `GET /approvals/{id}`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject` |
| Search and reports | `GET /search`, `GET /reports/{report_type}`, `POST /reports/{report_type}/exports` |
| Notifications | `GET /notifications`, `POST /notifications/{id}/read` |
| Audit | `GET /audit-events`, `GET /audit-events/{id}` |
| Documents | `GET /documents/{id}/download` |

Endpoint names, payloads, pagination, idempotency keys, and approval semantics are implementation decisions to be reviewed against the confirmed requirements.

## Quality attributes and verification

- **Responsive access:** test core flows at mobile, tablet, and desktop breakpoints.
- **Authorization:** test every protected route for allowed and denied roles.
- **Consistency:** test duplicate prevention, concurrent allocation, transaction rollback, and interrupted workflow recovery.
- **Auditability:** verify each state-changing service emits complete audit context.
- **Availability:** define backup/restore and notification retry targets before production readiness.
- **Observability:** log correlation ID, actor, route, result, and safe error category without sensitive payloads.
## Resolved gap: employee exit clearance

The confirmed R-07 rule is mandatory return before exit completion. The proposed workflow persists an `employee_exits` case and `employee_exit_items` snapshot, with states `DRAFT`, `OPEN`, `AWAITING_RETURNS`, `READY_FOR_CLEARANCE`, `CLEARED`, `COMPLETED`, and `CANCELLED`. The backend identifies active tracked allocations and quantity allocations, requires verified returns for all outstanding quantities, and performs a final locked re-check before completion.

The exit service locks the employee first, then the exit, active allocations, and asset/lot rows in a consistent order. Allocation commands use the same employee lock and reject new allocations while an exit is in an active clearance state. The final clearance, employee status change, audit events, and completion state are one transaction. No exception bypass is enabled; any future exception must be a separate management-approved workflow with reason, evidence, named authority, and audit history.

## Resolved gap: request idempotency

Important write commands use an `Idempotency-Key` header and the proposed `idempotency_requests` table. The uniqueness scope is authenticated principal plus operation scope plus client key. The backend fingerprints the canonical validated payload. Identical retries replay the stored result; the same key with a different fingerprint is rejected; a concurrent request observes `PROCESSING` rather than executing twice.

The idempotency claim, business mutation, and audit event commit together. Permanent validation failures can be stored for replay without business mutation. Transient failures roll back the claim and business transaction so the client can retry safely. A crash after commit is recovered by replaying the stored result. Retention and expiry are configurable decisions and must be implemented with reconciliation rather than blind deletion.

The required command coverage is receiving, allocation, return, approval decision, disposal, and employee exit. Endpoint contracts must define operation scope, fingerprint inputs, replay response, and transaction boundary before implementation.

## Updated API safety requirements

The representative write endpoints below require an `Idempotency-Key` header and authorization checks before any state change:

- `POST /receipts` and receipt submission
- `POST /allocations`
- `POST /allocations/{id}/return`
- `POST /approvals/{id}/approve` and `/reject`
- `POST /assets/{id}/dispose`
- `POST /employees/{id}/exit` and final clearance

A repeated successful command returns the original response/resource reference. A different payload under the same scoped key returns a conflict. A request in progress returns a bounded in-progress response and does not create a second business operation.
## Core database safeguard status

The pending core migration adds PostgreSQL-side UUID generation, update-timestamp triggers, and an append-only trigger for employee organizational history. SQLAlchemy retains compatible application-side UUID and timestamp behavior. Employee-history corrections use compensating events; `change_source` records user, system, or import provenance, with user-originated events requiring an actor reference. These are implemented technical controls, not new management approval rules.

Employee and user status vocabularies and transitions remain proposed application behavior until management confirms the policy. The initial migration does not add status checks. Live trigger and rollback testing must be performed in an isolated development database after explicit migration approval; no production or Management AIOS database is in scope.
