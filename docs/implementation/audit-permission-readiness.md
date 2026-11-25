# Audit minimum-permission readiness

Status: technical configuration finalized; permanent rehearsal grants and the proposed audit trust model await management approval. This document does not authorize executing the grant script. Employee registration remains disabled. Scope is localhost:5432/inventory_aios_restore_check at revision 7d4a9c2e1b60.

## Tested permission configuration

The proposed scripts/database/06_post_audit_migration_grants.sql grants only:

- INSERT(id, actor_user_id, action, entity_type, entity_id, change_source, metadata) on public.audit_events: columns supplied by the current SQLAlchemy writer, including its Python-generated UUID.
- SELECT(occurred_at): required by the ORM RETURNING clause for PostgreSQL's generated timestamp. This also exposes timestamps across audit records; it is not restricted to the inserted row.
- EXECUTE on public.inventory_aios_audit_metadata_is_valid(jsonb): required by the metadata CHECK constraint.

The script clears stale table and column grants, including PUBLIC column grants, and verifies exact effective column permissions. Table-wide INSERT/SELECT, caller-supplied occurred_at, mutations, truncation, trigger privileges, schema/database CREATE, temporary-table creation and owner/migrator membership remain prohibited. The existing SELECT permissions on employees, roles, user_roles and users remain in place. No grant is committed by the test.

## Evidence and execution boundary

The opt-in administrator test backend/tests/test_audit_admin_rehearsal.py exercises the actual script body, its migrator/owner guards, and the real writer in one connection and outer transaction. Only the script's psql wrapper and outer BEGIN/COMMIT are removed in memory. The session authorization is reset to postgres before switching effective role to inventory_aios_app; these are session-local changes, not role membership grants. Session savepoints and an outer commit guard prevent ORM commits from persisting the test. Direct runtime connections separately test role escalation, because a postgres-authenticated connection cannot prove resistance to escalation.

Finally cleanup rolls back grants, fixtures and audit records, then compares catalog ownership/ACLs, role membership, object definitions and public-table row hashes with the baseline. Permanent execution of the reviewed SQL file remains a separate approval step. No new migration or architecture is introduced.

## R-11 technical work still required

R-11 remains partial: the requirements PDF section 11 requires user, date/time, previous value and updated value. The current foundation stores changed-field names, not old/new values. See the [requirements matrix](../requirements/requirements-matrix.md) and [audit architecture](../architecture/audit-logging.md).

- Implement previous/updated field capture and sensitive-field redaction after the policy is approved.
- Implement authorized audit-history queries, filtering, viewing and export after reader scopes and export permissions are approved.
- Integrate the chosen authentication provider and map its verified subjects to local user records. Enforce actor derivation from authenticated and authorized backend context; clients and future Grok AI integrations must not nominate trusted actors independently.
- Keep business changes and their audit records in the same database transaction, preserving rollback on failure and PostgreSQL-generated timestamps.
- Implement retention/archival behavior only after retention and deletion authority are approved.
- Keep employee registration fail-closed until its authentication, authorization and persistence prerequisites are complete.

## Management and security decisions still required

- Approve or reject the proposed application-controlled audit trust model. Compromised runtime credentials can fabricate new allowed events and actor IDs; foreign keys and append-only protection do not independently authenticate the human actor.
- Approve timestamp visibility across audit records under SELECT(occurred_at).
- Specify approved event/source semantics, sensitive-field redaction and which previous/updated values may be retained.
- Approve audit-history reader scope, viewing and export permissions.
- Define retention, archival, legal hold and deletion authority.
- Select the authentication provider and approve identity-mapping/account-lifecycle rules; backend implementation must enforce that mapping.
- Separately authorize permanent grants on the rehearsal database. Technical test success is not policy approval or authorization for the development database.
