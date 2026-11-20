# Authentication and Authorization Foundation

## Status

The following is a technical recommendation, not an approved company identity or role policy. No identity provider, login flow, role assignments, or grants have been configured. Employee endpoints remain protected and deny access by default.

## Recommended production direction

Prefer company-managed OpenID Connect (OIDC) using Authorization Code with PKCE. Inventory AIOS should not store company passwords. The identity provider authenticates the person; the backend must validate issuer, audience, signature, expiry, and nonce/state at the protocol boundary and map the verified external identity to one local `users.id`. The mapping must be stable and must not rely on mutable email addresses.

For browser sessions, prefer a random opaque session cookie marked `HttpOnly`, `Secure`, and an approved `SameSite` value, with CSRF protection for state-changing requests. Store only a cryptographic hash of the session token server-side. Rotate session identifiers after authentication and privilege changes. Logout revokes the session; enforce idle and absolute expiration. Exact durations and cookie policy require security approval. A short-lived provider access-token design is an alternative, but logout/revocation behavior depends on provider support and token lifetime.

Do not build local password login unless the company explicitly chooses it and approves password policy, recovery, MFA, hashing parameters, lockout, and support procedures. If chosen, use a maintained password-hashing implementation (Argon2id or an approved equivalent); never store plaintext or reversible passwords.

## Current code boundary

- `CredentialVerifier` is the adapter interface for validating credentials and mapping the verified subject to a local user UUID. The default implementation is intentionally unconfigured and returns service-unavailable for supplied credentials.
- Missing credentials return 401; invalid/expired credentials return 401; unavailable verifier returns 503.
- The backend loads the local user and rejects missing or non-`active` users. It reloads currently valid `user_roles` assignments on every request, so a role expiry/removal takes effect on the next request.
- `RolePermissionPolicy` maps approved role codes to permission strings. Its current implementation grants nothing. No role-to-permission mapping is enabled.
- Employee directory access requires `employees:read:all`; registration requires `employees:create`. Backend dependencies enforce these checks; frontend visibility is not a security boundary.
- The principal's local user UUID is the actor identity to use for employee history and future audit events. Never accept an actor ID from request data.
- No login, credential issuance, logout, refresh, or session-revocation endpoint is implemented. No test credentials or development bypass exist.

## Session and schema work required before production login

The existing `users` table has no password hash, external subject, or session state. `user_roles` supports assignment validity but is not itself a login session. Before enabling a provider adapter, approve and migrate an external identity mapping (recommended separate `user_identities` table with `issuer`, immutable `subject`, `user_id`, created/last-used timestamps, and unique `(issuer, subject)`) and, for revocable browser sessions, an `auth_sessions` table containing `id`, `user_id`, unique token hash, creation/last-seen/expiry/revocation timestamps, and non-sensitive client metadata. Never store raw bearer/session secrets. Add indexes for user lookup and expiration/revocation cleanup. Session retention and cleanup policy require approval.

These are proposals only. No migration or database schema change was made for authentication.

## Decisions requiring approval

1. Identity provider, tenant/issuer, client registration, callback domains, MFA and account-provisioning/deprovisioning ownership.
2. OIDC provider-token validation versus backend-managed opaque browser sessions; session idle/absolute durations, cookie/CSRF policy, logout and revocation expectations.
3. Stable external-identity mapping and handling of duplicate, changed, or unlinked identities.
4. Approved role catalog, permission grants, organizational scoping, role assignment authority, and how role changes are audited.
5. Inactive/suspended status vocabulary and whether provider deactivation is synchronized; current local `users.status != active` is denied.
6. Whether local passwords are prohibited (recommended) or explicitly required and governed by a company policy.
7. Audit event retention, sensitive-field redaction, and whether failed authentication attempts require a separate security log.

## Verification boundary

Unit tests use fake verifiers and synthetic users/role results. They do not validate a real OIDC provider, cryptographic key rotation, browser cookie/CSRF behavior, database session revocation, or production role assignments. Those require approved provider configuration and later integration/security testing.
