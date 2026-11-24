# Audit logging foundation

## Status and scope

The requirements identify auditability as R-11. The database plan had proposed an `audit_events` table, but no table, ORM model, or reusable audit writer existed before this task. Revision `7d4a9c2e1b60` prepares the schema; it has not been applied. Employee registration remains disabled by its `employee_audit_writer` dependency.

## Event contract

Each event contains a generated UUID, optional local actor UUID (required for `user` source), action, entity type, entity UUID, database timestamp, change source (`user`, `system`, or `import`), and JSONB metadata. Actor references use `ON DELETE RESTRICT`. Indexes support actor/time and entity/time review.

Metadata is allowlisted to a UUID request ID, up to 20 unique changed field names, and a `success` or `failure` outcome. PostgreSQL enforces that metadata is an object, contains no unknown keys or nested values, and conforms to those key-specific types and values. Application validation mirrors those checks. Free-form values, employee field values, credentials, passwords, tokens, secrets, and authorization data are rejected. Before/after values are intentionally omitted until management approves a field-level redaction and confidentiality policy; this means the current foundation does not yet satisfy the full R-11 change-value acceptance criterion.

## Transaction and append-only behavior

`write_audit_event` stages the ORM row and flushes it through the caller's SQLAlchemy session. It does not commit, roll back, or suppress database errors. Business services must keep the business mutation, history, and audit event in the same transaction and roll the whole transaction back if audit writing or flushing fails. The existing employee service follows this failure behavior, but its route still obtains an unavailable audit-writer dependency and cannot register employees.

The migration explicitly creates the audit table, indexes, constraints, functions, and triggers in `public`; its immutable metadata validator uses a restricted `pg_catalog` search path. The migration installs a PostgreSQL trigger that rejects UPDATE, DELETE, and TRUNCATE. Corrections must be represented as new compensating events. Downgrade refuses to discard any existing audit rows; an operator must make an explicit retention and archival decision before removing the table. The trigger protects against normal DML and is not a defense against a database superuser disabling it.

## Decisions still required

- Retention, archival, legal hold, backup, and deletion authority for audit records.
- Whether R-11 requires before/after values for every field, and an approved per-field redaction policy that prevents confidential employee data from entering the log.
- Which event metadata is approved for each event type and whether failed authentication/security events belong in this business audit stream.
- Which roles may query audit history, their organizational scope, and whether exports are allowed.
- Database-role ownership and operational controls for trigger/function changes and emergency correction procedures.

No migration, database mutation, employee registration, user creation, credential setup, or permission grant is performed by this foundation.
