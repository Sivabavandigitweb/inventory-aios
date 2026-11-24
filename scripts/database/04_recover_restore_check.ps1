param(
    [string]$Backup = "backups\inventory_aios_dev_full_20261123_174845.dump",
    [string]$Database = "inventory_aios_restore_check",
    [string]$PsqlExe,
    [string]$PgRestoreExe,
    [string]$CreatedbExe,
    [string]$DropdbExe,
    [string]$PythonExe
)
$ErrorActionPreference = "Stop"
if ($Database -ne "inventory_aios_restore_check") { throw "Recovery target must be inventory_aios_restore_check." }
if (-not (Test-Path -LiteralPath $Backup -PathType Leaf)) { throw "Verified backup file was not found." }
function Resolve-PgTool([string]$Explicit, [string]$Name) {
    if ($Explicit) { if (-not (Test-Path -LiteralPath $Explicit -PathType Leaf)) { throw "$Name executable path does not exist." }; return (Resolve-Path -LiteralPath $Explicit).Path }
    $cmd = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path 'C:\Program Files\PostgreSQL\18\bin' "$Name.exe"
    if (Test-Path -LiteralPath $fallback -PathType Leaf) { return $fallback }
    throw "Could not find $Name on PATH; pass -$($Name)Exe with its full path."
}
$PsqlExe = Resolve-PgTool $PsqlExe 'psql'
$PgRestoreExe = Resolve-PgTool $PgRestoreExe 'pg_restore'
$CreatedbExe = Resolve-PgTool $CreatedbExe 'createdb'
$DropdbExe = Resolve-PgTool $DropdbExe 'dropdb'
if ($PythonExe) {
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Python executable path does not exist.' }
    $PythonExe = (Resolve-Path -LiteralPath $PythonExe).Path
} else {
    $venvPython = Join-Path $PSScriptRoot '..\..\backend\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) { $PythonExe = (Resolve-Path -LiteralPath $venvPython).Path }
    else {
        $pythonCommand = Get-Command 'python.exe' -ErrorAction SilentlyContinue
        if (-not $pythonCommand) { throw 'Could not find Python to verify the backup manifest.' }
        $PythonExe = $pythonCommand.Source
    }
}
$archive = (Resolve-Path -LiteralPath $Backup).Path
$manifest = "$archive.sha256"
$checksumTool = Join-Path $PSScriptRoot 'backup_checksum.py'
& $PythonExe $checksumTool --backup $archive --manifest $manifest
if ($LASTEXITCODE -ne 0) { throw 'Backup checksum verification failed; recovery stopped before connecting to PostgreSQL.' }
# Credentials are supplied by a secured PGPASSFILE; never pass passwords as arguments.
$admin = Read-Host 'PostgreSQL administrator login'
$identity = & $PsqlExe -X -w -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d $Database -Atc "SELECT current_database()"
if ($LASTEXITCODE -ne 0 -or $identity.Trim() -ne "inventory_aios_restore_check") { throw "Recovery identity guard failed." }
$confirm = Read-Host 'Type REBUILD inventory_aios_restore_check to replace this disposable database from backup'
if ($confirm -cne 'REBUILD inventory_aios_restore_check') { throw 'Recovery cancelled.' }
# Recreate so rehearsal-created objects absent from the archive cannot survive.
& $PgRestoreExe --list $archive *> $null
if ($LASTEXITCODE -ne 0) { throw "Backup archive could not be read." }
& $DropdbExe --if-exists --no-password --host localhost --port 5432 --username $admin $Database
if ($LASTEXITCODE -ne 0) { throw "Could not drop the guarded rehearsal database." }
& $CreatedbExe --no-password --host localhost --port 5432 --username $admin --owner inventory_aios_app $Database
if ($LASTEXITCODE -ne 0) { throw "Could not recreate rehearsal database with the baseline runtime owner." }
& $PgRestoreExe --exit-on-error --no-password --host localhost --port 5432 --username $admin --dbname=$Database $archive
if ($LASTEXITCODE -ne 0) { throw "Restore failed; keep application access stopped and rebuild from the verified archive before retrying." }
# The stock template ACL grants PUBLIC CONNECT, but not TEMP. Add only the missing
# default-effective privilege; the database owner has owner rights without an ACL grant.
& $PsqlExe -X -w -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d $Database -c "GRANT TEMPORARY ON DATABASE inventory_aios_restore_check TO PUBLIC;"
if ($LASTEXITCODE -ne 0) { throw "Restore completed but default-effective database TEMP access could not be restored." }
$aclCheck = & $PsqlExe -X -w -v ON_ERROR_STOP=1 -h localhost -p 5432 -U $admin -d $Database -Atc "SELECT current_database()='inventory_aios_restore_check' AND (SELECT pg_catalog.pg_get_userbyid(datdba)='inventory_aios_app' FROM pg_catalog.pg_database WHERE datname=current_database()) AND (SELECT nspowner='pg_database_owner'::regrole AND nspacl=pg_catalog.acldefault('n',nspowner) FROM pg_catalog.pg_namespace WHERE nspname='public') AND has_database_privilege('inventory_aios_app',current_database(),'CONNECT') AND has_database_privilege('inventory_aios_app',current_database(),'TEMP') AND has_database_privilege('inventory_aios_app',current_database(),'CREATE') AND EXISTS (SELECT 1 FROM pg_catalog.pg_database d CROSS JOIN LATERAL pg_catalog.aclexplode(d.datacl) a WHERE d.datname=current_database() AND a.grantee=0 AND a.privilege_type='CONNECT') AND EXISTS (SELECT 1 FROM pg_catalog.pg_database d CROSS JOIN LATERAL pg_catalog.aclexplode(d.datacl) a WHERE d.datname=current_database() AND a.grantee=0 AND a.privilege_type='TEMPORARY') AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_database d CROSS JOIN LATERAL pg_catalog.aclexplode(d.datacl) a WHERE d.datname=current_database() AND a.grantee=0 AND a.privilege_type='CREATE') AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_database d CROSS JOIN LATERAL pg_catalog.aclexplode(d.datacl) a JOIN pg_catalog.pg_roles r ON r.oid=a.grantee WHERE d.datname=current_database() AND r.rolname='inventory_aios_app') AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f') AND c.relacl IS NOT NULL) AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind IN ('f','p') AND p.proacl IS NOT NULL) AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_default_acl)"
if ($LASTEXITCODE -ne 0 -or $aclCheck.Trim() -ne 't') { throw 'Recovery completed but ownership, effective database access, or recorded default ACL checks failed; inspect as administrator.' }


