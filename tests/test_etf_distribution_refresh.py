import json
from datetime import UTC, date, datetime

import httpx
import pytest

from backend.app.ingestion.etf_distribution_refresh import (
    DistributionRefreshQuarantined,
    build_refresh_window,
    build_refreshed_event_master,
    merge_distribution_events,
)
from backend.app.ingestion.official_raw_storage import (
    OFFICIAL_ETF_DISTRIBUTION_RAW_BUCKET,
    OFFICIAL_ETF_UNIVERSE_REFERENCE_RAW_BUCKET,
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


def test_refresh_preserves_non_distribution_history_and_replaces_stale_ex_dates(
) -> None:
    merged = merge_distribution_events(
        previous_events=[
            {
                "effective_date": "2025-01-01",
                "event_type": "split",
                "status": "confirmed_from_explicit_reason",
            },
            {
                "effective_date": "2026-07-10",
                "event_type": "distribution_ex_date_unmatched",
                "status": "reference_only",
            },
        ],
        refreshed_events=[
            {
                "effective_date": "2026-07-11",
                "event_type": "distribution_ex_date_unmatched",
                "status": "reference_only",
            },
        ],
        kind_from=date(2026, 6, 1),
    )

    assert [event["event_type"] for event in merged] == [
        "split",
        "distribution_ex_date_unmatched",
    ]
    assert merged[1]["effective_date"] == "2026-07-11"


def test_build_refreshed_master_keeps_loadable_metadata_and_records_policy() -> None:
    refreshed = build_refreshed_event_master(
        previous_master={"events": [_confirmed("2026-05-01")]},
        refreshed_master={
            "report_type": "pension_eligible_etf_corporate_event_master",
            "as_of": "2026-07-24",
            "events": [_confirmed("2026-06-11")],
        },
        kind_from=date(2026, 6, 1),
    )

    assert refreshed["event_count"] == 2
    assert refreshed["cash_distribution_count"] == 2
    assert refreshed["event_type_counts"] == {"cash_distribution": 2}


def test_refresh_normalizes_date_values_from_database_payloads() -> None:
    refreshed = build_refreshed_event_master(
        previous_master={
            "events": [
                {
                    **_confirmed("2026-05-01"),
                    "effective_date": date(2026, 5, 1),
                }
            ]
        },
        refreshed_master={
            "report_type": "pension_eligible_etf_corporate_event_master",
            "as_of": "2026-07-24",
            "events": [_confirmed("2026-06-11")],
        },
        kind_from=date(2026, 6, 1),
    )

    assert refreshed["events"][0]["effective_date"] == "2026-05-01"
    assert refreshed["refresh_policy"]["kind_correction_from"] == "2026-06-01"


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


def test_private_raw_manifest_preserves_nested_official_raw_paths(tmp_path) -> None:
    raw_root = tmp_path / "raw"
    nested = raw_root / "search" / "20260701_20260724"
    nested.mkdir(parents=True)
    (nested / "page_0001.html").write_text("official", encoding="utf-8")

    manifest = build_raw_run_manifest(
        run_id="20260724T010203Z",
        files={},
        directories={"kind": raw_root},
        collected_at=datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC),
    )

    assert manifest.artifacts[0].object_path == (
        "runs/20260724T010203Z/kind/search/20260701_20260724/page_0001.html"
    )


def test_private_raw_manifest_uses_ascii_key_for_non_ascii_direct_filename(
    tmp_path,
) -> None:
    source = tmp_path / "펀드별 보수비용비교.xls"
    source.write_bytes(b"official-workbook")

    manifest = build_raw_run_manifest(
        run_id="20260724T010203Z",
        files={"kofia-fund-costs": source},
        collected_at=datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC),
    )

    artifact = manifest.artifacts[0]
    assert artifact.object_path.endswith("/source-1489103cb41960bb.xls")
    assert artifact.original_filename == "펀드별 보수비용비교.xls"


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


