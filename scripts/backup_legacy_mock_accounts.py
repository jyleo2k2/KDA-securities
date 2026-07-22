"""Export a verified, Git-ignored backup before retiring legacy mock tables.

The script only reads PostgreSQL. It writes a canonical JSON export and a
SHA-256 manifest below ``output/`` by default, so neither the database URL nor
the backup artifact is committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.settings import Settings  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT / "output" / "legacy_mock_account_backups"
TABLES = ("mock_scenarios", "mock_accounts", "mock_holdings")
EXPECTED_COUNTS = {
    "mock_scenarios": 6,
    "mock_accounts": 13,
    "mock_holdings": 86,
}


class LegacyMockBackupError(RuntimeError):
    """Raised when the legacy data is not safe to retire."""


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_bytes(content)
    temporary_path.replace(path)


def _read_legacy_payload(cursor: psycopg.Cursor[Any]) -> dict[str, list[object]]:
    payload: dict[str, list[object]] = {}
    for table in TABLES:
        cursor.execute(
            f"select to_jsonb(row) from public.{table} as row order by row.id"
        )
        payload[table] = [row[0] for row in cursor]
    return payload


def _summary(payload: dict[str, list[object]]) -> dict[str, str | int]:
    counts = {table: len(payload[table]) for table in TABLES}
    if counts != EXPECTED_COUNTS:
        raise LegacyMockBackupError(
            f"unexpected legacy mock counts: {counts}; expected {EXPECTED_COUNTS}"
        )

    accounts = payload["mock_accounts"]
    if not all(isinstance(account, dict) for account in accounts):
        raise LegacyMockBackupError("mock account backup rows are not JSON objects")
    total_balance = sum(
        (Decimal(str(account["balance_krw"])) for account in accounts),
        Decimal("0"),
    )
    return {
        **counts,
        "total_balance_krw": format(total_balance, "f"),
    }


def _verify_common_equivalence(cursor: psycopg.Cursor[Any]) -> None:
    cursor.execute(
        """
        with legacy_accounts as (
            select
                scenario.code,
                account.account_type,
                account.label,
                account.balance_krw,
                md5(
                    'mock-account:' || scenario.code || ':'
                    || account.account_type || ':' || account.label
                )::uuid as common_account_id,
                md5(
                    'mock-snapshot:' || scenario.code || ':'
                    || account.account_type || ':' || account.label
                    || ':2026-07-16'
                )::uuid as common_snapshot_id
            from public.mock_accounts as account
            join public.mock_scenarios as scenario on scenario.id = account.scenario_id
        ),
        legacy_holdings as (
            select
                md5(
                    'mock-holding:' || scenario.code || ':'
                    || account.account_type || ':' || account.label || ':'
                    || holding.instrument_name || ':2026-07-16'
                )::uuid as common_holding_id,
                holding.instrument_name,
                holding.etf_isu_code,
                holding.asset_class_id,
                holding.market_value_krw,
                holding.risk_treatment,
                holding.statutory_exception
            from public.mock_holdings as holding
            join public.mock_accounts as account on account.id = holding.account_id
            join public.mock_scenarios as scenario on scenario.id = account.scenario_id
        )
        select
            (
                select count(*)
                from legacy_accounts as legacy
                left join public.pension_accounts as account
                  on account.id = legacy.common_account_id
                 and account.data_kind = 'mock'
                 and account.origin = 'synthetic'
                left join public.account_snapshots as snapshot
                  on snapshot.id = legacy.common_snapshot_id
                 and snapshot.account_id = account.id
                where account.id is null
                   or snapshot.id is null
                   or snapshot.market_value_krw is distinct from legacy.balance_krw
                   or snapshot.contributed_principal_krw is not null
            ) as account_mismatches,
            (
                select count(*)
                from legacy_holdings as legacy
                left join public.account_holding_snapshots as holding
                  on holding.id = legacy.common_holding_id
                where holding.id is null
                   or holding.raw_instrument_name
                      is distinct from legacy.instrument_name
                   or holding.etf_isu_code is distinct from legacy.etf_isu_code
                   or holding.asset_class_id is distinct from legacy.asset_class_id
                   or holding.market_value_krw is distinct from legacy.market_value_krw
                   or holding.risk_treatment is distinct from legacy.risk_treatment
                   or holding.statutory_exception
                      is distinct from legacy.statutory_exception
            ) as holding_mismatches
        """
    )
    account_mismatches, holding_mismatches = cursor.fetchone()
    if account_mismatches or holding_mismatches:
        raise LegacyMockBackupError(
            "common-account equivalence failed: "
            f"accounts={account_mismatches}, holdings={holding_mismatches}"
        )


def write_backup(
    payload: dict[str, list[object]],
    output_dir: Path,
    *,
    created_at: datetime | None = None,
) -> Path:
    summary = _summary(payload)
    created_at = created_at or datetime.now(UTC)
    backup_dir = output_dir / created_at.strftime("%Y%m%dT%H%M%SZ")
    data_path = backup_dir / "legacy_mock_accounts.json"
    data_bytes = _canonical_json_bytes(payload)
    _atomic_write(data_path, data_bytes)

    manifest = {
        "schema_version": 1,
        "created_at": created_at.isoformat(),
        "data_file": data_path.name,
        "data_sha256": hashlib.sha256(data_bytes).hexdigest(),
        "summary": summary,
        "restore_target": "common pension-account tables only",
    }
    _atomic_write(backup_dir / "manifest.json", _canonical_json_bytes(manifest))
    return backup_dir


def load_verified_backup(path: Path) -> dict[str, list[object]]:
    backup_dir = path if path.is_dir() else path.parent
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise LegacyMockBackupError("manifest.json is required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    data_path = backup_dir / manifest["data_file"]
    data_bytes = data_path.read_bytes()
    actual_sha256 = hashlib.sha256(data_bytes).hexdigest()
    if actual_sha256 != manifest.get("data_sha256"):
        raise LegacyMockBackupError("backup SHA-256 does not match manifest")
    payload = json.loads(data_bytes)
    summary = _summary(payload)
    if summary != manifest.get("summary"):
        raise LegacyMockBackupError("backup summary does not match manifest")
    return payload


def export_backup(database_url: str, output_dir: Path) -> Path:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("begin transaction isolation level repeatable read read only")
        try:
            _verify_common_equivalence(cursor)
            payload = _read_legacy_payload(cursor)
        finally:
            connection.rollback()
    return write_backup(payload, output_dir)


def _database_url() -> str:
    database_url = Settings().database_url
    if database_url is None or not database_url.get_secret_value().strip():
        raise LegacyMockBackupError("DATABASE_URL is not configured")
    return database_url.get_secret_value().strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--verify",
        type=Path,
        metavar="BACKUP_DIR",
        help="verify an existing backup without opening the database",
    )
    args = parser.parse_args()

    if args.verify is not None:
        payload = load_verified_backup(args.verify)
        summary = _summary(payload)
        print(f"verified backup: {args.verify}")
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return

    backup_dir = export_backup(_database_url(), args.output_dir)
    summary = _summary(load_verified_backup(backup_dir))
    print(f"backup created: {backup_dir}")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
