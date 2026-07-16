from datetime import date, timedelta
from io import BytesIO
from zipfile import ZipFile

import httpx
import pytest

from backend.app.ingestion.dart import (
    _date_windows,
    _match_targets,
    dart_fund_match_key,
)
from backend.app.ingestion.dart_client import (
    DartApiError,
    fetch_fund_disclosure_page,
    fetch_original_document,
    parse_disclosure_payload,
)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "corp_code": "00123456",
        "corp_name": "삼성자산운용",
        "stock_code": "",
        "corp_cls": "E",
        "report_nm": (
            "[기재정정]투자설명서(집합투자증권)"
            "(삼성KODEX은선물특별자산상장지수투자신탁[은-파생형](H))"
        ),
        "rcept_no": "20260709000189",
        "flr_nm": "삼성자산운용",
        "rcept_dt": "20260709",
        "rm": "",
    }
    row.update(overrides)
    return row


def _payload(rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "status": "000",
        "message": "정상",
        "page_no": 1,
        "page_count": 100,
        "total_count": len(rows),
        "total_page": 1,
        "list": rows,
    }


def _zip_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("document.xml", "<p>총보수 연 0.39%</p>")
    return output.getvalue()


def test_fetch_dart_page_validates_contract_without_echoing_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["crtfc_key"] == "never-print-key"
        assert request.url.params["pblntf_ty"] == "G"
        return httpx.Response(200, json=_payload([_row()]))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        page = fetch_fund_disclosure_page(
            client,
            api_key="never-print-key",
            begin_date=date(2026, 7, 1),
            end_date=date(2026, 7, 16),
            page_number=1,
        )

    assert page.total_count == 1
    assert page.disclosures[0].receipt_number == "20260709000189"


def test_dart_errors_never_echo_credentials() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(DartApiError) as error,
    ):
        fetch_fund_disclosure_page(
            client,
            api_key="never-print-key",
            begin_date=date(2026, 7, 1),
            end_date=date(2026, 7, 16),
            page_number=1,
        )
    assert "never-print-key" not in str(error.value)


def test_dart_no_data_is_an_empty_page() -> None:
    page = parse_disclosure_payload({"status": "013", "message": "조회 없음"})
    assert page.total_count == 0
    assert page.disclosures == []


def test_original_document_must_be_a_valid_zip() -> None:
    def valid_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_zip_bytes())

    with httpx.Client(transport=httpx.MockTransport(valid_handler)) as client:
        document = fetch_original_document(
            client,
            api_key="never-print-key",
            receipt_number="20260709000189",
        )
    assert document.member_names == ("document.xml",)

    def invalid_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "014"})

    with (
        httpx.Client(transport=httpx.MockTransport(invalid_handler)) as client,
        pytest.raises(DartApiError, match="not a ZIP"),
    ):
        fetch_original_document(
            client,
            api_key="never-print-key",
            receipt_number="20260709000189",
        )


def test_dart_fund_name_matching_keeps_latest_correction() -> None:
    page = parse_disclosure_payload(
        _payload(
            [
                _row(rcept_no="20260601000001", rcept_dt="20260601"),
                _row(rcept_no="20260709000189", rcept_dt="20260709"),
            ]
        )
    )
    target = {
        "isu_code": "144600",
        "isu_name": "KODEX 은선물(H)",
        "match_key": dart_fund_match_key("KODEX 은선물(H)"),
        "reasons": ["missing_kis_total_expense_ratio"],
    }

    matched = _match_targets([target], page.disclosures)

    assert matched[0]["match_status"] == "matched_exact_normalized_name"
    assert matched[0]["candidate_count"] == 2
    assert matched[0]["selected_disclosure"]["receipt_number"] == "20260709000189"


def test_dart_long_lookback_is_split_without_gaps() -> None:
    windows = _date_windows(date(2025, 7, 16), date(2026, 7, 16))

    assert windows[0][1] == date(2026, 7, 16)
    assert windows[-1][0] == date(2025, 7, 16)
    assert all((end - begin).days <= 90 for begin, end in windows)
    assert all(
        newer_begin - timedelta(days=1) == older_end
        for (newer_begin, _), (_, older_end) in zip(
            windows, windows[1:], strict=False
        )
    )
