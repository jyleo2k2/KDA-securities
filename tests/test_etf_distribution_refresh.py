from datetime import UTC, date, datetime

import httpx
import pytest

from backend.app.ingestion.etf_distribution_refresh import (
    DistributionRefreshQuarantined,
    build_refresh_window,
    merge_distribution_events,
)
from backend.app.ingestion.official_raw_storage import (
    OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET,
    OfficialRawStorage,
    build_raw_run_manifest,
)


def _confirmed(day: str) -> dict[str, str]:
    return {
        "effective_date": day,
        "event_type": "cash_distribution",
        "status": "confirmed_cash_flow",
    }


def test_refresh_window_preserves_kind_history_and_limits_kis_schedule() -> None:
    window = build_refresh_window(
        latest_ready_as_of=date(2026, 7, 16), today=date(2026, 7, 24)
    )

    assert window.kind_from == date(2026, 6, 1)
    assert window.kind_to == date(2026, 7, 24)
    assert window.kis_from == date(2026, 7, 24)
    assert window.kis_to == date(2026, 11, 21)


def test_refresh_merge_keeps_old_history_replaces_window_and_schedules() -> None:
    merged = merge_distribution_events(
        previous_events=[
            _confirmed("2026-05-01"),
            _confirmed("2026-06-10"),
            {
                "effective_date": "2026-07-10",
                "event_type": "scheduled_cash_distribution",
                "status": "excluded_from_historical_total_return",
            },
        ],
        refreshed_events=[
            _confirmed("2026-06-11"),
            {
                "effective_date": "2026-07-20",
                "event_type": "scheduled_cash_distribution",
                "status": "excluded_from_historical_total_return",
            },
        ],
        kind_from=date(2026, 6, 1),
    )

    assert [event["effective_date"] for event in merged] == [
        "2026-05-01",
        "2026-06-11",
        "2026-07-20",
    ]


def test_refresh_quarantines_material_confirmed_event_drop() -> None:
    with pytest.raises(DistributionRefreshQuarantined):
        merge_distribution_events(
            previous_events=[_confirmed("2026-06-01") for _ in range(10)],
            refreshed_events=[_confirmed("2026-06-02") for _ in range(6)],
            kind_from=date(2026, 6, 1),
        )


def test_private_raw_manifest_hashes_source_and_sets_one_year_retention(
    tmp_path,
) -> None:
    source = tmp_path / "kind.json"
    source.write_text('{"official":true}', encoding="utf-8")

    manifest = build_raw_run_manifest(
        run_id="20260724T010203Z",
        files={"kind": source},
        collected_at=datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC),
    )

    assert manifest.retention_until == "2027-07-24"
    assert manifest.artifacts[0].object_path.endswith("/kind/kind.json")
    assert len(manifest.artifacts[0].sha256) == 64


def test_private_raw_storage_uploads_artifacts_and_manifest_without_public_url(
    tmp_path,
) -> None:
    source = tmp_path / "kind.json"
    source.write_text('{"official":true}', encoding="utf-8")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer server-only-key"
        assert request.headers["apikey"] == "server-only-key"
        return httpx.Response(200, json={"Key": "stored"})

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://example.test"
    ) as client:
        storage = OfficialRawStorage(
            supabase_url="https://example.test",
            service_key="server-only-key",
            client=client,
        )
        storage.upload_run(
            run_id="20260724T010203Z",
            files={"kind": source},
            collected_at=datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC),
        )

    assert len(requests) == 2
    assert all(request.method == "PUT" for request in requests)
    assert all(
        OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET in str(request.url)
        for request in requests
    )
    assert all("/public/" not in str(request.url) for request in requests)
