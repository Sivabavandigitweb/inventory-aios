from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.errors import AppError
from app.services.employee_sync import (
    ConfiguredReadOnlyPostgresSource,
    SourceEmployee,
    SqlAlchemyEmployeeSyncRepository,
    synchronize_employees,
)


class Source:
    def __init__(self, rows):
        self.rows = rows

    def fetch_employees(self):
        return self.rows


class Repository:
    def __init__(self):
        self.calls = []

    def synchronize(self, **kwargs):
        self.calls.append(kwargs)
        return "result"


def row(external_id="fictional-source-1", number="DEMO-001"):
    return SourceEmployee(external_id, number, "Fictional", "Person", "DEPT-X", "TEAM-X",
                          "ROLE-X", date(2025, 1, 2), "active")


def test_sync_passes_validated_fictional_snapshot_and_dry_run_flag():
    repository = Repository()
    result = synchronize_employees(source_key="fictional", source=Source([row()]),
        mapping=object(), repository=repository, audit=object(), dry_run=True,
        now=datetime(2026, 11, 26, tzinfo=timezone.utc))
    assert result == "result"
    assert repository.calls[0]["dry_run"] is True
    assert repository.calls[0]["rows"] == (row(),)


@pytest.mark.parametrize("rows", [
    [row("same", "DEMO-001"), row("same", "DEMO-002")],
    [row("one", "DEMO-001"), row("two", "DEMO-001")],
])
def test_duplicate_source_identity_or_employee_number_fails_before_persistence(rows):
    repository = Repository()
    with pytest.raises(AppError) as error:
        synchronize_employees(source_key="fictional", source=Source(rows), mapping=object(),
            repository=repository, audit=object())
    assert error.value.code == "EMPLOYEE_SYNC_CONFLICT"
    assert repository.calls == []


def test_unconfirmed_source_schema_is_not_assumed_and_config_validates_mapping():
    with pytest.raises(ValueError):
        ConfiguredReadOnlyPostgresSource(lambda: None, table="employees; DROP TABLE users", column_map={})


def test_persistent_sync_is_closed_without_approved_complete_audit():
    repository = SqlAlchemyEmployeeSyncRepository(MagicMock())
    with pytest.raises(AppError) as error:
        repository.synchronize(source_key="fictional", rows=(), mapping=object(), dry_run=False,
                               audit=object(), started_at=datetime.now(timezone.utc))
    assert error.value.code == "EMPLOYEE_SYNC_NOT_ENABLED"
    repository.session.begin.assert_not_called()
