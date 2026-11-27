# Task 10F.6 — Combined Offline Authentication Review

## Scope and evidence boundary

This review combines the password service and Argon2id adapter, credential verification, session lifecycle, login/logout orchestration, isolated authentication HTTP router, authentication models, prepared migration, operational router registration, and authentication/role/schema/requirements documentation. It is an offline implementation review. Test repositories, accounts, completion policies, attempt protection, clock, and CSRF comparison are fictional/test-only. They do not establish database concurrency, production rate limiting, real-browser behavior, or operational security readiness.

HEAD remains the previously verified development checkpoint. Task 10B–10F.5 changes and unrelated work were preserved. No database, external service, Management AIOS repository, or remote Git repository was accessed. The two existing scratch files remain untouched and untracked.

## Combined contract findings

The exercised path is: strict login HTTP input → exact Origin and injected CSRF checks → bounded body and input checks → injected attempt protection → identity and active-state lookup → credential lookup and Argon2id verification → injected authentication-completion policy → account/credential-version revalidation → fake repository session insert containing only a SHA-256 digest → protected raw-token delivery through a Secure, HttpOnly, host-only cookie. Later status validation reads only that cookie, checks active account/current credential version/revocation/expiry and does not update activity. Logout validates browser request protections, revokes only the presented session, clears the local cookie on accepted requests, and a revoked token is subsequently rejected.

The service contracts align on stable local user UUID and credential-version snapshots. Login success is not authorization or MFA proof. Session validity does not embed roles; current role assignments remain a separate backend check. Persistence interfaces are prepared, but no SQL repository is registered.

## Findings and disposition

| Severity | Component | Finding and evidence | Disposition |
|---|---|---|---|
| Medium | Authentication HTTP login | Python JSON decoding accepted duplicate object keys using the last value. This made a credential request ambiguous. | Corrected: duplicate keys now receive a generic 400 before orchestration. Regression test confirms the password is not echoed and no login is attempted. |
| Medium | Authentication cookie parsing | Starlette's parsed cookie mapping can collapse duplicate values for the configured authentication cookie. Login, session status, or logout could otherwise operate on an ambiguous cookie header. | Corrected: the adapter inspects raw Cookie header values, rejects duplicate/malformed target cookies, and performs no auth/session operation. Regression tests cover login, status, and logout; rejected logout does not clear cookies. |
| Medium | HTTP body framing | Simultaneous Content-Length and Transfer-Encoding headers were not explicitly rejected by the adapter. | Corrected: reject the ambiguous framing before reading/authenticating. Regression test confirms no login call. The ASGI server/reverse proxy still requires separate request-smuggling hardening. |
| Deferred activation blocker | Browser CSRF | Production CSRF remains an injected boundary; the only concrete comparator is test-only. Login CSRF, authenticated write CSRF, and token issuance policy are not operationally protected. | Not activated or bypassed. Must implement and review a production mechanism before mounting the router. |
| Deferred activation blocker | Persistence/concurrency | Repository contracts require conditional atomic insert/update/revocation, but only fakes are exercised. | Requires separately approved PostgreSQL rehearsal and concurrency tests. |
| Deferred activation blocker | Identity normalization | PostgreSQL `lower(username)` uniqueness may not match application NFC/casefold canonicalization. | Policy and collision/index analysis remain required before login/provisioning. No normalization policy selected here. |
| Informational | Browser/deployment | TestClient checks headers and route contracts, not browser cookie rules, SameSite, CORS, proxy behavior, or HTTPS deployment. | Real-browser and deployment-topology verification remain required. |

No unresolved critical/high defect was identified within the reviewed offline adapter/service scope. Known deferred operational controls are not represented as complete.

## Password, identity, and session review

Argon2id uses explicit bounded configuration, library-generated salts, PHC strings, and a separate verification safety ceiling. Stored algorithm/version/cost/size parameters are checked before expensive verification; supported old hashes can be marked for rehash without mutation. Inputs preserve Unicode and are bounded by explicitly supplied configuration without truncation. Dummy verification reduces one unknown-user timing distinction but cannot guarantee equivalent timing; future analysis, distributed throttling and concurrent resource caps are required.

Unknown, inactive, ambiguous, credential-less, inconsistent, wrong-password, stale-version and infrastructure failure paths fail closed. Verified identity results contain only local identity/version and a rehash recommendation. Username normalization remains unresolved; no account merge or existing username/index change was made.

Session tokens use 32 random bytes and a canonical URL-safe representation; only the 32-byte SHA-256 digest enters repository records. Absolute and idle deadlines use explicit UTC boundary checks; activity cannot move backwards or extend absolute expiry. Status polling opts out of activity updates. Revocation is individual and idempotent; user-wide revocation is only an internal future contract. Session issuance rechecks the account and credential version, but the future repository must make insert conditional atomically. Fakes do not prove race safety.

