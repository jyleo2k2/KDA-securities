from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.ingestion.official_etf_component_snapshots import (
    OfficialEtfSourceBinding,
    normalize_ace_pdf_payload,
    normalize_kiwoom_pdf_html,
    normalize_samsung_product_payload,
    normalize_sol_summary_html,
    normalize_tiger_pdf_html,
)


def _binding(
    *,
    adapter_code: str,
    source_kind: str = "actual_portfolio",
    coverage_kind: str = "published_top_n",
) -> OfficialEtfSourceBinding:
    return OfficialEtfSourceBinding(
        isu_code="123456",
        source_code="official_test",
        publisher="테스트자산운용",
        adapter_code=adapter_code,
        source_product_key="product-key",
        product_url="https://example.com/product",
        holdings_url="https://example.com/holdings",
        source_kind=source_kind,
        coverage_kind=coverage_kind,
        weight_basis="fund_nav_percent",
        replication_type="physical",
        management_type="passive",
    )


def test_sol_summary_normalizes_dated_official_top3() -> None:
    html = """
    <h1>SOL 테스트 ETF</h1>
    <p>2026년 07월 21일 기준</p>
    <h2>상위 10 종목</h2>
    <table>
      <thead><tr><th>순위</th><th>종목명</th><th>비중(%)</th></tr></thead>
      <tbody>
        <tr><td>1</td><td>Alpha Inc</td><td>9.80%</td></tr>
        <tr><td>2</td><td>Beta Corp</td><td>8.92%</td></tr>
        <tr><td>3</td><td>Gamma PLC</td><td>8.03%</td></tr>
        <tr><td>4</td><td>Delta Ltd</td><td>7.42%</td></tr>
      </tbody>
    </table>
    """

    snapshot = normalize_sol_summary_html(_binding(adapter_code="sol_summary"), html)

    assert snapshot.as_of_date == date(2026, 7, 21)
    assert snapshot.completeness == "complete"
    assert snapshot.source_component_count == 4
    assert [holding.component_name for holding in snapshot.holdings] == [
        "Alpha Inc",
        "Beta Corp",
        "Gamma PLC",
    ]
    assert snapshot.holdings[0].weight_percent == Decimal("9.80")


def test_tiger_pdf_normalizes_creation_basket_top3() -> None:
    binding = _binding(
        adapter_code="tiger_pdf",
        source_kind="creation_basket",
        coverage_kind="creation_basket",
    )
    overview_html = '<input name="fixDate" value="2026.07.21">'
    rows_html = """
    <tr data-tot-cnt="31"><td>NVDA US EQUITY</td><td>NVIDIA Corp</td>
      <td>958.17</td><td>286984133</td><td>12.71</td><td>-0.12</td></tr>
    <tr data-tot-cnt="31"><td>AVGO US EQUITY</td><td>Broadcom Inc</td>
      <td>377.35</td><td>210252229</td><td>9.31</td><td>-1.53</td></tr>
    <tr data-tot-cnt="31"><td>MU US EQUITY</td><td>Micron Technology Inc</td>
      <td>138.9</td><td>177120941</td><td>7.85</td><td>-7.64</td></tr>
    """

    snapshot = normalize_tiger_pdf_html(binding, overview_html, rows_html)

    assert snapshot.as_of_date == date(2026, 7, 21)
    assert snapshot.source_kind == "creation_basket"
    assert snapshot.source_component_count == 31
    assert snapshot.holdings[0].component_code == "NVDA US EQUITY"
    assert snapshot.holdings[2].weight_percent == Decimal("7.85")


