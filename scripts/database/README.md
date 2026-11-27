# Database restore verification and role rehearsal

These scripts are for controlled local rehearsal. `inventory_aios_restore_check` and the separately approved `inventory_aios_restore_validation` are the only rehearsal targets; none of these files should be retargeted to `inventory_aios_dev`.

## 1. Prerequisites and secure credentials

PostgreSQL 18.7 client tools are installed at `C:\Program Files\PostgreSQL\18\bin` (`psql.exe`, `pg_dump.exe`, `pg_restore.exe`, `createdb.exe`). The wrappers use PATH first and fall back to that location; pass executable parameters when using another installation. The role-membership `INHERIT FALSE, SET TRUE` options require PostgreSQL 16 or later. Use an approved PostgreSQL administrator account for the SQL changes. Do not place passwords in command arguments, URLs, shell history, `.env` files, or logs.

Use a secured Windows password file (`pgpass.conf`) and set `PGPASSFILE` in the current PowerShell session. Store one record per needed identity in this format, entering secrets only in the local file:

```text
localhost:5432:postgres:<administrator-login>:<secret>
localhost:5432:inventory_aios_restore_check:<administrator-login>:<secret>
localhost:5432:inventory_aios_restore_check:inventory_aios_app:<secret>
localhost:5432:inventory_aios_restore_check:inventory_aios_migrator:<secret>
```

PowerShell setup (then edit the file locally without copying its contents into chat or command history):

```powershell
$pgpass = Join-Path $env:APPDATA 'postgresql\pgpass.conf'
New-Item -ItemType Directory -Force (Split-Path $pgpass) | Out-Null
if (-not (Test-Path -LiteralPath $pgpass)) { New-Item -ItemType File $pgpass | Out-Null }
icacls.exe $pgpass /inheritance:r /grant:r "$($env:USERNAME):(R,W)"
notepad.exe $pgpass
$env:PGPASSFILE = $pgpass
```

## 2. Restore comparison, read-only

From the repository root, run the prepared comparator. It requires `.test.env` and refuses a URL with a password; libpq reads the credential from `PGPASSFILE`. It starts a read-only transaction, validates database/login identity, compares normalized schema statements, counts table rows in the backup stream without writing or printing row contents, and checks the specified object counts/revision. The verification URL is `INVENTORY_TEST_DATABASE_URL` from `backend\.test.env`, and must be a passwordless URL for `inventory_aios_app@localhost:5432/inventory_aios_restore_check`; `PGPASSFILE` supplies credentials without placing them in commands. This read-only verification does not use the migration URL or require the migrator role.

```powershell
Set-Location 'C:\Users\Digit Web\Desktop\Sivabavan\Projects\inventory-aios'
.\backend\.venv\Scripts\python.exe .\scripts\database\backup_checksum.py --backup .\backups\inventory_aios_dev_full_20261123_174845.dump
$env:PGPASSFILE = Join-Path $env:APPDATA 'postgresql\pgpass.conf'
.\backend\.venv\Scripts\python.exe .\scripts\database\verify_restore.py --backup .\backups\inventory_aios_dev_full_20261123_174845.dump `
  --pg-restore 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe' `
  --pg-dump 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe'
