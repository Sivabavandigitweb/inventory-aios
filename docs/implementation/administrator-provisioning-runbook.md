# Administrator provisioning runbook (pre-activation)

## Phase F.1C.4 verified current state

The pre-activation status below is historical. On 2026-11-27 the developer and Team Leader reported, and the authorized read-only restore-check inspection confirmed, that both accounts are active and have credentials at `inventory_aios_restore_check` revision `d2a8f4c1b790`. `super_admin` has `inventory_administrator` and `security_administrator`; `system_admin` has `inventory_administrator`. Bootstrap was attributed to operator `DWL 347` with authorization reference `F.1C.4`; dedicated administrator and ordinary audit events were manually verified. The current integration step did not repeat provisioning or inspect credential material.

This does not authorize provisioning in another database or environment. Production remains subject to separate authorization, least-privilege grants, activation evidence, and security review.

This is a controlled procedure design for the two individually assigned accounts. It does not create accounts and is not an executable provisioning command. The application currently has no operational credential-write path, and runtime credential writes must remain denied.

## Confirmed account identifiers

- `super_admin`
- `system_admin`
- Normalize by accepting ASCII only and applying lowercase; reject whitespace rather than trimming it.
- `super_admin` is the designated authority for normal account provisioning. Usernames do not grant permissions.

## Initial bootstrap

The first `super_admin` cannot authorize their own creation. An explicitly authorized company operator must approve and attribute the bootstrap outside the new account. Before execution, record the approving authority and bootstrap operator in the approved change record; verify the exact account holder and approved role/capability assignment. If the audit contract cannot attribute the bootstrap operation, do not provision.

Create the user row, Argon2id credential, and explicitly approved role assignments in one transaction. Record the audit event in that transaction. Accept the password through a non-echoing secure prompt; do not accept it as a command-line argument or write it to logs, shell history, files, tickets, or audit payloads. Return no credential material. Deliver enrollment instructions through an approved private channel. Do not set a default password or create a public registration/reset link.

## Normal provisioning and lifecycle

After bootstrap, `super_admin` may request provisioning of `system_admin` only through an approved operator workflow. Confirm uniqueness after lowercase-ASCII normalization, attach only the approved role/capability assignments, and attribute the audit actor to the stable local user UUID. The second administrator does not receive account-provisioning authority unless separately configured.

Deactivation must atomically set the existing user status inactive, revoke active sessions, and write the audit event. Credential reset must update the Argon2id hash and increment `credential_version`, revoke active sessions, and write the audit event in the same transaction. Do not implement self-service registration or assume either administrator may reset the other's credential.

## Release blockers

This procedure remains non-executable until management supplies the bootstrap approver/operator, account-holder confirmation, exact role-to-capability mapping, approved credential recovery and MFA policies, audit/bootstrap attribution, and least-privilege database grants. A controlled provisioning command with a non-echoing prompt and transaction/audit tests is not yet implemented. No administrator account has been created.