@pytest.mark.parametrize(
    ("adapter_code", "source_kind"),
    [
        ("samsung_kodex_pdf", "creation_basket"),
        ("samsung_active_pdf", "creation_basket"),
    ],
)
def test_samsung_product_payload_normalizes_non_cash_top3(
    adapter_code: str,
    source_kind: str,
) -> None:
    binding = _binding(
        adapter_code=adapter_code,
        source_kind=source_kind,
        coverage_kind="creation_basket",
    )
    payload = {
        "pdf": {
            "gijunYMD": "20260722",
            "totalCnt": 30,
            "list": [
                {
                    "secNm": "설정현금액",
                    "itmNo": "CASH00000001",
                    "ratio": None,
                },
                {"secNm": "Alpha Inc", "itmNo": "AAA US Equity", "ratio": "10.05"},
                {"secNm": "Beta Corp", "itmNo": "BBB US Equity", "ratio": "8.58"},
                {"secNm": "Gamma PLC", "itmNo": "CCC US Equity", "ratio": "6.64"},
                {"secNm": "Delta Ltd", "itmNo": "DDD US Equity", "ratio": "5.07"},
            ],
        }
    }

    snapshot = normalize_samsung_product_payload(binding, payload)

    assert snapshot.as_of_date == date(2026, 7, 22)
    assert snapshot.source_component_count == 30
    assert [holding.component_name for holding in snapshot.holdings] == [
        "Alpha Inc",
        "Beta Corp",
        "Gamma PLC",
    ]


def test_kiwoom_pdf_html_normalizes_selected_date_and_top3() -> None:
    binding = _binding(
        adapter_code="kiwoom_pdf",
        source_kind="creation_basket",
        coverage_kind="creation_basket",
    )
    html = """
    <input type="date" id="pdfDt" value="2026-07-22">
    <table>
      <caption>구성종목(PDF) 정보 테이블입니다.</caption>
      <thead><tr><th>NO.</th><th>종목명</th><th>종목코드</th><th>비중</th></tr></thead>
      <tbody id="pdfData">
        <tr><th>1</th><td>설정현금액</td><td>CASH00000001</td><td>-</td></tr>
        <tr><th>2</th><td>D-Wave Quantum Inc</td>
            <td>US26740W1099</td><td>9.07%</td></tr>
        <tr><th>3</th><td>Rigetti Computing Inc</td>
            <td>US76655K1034</td><td>8.97%</td></tr>
        <tr><th>4</th><td>Quantum Computing Inc</td>
            <td>US74766W1080</td><td>7.98%</td></tr>
      </tbody>
    </table>
    """

    snapshot = normalize_kiwoom_pdf_html(binding, html)

    assert snapshot.as_of_date == date(2026, 7, 22)
    assert snapshot.source_component_count == 3
    assert snapshot.holdings[0].component_code == "US26740W1099"
    assert snapshot.holdings[0].weight_percent == Decimal("9.07")


def test_fewer_than_three_weighted_rows_are_partial_and_not_top3_complete() -> None:
    payload = {
        "pdf": {
            "gijunYMD": "20260722",
            "totalCnt": 30,
            "list": [
                {"secNm": "Alpha Inc", "itmNo": "AAA", "ratio": "10.05"},
                {"secNm": "Beta Corp", "itmNo": "BBB", "ratio": "8.58"},
            ],
        }
    }

    snapshot = normalize_samsung_product_payload(
        _binding(adapter_code="samsung_active_pdf"),
        payload,
    )

    assert snapshot.completeness == "partial"
    assert snapshot.holdings == ()


def test_ace_pdf_normalizes_issuer_published_bond_constituents() -> None:
    payload = {
        "stdDt": "2026-07-22",
        "pdfList": [
            {"jm_KSC_CD": "US9219107094", "sec_NM": "Vanguard Extended", "wg": 23.09},
            {"jm_KSC_CD": "US4642874329", "sec_NM": "iShares 20+ Year", "wg": 14.82},
            {"jm_KSC_CD": "US912810UP11", "sec_NM": "U.S. Treasury 2055", "wg": 13.86},
        ],
    }

    snapshot = normalize_ace_pdf_payload(
        _binding(
            adapter_code="ace_pdf",
            source_kind="creation_basket",
            coverage_kind="creation_basket",
        ),
        payload,
    )

    assert snapshot.as_of_date == date(2026, 7, 22)
    assert snapshot.completeness == "complete"
    assert [holding.component_name for holding in snapshot.holdings] == [
        "Vanguard Extended",
        "iShares 20+ Year",
        "U.S. Treasury 2055",
    ]


def test_official_component_workflow_runs_each_weekday() -> None:
    workflow = Path(
        ".github/workflows/official-etf-components.yml"
    ).read_text(encoding="utf-8")

    assert 'cron: "40 3 * * 1-5"' in workflow
    assert "secrets.DATABASE_URL" in workflow
    assert "KIS_APP_KEY" not in workflow
    assert "backend.app.ingestion.official_etf_component_snapshots" in workflow
