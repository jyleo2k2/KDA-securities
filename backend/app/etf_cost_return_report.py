import argparse
import json
from bisect import bisect_left
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backend.app.ingestion.fsc_fund_client import FSC_FUND_PRODUCT_ENDPOINT
from backend.app.ingestion.kis_pension_eligibility import (
    load_kis_retirement_etfs,
)
from backend.app.ingestion.kofia_fund_costs import match_kofia_costs_to_etfs
from backend.app.ingestion.krx_client import parse_krx_etf_payload

ACCOUNT_TYPES = ("dc", "irp", "pension_savings")
PERIODS = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "1y": 252,
    "2y": 504,
    "3y": 756,
    "5y": 1260,
}
PERCENT_QUANTUM = Decimal("0.0001")
KIND_SOURCE_URL = (
    "https://kind.krx.co.kr/disclosure/disclosurebystocktype.do"
    "?method=searchDisclosureByStockTypeEtf"
)
KRX_SOURCE_URL = "https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd"
KIS_RETIREMENT_NOTICE_URL = (
    "https://www.truefriend.com/pension/nwEtcinfo/Notice.jsp"
    "?cmd=A_NW_33030View&num=47065&subFlag=1"
)


def _latest(root: Path, pattern: str) -> Path:
    candidates = sorted(root.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"no files matching {pattern} under {root}")
    return candidates[-1]


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _decimal(value: object, *, positive: bool = False) -> Decimal | None:
    if value in {None, "", "-"}:
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid numeric value: {value}") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        return None
    return parsed


def _percent(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _sample_std(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum(((value - mean) ** 2 for value in values), Decimal("0")) / Decimal(
        len(values) - 1
    )
    return variance.sqrt()


def _load_krx_histories(
    raw_root: Path, eligible_codes: set[str]
) -> tuple[dict[str, list[dict[str, Any]]], date]:
    histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    latest_date: date | None = None
    files = sorted((raw_root / "etf_bydd_trd").glob("*/*/*.json"))
    if not files:
        raise FileNotFoundError(f"no KRX ETF files under {raw_root}")
    for path in files:
        base_date = date.fromisoformat(
            f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:8]}"
        )
        response = parse_krx_etf_payload(
            json.loads(path.read_bytes()), base_date=base_date
        )
        for row in response.records:
            code = row["ISU_CD"]
            if code not in eligible_codes:
                continue
            close = _decimal(row["TDD_CLSPRC"], positive=True)
            if close is None:
                continue
            histories[code].append(
                {
                    "date": base_date,
                    "close": close,
                    "nav": _decimal(row["NAV"], positive=True),
                    "volume": _decimal(row["ACC_TRDVOL"]),
                    "trading_value": _decimal(row["ACC_TRDVAL"]),
                    "net_assets": _decimal(
                        row["INVSTASST_NETASST_TOTAMT"], positive=True
                    ),
                    "benchmark_close": _decimal(row["OBJ_STKPRC_IDX"], positive=True),
                    "benchmark_name": row["IDX_IND_NM"],
                }
            )
            latest_date = max(latest_date or base_date, base_date)
    if latest_date is None:
        raise ValueError("KRX history contains no eligible ETF observations")
    return histories, latest_date


