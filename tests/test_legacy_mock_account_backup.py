from datetime import UTC, datetime
from decimal import Decimal

import pytest

from scripts.backup_legacy_mock_accounts import (
    LegacyMockBackupError,
    load_verified_backup,
    write_backup,
)


def _payload() -> dict[str, list[object]]:
    return {
        "mock_scenarios": [{"id": index} for index in range(1, 7)],
        "mock_accounts": [
            {"id": index, "balance_krw": Decimal("1000000")}
            for index in range(1, 14)
        ],
        "mock_holdings": [{"id": index} for index in range(1, 87)],
    }


def test_backup_writes_canonical_json_and_verifies_manifest(tmp_path) -> None:
    backup_dir = write_backup(
        _payload(),
        tmp_path,
        created_at=datetime(2026, 7, 22, 1, 2, 3, tzinfo=UTC),
    )

    restored = load_verified_backup(backup_dir)

    assert backup_dir.name == "20260722T010203Z"
    assert restored["mock_accounts"][0] == {
        "balance_krw": "1000000",
        "id": 1,
    }


def test_backup_rejects_changed_export(tmp_path) -> None:
    backup_dir = write_backup(_payload(), tmp_path)
    data_path = backup_dir / "legacy_mock_accounts.json"
    data_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(LegacyMockBackupError, match="SHA-256"):
        load_verified_backup(backup_dir)


def test_backup_rejects_unexpected_legacy_counts(tmp_path) -> None:
    payload = _payload()
    payload["mock_holdings"] = []

    with pytest.raises(LegacyMockBackupError, match="unexpected legacy mock counts"):
        write_backup(payload, tmp_path)
