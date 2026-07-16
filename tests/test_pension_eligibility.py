from datetime import date
from pathlib import Path
from zipfile import ZipFile

from backend.app.engine.pension_eligibility import (
    classify_pension_account_eligibility,
)
from backend.app.ingestion.kis_pension_eligibility import (
    load_kis_retirement_etfs,
)
from backend.app.pension_eligible_etf_report import (
    build_pension_eligibility_report,
)


def _workbook(path: Path) -> None:
    shared = """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>주식</t></si><si><t>시장대표</t></si><si><t>국내</t></si>
  <si><t>정상 ETF</t></si><si><t>000001</t></si>
  <si><t>채권</t></si><si><t>국채</t></si><si><t>단기</t></si>
  <si><t>100% ETF</t></si><si><t>000002</t></si>
  <si><t>테스트운용</t></si><si><t>월분배</t></si>
</sst>"""
    sheet = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="5">
      <c r="A5" t="s"><v>0</v></c><c r="B5" t="s"><v>1</v></c>
      <c r="C5" t="s"><v>2</v></c><c r="D5" t="s"><v>3</v></c>
      <c r="E5" t="s"><v>4</v></c><c r="G5"><v>0.7</v></c>
      <c r="F5" t="s"><v>10</v></c><c r="H5" t="s"><v>11</v></c>
      <c r="I5"><v>0.15</v></c><c r="J5"><v>45392</v></c>
      <c r="K5"><v>123.45</v></c><c r="L5"><v>1.25</v></c>
      <c r="O5"><v>12.5</v></c>
    </row>
    <row r="6">
      <c r="A6" t="s"><v>5</v></c><c r="B6" t="s"><v>6</v></c>
      <c r="C6" t="s"><v>7</v></c><c r="D6" t="s"><v>8</v></c>
      <c r="E6" t="s"><v>9</v></c><c r="G6"><v>1</v></c>
    </row>
  </sheetData>
</worksheet>"""
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def _product(code: str, leverage_type: str) -> dict[str, object]:
    return {
        "isu_code": code,
        "isu_name": f"ETF {code}",
        "classification": {
            "asset_class": "equity",
            "leverage_type": leverage_type,
        },
        "fsc_join_status": "unmatched",
        "fsc_support": "none",
        "evidence": [],
    }


def test_kis_retirement_workbook_parser_preserves_codes_and_limits(
    tmp_path: Path,
) -> None:
    path = tmp_path / "retirement.xlsx"
    _workbook(path)

    products = load_kis_retirement_etfs(path)

    assert [product["isu_code"] for product in products] == ["000001", "000002"]
    assert products[0]["retirement_investment_limit_percent"] == 70
    assert products[1]["retirement_investment_limit_percent"] == 100
    assert products[1]["major_category"] == "채권"
    assert products[0]["asset_manager"] == "테스트운용"
    assert products[0]["monthly_distribution_target"] is True
    assert products[0]["total_expense_ratio_percent"] == "0.15"
    assert products[0]["listing_date"] == "2024-04-10"
    assert products[0]["net_assets_krw"] == 12_345_000_000
    assert products[0]["provider_reported_returns_percent"]["1m"] == "1.25"
    assert products[0]["provider_reported_returns_percent"]["1y"] == "12.5"


def test_account_rules_separate_provider_list_from_pension_savings() -> None:
    official = {
        "retirement_investment_limit_percent": 100,
        "major_category": "채권",
        "middle_category": "국채",
        "minor_category": "단기",
    }

    result = classify_pension_account_eligibility(
        {"leverage_type": "normal"}, official
    )

    assert result["dc"]["eligible"] is True
    assert result["dc"]["allocation_bucket"] == "full_allocation_eligible"
    assert result["dc"]["cap_treatment"] == "PROVIDER_CONFIRMED_100"
    assert result["dc"]["exception_type"] == (
        "provider_limit_reason_not_inferred"
    )
    assert result["irp"] == result["dc"]
    assert result["pension_savings"]["status"] == "eligible_by_account_rule"


def test_leverage_and_inverse_are_blocked_for_all_three_accounts() -> None:
    listed_product = {
        "retirement_investment_limit_percent": 70,
        "major_category": "주식",
        "middle_category": "파생",
        "minor_category": "레버리지",
    }
    for leverage_type in ("leveraged", "inverse"):
        result = classify_pension_account_eligibility(
            {"leverage_type": leverage_type}, listed_product
        )
        assert all(not account["eligible"] for account in result.values())
        assert result["dc"]["status"] == "ineligible_by_account_rule"
        assert result["dc"]["reason_code"] == (
            "RETIREMENT_LEVERAGE_INVERSE_PROHIBITED"
        )
        assert result["irp"] == result["dc"]
        assert result["pension_savings"]["reason_code"] == (
            "PENSION_SAVINGS_LEVERAGE_INVERSE_PROHIBITED"
        )


def test_report_contains_only_products_eligible_for_at_least_one_account() -> None:
    classification_report = {
        "products": [
            _product("000001", "normal"),
            _product("000002", "normal"),
            _product("000003", "leveraged"),
        ]
    }
    kis_products = [
        {
            "isu_code": "000001",
            "isu_name": "정상 ETF",
            "major_category": "주식",
            "middle_category": "시장대표",
            "minor_category": "국내",
            "retirement_investment_limit_percent": 70,
        }
    ]

    report = build_pension_eligibility_report(
        classification_report=classification_report,
        kis_retirement_products=kis_products,
        classification_path=Path("classification.json"),
        kis_retirement_path=Path("retirement.xlsx"),
        as_of=date(2026, 7, 15),
        eligibility_as_of=date(2026, 6, 30),
    )

    assert [product["isu_code"] for product in report["products"]] == [
        "000001",
        "000002",
    ]
    assert report["eligible_product_counts"] == {
        "dc": 1,
        "irp": 1,
        "pension_savings": 2,
    }
    assert report["eligible_asset_class_counts"] == {
        "dc": {"equity": 1},
        "irp": {"equity": 1},
        "pension_savings": {"equity": 2},
    }