def _events_by_code(
    distribution_report: dict[str, Any],
    corporate_event_report: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    events = (
        corporate_event_report.get("events")
        if corporate_event_report is not None
        else distribution_report.get("events")
    )
    if not isinstance(events, list):
        raise ValueError("distribution event source must contain events")
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("distribution event must be an object")
        if (
            corporate_event_report is not None
            and event.get("event_type") != "cash_distribution"
        ):
            continue
        code = event.get("isu_code")
        if not isinstance(code, str):
            raise ValueError("distribution event has no ETF code")
        record_date = date.fromisoformat(str(event["record_date"]))
        application_date = date.fromisoformat(
            str(event.get("effective_date") or event["record_date"])
        )
        amount_field = (
            "cash_per_share_krw"
            if corporate_event_report is not None
            else "distribution_per_share_krw"
        )
        result[code].append(
            {
                **event,
                "record_date": record_date,
                "application_date": application_date,
                "amount": Decimal(str(event[amount_field])),
                "timing_basis": event.get("timing_basis", "record_date_fallback"),
            }
        )
    for code in result:
        result[code].sort(key=lambda item: item["application_date"])
    return result


def _period_result(
    observations: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    periods: int,
    coverage_start: date,
    source_complete: bool,
) -> dict[str, Any]:
    if len(observations) <= periods:
        return {
            "status": "insufficient_observations",
            "required_observations": periods + 1,
            "available_observations": len(observations),
        }
    window = observations[-periods - 1 :]
    start = window[0]
    end = window[-1]
    dates = [item["date"] for item in window]
    relevant_events = [
        event
        for event in events
        if start["date"] < event["application_date"] <= end["date"]
    ]
    distributions: dict[date, Decimal] = defaultdict(Decimal)
    for event in relevant_events:
        index = bisect_left(dates, event["application_date"])
        if index < len(dates):
            distributions[dates[index]] += event["amount"]

    total_factor = Decimal("1")
    for previous, current in zip(window, window[1:], strict=False):
        cash = distributions.get(current["date"], Decimal("0"))
        total_factor *= (current["close"] + cash) / previous["close"]

    price_return = end["close"] / start["close"] - Decimal("1")
    nav_return = None
    if start["nav"] is not None and end["nav"] is not None:
        nav_return = end["nav"] / start["nav"] - Decimal("1")
    benchmark_return = None
    if start["benchmark_close"] is not None and end["benchmark_close"] is not None:
        benchmark_return = end["benchmark_close"] / start["benchmark_close"] - Decimal(
            "1"
        )
    if start["date"] < coverage_start:
        status = "distribution_coverage_insufficient"
        total_return = None
    elif not source_complete:
        status = "kind_source_failures"
        total_return = None
    else:
        status = "complete"
        total_return = total_factor - Decimal("1")
    return {
        "status": status,
        "start_date": start["date"].isoformat(),
        "end_date": end["date"].isoformat(),
        "observation_count": len(window),
        "price_return_percent": _percent(price_return * Decimal("100")),
        "nav_return_percent": _percent(
            nav_return * Decimal("100") if nav_return is not None else None
        ),
        "benchmark_return_percent": _percent(
            benchmark_return * Decimal("100") if benchmark_return is not None else None
        ),
        "distribution_reinvested_total_return_percent": _percent(
            total_return * Decimal("100") if total_return is not None else None
        ),
        "distribution_event_count": len(relevant_events),
        "exact_ex_date_event_count": sum(
            event["timing_basis"] == "exact_kind_ex_distribution_date"
            for event in relevant_events
        ),
        "record_date_fallback_event_count": sum(
            event["timing_basis"] == "record_date_fallback" for event in relevant_events
        ),
        "distribution_per_share_sum_krw": format(
            sum(
                (event["amount"] for event in relevant_events),
                Decimal("0"),
            ),
            "f",
        ),
    }


def _implementation_metrics(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    window = observations[-253:]
    trading_values = [
        item["trading_value"] for item in window if item["trading_value"] is not None
    ]
    volumes = [item["volume"] for item in window if item["volume"] is not None]
    net_assets = [
        item["net_assets"] for item in window if item["net_assets"] is not None
    ]
    nav_divergences = [
        (item["close"] / item["nav"] - Decimal("1")).copy_abs() * Decimal("100")
        for item in window
        if item["nav"] is not None
    ]
    active_returns = []
    for previous, current in zip(window, window[1:], strict=False):
        if any(
            value is None
            for value in (
                previous["nav"],
                current["nav"],
                previous["benchmark_close"],
                current["benchmark_close"],
            )
        ):
            continue
        nav_return = current["nav"] / previous["nav"] - Decimal("1")
        benchmark_return = current["benchmark_close"] / previous[
            "benchmark_close"
        ] - Decimal("1")
        active_returns.append(nav_return - benchmark_return)
    active_std = _sample_std(active_returns)
    tracking_error = (
        active_std * Decimal("252").sqrt() * Decimal("100")
        if active_std is not None and len(active_returns) >= 20
        else None
    )
    latest = observations[-1]
    return {
        "window_start": window[0]["date"].isoformat(),
        "window_end": window[-1]["date"].isoformat(),
        "observation_count": len(window),
        "latest_close_krw": format(latest["close"], "f"),
        "latest_nav_krw": (
            format(latest["nav"], "f") if latest["nav"] is not None else None
        ),
        "latest_net_assets_krw": (
            int(latest["net_assets"]) if latest["net_assets"] is not None else None
        ),
        "latest_trading_volume": (
            int(latest["volume"]) if latest["volume"] is not None else None
        ),
        "latest_trading_value_krw": (
            int(latest["trading_value"])
            if latest["trading_value"] is not None
            else None
        ),
        "median_daily_trading_volume": (int(_median(volumes)) if volumes else None),
        "median_daily_trading_value_krw": (
            int(_median(trading_values)) if trading_values else None
        ),
        "median_net_assets_krw": (int(_median(net_assets)) if net_assets else None),
        "median_abs_premium_discount_percent": _percent(_median(nav_divergences)),
        "tracking_error_proxy_percent": _percent(tracking_error),
        "benchmark_name": latest["benchmark_name"],
    }


def build_etf_cost_return_report(
    *,
    eligibility_report: dict[str, Any],
    distribution_report: dict[str, Any],
    kis_retirement_products: list[dict[str, object]],
    kis_snapshot: dict[str, Any],
    krx_raw_root: Path,
    source_files: dict[str, str],
    as_of: date,
    corporate_event_report: dict[str, Any] | None = None,
    kofia_cost_report: dict[str, Any] | None = None,
    fsc_fund_join_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    products = eligibility_report.get("products")
    if not isinstance(products, list):
        raise ValueError("eligibility report must contain products")
    eligible_codes = {
        product["isu_code"] for product in products if isinstance(product, dict)
    }
    histories, market_as_of = _load_krx_histories(krx_raw_root, eligible_codes)
    events_by_code = _events_by_code(distribution_report, corporate_event_report)
    coverage_start = date.fromisoformat(distribution_report["coverage_start"])
    coverage_end = date.fromisoformat(distribution_report["coverage_end"])
    source_complete = distribution_report.get("failure_count") == 0
    kis_by_code = {
        str(product["isu_code"]): product for product in kis_retirement_products
    }
    kis_stated_fee_by_code = {
        code: str(product["total_expense_ratio_percent"])
        for code, product in kis_by_code.items()
        if product.get("total_expense_ratio_percent") is not None
    }
    snapshot_products = kis_snapshot.get("products")
    if not isinstance(snapshot_products, list):
        raise ValueError("KIS snapshot must contain products")
    snapshot_by_code = {
        product["isu_code"]: product
        for product in snapshot_products
        if isinstance(product, dict) and isinstance(product.get("isu_code"), str)
    }
    kofia_cost_by_code = (
        match_kofia_costs_to_etfs(
            kofia_cost_report,
            etf_products=products,
            fsc_fund_join_report=fsc_fund_join_report,
            kis_stated_fee_by_code=kis_stated_fee_by_code,
        )
        if kofia_cost_report is not None
        else {}
    )

    output_products = []
    missing_history_codes = []
    for product in products:
        code = product["isu_code"]
        observations = histories.get(code, [])
        if not observations:
            missing_history_codes.append(code)
            continue
        events = events_by_code.get(code, [])
        kis_product = kis_by_code.get(code)
        snapshot = snapshot_by_code.get(code, {})
        price = snapshot.get("price") if isinstance(snapshot, dict) else None
        if not isinstance(price, dict):
            price = {}
        fee = (
            kis_product.get("total_expense_ratio_percent")
            if kis_product is not None
            else None
        )
        kofia_cost = kofia_cost_by_code.get(code)
        output_products.append(
            {
                "isu_code": code,
                "isu_name": product["isu_name"],
                "classification": product["classification"],
                "account_eligibility": product["account_eligibility"],
                "history_start": observations[0]["date"].isoformat(),
                "history_end": observations[-1]["date"].isoformat(),
                "observation_count": len(observations),
                "cost": {
                    "kis_total_expense_ratio_percent": fee,
                    "kis_cost_as_of": eligibility_report.get("eligibility_as_of"),
                    "kofia_reported_ter_percent": (
                        kofia_cost.get("ter_percent") if kofia_cost else None
                    ),
                    "kofia_reported_stated_fee_total_percent": (
                        kofia_cost.get("stated_fee_total_percent")
                        if kofia_cost
                        else None
                    ),
                    "kofia_reported_other_cost_percent": (
                        kofia_cost.get("other_cost_percent") if kofia_cost else None
                    ),
                    "kofia_reported_brokerage_commission_percent": (
                        kofia_cost.get("brokerage_commission_percent")
                        if kofia_cost
                        else None
                    ),
                    "kofia_standard_code": (
                        kofia_cost.get("standard_code") if kofia_cost else None
                    ),
                    "kofia_match_method": (
                        kofia_cost.get("match_method") if kofia_cost else None
                    ),
                    "issuer_identity_source_url": (
                        kofia_cost.get("issuer_identity_source_url")
                        if kofia_cost
                        else None
                    ),
                    "fsc_fund_standard_code": (
                        kofia_cost.get("fsc_fund_standard_code")
                        if kofia_cost
                        else None
                    ),
                    "fsc_match_status": (
                        kofia_cost.get("fsc_match_status") if kofia_cost else None
                    ),
                    "fsc_fund_join_as_of": (
                        fsc_fund_join_report.get("snapshot_date")
                        if fsc_fund_join_report is not None and kofia_cost
                        else None
                    ),
                    "kis_fee_cross_check_percent": (
                        kofia_cost.get("kis_stated_fee_percent")
                        if kofia_cost
                        else None
                    ),
                    "kofia_cost_as_of": (
                        kofia_cost_report.get("as_of")
                        if kofia_cost_report is not None and kofia_cost
                        else None
                    ),
                    "effective_total_cost_percent": (
                        kofia_cost.get("ter_percent") if kofia_cost else None
                    ),
                    "effective_total_cost_status": (
                        "kofia_reported_ter"
                        if kofia_cost
                        else "issuer_or_fund_disclosure_required"
                    ),
                    "important_interpretation": (
                        "KRX market price and NAV returns already reflect ongoing "
                        "fund operating expenses; do not subtract the stated fee "
                        "again from historical returns. KOFIA brokerage commission "
                        "is preserved separately and is not added to TER."
                    ),
                },
                "distribution": {
                    "kind_event_count": len(events),
                    "exact_ex_date_event_count": sum(
                        event["timing_basis"] == "exact_kind_ex_distribution_date"
                        for event in events
                    ),
                    "record_date_fallback_event_count": sum(
                        event["timing_basis"] == "record_date_fallback"
                        for event in events
                    ),
                    "kind_event_coverage_start": coverage_start.isoformat(),
                    "kind_event_coverage_end": coverage_end.isoformat(),
                    "monthly_distribution_target": (
                        kis_product.get("monthly_distribution_target")
                        if kis_product is not None
                        else None
                    ),
                    "kis_distribution_cycle_code": price.get("etf_dvdn_cycl"),
                    "calculation_assumption": (
                        "Each cash distribution is reinvested at the first KRX "
                        "closing price on or after the exact KIND ex-distribution "
                        "date when linked; otherwise the record date is used as "
                        "an explicit fallback."
                    ),
                },
                "returns": {
                    period: _period_result(
                        observations,
                        events,
                        periods=periods,
                        coverage_start=coverage_start,
                        source_complete=source_complete,
                    )
                    for period, periods in PERIODS.items()
                },
                "implementation_metrics": {
                    **_implementation_metrics(observations),
                    "kis_current_tracking_error_percent": price.get("trc_errt"),
                },
                "kis_provider_reported_returns_percent": (
                    kis_product.get("provider_reported_returns_percent")
                    if kis_product is not None
                    else None
                ),
                "sources": [
                    {
                        "label": "KRX ETF 일별매매정보",
                        "url": KRX_SOURCE_URL,
                        "as_of": market_as_of.isoformat(),
                    },
                    {
                        "label": "KIND ETF 이익금분배 공시",
                        "url": KIND_SOURCE_URL,
                        "coverage_start": coverage_start.isoformat(),
                        "coverage_end": coverage_end.isoformat(),
                    },
                    {
                        "label": "한국투자증권 퇴직연금 ETF 리스트",
                        "url": KIS_RETIREMENT_NOTICE_URL,
                        "as_of": eligibility_report.get("eligibility_as_of"),
                    },
                    *(
                        [
                            {
                                "label": "금융투자협회 펀드별 보수비용 비교",
                                "url": kofia_cost_report["source_url"],
                                "as_of": kofia_cost_report["as_of"],
                                "standard_code": kofia_cost["standard_code"],
                            }
                        ]
                        if kofia_cost is not None and kofia_cost_report is not None
                        else []
                    ),
                    *(
                        [
                            {
                                "label": "금융위원회 펀드기본정보 표준코드",
                                "url": FSC_FUND_PRODUCT_ENDPOINT,
                                "as_of": fsc_fund_join_report["snapshot_date"],
                                "standard_code": kofia_cost["fsc_fund_standard_code"],
                            }
                        ]
                        if kofia_cost is not None
                        and fsc_fund_join_report is not None
                        and kofia_cost.get("fsc_fund_standard_code")
                        else []
                    ),
                    *(
                        [
                            {
                                "label": "운용사 ETF 코드·정식명칭 확인",
                                "url": kofia_cost["issuer_identity_source_url"],
                            }
                        ]
                        if kofia_cost is not None
                        and kofia_cost.get("issuer_identity_source_url")
                        else []
                    ),
                ],
            }
        )

    return {
        "report_type": "pension_eligible_etf_cost_return_master",
        "algorithm_input": True,
        "as_of": as_of.isoformat(),
        "market_data_as_of": market_as_of.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "engine_name": "pension_etf_cost_return_evidence",
        "engine_version": "2026-07-22.1",
        "product_scope": "eligible_in_at_least_one_pension_account",
        "source_files": source_files,
        "eligible_source_product_count": len(products),
        "product_count": len(output_products),
        "missing_history_count": len(missing_history_codes),
        "missing_history_codes": missing_history_codes,
        "distribution_source_complete": source_complete,
        "period_definitions_trading_days": PERIODS,
        "limitations": [
            "Historical returns are evidence, not future return forecasts.",
            "Total return timing uses exact KIND ex-distribution dates where "
            "available; remaining events explicitly use record-date fallback.",
            "KOFIA TER is used as the verified recurring fund-cost input only "
            "when a unique normalized ETF-name match is available.",
            "KOFIA brokerage commission is reported separately from TER and is "
            "not added without a benchmark-convention and cost-overlap check.",
            "Brokerage costs, bid-ask spread, taxes, and account-specific order "
            "availability are not included in return calculations.",
            "DC and IRP eligibility is provider-specific; account exports must be "
            "used instead of the cross-account union for portfolio construction.",
        ],
        "products": output_products,
    }


def _account_report(report: dict[str, Any], account: str) -> dict[str, Any]:
    products = []
    for product in report["products"]:
        eligibility = product["account_eligibility"].get(account)
        if eligibility is None:
            continue
        products.append(
            {
                **{
                    key: value
                    for key, value in product.items()
                    if key != "account_eligibility"
                },
                "account_eligibility": eligibility,
            }
        )
    return {
        **{key: value for key, value in report.items() if key != "products"},
        "report_type": "pension_account_etf_cost_return_master",
        "product_scope": "account_eligible_only",
        "account_type": account,
        "product_count": len(products),
        "products": products,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build cost and distribution-adjusted returns for eligible ETFs."
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--eligibility", type=Path)
    parser.add_argument("--distributions", type=Path)
    parser.add_argument("--corporate-events", type=Path)
    parser.add_argument("--kis-retirement-list", type=Path)
    parser.add_argument("--kis-snapshot", type=Path)
    parser.add_argument("--kofia-fund-costs", type=Path)
    parser.add_argument("--fsc-fund-join", type=Path)
    parser.add_argument("--krx-raw-root", type=Path, default=Path("data/raw/krx"))
    parser.add_argument("--output", type=Path, default=Path("data/cache/returns"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    eligibility_path = args.eligibility or _latest(
        Path("data/cache/classification"),
        "pension_account_eligible_etfs_*.json",
    )
    distribution_path = args.distributions or _latest(
        Path("data/cache/kind"), "etf_distributions_*.json"
    )
    corporate_event_path = args.corporate_events
    if corporate_event_path is None:
        candidates = sorted(
            Path("data/cache/events").glob("etf_corporate_events_*.json")
        )
        corporate_event_path = candidates[-1] if candidates else None
    kis_retirement_path = args.kis_retirement_list or _latest(
        Path("data/raw/kis"), "retirement_etf_list_*.xlsx"
    )
    kis_snapshot_path = args.kis_snapshot or _latest(
        Path("data/cache/kis"), "etf_snapshot_*.json"
    )
    kofia_cost_path = args.kofia_fund_costs
    if kofia_cost_path is None:
        candidates = sorted(
            Path("data/cache/kofia").glob("fund_fee_cost_comparison_*.json")
        )
        kofia_cost_path = candidates[-1] if candidates else None
    fsc_fund_join_path = args.fsc_fund_join
    if fsc_fund_join_path is None:
        candidates = sorted(Path("data/cache/fsc").glob("krx_etf_fund_join_*.json"))
        fsc_fund_join_path = candidates[-1] if candidates else None
    source_files = {
        "eligibility": eligibility_path.as_posix(),
        "kind_distributions": distribution_path.as_posix(),
        "kis_retirement_etf_list": kis_retirement_path.as_posix(),
        "kis_snapshot": kis_snapshot_path.as_posix(),
        "krx_raw_root": args.krx_raw_root.as_posix(),
    }
    if corporate_event_path is not None:
        source_files["corporate_events"] = corporate_event_path.as_posix()
    if kofia_cost_path is not None:
        source_files["kofia_fund_cost_comparison"] = kofia_cost_path.as_posix()
    if fsc_fund_join_path is not None:
        source_files["fsc_fund_join"] = fsc_fund_join_path.as_posix()
    report = build_etf_cost_return_report(
        eligibility_report=_load(eligibility_path),
        distribution_report=_load(distribution_path),
        kis_retirement_products=load_kis_retirement_etfs(kis_retirement_path),
        kis_snapshot=_load(kis_snapshot_path),
        krx_raw_root=args.krx_raw_root,
        source_files=source_files,
        as_of=args.as_of,
        corporate_event_report=(
            _load(corporate_event_path) if corporate_event_path is not None else None
        ),
        kofia_cost_report=(
            _load(kofia_cost_path) if kofia_cost_path is not None else None
        ),
        fsc_fund_join_report=(
            _load(fsc_fund_join_path) if fsc_fund_join_path is not None else None
        ),
    )
    union_path = args.output / (f"pension_etf_cost_return_master_{args.as_of}.json")
    _write_json(union_path, report)
    account_paths = {}
    for account in ACCOUNT_TYPES:
        path = args.output / f"{account}_etf_cost_return_{args.as_of}.json"
        _write_json(path, _account_report(report, account))
        account_paths[account] = path.as_posix()
    print(
        json.dumps(
            {
                "as_of": report["as_of"],
                "market_data_as_of": report["market_data_as_of"],
                "product_count": report["product_count"],
                "missing_history_count": report["missing_history_count"],
                "distribution_source_complete": report["distribution_source_complete"],
                "output_path": union_path.as_posix(),
                "account_output_paths": account_paths,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