The login attempt protection and authentication completion policies are explicit injected boundaries. Test policies allow only fictional tests; no production defaults, account provisioning, MFA, role grants, audit writing or authentication activation were added. Session persistence failure does not deliver a token. A response failure after successful insert can leave a digest-only orphan session; operational recovery/reconciliation must be designed.

## HTTP/browser contract and isolation

The prepared router supports candidate login, logout, and session status endpoints, but `backend/app/api/v1/router.py` does not import or include it. The operational app therefore exposes none of these endpoints and retains the unconfigured, fail-closed bearer verifier. Tests verify router isolation and that no fake test policy is activated by application construction.

The adapter requires explicit dependencies and secure `__Host-` cookie configuration (Secure, HttpOnly, Path `/`, no Domain). Tokens are excluded from JSON and URLs; status reads cookie only; logout deletion matches scope. Origin validation is an exact scheme/host/effective-port allowlist and remains separate from CORS. Rejected Origin/CSRF requests perform no auth operation and do not clear cookies. Responses from the prepared handlers use `no-store` and safe request IDs; validation/error bodies do not echo passwords or internal exception details.

The production CSRF mechanism is **not implemented**. Before activation it must cover login CSRF, authenticated session requests, and every future state-changing inventory request. Prefer same-origin browser/API deployment, independent application cookies, HTTPS, an explicit trusted-proxy contract, strict Origin validation, and a synchronizer token or cryptographically signed session-bound design. If cross-origin deployment is approved, credentialed CORS must use exact origins and must not substitute for CSRF. Reverse proxies/APM/access logs must redact bodies, Cookie, Set-Cookie, CSRF and authorization headers. Browser tests must verify actual supported browser behavior.

## Authorization and requirements traceability

The production credential verifier remains unconfigured and returns unavailable; the role policy remains deny-all absent explicit permissions. Successful offline password or session checks create no role grants. Employee APIs continue to require authenticated current principals and permissions; registration remains fail-closed when audit writing is unavailable. No administrator, summary-viewer, approval, wildcard, or default-allow permission was introduced.

- **R-17, PDF section 17/page 6:** preferred login and role permissions are supported by the prepared architecture and offline adapters, but operational authentication and permission grants are not enabled.
- **R-11, PDF section 11/page 4:** actor, time, previous and updated values remain required. Audit attribution architecture is documented, but operational audit writing, permission, retention and redaction policy remain incomplete. R-11 is not fully satisfied.
- **AUTH-01–AUTH-15:** remain Pending Approval unless separately recorded; this task grants no approval.

## Test coverage and limits

Existing suites cover real bounded Argon2id hashing/verification, fake and real credential verification, session boundary/revocation behavior, login/logout orchestration, HTTP cookie/Origin/CSRF/error behavior, migration/model metadata, and operational router isolation. The combined HTTP workflow uses fake user/credential/session repositories and explicit test-only policies. New regression cases cover duplicate JSON keys, duplicate auth cookies across login/status/logout, and conflicting body framing. Simulated repository changes/failures are not PostgreSQL execution or concurrency evidence.

Validation completed from a neutral working directory: the focused authentication component suite passed **222 tests**; the complete backend non-integration suite passed **337 tests**, with **41 integration tests deselected**. The HTTP adapter suite passed **57 tests**. `pip check`, Ruff, Python compilation, and `git diff --check` passed. Pytest reported one existing Starlette deprecation warning for its `httpx` TestClient integration; it was not suppressed and dependencies were not changed. PostgreSQL integration tests were not run.

## Operational activation blockers

Before authentication activation: resolve applicable AUTH decisions; settle username canonicalization/collision policy; benchmark Argon2id and approve input/password/MFA/recovery/attempt policies; implement production CSRF; approve SameSite, exact origins, deployment and trusted proxy; perform real-browser testing; prepare database-backed repositories with atomic status/version conditions; separately authorize and rehearse migration/ownership/least-privilege grants; provision individual accounts through an approved process; define audit behavior and monitoring/recovery. No production readiness is claimed.

## Task 10G readiness

Offline capability and role-to-permission mapping can proceed using the existing deny-by-default policy, stable local user UUID, and current `roles`/`user_roles` concepts. Define separate administrator and approved-summary capabilities, test allow/deny/current assignment expiry/removal and employee-detail restrictions, and do not grant roles. Management must still approve administrator scope, summary fields/viewers, approval authority/self-approval, audit access, and service identity. Task 10G must not mount the authentication router or enable operational access.
