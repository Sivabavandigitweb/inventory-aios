from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.database.backup_checksum import verify_backup_checksum  # noqa: E402

TRANSFER = (REPO / "scripts/database/02_transfer_database_owner.ps1").read_text(encoding="utf-8-sig")
RECOVERY = (REPO / "scripts/database/04_recover_restore_check.ps1").read_text(encoding="utf-8-sig")


def test_backup_checksum_manifest_accepts_recorded_digest(tmp_path):
    backup = tmp_path / "snapshot.dump"
    backup.write_bytes(b"verified archive")
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    manifest = tmp_path / "snapshot.dump.sha256"
    manifest.write_text(f"{digest}  {backup.name}\n", encoding="ascii")

    assert verify_backup_checksum(backup, manifest) == digest


def test_backup_checksum_manifest_rejects_changed_backup(tmp_path):
    backup = tmp_path / "snapshot.dump"
    backup.write_bytes(b"archive content")
    manifest = tmp_path / "snapshot.dump.sha256"
    manifest.write_text(f"{'0' * 64}  {backup.name}\n", encoding="ascii")

    with pytest.raises(ValueError, match="does not match"):
        verify_backup_checksum(backup, manifest)


def test_backup_checksum_manifest_rejects_unexpected_filename(tmp_path):
    backup = tmp_path / "snapshot.dump"
    backup.write_bytes(b"archive content")
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    manifest = tmp_path / "snapshot.dump.sha256"
    manifest.write_text(f"{digest}  another.dump\n", encoding="ascii")

    with pytest.raises(ValueError, match="different backup"):
        verify_backup_checksum(backup, manifest)


def test_owner_transfer_uses_superuser_without_temporary_createdb():
    assert "current_database() = '$db'" in TRANSFER
    assert "rolsuper" in TRANSFER
    assert "ALTER DATABASE inventory_aios_restore_check OWNER TO inventory_aios_owner" in TRANSFER
    assert "ALTER ROLE inventory_aios_owner CREATEDB" not in TRANSFER
    assert "ALTER ROLE inventory_aios_owner NOCREATEDB" not in TRANSFER
    assert "$LASTEXITCODE -ne 0" in TRANSFER
    assert "CRITICAL:" in TRANSFER
    assert "rolcreatedb" in TRANSFER


def test_recovery_rejects_unexpected_database_before_database_operations():
    guard = '$Database -ne "inventory_aios_restore_check"'
    assert guard in RECOVERY
    assert RECOVERY.index(guard) < RECOVERY.index("& $DropdbExe")
    assert "current_database()" in RECOVERY


def test_recovery_restores_default_effective_acl_without_app_acl_grant():
    assert "GRANT TEMPORARY ON DATABASE inventory_aios_restore_check TO PUBLIC" in RECOVERY
    assert "GRANT CONNECT, TEMPORARY ON DATABASE inventory_aios_restore_check TO inventory_aios_app" not in RECOVERY
    assert "pg_database_owner" in RECOVERY
    assert "has_database_privilege('inventory_aios_app',current_database(),'CONNECT')" in RECOVERY
    assert "has_database_privilege('inventory_aios_app',current_database(),'TEMP')" in RECOVERY
    assert "has_database_privilege('inventory_aios_app',current_database(),'CREATE')" in RECOVERY
    assert "a.privilege_type='CREATE'" in RECOVERY
    assert "aclexplode(d.datacl)" in RECOVERY
    assert "pg_default_acl" in RECOVERY
    assert "c.relacl IS NOT NULL" in RECOVERY
    assert "p.proacl IS NOT NULL" in RECOVERY





def test_recovery_verifies_public_schema_default_acl():
    assert "acldefault('n',nspowner)" in RECOVERY
