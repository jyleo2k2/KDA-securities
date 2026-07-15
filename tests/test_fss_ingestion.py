from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from backend.app.ingestion import fss as fss_ingestion
from backend.app.ingestion import fss_repository as fss_repository_module
from backend.app.ingestion.fss_client import (
    FssApiError,
    FssResponse,
    fetch_fss_response,
    normalize_pension_savings,
    normalize_retirement,
)
from backend.app.ingestion.fss_repository import (
    FssDisclosureRepository,
    FssRepositoryError,
    RunHandle,
)


class _TransitionCursor:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.last_params: tuple[object, ...] | None = None

    def __enter__(self) -> "_TransitionCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, _: str, params: tuple[object, ...]) -> None:
        self.last_params = params

    def executemany(self, _: str, __: list[dict[str, object]]) -> None:
        return None


class _TransitionConnection:
    def __init__(self, cursor: _TransitionCursor) -> None:
        self._cursor = cursor
        self.rolled_back = False

    def __enter__(self) -> "_TransitionConnection":
        return self

    def __exit__(self, exc_type: object, *_: object) -> None:
        self.rolled_back = exc_type is not None

    def cursor(self) -> _TransitionCursor:
        return self._cursor


def _client(payload: dict[str, object], status_code: int = 200) -> httpx.Client:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_validates_success_code_and_count() -> None:
    payload = {
        "code": "000",
        "message": "remote-success-message",
        "count": 1,
        "list": [{"company": "테스트"}],
    }
    with _client(payload) as client:
        response = fetch_fss_response(
            client,
            endpoint="https://example.test/fss.json",
            api_key="secret-value",
            request_params={"year": 2026, "quarter": 1},
        )

    assert response.source_count == 1
    assert response.records == [{"company": "테스트"}]
    assert response.message == "accepted"
    assert "remote-success-message" not in repr(response)


def test_fetch_rejects_count_mismatch() -> None:
    payload = {"code": "000", "message": "정상", "count": 2, "list": [{}]}
    with _client(payload) as client, pytest.raises(FssApiError, match="count mismatch"):
        fetch_fss_response(
            client,
            endpoint="https://example.test/fss.json",
            api_key="secret-value",
            request_params={"year": 2026, "quarter": 1},
        )


def test_api_error_does_not_echo_key() -> None:
    payload = {
        "code": "100",
        "message": "never-print-this-key",
        "count": 0,
        "list": [],
    }
    with _client(payload) as client, pytest.raises(FssApiError) as error:
        fetch_fss_response(
            client,
            endpoint="https://example.test/fss.json",
            api_key="never-print-this-key",
            request_params={"year": 2026, "quarter": 1},
        )

    assert "never-print-this-key" not in str(error.value)
    assert error.value.code == "provider_rejected_100"


def test_live_ingestion_exposes_only_safe_fss_error_code_and_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "remote-message-with-api-key"

    def fake_fetch(*_: object, **__: object) -> FssResponse:
        raise FssApiError(secret, code="provider_rejected_100")

    monkeypatch.setattr(fss_ingestion, "fetch_fss_response", fake_fetch)

    result = fss_ingestion.run_live_ingestion(
        api_key="not-logged",
        database_url=None,
        fetch_only=True,
        ps_year=2025,
        ps_quarter=3,
        rp_year=2026,
        rp_quarter=1,
        rp_sys_type=3,
    )

    endpoint = result["endpoints"]["pension_savings"]
    assert endpoint["error_type"] == "FssApiError"
    assert endpoint["error_code"] == "provider_rejected_100"
    assert "error" not in endpoint
    assert secret not in repr(result)


def test_pension_savings_fee_rate_one_is_stored_as_one_year_rate() -> None:
    record = {
        "area": "자산운용",
        "company": "테스트운용",
        "reserve": 100,
        "reserve1": 90,
        "reserve2": 80,
        "reserve3": 70,
        "earnRate": 1.1,
        "earnRate1": 1.2,
        "earnRate2": 1.3,
        "earnRate3": 1.4,
        "feeRate1": 0.1,
        "feeRate2": 0.2,
        "feeRate3": 0.3,
        "avgEarnRate3": 2.1,
        "avgEarnRate5": 2.2,
        "avgEarnRate7": 2.3,
        "avgEarnRate10": 2.4,
        "avgFeeRate3": 0.4,
        "avgFeeRate5": 0.5,
        "avgFeeRate7": 0.6,
        "avgFeeRate10": 0.7,
    }
    response = type("Response", (), {"records": [record]})()

    row = normalize_pension_savings(response)[0]

    assert row.fee_rate_1y == Decimal("0.1")
    assert not hasattr(row, "fee_rate_current")
    assert row.reserve_source_value_3y == Decimal("70")


def test_retirement_expands_company_to_three_schemes_and_preserves_null() -> None:
    result = {"division": "합계"}
    for prefix in ("db", "dc", "irp"):
        result.update(
            {
                f"{prefix}Reserve": 100,
                f"{prefix}EarnRate": 1,
                f"{prefix}EarnRate3": 2,
                f"{prefix}EarnRate5": 3,
                f"{prefix}EarnRate7": 4,
                f"{prefix}EarnRate10": 5,
            }
        )
    result["dbReserve"] = None
    response = type(
        "Response",
        (),
        {"records": [{"company": "테스트증권", "area": "증권", "list": [result]}]},
    )()

    rows = normalize_retirement(response)

    assert [row.scheme for row in rows] == ["db", "dc", "irp"]
    assert rows[0].reserve_source_value is None
    assert "reserve_missing" in rows[0].quality_flags
    assert rows[1].reserve_source_value == Decimal("100")


