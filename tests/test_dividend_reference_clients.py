import httpx
import pytest

from backend.app.ingestion import fsc_stock_dividends, kis_dividend_schedules
from backend.app.ingestion.fsc_stock_dividend_client import (
    FscStockDividendApiError,
    fetch_fsc_stock_dividend_page,
    parse_fsc_stock_dividend_payload,
)
from backend.app.ingestion.kis_client import (
    KIS_BASE_URL,
    KisApiError,
    fetch_ksd_dividend_schedule,
    parse_ksd_dividend_payload,
)


def _kis_row(**overrides: str) -> dict[str, str]:
    row = {
        "record_date": "20260715",
        "sht_cd": "069500",
        "divi_kind": "분기배당",
        "face_val": "0",
        "per_sto_divi_amt": "100",
        "divi_rate": "0.00",
        "stk_divi_rate": "0.00",
        "divi_pay_dt": "20260717",
        "stk_div_pay_dt": "",
        "odd_pay_dt": "",
        "stk_kind": "보통주",
        "high_divi_gb": "N",
    }
    row.update(overrides)
    return row


def _fsc_row(**overrides: str) -> dict[str, str]:
    row = {
        "basDt": "20260716",
        "crno": "1101110000000",
        "isinCd": "KR7069500007",
        "isinCdNm": "KODEX 200",
        "stckIssuCmpyNm": "삼성자산운용",
        "dvdnBasDt": "20260715",
        "cashDvdnPayDt": "20260717",
        "stckHndvDt": "",
        "stckDvdnRcd": "01",
        "stckDvdnRcdNm": "현금배당",
        "trsnmDptyDcd": "01",
        "trsnmDptyDcdNm": "한국예탁결제원",
        "scrsItmsKcd": "01",
        "scrsItmsKcdNm": "보통주",
        "stckGenrDvdnAmt": "100",
        "stckGrdnDvdnAmt": "0",
        "stckGenrCashDvdnRt": "0.00",
        "stckGenrDvdnRt": "0.00",
        "cashGrdnDvdnRt": "0.00",
        "stckGrdnDvdnRt": "0.00",
        "stckParPrc": "0",
        "stckStacMd": "12",
    }
    row.update(overrides)
    return row


def test_kis_ksd_dividend_request_uses_official_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["tr_id"] == "HHKDB669102C0"
        assert request.url.path == "/uapi/domestic-stock/v1/ksdinfo/dividend"
        assert request.url.params["GB1"] == "0"
        assert request.url.params["F_DT"] == "20260701"
        assert request.url.params["T_DT"] == "20260731"
        assert request.url.params["SHT_CD"] == "069500"
        return httpx.Response(
            200,
            json={"rt_cd": "0", "msg_cd": "MCA00000", "output1": [_kis_row()]},
        )

    with httpx.Client(
        base_url=KIS_BASE_URL, transport=httpx.MockTransport(handler)
    ) as client:
        response = fetch_ksd_dividend_schedule(
            client,
            app_key="app-key",
            app_secret="app-secret",
            access_token="token",
            start_date="20260701",
            end_date="20260731",
            isu_code="069500",
        )

    assert response.payload["output1"][0]["per_sto_divi_amt"] == "100"


def test_kis_ksd_dividend_rejects_incomplete_or_invalid_rows() -> None:
    missing = _kis_row()
    missing.pop("record_date")
    with pytest.raises(KisApiError, match="record_date"):
        parse_ksd_dividend_payload({"rt_cd": "0", "output1": [missing]})
    with pytest.raises(KisApiError, match="divi_pay_dt"):
        parse_ksd_dividend_payload(
            {"rt_cd": "0", "output1": [_kis_row(divi_pay_dt="2026-07-17")]}
        )
    with pytest.raises(KisApiError, match="record_date"):
        parse_ksd_dividend_payload(
            {"rt_cd": "0", "output1": [_kis_row(record_date="20261340")]}
        )

    assert parse_ksd_dividend_payload({"rt_cd": "0"}).payload.get("output1") is None
    sentinel = parse_ksd_dividend_payload(
        {"rt_cd": "0", "output1": [_kis_row(divi_pay_dt="00000000")]}
    )
    assert sentinel.payload["output1"][0]["divi_pay_dt"] == "00000000"


def test_fsc_stock_dividend_request_and_schema_are_exact() -> None:
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "pageNo": "1",
                "numOfRows": "1000",
                "totalCount": "1",
                "items": {"item": [_fsc_row()]},
            },
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/getDiviInfo_V2")
        assert request.url.params["serviceKey"] == "never-print-key"
        assert request.url.params["resultType"] == "json"
        assert request.url.params["basDt"] == "20260716"
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        page = fetch_fsc_stock_dividend_page(
            client,
            api_key="never-print-key",
            page_number=1,
            rows_per_page=1000,
            base_date="20260716",
        )

    assert page.records[0]["isinCd"] == "KR7069500007"


