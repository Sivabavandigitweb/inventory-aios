from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def verify_backup_checksum(backup: Path, manifest: Path) -> str:
    """Verify a single-file SHA-256 manifest bound to the backup basename."""
    backup = Path(backup)
    manifest = Path(manifest)
    lines = manifest.read_text(encoding="ascii").splitlines()
    if len(lines) != 1:
        raise ValueError("Checksum manifest must contain exactly one entry")
    match = re.fullmatch(r"([0-9a-fA-F]{64})[ \t]+\*?(.+)", lines[0])
    if match is None or not _SHA256.fullmatch(match.group(1)):
        raise ValueError("Checksum manifest entry is malformed")
    if Path(match.group(2)).name != backup.name:
        raise ValueError("Checksum manifest names a different backup")

    digest = hashlib.sha256()
    with backup.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != match.group(1).lower():
        raise ValueError("Backup SHA-256 does not match its checksum manifest")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a local PostgreSQL backup SHA-256 manifest")
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    manifest = args.manifest or Path(f"{args.backup}.sha256")
    try:
        digest = verify_backup_checksum(args.backup, manifest)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"backup_sha256_verified: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
