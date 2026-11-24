param([string]$PsqlExe)
$ErrorActionPreference = 'Stop'
function Resolve-Psql([string]$Explicit) {
    if ($Explicit) { if (-not (Test-Path -LiteralPath $Explicit -PathType Leaf)) { throw 'psql executable path does not exist.' }; return (Resolve-Path -LiteralPath $Explicit).Path }
    $cmd = Get-Command 'psql.exe' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
    if (Test-Path -LiteralPath $fallback -PathType Leaf) { return $fallback }
    throw 'Could not find psql on PATH; pass -PsqlExe with its full path.'
}
$PsqlExe = Resolve-Psql $PsqlExe
$admin = Read-Host 'PostgreSQL administrator login'
$db = 'inventory_aios_restore_check'
$guard = & $PsqlExe -X -w -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d $db -Atc "SELECT current_database() = '$db' AND EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = current_user AND rolsuper) AND EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_owner' AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls)"
if ($LASTEXITCODE -ne 0 -or $guard.Trim() -ne 't') { throw 'Database identity/role guard failed; no change was made.' }
# PostgreSQL superusers automatically satisfy ALTER DATABASE OWNER requirements.
# No temporary privilege is granted to inventory_aios_owner.
& $PsqlExe -X -w -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d $db -c 'ALTER DATABASE inventory_aios_restore_check OWNER TO inventory_aios_owner'
if ($LASTEXITCODE -ne 0) { throw 'Database ownership transfer failed; inspect the target and owner role before retrying.' }
$verify = & $PsqlExe -X -w -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d $db -Atc "SELECT current_database() = '$db' AND pg_catalog.pg_get_userbyid(datdba) = 'inventory_aios_owner' AND EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_owner' AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls) FROM pg_catalog.pg_database WHERE datname = current_database()"
if ($LASTEXITCODE -ne 0 -or $verify.Trim() -ne 't') { throw 'CRITICAL: database owner or owner-role attributes could not be verified; stop rehearsal and inspect as administrator.' }
