import asyncio
import json
from datetime import date

import httpx
import pytest

from backend.app.ingestion.krx_client import (
    KrxApiError,
    fetch_krx_index_daily_async,
    parse_krx_index_payload,
)
from backend.app.ingestion.krx_indices import (
    _raw_path,
    build_benchmark_history,
)

BASE_DATE = date(2026, 7, 15)


def _equity_row(**overrides: str) -> dict[str, str]:
    row = {
        "BAS_DD": "20260715",
        "IDX_CLSS": "KOSPI",
        "IDX_NM": "코스피 200",
        "CLSPRC_IDX": "550.12",
        "CMPPREVDD_IDX": "1.20",
        "FLUC_RT": "0.22",
        "OPNPRC_IDX": "548.00",
        "HGPRC_IDX": "551.00",
        "LWPRC_IDX": "547.00",
        "ACC_TRDVOL": "1234",
        "ACC_TRDVAL": "5678",
        "MKTCAP": "9000",
    }
    row.update(overrides)
    return row


def _bond_row(**overrides: str) -> dict[str, str]:
    row = {
        "BAS_DD": "20260715",
        "BND_IDX_GRP_NM": "KTB 지수",
        "TOT_EARNG_IDX": "15933.47",
        "TOT_EARNG_IDX_CMPPREVDD": "0.12",
        "NETPRC_IDX": "102.00",
        "NETPRC_IDX_CMPPREVDD": "0.01",
        "ZERO_REINVST_IDX": "110.00",
        "ZERO_REINVST_IDX_CMPPREVDD": "0.02",
        "CALL_REINVST_IDX": "111.00",
        "CALL_REINVST_IDX_CMPPREVDD": "0.03",
        "MKT_PRC_IDX": "101.00",
        "MKT_PRC_IDX_CMPPREVDD": "0.01",
        "BND_IDX_AVG_YD": "2.80",
        "AVG_DURATION": "7.20",
        "AVG_CONVEXITY_PRC": "64.00",
    }
    row.update(overrides)
    return row


def test_krx_equity_and_bond_index_contracts_are_separate() -> None:
    equity = parse_krx_index_payload(
        {"OutBlock_1": [_equity_row()]},
        series="kospi",
        base_date=BASE_DATE,
    )
    bond = parse_krx_index_payload(
        {"OutBlock_1": [_bond_row()]},
        series="bond",
        base_date=BASE_DATE,
    )

    assert equity.records[0]["CLSPRC_IDX"] == "550.12"
    assert bond.records[0]["TOT_EARNG_IDX"] == "15933.47"


def test_krx_index_schema_rejects_missing_fields() -> None:
    row = _bond_row()
    row.pop("AVG_DURATION")

    with pytest.raises(KrxApiError, match="AVG_DURATION"):
        parse_krx_index_payload(
            {"OutBlock_1": [row]},
            series="bond",
            base_date=BASE_DATE,
        )


def test_krx_index_fetch_never_echoes_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["AUTH_KEY"] == "never-print-key"
        assert request.url.params["basDd"] == "20260715"
        return httpx.Response(401)

    async def call() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await fetch_krx_index_daily_async(
                client,
                api_key="never-print-key",
                series="krx",
                base_date=BASE_DATE,
            )

    with pytest.raises(KrxApiError) as error:
        asyncio.run(call())
    assert "never-print-key" not in str(error.value)


def test_benchmark_cache_uses_total_return_for_bonds(tmp_path) -> None:
    raw_root = tmp_path / "raw"
    cache_root = tmp_path / "cache"
    payloads = {
        "krx": {"OutBlock_1": [_equity_row(IDX_CLSS="KRX", IDX_NM="KRX 300")]},
        "kospi": {"OutBlock_1": [_equity_row()]},
        "kosdaq": {
            "OutBlock_1": [
                _equity_row(IDX_CLSS="KOSDAQ", IDX_NM="코스닥 150")
            ]
        },
        "bond": {"OutBlock_1": [_bond_row()]},
    }
    for series, payload in payloads.items():
        path = _raw_path(raw_root, series, BASE_DATE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    report = build_benchmark_history(
        start_date=BASE_DATE,
        end_date=BASE_DATE,
        raw_root=raw_root,
        cache_root=cache_root,
    )

    bond = next(
        item for item in report["benchmarks"] if item["index_name"] == "KTB 지수"
    )
    assert bond["return_basis"] == "total_return_index"
    assert bond["observations"][0]["total_return_index"] == "15933.47"
    assert report["benchmark_count"] == 8
