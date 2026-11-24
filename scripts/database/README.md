# Database restore verification and role rehearsal

These scripts are prepared only. They have not been executed. The restore database is the only rehearsal target; none of these files should be retargeted to `inventory_aios_dev`.

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



