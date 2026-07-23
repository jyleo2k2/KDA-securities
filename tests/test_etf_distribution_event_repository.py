import json
from datetime import date
from pathlib import Path

import pytest

from backend.app import etf_distribution_event_repository
from backend.app.etf_distribution_event_repository import (
    EtfDistributionEventLoadError,
    load_etf_distribution_event_master,
)


def _report(*, source_evidence: object = None) -> dict[str, object]:
    return {
        "report_type": "pension_eligible_etf_corporate_event_master",
        "as_of": "2026-07-23",
        "engine_name": "etf_corporate_event_evidence",
        "engine_version": "2026-07-23.1",
        "source_files": {"kind_distribution": "kind.json"},
        "events": [
            {
                "isu_code": "069500",
                "isu_name": "KODEX 200",
                "isin": "KR7069500007",
                "event_type": "cash_distribution",
                "effective_date": "2026-07-20",
                "record_date": "2026-07-20",
                "payment_date": "2026-07-23",
                "cash_per_share_krw": "125",
                "ratio": None,
                "timing_basis": "kind",
                "confidence": "high",
                "status": "confirmed_cash_flow",
                "source_evidence": (
                    source_evidence
                    if source_evidence is not None
                    else [{"source_type": "kind", "source_url": "https://example.test"}]
                ),
            }
        ],
    }


def test_loads_normalized_event_master_as_one_ready_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_path = tmp_path / "events.json"
    event_path.write_text(json.dumps(_report()), encoding="utf-8")
    connection = _Connection()
    monkeypatch.setattr(
        etf_distribution_event_repository.psycopg,
        "connect",
        lambda _url: connection,
    )

    summary = load_etf_distribution_event_master(
        "postgresql://unused", event_path=event_path
    )

    assert summary.as_of == date(2026, 7, 23)
    assert summary.version_id == 42
    assert summary.event_rows == 1
    assert len(summary.source_sha256) == 64
    assert "etf_distribution_event_versions" in connection.cursor_obj.executed[0][0]
    assert "etf_distribution_events" in connection.cursor_obj.executemany_calls[0][0]
    assert "status = 'ready'" in connection.cursor_obj.executed[-1][0]


def test_rejects_event_master_without_source_evidence(tmp_path: Path) -> None:
    event_path = tmp_path / "events.json"
    event_path.write_text(json.dumps(_report(source_evidence=[])), encoding="utf-8")

    with pytest.raises(EtfDistributionEventLoadError, match="source_evidence"):
        load_etf_distribution_event_master("postgresql://unused", event_path=event_path)


class _Cursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))

    def executemany(self, sql: str, params: list[tuple[object, ...]]) -> None:
        self.executemany_calls.append((sql, params))

    def fetchone(self) -> tuple[int]:
        return (42,)


class _Connection:
    def __init__(self) -> None:
        self.cursor_obj = _Cursor()

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self.cursor_obj
