from decimal import Decimal

import httpx
import pytest

from backend.app.ingestion.fss_client import (
    FssApiError,
    fetch_fss_response,
    normalize_pension_savings,
    normalize_retirement,
)


def _client(payload: dict[str, object], status_code: int = 200) -> httpx.Client:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_validates_success_code_and_count() -> None:
    payload = {
        "code": "000",
        "message": "정상",
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
    payload = {"code": "100", "message": "인증 실패", "count": 0, "list": []}
    with _client(payload) as client, pytest.raises(FssApiError) as error:
        fetch_fss_response(
            client,
            endpoint="https://example.test/fss.json",
            api_key="never-print-this-key",
            request_params={"year": 2026, "quarter": 1},
        )

    assert "never-print-this-key" not in str(error.value)


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
