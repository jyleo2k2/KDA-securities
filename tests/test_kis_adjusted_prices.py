import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from backend.app.ingestion.kis_adjusted_prices import (
    _collect_product,
    load_pension_etf_universe,
)
from backend.app.ingestion.kis_client import (
    KIS_BASE_URL,
    KisApiError,
    fetch_adjusted_daily_item_prices,
    parse_adjusted_daily_price_payload,
)


def _row(business_date: str, **overrides: str) -> dict[str, str]:
    row = {
        "stck_bsop_date": business_date,
        "stck_clpr": "10000",
        "stck_oprc": "9900",
        "stck_hgpr": "10100",
        "stck_lwpr": "9800",
        "acml_vol": "1234",
        "acml_tr_pbmn": "5678",
        "flng_cls_code": "00",
        "prtt_rate": "0.00",
        "mod_yn": "N",
        "prdy_vrss_sign": "2",
        "prdy_vrss": "100",
        "revl_issu_reas": "",
    }
    row.update(overrides)
    return row


def _payload(rows: list[dict[str, str]]) -> dict[str, object]:
    return {
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리 되었습니다.",
        "output1": {"stck_shrn_iscd": "069500"},
        "output2": rows,
    }


def test_kis_adjusted_price_request_forces_fid_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["FID_ORG_ADJ_PRC"] == "0"
        assert request.url.params["FID_PERIOD_DIV_CODE"] == "D"
        assert request.url.params["FID_INPUT_ISCD"] == "069500"
        assert request.headers["tr_id"] == "FHKST03010100"
        return httpx.Response(200, json=_payload([_row("20260715")]))

    with httpx.Client(
        base_url=KIS_BASE_URL, transport=httpx.MockTransport(handler)
    ) as client:
        response = fetch_adjusted_daily_item_prices(
            client,
            app_key="app-key",
            app_secret="app-secret",
            access_token="token",
            isu_code="069500",
            start_date="20260101",
            end_date="20260715",
        )

    assert response.payload["output2"][0]["stck_clpr"] == "10000"


def test_adjusted_price_rows_must_be_descending_and_complete() -> None:
    response = parse_adjusted_daily_price_payload(
        _payload([_row("20260715"), _row("20260714")])
    )
    assert len(response.payload["output2"]) == 2

    with pytest.raises(KisApiError, match="descending"):
        parse_adjusted_daily_price_payload(
            _payload([_row("20260714"), _row("20260715")])
        )

    missing = _row("20260715")
    missing.pop("mod_yn")
    with pytest.raises(KisApiError, match="mod_yn"):
        parse_adjusted_daily_price_payload(_payload([missing]))


def test_product_collection_writes_adjusted_price_contract(tmp_path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_payload(
                [
                    _row("20260715"),
                    _row("20260714", mod_yn="Y", revl_issu_reas="분할"),
                ]
            ),
        )

    with httpx.Client(
        base_url=KIS_BASE_URL, transport=httpx.MockTransport(handler)
    ) as client:
        result = _collect_product(
            client=client,
            app_key="app-key",
            app_secret="app-secret",
            access_token="token",
            product={"isu_code": "069500", "isu_name": "KODEX 200"},
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 15),
            raw_root=tmp_path / "raw",
            cache_root=tmp_path / "cache",
            delay_seconds=0,
            force=False,
        )

    payload = json.loads((tmp_path / result.cache_path).read_text(encoding="utf-8"))
    assert payload["price_policy"]["FID_ORG_ADJ_PRC"] == "0"
    assert payload["return_basis"] == "adjusted_close_price_not_total_return"
    assert payload["modified_observation_count"] == 1
    assert payload["observations"][0]["date"] == "2026-07-14"


def test_product_collection_refetches_cached_boundary_for_earlier_start(
    tmp_path,
) -> None:
    raw_path = (
        tmp_path
        / "raw"
        / "adjusted_daily_itemchartprice"
        / "069500"
        / "20200102.json"
    )
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(
        json.dumps(_payload([_row("20200102")])),
        encoding="utf-8",
    )
    request_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json=_payload([_row("20200102"), _row("20191231")]),
        )

    with httpx.Client(
        base_url=KIS_BASE_URL, transport=httpx.MockTransport(handler)
    ) as client:
        result = _collect_product(
            client=client,
            app_key="app-key",
            app_secret="app-secret",
            access_token="token",
            product={"isu_code": "069500", "isu_name": "KODEX 200"},
            start_date=date(2019, 1, 1),
            end_date=date(2020, 1, 2),
            raw_root=tmp_path / "raw",
            cache_root=tmp_path / "cache",
            delay_seconds=0,
            force=False,
        )

    payload = json.loads(Path(result.cache_path).read_text(encoding="utf-8"))
    assert request_count == 1
    assert result.status == "fetched"
    assert payload["page_evidence"][0]["status"] == (
        "refetched_for_extended_start"
    )
    assert payload["history_start"] == "2019-12-31"


def test_universe_loader_accepts_only_unique_pension_etfs(tmp_path) -> None:
    path = tmp_path / "universe.json"
    path.write_text(
        json.dumps(
            {
                "products": [
                    {"isu_code": "069500", "isu_name": "KODEX 200"},
                    {"isu_code": "102110", "isu_name": "TIGER 200"},
                ]
            }
        ),
        encoding="utf-8",
    )

    products = load_pension_etf_universe(path)

    assert [product["isu_code"] for product in products] == ["069500", "102110"]