def test_private_raw_storage_uploads_nested_raw_artifacts(tmp_path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    (raw_root / "response.json").write_text('{"official":true}', encoding="utf-8")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"Key": "stored"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        storage = OfficialRawStorage(
            supabase_url="https://example.test",
            service_key="server-only-key",
            client=client,
        )
        storage.upload_run(
            run_id="20260724T010203Z",
            files={},
            directories={"kis": raw_root},
            collected_at=datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC),
        )

    assert len(requests) == 2
    assert any("/kis/response.json" in str(request.url) for request in requests)


def test_private_raw_storage_deletes_only_concrete_run_paths() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"message": "success"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        storage = OfficialRawStorage(
            supabase_url="https://example.test",
            service_key="server-only-key",
            client=client,
        )
        deleted = storage.delete_paths(
            ["runs/20240101T000000Z/manifest.json", "runs/20240101T000000Z/a.json"]
        )

    assert deleted == 2
    assert requests[0].method == "DELETE"
    assert json.loads(requests[0].content) == {
        "prefixes": [
            "runs/20240101T000000Z/a.json",
            "runs/20240101T000000Z/manifest.json",
        ]
    }


def test_private_raw_storage_rejects_directory_deletion() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    with httpx.Client(transport=transport) as client:
        storage = OfficialRawStorage(
            supabase_url="https://example.test",
            service_key="server-only-key",
            client=client,
        )
        with pytest.raises(ValueError, match="concrete raw run"):
            storage.delete_paths(["runs/20240101T000000Z/"])


def test_private_raw_storage_can_promote_a_complete_reference_run(tmp_path) -> None:
    source = tmp_path / "reference.xls"
    source.write_bytes(b"official-workbook")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"Key": "stored"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        storage = OfficialRawStorage(
            supabase_url="https://example.test",
            service_key="server-only-key",
            bucket_name=OFFICIAL_ETF_UNIVERSE_REFERENCE_RAW_BUCKET,
            client=client,
        )
        manifest = storage.upload_run(
            run_id="20260724T010203Z",
            files={"kofia-fund-costs": source},
            collected_at=datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC),
        )
        storage.promote_current_run(
            dataset="etf-universe-reference-inputs", manifest=manifest
        )

    assert len(requests) == 3
    assert all(
        OFFICIAL_ETF_UNIVERSE_REFERENCE_RAW_BUCKET in str(request.url)
        for request in requests
    )
    assert str(requests[-1].url).endswith(
        "/current/etf-universe-reference-inputs.json"
    )


def test_private_raw_storage_materializes_only_a_hash_verified_current_run(
    tmp_path,
) -> None:
    source = tmp_path / "retirement.xlsx"
    source.write_bytes(b"verified-official-workbook")
    manifest = build_raw_run_manifest(
        run_id="20260724T010203Z",
        files={"kis-retirement-list": source},
        collected_at=datetime(2026, 7, 24, 1, 2, 3, tzinfo=UTC),
    )
    artifact = manifest.artifacts[0]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/current/etf-universe-reference-inputs.json"):
            return httpx.Response(
                200,
                json={
                    "manifest_path": "runs/20260724T010203Z/manifest.json",
                    "run_id": "20260724T010203Z",
                },
            )
        if path.endswith("/runs/20260724T010203Z/manifest.json"):
            return httpx.Response(200, content=manifest.as_json())
        if path.endswith(artifact.object_path):
            return httpx.Response(200, content=source.read_bytes())
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        storage = OfficialRawStorage(
            supabase_url="https://example.test",
            service_key="server-only-key",
            bucket_name=OFFICIAL_ETF_UNIVERSE_REFERENCE_RAW_BUCKET,
            client=client,
        )
        downloaded = storage.materialize_current_run(
            dataset="etf-universe-reference-inputs",
            destination=tmp_path / "materialized",
        )

    assert downloaded == manifest
    assert (
        tmp_path / "materialized" / "kis-retirement-list" / "retirement.xlsx"
    ).read_bytes() == b"verified-official-workbook"
