param(
    [string]$Backup = "backups\inventory_aios_dev_full_20261123_174845.dump",
    [string]$PgRestoreExe,
    [string]$PgDumpExe
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path ".").Path
$archive = (Resolve-Path -LiteralPath $Backup).Path
if (-not $env:PGPASSFILE -or -not (Test-Path -LiteralPath $env:PGPASSFILE -PathType Leaf)) { throw "Set PGPASSFILE to the secured PostgreSQL password file before verification." }
$arguments = @("--backup", $archive)
if ($PgRestoreExe) { $arguments += @("--pg-restore", (Resolve-Path -LiteralPath $PgRestoreExe).Path) }
if ($PgDumpExe) { $arguments += @("--pg-dump", (Resolve-Path -LiteralPath $PgDumpExe).Path) }
Push-Location (Join-Path $repo "backend")
try {
    & .\.venv\Scripts\python.exe ..\scripts\database\verify_restore.py @arguments
    if ($LASTEXITCODE -ne 0) { throw "Restore comparison reported a mismatch or tool error." }
} finally { Pop-Location }