@pytest.mark.parametrize(
    ("failed_endpoints", "expected_outcome"),
    [
        (set(), "succeeded"),
        ({"pension_savings"}, "partial"),
        ({"pension_savings", "retirement"}, "failed"),
    ],
)
def test_live_ingestion_attempts_endpoints_independently(
    monkeypatch: pytest.MonkeyPatch,
    failed_endpoints: set[str],
    expected_outcome: str,
) -> None:
    attempted: list[str] = []

    def fake_fetch(
        _: httpx.Client,
        *,
        endpoint: str,
        api_key: str,
        request_params: dict[str, int],
    ) -> FssResponse:
        del api_key, request_params
        name = (
            "pension_savings"
            if endpoint == fss_ingestion.PS_CORP_ENDPOINT
            else "retirement"
        )
        attempted.append(name)
        if name in failed_endpoints:
            raise FssApiError(f"{name} unavailable")
        return FssResponse("000", "정상", 0, [])

    monkeypatch.setattr(fss_ingestion, "fetch_fss_response", fake_fetch)

    result = fss_ingestion.run_live_ingestion(
        api_key="not-logged",
        database_url=None,
        fetch_only=True,
        ps_year=2025,
        ps_quarter=3,
        rp_year=2026,
        rp_quarter=1,
        rp_sys_type=3,
    )

    assert attempted == ["pension_savings", "retirement"]
    assert result["outcome"] == expected_outcome
    assert result["database"] == "not_requested"


def test_live_ingestion_does_not_hide_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_unexpected(*_: object, **__: object) -> FssResponse:
        raise ValueError("programming error")

    monkeypatch.setattr(fss_ingestion, "fetch_fss_response", fail_unexpected)

    with pytest.raises(ValueError, match="programming error"):
        fss_ingestion.run_live_ingestion(
            api_key="not-logged",
            database_url=None,
            fetch_only=True,
            ps_year=2025,
            ps_quarter=3,
            rp_year=2026,
            rp_quarter=1,
            rp_sys_type=3,
        )


@pytest.mark.parametrize(
    ("outcome", "exit_code"),
    [("succeeded", 0), ("partial", 1), ("failed", 1)],
)
def test_fss_cli_exit_code_reflects_full_success_only(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    exit_code: int,
) -> None:
    args = SimpleNamespace(
        fetch_only=True,
        ps_year=2025,
        ps_quarter=3,
        rp_year=2026,
        rp_quarter=1,
        rp_sys_type=3,
    )
    settings = SimpleNamespace(
        pension_portal_api_key=SecretStr("not-logged"),
        database_url=None,
    )
    monkeypatch.setattr(
        fss_ingestion,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda: args),
    )
    monkeypatch.setattr(fss_ingestion, "get_settings", lambda: settings)
    monkeypatch.setattr(
        fss_ingestion,
        "run_live_ingestion",
        lambda **_: {"outcome": outcome},
    )

    assert fss_ingestion.main() == exit_code


def test_fss_completion_requires_one_running_row_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = _TransitionCursor(rowcount=0)
    connection = _TransitionConnection(cursor)
    monkeypatch.setattr(
        fss_repository_module.psycopg,
        "connect",
        lambda _: connection,
    )
    repository = FssDisclosureRepository("postgresql://example.invalid/db")

    with pytest.raises(FssRepositoryError, match="not running"):
        repository.complete_pension_savings(
            handle=RunHandle(
                run_id=UUID("00000000-0000-0000-0000-000000000001"),
                source_id=1,
            ),
            response=FssResponse("000", "remote-secret-message", 0, []),
            rows=[],
            year=2025,
            quarter=3,
        )

    assert connection.rolled_back is True
    assert cursor.last_params is not None
    assert cursor.last_params[1] == "accepted"
    assert "remote-secret-message" not in repr(cursor.last_params)


@pytest.mark.parametrize(("rowcount", "expected"), [(1, True), (0, False)])
def test_fss_fail_run_returns_exact_transition_result_and_stores_safe_error(
    monkeypatch: pytest.MonkeyPatch,
    rowcount: int,
    expected: bool,
) -> None:
    cursor = _TransitionCursor(rowcount=rowcount)
    connection = _TransitionConnection(cursor)
    monkeypatch.setattr(
        fss_repository_module.psycopg,
        "connect",
        lambda _: connection,
    )
    repository = FssDisclosureRepository("postgresql://example.invalid/db")

    changed = repository.fail_run(
        UUID("00000000-0000-0000-0000-000000000001"),
        FssApiError(
            "remote-message-with-api-key",
            code="provider_rejected_100",
        ),
    )

    assert changed is expected
    assert cursor.last_params is not None
    assert cursor.last_params[0] == "FssApiError:provider_rejected_100"
    assert "remote-message-with-api-key" not in repr(cursor.last_params)
