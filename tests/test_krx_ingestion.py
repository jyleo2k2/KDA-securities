from datetime import date

import httpx
import pytest

from backend.app.ingestion.krx_client import (
    KRX_ETF_REQUIRED_FIELDS,
    KrxApiError,
    fetch_krx_etf_daily,
    parse_krx_etf_payload,
)


def _row(**overrides: str) -> dict[str, str]:
    row = {field: "1" for field in KRX_ETF_REQUIRED_FIELDS}
    row.update(
        {
            "BAS_DD": "20260714",
            "ISU_CD": "069500",
            "ISU_NM": "KODEX 200",
            "IDX_IND_NM": "코스피 200",
        }
    )
    row.update(overrides)
    return row


def test_fetch_krx_etf_daily_validates_schema_without_echoing_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["AUTH_KEY"] == "secret-value"
        assert request.url.params["basDd"] == "20260714"
        return httpx.Response(200, json={"OutBlock_1": [_row()]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_krx_etf_daily(
            client,
            api_key="secret-value",
            base_date=date(2026, 7, 14),
        )

    assert len(result.records) == 1
    assert result.records[0]["ISU_CD"] == "069500"


def test_krx_http_error_does_not_echo_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(KrxApiError) as error,
    ):
        fetch_krx_etf_daily(
            client,
            api_key="never-print-this-key",
            base_date=date(2026, 7, 14),
        )

    assert error.value.status_code == 401
    assert "never-print-this-key" not in str(error.value)


def test_krx_contract_rejects_missing_field_and_wrong_date() -> None:
    missing_nav = _row()
    missing_nav.pop("NAV")
    with pytest.raises(KrxApiError, match="NAV"):
        parse_krx_etf_payload(
            {"OutBlock_1": [missing_nav]},
            base_date=date(2026, 7, 14),
        )

    with pytest.raises(KrxApiError, match="date"):
        parse_krx_etf_payload(
            {"OutBlock_1": [_row(BAS_DD="20260713")]},
            base_date=date(2026, 7, 14),
        )
