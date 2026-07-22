"""Parse KOFIA's fund fee and cost comparison workbook.

The KOFIA export is an XLS (BIFF) workbook.  Its TER is the reported recurring
fund burden (stated fee plus other expenses); brokerage commission is a separate
historical fund-trading-cost disclosure and must never be added to TER blindly.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import xlrd

KOFIA_FUND_COST_URL = "https://dis.kofia.or.kr/websquare/index.jsp"
STANDARD_CODE_PATTERN = re.compile(r"[A-Z0-9]{12}")
ETF_FUND_NAME_MARKER = "상장지수"
ETF_BRANDS = (
    "DAISHIN343",
    "TIMEFOLIO",
    "KODEX",
    "TIGER",
    "KIWOOM",
    "HANARO",
    "UNICORN",
    "TRUSTON",
    "에셋플러스",
    "아이엠에셋",
    "마이티",
    "KCGI",
    "KoAct",
    "RISE",
    "ACE",
    "PLUS",
    "SOL",
    "TIME",
    "WON",
    "FOCUS",
    "MIDAS",
    "TREX",
    "BNK",
    "IBK",
    "1Q",
    "HK",
    "파워",
)
ETF_SUFFIX_PATTERN = re.compile(
    r"(?:증권|특별자산|부동산|혼합자산)?상장지수(?:자)?투자신탁"
)
NORMALIZATION_PATTERN = re.compile(r"[^0-9A-Za-z가-힣]+")

# These KRX listings use marketing names that differ materially from the
# legal fund names in KOFIA's XLS.  Each link is an issuer product page/fact
# sheet that identifies the KRX code and legal fund name; the KOFIA standard
# code then identifies the reported fee row.  Do not add fuzzy aliases here.
CONFIRMED_ISSUER_ALIAS_EVIDENCE: dict[str, dict[str, str]] = {
    "0000D0": {
        "standard_code": "K55301EG5219",
        "source_url": (
            "https://investments.miraeasset.com/tigeretf/upload/etf/"
            "20250611092527004879.pdf"
        ),
    },
    "130680": {
        "standard_code": "KR5225287949",
        "source_url": (
            "https://investments.miraeasset.com/tigeretf/upload/etf/"
            "20250708095821000210.pdf"
        ),
    },
    "137610": {
        "standard_code": "KR5225987118",
        "source_url": "https://www.tigeretf.com/upload/etf/20250611092528004587.pdf",
    },
    "143850": {
        "standard_code": "KR5225A46688",
        "source_url": "https://www.tigeretf.com/upload/etf/20250708095821008574.pdf",
    },
    "152380": {
        "standard_code": "KR5105A81382",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETF34",
    },
    "219480": {
        "standard_code": "K55105B29847",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETF50",
    },
    "291890": {
        "standard_code": "K55105C52086",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETFA3",
    },
    "108450": {
        "standard_code": "KR5101897761",
        "source_url": "https://www.aceetf.co.kr/fund/KR5101897761",
    },
    "114460": {
        "standard_code": "KR5101148215",
        "source_url": "https://www.aceetf.co.kr/fund/KR5101148215",
    },
    "131890": {
        "standard_code": "KR5101299273",
        "source_url": "https://www.aceetf.co.kr/fund/KR5101299273",
    },
    "168580": {
        "standard_code": "KR5101AD5756",
        "source_url": "https://www.aceetf.co.kr/fund/KR5101AD5756",
    },
    "190620": {
        "standard_code": "KR5101AN3254",
        "source_url": "https://www.aceetf.co.kr/fund/KR5101AN3254",
    },
    "226380": {
        "standard_code": "K55101B54539",
        "source_url": "https://www.aceetf.co.kr/fund/K55101B54539",
    },
    "438080": {
        "standard_code": "K55101DU8887",
        "source_url": "https://www.aceetf.co.kr/fund/K55101DU8887",
    },
    "456880": {
        "standard_code": "K55101E19692",
        "source_url": "https://www.aceetf.co.kr/fund/K55101E19692",
    },
    "102780": {
        "standard_code": "KR5105834570",
        "source_url": "https://m.samsungfund.com/etf/product/view.do?id=2ETF14",
    },
    "102970": {
        "standard_code": "KR5105837847",
        "source_url": "https://m.samsungfund.com/etf/product/view.do?id=2ETF15",
    },
    "169950": {
        "standard_code": "KR5105AE5728",
        "source_url": "https://m.samsungfund.com/etf/product/view.do?id=2ETF38",
    },
    "185680": {
        "standard_code": "KR5105AL9630",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETF40",
    },
    "278540": {
        "standard_code": "K55105BW1235",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETF93",
    },
    "289040": {
        "standard_code": "K55105BZ5845",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETFA1",
    },
    "321410": {
        "standard_code": "K55105CK0701",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETFB7",
    },
    "359210": {
        "standard_code": "K55105B62905",
        "source_url": "https://m.samsungfund.com/etf/product/view.do?id=2ETFD2",
    },
    "363580": {
        "standard_code": "K55105D67108",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETFD5",
    },
    "441640": {
        "standard_code": "K55105DW2744",
        "source_url": "https://www.samsungfund.com/etf/product/view.do?id=2ETFH4",
    },
    "367770": {
        "standard_code": "K55223DB4890",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44A8",
    },
    "399580": {
        "standard_code": "K55223DK6670",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44C3",
    },
    "448630": {
        "standard_code": "K55223DY8589",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44E0",
    },
    "449580": {
        "standard_code": "K55223DZ2888",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44E1",
    },
    "417450": {
        "standard_code": "K55223DQ9652",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44C6",
    },
    "437370": {
        "standard_code": "K55223DV1611",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44D1",
    },
    "442320": {
        "standard_code": "K55223DX4944",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44D6",
    },
    "446700": {
        "standard_code": "K55223DY3945",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44D7",
    },
    "354240": {
        "standard_code": "K55223D48455",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44A4",
    },
    "361580": {
        "standard_code": "KR5223A66905",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44A5",
    },
    "401170": {
        "standard_code": "K55223DN5018",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44C2",
    },
    "465330": {
        "standard_code": "K55223E57140",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44F2",
    },
    "418670": {
        "standard_code": "K55301DQ2231",
        "source_url": "https://www.tigeretf.com/upload/etf/20250523021322000228.pdf",
    },
    "476690": {
        "standard_code": "K55301E88149",
        "source_url": "https://www.tigeretf.com/upload/etf/20250523022712005444.pdf",
    },
    "0013R0": {
        "standard_code": "K55223EH6161",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/44I1",
    },
    "114470": {
        "standard_code": "KR5206150033",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=114470",
    },
    "138530": {
        "standard_code": "KR5225A04026",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7138530001",
    },
    "269540": {
        "standard_code": "K55213BO8445",
        "source_url": "https://www.plusetf.co.kr/product/detail?n=006306",
    },
    "278530": {
        "standard_code": "K55105BW3843",
        "source_url": "https://m.samsungfund.com/etf/product/view.do?id=2ETF92",
    },
    "295040": {
        "standard_code": "K55210C54247",
        "source_url": "https://www.soletf.co.kr/ko/fund/etf/210734",
    },
    "494210": {
        "standard_code": "K55210EC9637",
        "source_url": "https://www.soletf.co.kr/ko/fund/etf/211064",
    },
    "495550": {
        "standard_code": "K55210EF9550",
        "source_url": "https://www.soletf.co.kr/ko/fund/etf/211073",
    },
    "138540": {
        "standard_code": "KR5225A04034",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?fundTypeCode=01000400&ksdFund=KR7138540000",
    },
    "182490": {
        "standard_code": "KR5301AK4675",
        "source_url": "https://www.tigeretf.com/upload/etf/20240704125954008412.pdf",
    },
    "195920": {
        "standard_code": "KR5301AR6046",
        "source_url": "https://www.tigeretf.com/upload/etf/20250611092529002223.pdf",
    },
    "276000": {
        "standard_code": "K55301BS2827",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7276000007",
    },
    "105010": {
        "standard_code": "KR5225844749",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7105010003",
    },
    "114820": {
        "standard_code": "KR5225151061",
        "source_url": "https://www.tigeretf.com/upload/etf/20250708095820005220.pdf",
    },
    "117690": {
        "standard_code": "KR5225874118",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7117690008",
    },
    "182480": {
        "standard_code": "KR5301AJ8059",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7182480004",
    },
    "203780": {
        "standard_code": "KR5301AT7943",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7203780002",
    },
    "237440": {
        "standard_code": "K55301BA0110",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7237440003",
    },
    "248270": {
        "standard_code": "K55301BE6980",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7248270001",
    },
    "275980": {
        "standard_code": "K55301BS2819",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7275980001",
    },
    "310960": {
        "standard_code": "K55301CG5203",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7310960000",
    },
    "310970": {
        "standard_code": "K55301CG5815",
        "source_url": "https://www.tigeretf.com/ko/product/search/detail/index.do?ksdFund=KR7310970009",
    },
    "069660": {
        "standard_code": "KR5206352894",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=069660",
    },
    "100910": {
        "standard_code": "KR5206773776",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=100910",
    },
    "104520": {
        "standard_code": "KR5206853859",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=104520",
    },
    "104530": {
        "standard_code": "KR5206853842",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=104530",
    },
    "122260": {
        "standard_code": "KR5206184115",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=122260",
    },
    "153270": {
        "standard_code": "KR5391A83228",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=153270",
    },
    "200250": {
        "standard_code": "KR5206AS8419",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=200250",
    },
    "294400": {
        "standard_code": "K55206C46472",
        "source_url": "https://www.kiwoometf.com/service/etf/KO02010200M?gcode=294400",
    },
    "315930": {
        "standard_code": "K55105CG9781",
        "source_url": "https://m.samsungfund.com/sheet/20211014/2ETFB5_20210930.pdf",
    },
    "315960": {
        "standard_code": "K55223CJ3036",
        "source_url": "https://www.riseetf.co.kr/prod/finderDetail/4494",
    },
    "328370": {
        "standard_code": "K55213CQ4342",
        "source_url": "https://www.plusetf.co.kr/upload/fund/PLUS_%EC%BD%94%EC%8A%A4%ED%94%BCTR_20260228.pdf",
    },
    "332500": {
        "standard_code": "K55101CT6711",
        "source_url": "https://www.aceetf.co.kr/fund/K55101CT6711",
    },
    "491220": {
        "standard_code": "K55213EE1753",
        "source_url": "https://www.plusetf.co.kr/upload/fund/PLUS_200TR_20260228.pdf",
    },
}

# These listings have no issuer document that states both the exact KRX code
# and the legal KOFIA fund name.  The mapping is therefore intentionally kept
# separate from issuer evidence: an exact-code market-data page and the KOFIA
# legal name/standard-code row must both be present.  It is not a fuzzy match.
CONFIRMED_SECONDARY_IDENTITY_EVIDENCE: dict[str, dict[str, str]] = {
    "0073X0": {
        "standard_code": "K55104EL0816",
        "source_url": "https://kr.investing.com/etfs/0073x0-seoul",
    },
    "140950": {
        "standard_code": "KR5207A24857",
        "source_url": "https://www.ktb.co.kr/calendar/calendar.jspx?cmd=day&date=20210730&hts=",
    },
    "152870": {
        "standard_code": "KR5207A82418",
        "source_url": "https://www.ktb.co.kr/calendar/calendar.jspx?cmd=day&date=20210730&hts=",
    },
    "159800": {
        "standard_code": "KR5216AB3979",
        "source_url": "https://kr.investing.com/etfs/dongbu-mighty-kospi-100",
    },
    "285690": {
        "standard_code": "K55104C03165",
        "source_url": "https://kr.investing.com/etfs/hi-focus-esg-leaders-150",
    },
    "332930": {
        "standard_code": "K55232CU2966",
        "source_url": "https://kr.investing.com/etfs/332930",
    },
}


def _decimal_string(value: object, *, field: str, fund_name: str) -> str | None:
    if value in {None, "", "-"}:
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"KOFIA {field} is invalid for {fund_name}") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"KOFIA {field} is invalid for {fund_name}")
    return format(parsed.normalize(), "f")


def _cell(row: list[Any], index: int) -> object:
    return row[index] if len(row) > index else None


def normalize_etf_name(name: str) -> str:
    """Normalize names only for an exact, auditable KOFIA-to-KRX ETF match."""

    normalized = unicodedata.normalize("NFKC", name).strip()
    positions = [
        normalized.find(brand) for brand in ETF_BRANDS if normalized.find(brand) >= 0
    ]
    if positions:
        normalized = normalized[min(positions) :]
    suffix = ETF_SUFFIX_PATTERN.search(normalized)
    if suffix:
        before_suffix = normalized[: suffix.start()]
        after_suffix = normalized[suffix.end() :]
        qualifiers = ""
        if "합성" in after_suffix and "합성" not in before_suffix:
            qualifiers += " 합성"
        if re.search(r"(?:^|[^A-Za-z])H(?:$|[^A-Za-z])", after_suffix):
            qualifiers += " H"
        normalized = before_suffix + qualifiers
    normalized = normalized.replace("TIMEFOLIO", "TIME")
    normalized = normalized.replace("TOTALRETURN", "TR")
    return NORMALIZATION_PATTERN.sub("", normalized).upper()


def _character_multiset_signature(name: str) -> str:
    """Make an order-independent signature for an exact set of name characters."""

    return "".join(sorted(normalize_etf_name(name)))


def load_kofia_fund_costs(path: Path, *, as_of: date) -> dict[str, Any]:
    """Load KOFIA fee rows without treating separate brokerage cost as TER."""

    try:
        workbook = xlrd.open_workbook(path)
    except (OSError, xlrd.XLRDError) as exc:
        raise ValueError(f"invalid KOFIA fund cost workbook: {path}") from exc
    if workbook.nsheets != 1:
        raise ValueError("KOFIA fund cost workbook must contain one worksheet")
    sheet = workbook.sheet_by_index(0)
    if sheet.nrows < 3 or sheet.ncols < 17:
        raise ValueError("KOFIA fund cost workbook has an unexpected layout")

    rows = []
    for row_index in range(2, sheet.nrows):
        values = sheet.row_values(row_index)
        fund_name = str(_cell(values, 1) or "").strip()
        if ETF_FUND_NAME_MARKER not in fund_name:
            continue
        standard_code = str(_cell(values, 16) or "").strip().upper()
        if not STANDARD_CODE_PATTERN.fullmatch(standard_code):
            raise ValueError(
                "KOFIA standard code is invalid for ETF row "
                f"{row_index + 1}: {fund_name}"
            )
        fee_total = _decimal_string(
            _cell(values, 9), field="stated_fee_total_percent", fund_name=fund_name
        )
        other_cost = _decimal_string(
            _cell(values, 11), field="other_cost_percent", fund_name=fund_name
        )
        ter = _decimal_string(
            _cell(values, 12), field="ter_percent", fund_name=fund_name
        )
        brokerage = _decimal_string(
            _cell(values, 15),
            field="brokerage_commission_percent",
            fund_name=fund_name,
        )
        if ter is None:
            raise ValueError(f"KOFIA TER is missing for ETF {fund_name}")
        reconciliation_difference = None
        if fee_total is not None and other_cost is not None:
            expected = Decimal(fee_total) + Decimal(other_cost)
            reconciliation_difference = abs(expected - Decimal(ter))
            if reconciliation_difference > Decimal("0.01"):
                raise ValueError(
                    "KOFIA TER is inconsistent with fee plus other cost for "
                    f"{fund_name}"
                )
        rows.append(
            {
                "asset_manager": str(_cell(values, 0) or "").strip(),
                "fund_name": fund_name,
                "normalized_etf_name": normalize_etf_name(fund_name),
                "fund_type": str(_cell(values, 3) or "").strip(),
                "inception_date": str(_cell(values, 4) or "").strip() or None,
                "stated_fee_total_percent": fee_total,
                "other_cost_percent": other_cost,
                "ter_percent": ter,
                "ter_reconciliation_difference_percent_points": (
                    format(reconciliation_difference.normalize(), "f")
                    if reconciliation_difference is not None
                    else None
                ),
                "brokerage_commission_percent": brokerage,
                "standard_code": standard_code,
                "source_row_number": row_index + 1,
            }
        )

    if not rows:
        raise ValueError("KOFIA fund cost workbook contains no ETF rows")
    duplicate_codes = {
        row["standard_code"]
        for row in rows
        if sum(item["standard_code"] == row["standard_code"] for item in rows) > 1
    }
    if duplicate_codes:
        raise ValueError(
            "KOFIA ETF rows contain duplicate standard codes: "
            + ", ".join(sorted(duplicate_codes))
        )
    return {
        "report_type": "kofia_fund_fee_cost_comparison",
        "algorithm_input": True,
        "source_url": KOFIA_FUND_COST_URL,
        "as_of": as_of.isoformat(),
        "source_file": path.as_posix(),
        "source_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count": len(rows),
        "cost_definition": {
            "ter_percent": "reported_stated_fee_total_plus_other_cost",
            "brokerage_commission_percent": "reported_separately_from_ter",
            "planning_cost_policy": (
                "use_ter_only_until_benchmark_convention_and_cost_overlap_are_verified"
            ),
        },
        "rows": rows,
    }


def match_kofia_costs_to_etfs(
    kofia_report: dict[str, Any],
    *,
    etf_products: list[dict[str, Any]],
    fsc_fund_join_report: dict[str, Any] | None = None,
    kis_stated_fee_by_code: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return exact matches and documented standard-code links only."""

    target_by_name: dict[str, list[str]] = {}
    for product in etf_products:
        code = product.get("isu_code")
        name = product.get("isu_name")
        if not isinstance(code, str) or not isinstance(name, str):
            raise ValueError("ETF products require isu_code and isu_name")
        target_by_name.setdefault(normalize_etf_name(name), []).append(code)
    rows_by_standard_code = {row["standard_code"]: row for row in kofia_report["rows"]}
    matches: dict[str, dict[str, Any]] = {}
    for isu_code, evidence in CONFIRMED_ISSUER_ALIAS_EVIDENCE.items():
        row = rows_by_standard_code.get(evidence["standard_code"])
        if row is not None:
            matches[isu_code] = {
                **row,
                "match_method": "confirmed_issuer_alias_standard_code",
                "issuer_identity_source_url": evidence["source_url"],
                "identity_evidence_level": "issuer_code_and_legal_name",
            }
    for isu_code, evidence in CONFIRMED_SECONDARY_IDENTITY_EVIDENCE.items():
        row = rows_by_standard_code.get(evidence["standard_code"])
        if row is not None:
            matches[isu_code] = {
                **row,
                "match_method": "confirmed_secondary_identity_standard_code",
                "identity_source_url": evidence["source_url"],
                "identity_evidence_level": "secondary_exact_code_and_legal_name",
            }
    if fsc_fund_join_report is not None:
        fsc_products = fsc_fund_join_report.get("products")
        if not isinstance(fsc_products, list):
            raise ValueError("FSC fund join report must contain products")
        for fsc_product in fsc_products:
            if not isinstance(fsc_product, dict):
                continue
            isu_code = fsc_product.get("isu_code")
            fund = fsc_product.get("fund")
            if (
                not isinstance(isu_code, str)
                or isu_code in matches
                or fsc_product.get("match_status") != "matched_exact_normalized_name"
                or not isinstance(fund, dict)
            ):
                continue
            standard_code = fund.get("fund_standard_code")
            if not isinstance(standard_code, str):
                continue
            row = rows_by_standard_code.get(standard_code)
            if row is not None:
                matches[isu_code] = {
                    **row,
                    "match_method": "fsc_exact_normalized_name_to_standard_code",
                    "fsc_fund_standard_code": standard_code,
                    "fsc_match_status": fsc_product["match_status"],
                }
    for row in kofia_report["rows"]:
        candidates = target_by_name.get(row["normalized_etf_name"], [])
        if len(candidates) == 1 and candidates[0] not in matches:
            matches[candidates[0]] = {
                **row,
                "match_method": "unique_normalized_etf_name",
            }
    if kis_stated_fee_by_code is not None:
        rows_by_signature: dict[str, list[dict[str, Any]]] = {}
        for row in kofia_report["rows"]:
            rows_by_signature.setdefault(
                _character_multiset_signature(row["fund_name"]), []
            ).append(row)
        for product in etf_products:
            isu_code = product["isu_code"]
            if isu_code in matches:
                continue
            kis_fee = kis_stated_fee_by_code.get(isu_code)
            if kis_fee is None:
                continue
            candidates = rows_by_signature.get(
                _character_multiset_signature(product["isu_name"]), []
            )
            if len(candidates) != 1:
                continue
            row = candidates[0]
            stated_fee = row.get("stated_fee_total_percent")
            if stated_fee is None or Decimal(kis_fee) != Decimal(stated_fee):
                continue
            matches[isu_code] = {
                **row,
                "match_method": "unique_order_independent_name_and_kis_fee",
                "kis_stated_fee_percent": kis_fee,
            }
    return matches


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Normalize a KOFIA fund fee and cost comparison XLS export."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/cache/kofia"))
    args = parser.parse_args()
    report = load_kofia_fund_costs(args.input, as_of=args.as_of)
    output_path = args.output / f"fund_fee_cost_comparison_{args.as_of}.json"
    _write_json(output_path, report)
    print(
        json.dumps(
            {
                "as_of": report["as_of"],
                "row_count": report["row_count"],
                "output_path": output_path.as_posix(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
