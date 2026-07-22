import pytest

from backend.app.ingestion.kis_client import KisApiResponse
from backend.app.ingestion.kis_component_snapshots import (
    KisComponentRefreshSummary,
    KisComponentSnapshotWriter,
    _fetch_components_with_retry,
    _is_transient_empty,
    _reported_component_count,
    _run_with_resume_sweeps,
)


class _TargetCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[tuple[object, ...] | None] = []
        self.rowcount = 1

    def execute(
        self, query: str, _params: tuple[object, ...] | None = None
    ) -> None:
        self.queries.append(query)
        self.params.append(_params)

    def fetchone(self) -> tuple[int]:
        return (2,)

    def fetchall(self) -> list[tuple[str]]:
        return [("069500",)]

    def __enter__(self) -> "_TargetCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _TargetConnection:
    def __init__(self) -> None:
        self.cursor_obj = _TargetCursor()

    def cursor(self) -> _TargetCursor:
        return self.cursor_obj

    def __enter__(self) -> "_TargetConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _response(*, reported_count: str, rows: list[dict[str, str]]) -> KisApiResponse:
    return KisApiResponse(
        payload={
            "rt_cd": "0",
            "msg_cd": "MCA00000",
            "output1": {"etf_cnfg_issu_cnt": reported_count},
            "output2": rows,
        },
        raw_content=b"{}",
    )


def test_transient_empty_is_retried_until_component_rows_arrive() -> None:
    responses = iter(
        [
            _response(reported_count="10", rows=[]),
            _response(
                reported_count="10",
                rows=[
                    {
                        "stck_shrn_iscd": "005930",
                        "hts_kor_isnm": "삼성전자",
                        "etf_cnfg_issu_rlim": "20.0",
                    }
                ],
            ),
        ]
    )
    calls = 0

    def fetch() -> KisApiResponse:
        nonlocal calls
        calls += 1
        return next(responses)

    result = _fetch_components_with_retry(fetch, sleep=lambda _: None)

    assert calls == 2
    assert result.transient_empty is False
    assert len(result.response.payload["output2"]) == 1


def test_exhausted_transient_empty_preserves_last_raw_response() -> None:
    response = _response(reported_count="10", rows=[])
    calls = 0

    def fetch() -> KisApiResponse:
        nonlocal calls
        calls += 1
        return response

    result = _fetch_components_with_retry(
        fetch,
        max_retries=2,
        sleep=lambda _: None,
    )

    assert calls == 3
    assert result.transient_empty is True
    assert result.response is response


def test_explicit_zero_count_is_a_true_empty_without_retry() -> None:
    response = _response(reported_count="0", rows=[])
    calls = 0

    def fetch() -> KisApiResponse:
        nonlocal calls
        calls += 1
        return response

    result = _fetch_components_with_retry(fetch, sleep=lambda _: None)

    assert calls == 1
    assert result.transient_empty is False
    assert _reported_component_count(response.payload) == 0
    assert _is_transient_empty(response.payload) is False


def test_missing_reported_count_is_treated_as_transient_not_true_empty() -> None:
    payload = {"output1": {}, "output2": []}

    assert _reported_component_count(payload) is None
    assert _is_transient_empty(payload) is True


def test_resume_skips_only_success_and_explicit_true_empty() -> None:
    from datetime import UTC, datetime

    connection = _TargetConnection()
    writer = KisComponentSnapshotWriter(
        "postgresql://example",
        connection_factory=lambda _: connection,
    )

    version_id, codes = writer.target_codes(
        resume_since=datetime(2026, 7, 21, tzinfo=UTC),
        isu_codes=[" 069500 ", "069500"],
    )

    query = connection.cursor_obj.queries[1].lower()
    assert version_id == 2
    assert codes == ["069500"]
    assert "snapshot.status = 'succeeded'" in query
    assert "etf_cnfg_issu_cnt" in query
    assert "snapshot.status = 'empty'" in query
    assert "isu_code = any(%s)" in query
    assert "payload->'classification'->>'asset_class' = 'equity'" in query
    assert "payload->'classification'->>'region' = 'south_korea'" in query
    assert connection.cursor_obj.params[1][1] == ["069500"]


def _summary(
    *,
    requested: int = 1,
    succeeded: int = 1,
    transient_empty: int = 0,
    true_empty: int = 0,
    failed: int = 0,
) -> KisComponentRefreshSummary:
    return KisComponentRefreshSummary(
        requested_etf_count=requested,
        succeeded_etf_count=succeeded,
        empty_etf_count=transient_empty + true_empty,
        failed_etf_count=failed,
        transient_empty_etf_count=transient_empty,
        true_empty_etf_count=true_empty,
    )


def test_summary_rejects_inconsistent_terminal_counts() -> None:
    with pytest.raises(ValueError, match="all terminal outcomes"):
        KisComponentRefreshSummary(
            requested_etf_count=2,
            succeeded_etf_count=1,
            empty_etf_count=0,
            failed_etf_count=0,
            transient_empty_etf_count=0,
            true_empty_etf_count=0,
        )


def test_partial_run_is_persisted_as_failed_not_succeeded() -> None:
    connection = _TargetConnection()
    writer = KisComponentSnapshotWriter(
        "postgresql://example",
        connection_factory=lambda _: connection,
    )

    writer.complete_run(
        run_id="run-id",
        summary=_summary(requested=1, succeeded=0, transient_empty=1),
    )

    query = connection.cursor_obj.queries[0].lower()
    params = connection.cursor_obj.params[0]
    assert "set status = %s" in query
    assert params is not None
    assert params[0] == "failed"
    assert params[3] == "207"


def test_complete_run_is_persisted_as_succeeded() -> None:
    connection = _TargetConnection()
    writer = KisComponentSnapshotWriter(
        "postgresql://example",
        connection_factory=lambda _: connection,
    )

    writer.complete_run(run_id="run-id", summary=_summary())

    params = connection.cursor_obj.params[0]
    assert params is not None
    assert params[0] == "succeeded"
    assert params[3] == "200"


def test_resume_sweeps_are_bounded_and_switch_to_resume_mode() -> None:
    resume_modes: list[bool] = []

    def refresh(resume_today: bool) -> KisComponentRefreshSummary:
        resume_modes.append(resume_today)
        return _summary(requested=1, succeeded=0, transient_empty=1)

    summaries = _run_with_resume_sweeps(refresh, max_resume_sweeps=3)

    assert len(summaries) == 4
    assert resume_modes == [False, True, True, True]


def test_resume_sweeps_stop_after_unresolved_etfs_recover() -> None:
    outcomes = iter(
        [
            _summary(requested=1, succeeded=0, transient_empty=1),
            _summary(),
        ]
    )

    summaries = _run_with_resume_sweeps(lambda _: next(outcomes))

    assert len(summaries) == 2
    assert summaries[-1].has_partial_failure is False
