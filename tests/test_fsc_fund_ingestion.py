import httpx
import pytest

from backend.app.ingestion.fsc_fund import fsc_match_key, krx_match_key
from backend.app.ingestion.fsc_fund_client import (
    FscFundApiError,
    fetch_fsc_fund_page,
    parse_fsc_fund_payload,
)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "basDt": "20260714",
        "srtnCd": "EX208",
        "fndNm": "삼성 KODEX 200증권상장지수투자신탁[주식]",
        "ctg": "자산운용",
        "setpDt": "20260710",
        "fndTp": "주식형",
        "prdClsfCd": "12111Z12044015911ZZ1",
        "asoStdCd": "K55105EX2080",
    }
    row.update(overrides)
    return row


def _payload(rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "pageNo": 1,
                "numOfRows": 1000,
                "totalCount": len(rows),
                "items": {"item": rows},
            },
        }
    }


def test_fetch_fsc_fund_page_validates_request_without_echoing_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["serviceKey"] == "never-print-key"
        assert request.url.params["likeFndNm"] == "상장지수투자신탁"
        return httpx.Response(200, json=_payload([_row()]))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        page = fetch_fsc_fund_page(
            client,
            api_key="never-print-key",
            page_number=1,
            rows_per_page=1000,
            name_query="상장지수투자신탁",
        )

    assert page.total_count == 1
    assert page.records[0]["asoStdCd"] == "K55105EX2080"


def test_fsc_errors_and_schema_never_echo_credentials() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(FscFundApiError) as error,
    ):
        fetch_fsc_fund_page(
            client,
            api_key="never-print-key",
            page_number=1,
            rows_per_page=1000,
            name_query="ETF",
        )
    assert "never-print-key" not in str(error.value)

    missing = _row()
    missing.pop("prdClsfCd")
    with pytest.raises(FscFundApiError, match="prdClsfCd"):
        parse_fsc_fund_payload(_payload([missing]))


def test_normalized_etf_names_match_only_after_legal_suffix_removal() -> None:
    fsc_name = "삼성 KODEX 200증권상장지수투자신탁[주식]"
    assert fsc_match_key(fsc_name) == krx_match_key("KODEX 200")

    renamed = "한화 ARIRANG 미국S&P500증권상장지수투자신탁[주식]"
    assert fsc_match_key(renamed) == krx_match_key("PLUS 미국S&P500")

    spaced = "키움 KIWOOM 미국30년국채 증권 상장지수투자신탁[채권](H)"
    assert fsc_match_key(spaced) == krx_match_key("KIWOOM 미국30년국채")