def test_fsc_stock_dividend_errors_do_not_echo_credentials() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(FscStockDividendApiError) as error,
    ):
        fetch_fsc_stock_dividend_page(
            client,
            api_key="never-print-key",
            page_number=1,
            rows_per_page=100,
        )
    assert "never-print-key" not in str(error.value)

    missing = _fsc_row()
    missing.pop("dvdnBasDt")
    payload = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {
                "pageNo": 1,
                "numOfRows": 100,
                "totalCount": 1,
                "items": {"item": [missing]},
            },
        }
    }
    with pytest.raises(FscStockDividendApiError, match="dvdnBasDt"):
        parse_fsc_stock_dividend_payload(payload)


def test_kis_dividend_collector_preserves_raw_and_normalized_evidence(
    tmp_path, monkeypatch
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        '{"products":[{"isu_code":"069500","isu_name":"KODEX 200"}]}',
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(
                200,
                json={"access_token": "token", "token_type": "Bearer"},
            )
        return httpx.Response(
            200,
            json={"rt_cd": "0", "msg_cd": "MCA00000", "output1": [_kis_row()]},
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        kis_dividend_schedules.httpx,
        "Client",
        lambda **_: real_client(
            base_url=KIS_BASE_URL,
            transport=httpx.MockTransport(handler),
        ),
    )
    report = kis_dividend_schedules.collect_kis_dividend_schedules(
        app_key="app-key",
        app_secret="app-secret",
        universe_path=universe,
        start_date=kis_dividend_schedules.date(2026, 7, 1),
        end_date=kis_dividend_schedules.date(2026, 7, 31),
        raw_root=tmp_path / "raw",
        output_root=tmp_path / "cache",
        delay_seconds=0,
    )

    assert report["failure_count"] == 0
    assert report["events"][0]["record_date"] == "2026-07-15"
    assert (tmp_path / report["evidence"][0]["raw_path"]).exists()


def test_kis_dividend_collector_retries_a_transient_server_error(
    tmp_path, monkeypatch
) -> None:
    universe = tmp_path / "universe.json"
    universe.write_text(
        '{"products":[{"isu_code":"069500","isu_name":"KODEX 200"}]}',
        encoding="utf-8",
    )
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        if request.url.path == "/oauth2/tokenP":
            return httpx.Response(
                200,
                json={"access_token": "token", "token_type": "Bearer"},
            )
        request_count += 1
        if request_count == 1:
            return httpx.Response(500)
        return httpx.Response(
            200,
            json={"rt_cd": "0", "msg_cd": "MCA00000", "output1": [_kis_row()]},
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        kis_dividend_schedules.httpx,
        "Client",
        lambda **_: real_client(
            base_url=KIS_BASE_URL,
            transport=httpx.MockTransport(handler),
        ),
    )
    report = kis_dividend_schedules.collect_kis_dividend_schedules(
        app_key="app-key",
        app_secret="app-secret",
        universe_path=universe,
        start_date=kis_dividend_schedules.date(2026, 7, 1),
        end_date=kis_dividend_schedules.date(2026, 7, 31),
        raw_root=tmp_path / "raw",
        output_root=tmp_path / "cache",
        delay_seconds=0,
    )

    assert request_count == 2
    assert report["failure_count"] == 0


def test_fsc_dividend_collector_paginates_and_preserves_raw(
    tmp_path, monkeypatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page_number = int(request.url.params["pageNo"])
        rows = [_fsc_row(isinCd=f"KR706950000{page_number}")]
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {
                        "pageNo": page_number,
                        "numOfRows": 1,
                        "totalCount": 2,
                        "items": {"item": rows},
                    },
                }
            },
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        fsc_stock_dividends.httpx,
        "Client",
        lambda **_: real_client(transport=httpx.MockTransport(handler)),
    )
    report = fsc_stock_dividends.collect_fsc_stock_dividends(
        api_key="never-print-key",
        base_date=fsc_stock_dividends.date(2026, 7, 16),
        raw_root=tmp_path / "raw",
        output_root=tmp_path / "cache",
        rows_per_page=1,
    )

    assert report["page_count"] == 2
    assert report["record_count"] == 2
    assert report["requested_base_date"] == "2026-07-16"
    assert report["data_as_of"] == "2026-07-16"
    assert all((tmp_path / page["raw_path"]).exists() for page in report["pages"])
