import hashlib
import json
from datetime import date
from decimal import Decimal

import httpx

from backend.app.ingestion.macro import build_macro_evidence_report
from backend.app.ingestion.macro_clients import (
    MacroApiError,
    MacroObservation,
    fetch_bok_series,
    fetch_fred_series,
    fetch_kosis_series,
)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_bok_client_normalizes_and_keeps_secret_out_of_manifest():
    api_key = "bok-secret-value"
    payload = {
        "StatisticSearch": {
            "list_total_count": 1,
            "row": [
                {
                    "STAT_CODE": "722Y001",
                    "ITEM_CODE1": "0101000",
                    "ITEM_NAME1": "한국은행 기준금리",
                    "UNIT_NAME": "연%",
                    "TIME": "20260717",
                    "DATA_VALUE": "2.75",
                }
            ],
        }
    }
    raw = json.dumps(payload).encode()

    def handler(request: httpx.Request):
        assert api_key in str(request.url)
        return httpx.Response(200, content=raw)

    with _client(handler) as client:
        response, rows = fetch_bok_series(
            client,
            api_key=api_key,
            metric_id="kr_base_rate",
            stat_code="722Y001",
            cycle="D",
            start_period="20260701",
            end_period="20260720",
            item_code="0101000",
        )

    assert api_key not in json.dumps(response.request_params)
    assert response.sha256 == hashlib.sha256(raw).hexdigest()
    assert rows[0].period == "2026-07-17"
    assert rows[0].value == Decimal("2.75")


def test_kosis_client_normalizes_both_sexes():
    payload = [
        {
            "ORG_ID": "101",
            "TBL_ID": "DT_2OEHG072",
            "TBL_NM": "65세 기대수명",
            "PRD_DE": "2023",
            "ITM_ID": "T001",
            "ITM_NM": "기대수명",
            "C1": "1005",
            "C1_NM": "대한민국",
            "C2": "A1",
            "C2_NM": "여성",
            "UNIT_NM": "년",
            "DT": "23.6",
        },
        {
            "ORG_ID": "101",
            "TBL_ID": "DT_2OEHG072",
            "TBL_NM": "65세 기대수명",
            "PRD_DE": "2023",
            "ITM_ID": "T001",
            "ITM_NM": "기대수명",
            "C1": "1005",
            "C1_NM": "대한민국",
            "C2": "A2",
            "C2_NM": "남성",
            "UNIT_NM": "년",
            "DT": "19.2",
        },
    ]

    with _client(lambda _: httpx.Response(200, json=payload)) as client:
        response, rows = fetch_kosis_series(
            client,
            api_key="kosis-secret",
            metric_id="kr_life_expectancy_65",
            org_id="101",
            table_id="DT_2OEHG072",
            item_id="T001",
            object_l1="1005",
            object_l2="A1+A2",
            latest_period_count=5,
        )

    assert "apiKey" not in response.request_params
    assert [row.metric_id for row in rows] == [
        "kr_life_expectancy_65_a1",
        "kr_life_expectancy_65_a2",
    ]
    assert rows[0].period == "2023-01-01"


def test_fred_client_skips_missing_observations_and_sanitizes_errors():
    payload = {
        "observations": [
            {"date": "2026-07-16", "value": "4.57"},
            {"date": "2026-07-17", "value": "."},
        ]
    }
    with _client(lambda _: httpx.Response(200, json=payload)) as client:
        response, rows = fetch_fred_series(
            client,
            api_key="fred-secret",
            metric_id="us_treasury_10y",
            series_id="DGS10",
            label="미국 10년 국채금리",
            unit="%",
            observation_start="2026-07-01",
            observation_end="2026-07-20",
        )
    assert "api_key" not in response.request_params
    assert len(rows) == 1
    assert rows[0].value == Decimal("4.57")

    secret = "must-not-leak"

    def failed(request: httpx.Request):
        raise httpx.ConnectError(f"failed {request.url}", request=request)

    with _client(failed) as client:
        try:
            fetch_fred_series(
                client,
                api_key=secret,
                metric_id="metric",
                series_id="DGS10",
                label="label",
                unit="%",
                observation_start="2026-07-01",
                observation_end="2026-07-20",
            )
        except MacroApiError as error:
            assert secret not in str(error)
        else:
            raise AssertionError("MacroApiError was not raised")


def _observation(metric_id: str, period: str, value: str) -> MacroObservation:
    return MacroObservation(
        metric_id=metric_id,
        source="TEST",
        label=metric_id,
        period=period,
        value=Decimal(value),
        unit="%",
        source_reference="https://example.test/source",
        dimensions={},
    )


def test_report_derives_historical_inflation_but_does_not_change_algorithm():
    observations = [
        _observation("kr_cpi_index", "2025-06-01", "116"),
        _observation("kr_cpi_index", "2026-06-01", "119.48"),
        _observation("kr_base_rate", "2026-07-17", "2.75"),
        _observation("kr_life_expectancy_65_a1", "2023-01-01", "23.6"),
        _observation("kr_life_expectancy_65_a2", "2023-01-01", "19.2"),
        _observation("us_federal_funds_rate", "2026-06-01", "3.63"),
        _observation("us_cpi_yoy", "2026-06-01", "3.46"),
        _observation("us_treasury_10y", "2026-07-16", "4.57"),
        _observation("us_breakeven_inflation_10y", "2026-07-17", "2.24"),
    ]
    report = build_macro_evidence_report(
        observations=observations, as_of=date(2026, 7, 20)
    )

    assert report["outcome"] == "ready"
    assert report["derived_observations"]["kr_cpi_yoy"]["value"] == "3"
    usage = report["algorithm_usage"]
    assert usage["annual_assumption_review_evidence"] is True
    assert usage["planning_return_input"] is False
    assert usage["allocation_weight_input"] is False
    assert usage["rebalancing_trigger_input"] is False
    assert usage["real_value_calculation_input"] is False
    assert usage["is_forecast"] is False
    assert report["quality"]["stale_metrics"] == []


def test_report_marks_a_lagging_daily_series_incomplete():
    observations = [
        _observation("kr_cpi_index", "2025-06-01", "116"),
        _observation("kr_cpi_index", "2026-06-01", "119.48"),
        _observation("kr_base_rate", "2026-07-17", "2.75"),
        _observation("kr_life_expectancy_65_a1", "2023-01-01", "23.6"),
        _observation("kr_life_expectancy_65_a2", "2023-01-01", "19.2"),
        _observation("us_federal_funds_rate", "2026-06-01", "3.63"),
        _observation("us_cpi_yoy", "2026-06-01", "3.46"),
        _observation("us_treasury_10y", "2026-06-30", "4.57"),
        _observation("us_breakeven_inflation_10y", "2026-07-17", "2.24"),
    ]

    report = build_macro_evidence_report(
        observations=observations, as_of=date(2026, 7, 20)
    )

    assert report["outcome"] == "incomplete"
    assert report["quality"]["stale_metrics"] == ["us_treasury_10y"]