```

The archive-listed eight explicit indexes are compared with catalog indexes not backing constraints. PostgreSQL primary-key and unique-constraint indexes therefore do not inflate that comparison. A nonzero exit or `schema_definitions_match: false` is a blocker; preserve the summary and investigate before role rehearsal. The script prints row counts and definitions comparison results, never table contents or URLs. The archive TOC lists primary, foreign-key, and unique constraints (36 entries here); CHECK constraints are embedded in table DDL and NOT NULL is represented by column declarations. PostgreSQL 18 exposes the latter as `pg_constraint.contype = 'n'`, so the verifier compares these categories separately and matches NOT NULL table/column pairs instead of comparing unlike aggregate totals. Schema normalization removes only `pg_dump` `\restrict`/`\unrestrict` guard lines and equivalent varchar/text casts in CHECK array expressions; types, defaults, nullability, indexes, functions, triggers, constraint names, and FK actions remain compared.

## 3. Role changes (do not run until explicitly approved)

First inspect cluster roles and memberships and resolve any conflict. `inventory_aios_app` must already exist; script 01 refuses to create it. The owner and migrator names must be absent or manually reconciled; script 01 refuses conflicts. Membership is set with `INHERIT FALSE, SET TRUE`. Role changes are cluster-wide.

```powershell
Set-Location 'C:\Users\Digit Web\Desktop\Sivabavan\Projects\inventory-aios'
$admin = Read-Host 'PostgreSQL administrator login'
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d postgres -f .\scripts\database\01_cluster_roles.sql
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d postgres
```

At the interactive `psql` prompt, set the new migrator password without echoing it:

```text
\password inventory_aios_migrator
\q
```

After review of the baseline report, and with the restore target verified, make database-specific object/privilege changes only to the rehearsal database:

```powershell
.\scripts\database\02_transfer_database_owner.ps1 -PsqlExe 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d inventory_aios_restore_check -f .\scripts\database\02_restore_database_roles.sql
```

The existing `inventory_aios_app` is never recreated. The database owner must be transferred to `inventory_aios_owner`; run `02_transfer_database_owner.ps1` before `02_restore_database_roles.sql`. The transfer wrapper requires a PostgreSQL superuser, which automatically satisfies PostgreSQL's ownership-transfer requirements; it does not grant CREATEDB to the owner. It verifies the exact rehearsal database and verifies that the owner remains NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION, and NOBYPASSRLS after transfer. Object/schema ownership and ACL changes are database-specific; role creation and membership are cluster-wide.

Re-verify after the role change:

```powershell
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d inventory_aios_restore_check -f .\scripts\database\03_verify_restore_roles.sql
```

The post-change check enforces ownership, migrator membership options, runtime SELECT-only employee access, no runtime schema CREATE, no employee-history mutation/truncate/trigger privileges, and no PUBLIC EXECUTE on application functions. If the pending audit migration is later approved and applied, run `06_post_audit_migration_grants.sql` only afterward; it grants the runtime role EXECUTE on the audit metadata validator and verifies it. Audit table INSERT/SELECT grants require separate workflow approval and are deliberately absent while registration is disabled.

## 4. Separate rehearsal environment files

The loaders use the exact settings below and the current working directory must be `backend` when running Alembic or pytest:

- `.migration.env`: `INVENTORY_MIGRATION_DATABASE_URL`
- `.test.env`: `INVENTORY_TEST_DATABASE_URL` and `INVENTORY_TEST_OWNER_DATABASE_URL`

For read-only restore verification only `INVENTORY_TEST_DATABASE_URL` is required. For integration rehearsal, both settings below are used. Copy the template, preserve the exact restore-check host/database and role names, and keep URLs passwordless. Set `PGPASSFILE` to the secured local password file; do not paste credential values into commands or chat:

```powershell
Set-Location 'C:\Users\Digit Web\Desktop\Sivabavan\Projects\inventory-aios\backend'
Copy-Item .migration.env.example .migration.env
Copy-Item .test.env.example .test.env
notepad.exe .migration.env
notepad.exe .test.env
```

Each URL must point to `localhost:5432/inventory_aios_restore_check`. The runtime application continues to use `.env` and `INVENTORY_DATABASE_URL`; do not add the migration secret to `.env`. `.migration.env` and `.test.env` are ignored by Git.

## 5. Identity and runtime permission checks (do not run yet)

Verify the migrator login and explicit owner assumption in a single session:

```powershell
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U inventory_aios_migrator -d inventory_aios_restore_check -c "SET ROLE inventory_aios_owner; SELECT session_user, current_user, current_database();"
```

Verify the Alembic loader uses that same connection and reaches the current revision. `current` performs inspection only; do not use `upgrade` during this preparation:

```powershell
Set-Location 'C:\Users\Digit Web\Desktop\Sivabavan\Projects\inventory-aios\backend'
$env:PGPASSFILE = Join-Path $env:APPDATA 'postgresql\pgpass.conf'
.\.venv\Scripts\alembic.exe -c alembic.ini current
```

Verify runtime permission checks without attempting writes:

```powershell
psql -X -v ON_ERROR_STOP=1 -h localhost -p 5432 -U inventory_aios_app -d inventory_aios_restore_check -c "SELECT current_database(),session_user,current_user,has_table_privilege(current_user,'public.employees','SELECT'),has_table_privilege(current_user,'public.employees','UPDATE'),has_table_privilege(current_user,'public.employee_history','UPDATE'),has_table_privilege(current_user,'public.employee_history','DELETE'),has_table_privilege(current_user,'public.employee_history','TRUNCATE'),has_table_privilege(current_user,'public.employee_history','TRIGGER'),has_schema_privilege(current_user,'public','CREATE');"
```

Expected: restore-check database, `inventory_aios_app` for both identities, employees SELECT true, and all listed mutation/schema privileges false. Once explicitly approved, the isolated integration test command is:

```powershell
Set-Location 'C:\Users\Digit Web\Desktop\Sivabavan\Projects\inventory-aios\backend'
$env:PGPASSFILE = Join-Path $env:APPDATA 'postgresql\pgpass.conf'
.\.venv\Scripts\python.exe -m pytest -m integration tests\test_postgres_integration.py
```

It uses app identity for permission assertions and migration identity plus `SET ROLE inventory_aios_owner` for owner-level trigger tests; fixtures roll back synthetic writes.

## 6. Recovery

Recovery is destructive to the disposable rehearsal database. Do not run it without explicit approval. Before connecting or dropping anything, it verifies the adjacent SHA-256 manifest. It drops and recreates only `inventory_aios_restore_check`, removing rehearsal-created objects absent from the archive, then restores archived objects and ownership. The captured database ACL was NULL/default. PostgreSQL's stock template stores PUBLIC CONNECT explicitly and omits TEMP; recovery adds only PUBLIC TEMP, does not add redundant grants to the database owner, and verifies app effective CONNECT/TEMP, schema ownership, absence of explicit app ACL entries, null/default table/function ACLs, and no default-privilege rows. PostgreSQL cannot restore the original NULL ACL representation through ordinary GRANT/REVOKE commands, so database ACL storage may be non-NULL while effective access matches the captured default. Inspect any non-default cluster template changes before recovery:

```powershell
Set-Location 'C:\Users\Digit Web\Desktop\Sivabavan\Projects\inventory-aios'
$env:PGPASSFILE = Join-Path $env:APPDATA 'postgresql\pgpass.conf'
.\scripts\database\04_recover_restore_check.ps1
```

Cluster-wide roles and membership are not automatically dropped during recovery. Review their memberships and object dependencies across all databases before considering any cluster-role cleanup. Do not use `DROP OWNED` as routine rollback.


## Ownership and privilege safety notes

- `inventory_aios_app` already exists and is not recreated. It must have no memberships and must not own the rehearsal database, `public` schema, application tables/sequences/types/functions, or protected history objects after rehearsal setup.
- `inventory_aios_owner` is `NOLOGIN`, has no persistent `CREATEDB`, and owns the rehearsal database plus application objects. `inventory_aios_migrator` is a restricted login with `NOINHERIT`; its membership in owner is explicitly `INHERIT FALSE, SET TRUE`. These role attributes and memberships are cluster-wide.
- The runtime role receives only database CONNECT, schema USAGE, and documented SELECT access for active read workflows. It receives no database/schema CREATE, DDL, ownership, trigger, employee-history UPDATE/DELETE/TRUNCATE, or owner membership. Confirm effective privileges, including PUBLIC ACLs and memberships.
- Default function EXECUTE for PUBLIC is revoked for objects created by `inventory_aios_owner`; existing application function grants to PUBLIC are revoked in the rehearsal database. Never grant runtime audit INSERT until the approved audit migration has granted `EXECUTE` on `public.inventory_aios_audit_metadata_is_valid(jsonb)` to `inventory_aios_app`.
- Database owner transfer is a separate autocommit operation because `ALTER DATABASE ... OWNER` cannot run inside a transaction. A superuser directly transfers ownership; the script grants no temporary CREATEDB and treats transfer failure or unverified owner attributes as blocking.
- Recovery recreates the disposable database and verifies effective default ACL behavior; it cannot roll back cluster-wide roles/memberships. Review those roles, memberships, and cross-database dependencies separately before any cleanup; do not use `DROP OWNED` as routine rollback.

## 7. Completed local PostgreSQL rehearsal (2026-11-27)

The developer and Team Leader approved the disposable-database rehearsal. No production or development database was accessed. The retained pre-migration archive is `backups/rehearsal/inventory_aios_restore_check_pre_migrations_20261127_091308.dump`; its verified SHA-256 is `b23683d410ef3643eb53dfcd64b42585326cd57cd0d8d8e5ea89d9b30fdb8242`.

- `inventory_aios_restore_validation` was restored from the archive and retained. It remains at `7d4a9c2e1b60`, owned by `inventory_aios_owner`. Read-only verification found 13 public tables, 120 constraints, 31 indexes, 13 non-internal triggers and 4 functions; all relations and functions are owner-owned. No audit or employee-history rows were present. Effective runtime ACL checks showed CONNECT and schema USAGE/read access required for employee reads, with no schema/database CREATE, employee UPDATE or audit INSERT/UPDATE/DELETE/TRUNCATE.
- `inventory_aios_restore_check` advanced from `7d4a9c2e1b60` through `0ea2d9c71b45`, `4b6f10a2c903`, `9c81e247a610`, and `a1c7e3052b94` (head). Database and schema ownership remained `inventory_aios_owner`; the runtime role has no memberships or object ownership.
- The narrowly scoped authentication grants were applied temporarily for the authentication PostgreSQL suite and explicitly revoked afterward. Final direct checks confirmed no runtime authentication-table access and no runtime audit writes or mutation privileges. The audit administrator grant rehearsal ran inside a rollback-only test transaction; it left no grants or audit records.
- 47 target-guarded PostgreSQL integration tests passed across core, authentication, inventory constraints, audit, employee sync, and registration/allocation/return workflows. The separate rollback-protected audit privilege rehearsal passed 1 test. These results verify only implemented paths and do not enable authentication, audit writing, or operational inventory writes.
- Fictional fixtures were transaction-rolled back or cleaned. Final counts for rehearsal users, employees, test categories, test products, receipts, assets, balances, approvals and audit rows were zero.

The grant scripts are rehearsal tools, not authorization for production activation. The verifier `08_verify_authentication_privileges.sql` expects temporary authentication grants to be present, so it is expected to fail after the explicit post-test revocation. Re-run this section only with approval for the exact database operations, a verified recovery path, and an approved backup. Never substitute `inventory_aios_dev` or production. Do not use Alembic downgrade as routine rollback; revisions intentionally refuse destructive downgrade when protected records exist.

## 8. Task F.1C.1 operational grant draft (not applied)

`09_operational_runtime_grants.sql` and `10_revoke_operational_runtime_grants.sql` are prepared-only drafts guarded to `inventory_aios_restore_check`, migrator-to-owner execution, and revision `b2d4f6a8c013`. The draft limits the app role to named application tables, omits employee-source synchronization writes, keeps credential rows read-only, limits session mutations to activity/revocation, makes audit append-only, and denies schema/database creation and role escalation. The matching revocation file removes the draft's grants while preserving the baseline user/role/employee read grants. Neither file has been executed or validated against an approved full application privilege matrix. Review the listed table operations against every production repository, capture the pre-grant ACL state, and obtain separate approval before any rehearsal or persistent grant. Exact user-to-role/capability assignments, custom repair currency codes, MFA policy, and distributed login-rate settings remain unresolved; database grants do not authorize a user operation.

## 9. Task F.1C.2 shared attempt protection grant draft (not applied)

Revision `c4e2b7a91d60` adds `public.auth_login_attempt_buckets` and the bounded `public.inventory_aios_cleanup_login_attempts(integer, integer)` cleanup function. The operational grant/revocation drafts now guard against this revision and include only the named bucket operations and cleanup-function execution needed by the shared login adapter. They have not been executed, and the revision itself has not been applied or PostgreSQL-verified. Before any use, verify the target and revision, take a fresh backup, review the complete repository privilege inventory, preserve owner/migrator/runtime separation, and obtain the separately required authorization. No permanent grant is authorized by this draft.

## 10. Phase F.1C.4 verified restore-check state (2026-11-27)

This section supersedes earlier forward-looking status in sections 7-9 for the current restore-check database. The developer and Team Leader supplied the backup and archive-readability evidence; it was not repeated during this read-only inspection. The inspection used the existing passwordless `.test.env` URL and PostgreSQL password file; no credential value was displayed.

- Guarded connection matched `inventory_aios_restore_check`, `localhost:5432`, `session_user=inventory_aios_migrator`, `current_user=inventory_aios_owner`, revision `d2a8f4c1b790`. Database owner is `inventory_aios_owner`.
- `inventory_aios_owner` is NOLOGIN. `inventory_aios_migrator` is LOGIN/NOINHERIT and has only SET (not INHERIT or ADMIN) membership in owner. `inventory_aios_app` is LOGIN, has no memberships, owns no public table/function, and has no database/schema CREATE.
- Both individually assigned accounts are active and have credentials. `super_admin` has `inventory_administrator` and `security_administrator`; `system_admin` has `inventory_administrator`. Bootstrap operator authorization reference is recorded as `DWL 347` / `F.1C.4`. The operator and credential values are not application secrets and must not be entered into runtime logs.
- Runtime effective baseline is database CONNECT, schema USAGE, and SELECT on `users`, `roles`, `user_roles`, and `employees`. No operational tables, auth credential/session/attempt columns, audit writes, or public application function execution are granted. No application tables/functions are owned by the runtime role.
- The only default ACL row is the owner’s global function default allowing owner EXECUTE. There are no table default ACLs and no migrator/app default ACLs. Current application table ACLs are owner-owned; baseline runtime SELECT is explicit on the four tables above.
- Developer/Team Leader manually verified bootstrap and ordinary audit event records. That evidence does not establish runtime audit writer privileges or inventory transaction integration tests.

The current `09_operational_runtime_grants.sql` and `10_revoke_operational_runtime_grants.sql` are transactional scripts guarded to revision `d2a8f4c1b790`. `09` adds repository-required inventory reads/writes, necessary auth column privileges, append-only audit INSERT plus `id`/`occurred_at` SELECT, and validator/cleanup EXECUTE. It does not change PUBLIC ACLs, database CONNECT, schema USAGE, baseline reads, or default privileges. `10` revokes those introduced grants and verifies operational/auth/audit rights are absent while baseline reads/connectivity remain. For the Phase F.1C.5 local rehearsal, `09` and `10` both committed successfully around the focused PostgreSQL auth/inventory/workflow suites; a final runtime connection verified the baseline ACL state was restored. No migration or provisioning was repeated. An interrupted transaction rolls back; inspect live ACL state before retrying either script.

Production activation remains gated by production CSRF/deployment and real-browser security evidence, runtime attempt-protection verification, runtime audit-writer verification, and inventory transaction/concurrency tests after separately approved grants. Summary activation also requires its distinct AUTH-09 through AUTH-12 field, viewer, scope and exposure approvals. Do not activate the normal application from this local rehearsal evidence alone.



