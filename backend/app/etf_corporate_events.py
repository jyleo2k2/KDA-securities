import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

MAX_EX_DATE_LINK_DAYS = 7


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _latest(root: Path, pattern: str) -> Path:
    candidates = sorted(root.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"no files matching {pattern} under {root}")
    return candidates[-1]


def _latest_adjusted_price_root(root: Path) -> Path:
    candidates = sorted(path for path in root.iterdir() if path.is_dir())
    if not candidates:
        raise FileNotFoundError(f"no adjusted-price date directories under {root}")
    return candidates[-1]


def _widest_ex_date_report(root: Path) -> Path | None:
    candidates = sorted(root.glob("etf_distribution_ex_dates_*.json"))
    if not candidates:
        return None

    def coverage(path: Path) -> tuple[int, str]:
        payload = _load(path)
        start = date.fromisoformat(str(payload["coverage_start"]))
        end = date.fromisoformat(str(payload["coverage_end"]))
        return (end - start).days, str(payload.get("generated_at") or "")

    return max(candidates, key=coverage)


def _events(payload: dict[str, Any], *, label: str) -> list[dict[str, Any]]:
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError(f"{label} report must contain events")
    if not all(isinstance(event, dict) for event in events):
        raise ValueError(f"{label} events must be objects")
    return events


def _decimal_text(value: object) -> str | None:
    if value in {None, "", "-"}:
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return format(parsed, "f")


def _name_key(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def _iso_date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:]}").isoformat()
    return date.fromisoformat(text).isoformat()


def _kis_dividend_references(
    payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if payload is None:
        return []
    rows = payload.get("events", payload.get("output1", []))
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("KIS dividend schedule must contain object rows")
    normalized = []
    for row in rows:
        code = row.get("isu_code", row.get("sht_cd"))
        record_date = _iso_date(row.get("record_date"))
        if not isinstance(code, str) or not code or record_date is None:
            raise ValueError("KIS dividend schedule row has no code or record date")
        normalized.append(
            {
                "source_type": "kis_ksd_dividend_schedule",
                "isu_code": code,
                "record_date": record_date,
                "payment_date": _iso_date(
                    row.get("payment_date", row.get("divi_pay_dt"))
                ),
                "cash_per_share_krw": _decimal_text(
                    row.get("cash_per_share_krw", row.get("per_sto_divi_amt"))
                ),
                "dividend_kind": row.get("dividend_kind", row.get("divi_kind")),
                "endpoint": "/uapi/domestic-stock/v1/ksdinfo/dividend",
                "tr_id": "HHKDB669102C0",
            }
        )
    return normalized


def _fsc_dividend_references(
    payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if payload is None:
        return []
    rows = payload.get("records")
    if rows is None:
        response = payload.get("response", payload)
        body = response.get("body", {}) if isinstance(response, dict) else {}
        items = body.get("items", []) if isinstance(body, dict) else []
        rows = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("FSC stock-dividend report must contain object rows")
    normalized = []
    for row in rows:
        isin = row.get("isin", row.get("isinCd"))
        record_date = _iso_date(row.get("record_date", row.get("dvdnBasDt")))
        if not isinstance(isin, str) or not isin or record_date is None:
            raise ValueError("FSC stock-dividend row has no ISIN or record date")
        normalized.append(
            {
                "source_type": "fsc_stock_dividend_information",
                "isin": isin.upper(),
                "record_date": record_date,
                "payment_date": _iso_date(
                    row.get("payment_date", row.get("cashDvdnPayDt"))
                ),
                "cash_per_share_krw": _decimal_text(
                    row.get("cash_per_share_krw", row.get("stckGenrDvdnAmt"))
                ),
                "base_date": _iso_date(row.get("base_date", row.get("basDt"))),
                "issuer_name": row.get("issuer_name", row.get("stckIssuCmpyNm")),
                "endpoint": (
                    "https://apis.data.go.kr/1160100/"
                    "GetStocDiviInfoService_V2/getDiviInfo_V2"
                ),
            }
        )
    return normalized


def _reference_conflicts(event: dict[str, Any], reference: dict[str, Any]) -> list[str]:
    conflicts = []
    for field in ("cash_per_share_krw", "payment_date"):
        current = event.get(field)
        other = reference.get(field)
        if current is None or other is None:
            continue
        values_match = current == other
        if field == "cash_per_share_krw":
            values_match = Decimal(str(current)) == Decimal(str(other))
        if not values_match:
            conflicts.append(field)
    return conflicts


def _cross_validate_cash_events(
    cash_events: list[dict[str, Any]],
    *,
    kis_references: list[dict[str, Any]],
    fsc_references: list[dict[str, Any]],
) -> tuple[dict[str, int], set[tuple[str, str]]]:
    kis_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    fsc_by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for reference in kis_references:
        kis_by_key[(reference["isu_code"], reference["record_date"])].append(reference)
    for reference in fsc_references:
        fsc_by_key[(reference["isin"], reference["record_date"])].append(reference)

    matched_kis_keys: set[tuple[str, str]] = set()
    matched_source_count = 0
    conflict_event_count = 0
    for event in cash_events:
        references = list(
            kis_by_key.get((str(event["isu_code"]), str(event["record_date"])), [])
        )
        isin = event.get("isin")
        if isinstance(isin, str) and isin:
            references.extend(
                fsc_by_key.get((isin.upper(), str(event["record_date"])), [])
            )
        matched_sources = []
        conflicts = []
        for reference in references:
            source_type = str(reference["source_type"])
            matched_sources.append(source_type)
            mismatched_fields = _reference_conflicts(event, reference)
            if mismatched_fields:
                conflicts.append(
                    {
                        "source_type": source_type,
                        "fields": mismatched_fields,
                    }
                )
            event["source_evidence"].append(reference)
            if source_type == "kis_ksd_dividend_schedule":
                matched_kis_keys.add(
                    (str(reference["isu_code"]), str(reference["record_date"]))
                )
        if conflicts:
            validation_status = "source_conflict_review_required"
            conflict_event_count += 1
        elif matched_sources:
            validation_status = "corroborated_by_secondary_source"
        else:
            validation_status = "primary_source_only"
        matched_source_count += len(set(matched_sources))
        event["cross_validation"] = {
            "status": validation_status,
            "matched_sources": sorted(set(matched_sources)),
            "conflicts": conflicts,
            "calculation_authority": "krx_kind_distribution_disclosure",
        }
    return (
        {
            "matched_secondary_source_count": matched_source_count,
            "source_conflict_event_count": conflict_event_count,
        },
        matched_kis_keys,
    )


def _scheduled_kis_dividend_events(
    references: list[dict[str, Any]],
    *,
    matched_keys: set[tuple[str, str]],
    eligible_codes: set[str],
    as_of: date,
) -> list[dict[str, Any]]:
    output = []
    for reference in references:
        key = (reference["isu_code"], reference["record_date"])
        if (
            key in matched_keys
            or reference["isu_code"] not in eligible_codes
            or date.fromisoformat(reference["record_date"]) < as_of
        ):
            continue
        output.append(
            {
                "isu_code": reference["isu_code"],
                "isu_name": None,
                "isin": None,
                "event_type": "scheduled_cash_distribution",
                "effective_date": reference["record_date"],
                "record_date": reference["record_date"],
                "payment_date": reference["payment_date"],
                "cash_per_share_krw": reference["cash_per_share_krw"],
                "ratio": None,
                "timing_basis": "record_date_schedule_not_ex_date",
                "confidence": "reference_only",
                "status": "excluded_from_historical_total_return",
                "source_evidence": [reference],
            }
        )
    return output


def _cash_distribution_events(
    distribution_report: dict[str, Any],
    ex_date_report: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], set[tuple[str, str]]]:
    ex_dates_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ex_dates_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if ex_date_report is not None:
        for event in _events(ex_date_report, label="KIND ex-date"):
            code = event.get("isu_code")
            effective_date = event.get("effective_date")
            if isinstance(code, str) and isinstance(effective_date, str):
                ex_dates_by_code[code].append(event)
                ex_dates_by_name[_name_key(event.get("isu_name"))].append(event)
    for code in ex_dates_by_code:
        ex_dates_by_code[code].sort(key=lambda event: event["effective_date"])
    for name in ex_dates_by_name:
        ex_dates_by_name[name].sort(key=lambda event: event["effective_date"])

    used_ex_dates: set[tuple[str, str]] = set()
    output = []
    distributions = sorted(
        _events(distribution_report, label="KIND distribution"),
        key=lambda event: (str(event["record_date"]), str(event["isu_code"])),
    )
    for event in distributions:
        code = str(event["isu_code"])
        record_date = date.fromisoformat(str(event["record_date"]))
        candidate_events: dict[str, dict[str, Any]] = {}
        for ex_event in [
            *ex_dates_by_code.get(code, []),
            *ex_dates_by_name.get(_name_key(event.get("isu_name")), []),
        ]:
            candidate_events[str(ex_event.get("receipt_number"))] = ex_event
        candidates = []
        for ex_event in candidate_events.values():
            ex_date = date.fromisoformat(str(ex_event["effective_date"]))
            ex_code = str(ex_event["isu_code"])
            key = (ex_code, ex_date.isoformat())
            days = (record_date - ex_date).days
            if key not in used_ex_dates and 0 <= days <= MAX_EX_DATE_LINK_DAYS:
                candidates.append((days, ex_date, ex_event))
        exact = (
            min(candidates, key=lambda item: (item[0], item[1])) if candidates else None
        )
        source_evidence = [
            {
                "source_type": "krx_kind_distribution_disclosure",
                "receipt_number": event.get("receipt_number"),
                "source_url": event.get("source_url"),
            }
        ]
        if exact is None:
            effective_date = record_date
            timing_basis = "record_date_fallback"
            confidence = "medium"
            reference_price = None
        else:
            _, ex_date, ex_event = exact
            used_ex_dates.add((str(ex_event["isu_code"]), ex_date.isoformat()))
            effective_date = ex_date
            timing_basis = "exact_kind_ex_distribution_date"
            confidence = "high"
            reference_price = _decimal_text(ex_event.get("reference_price_krw"))
            source_evidence.append(
                {
                    "source_type": "krx_kind_ex_distribution_disclosure",
                    "receipt_number": ex_event.get("receipt_number"),
                    "source_url": ex_event.get("source_url"),
                    "reference_price_krw": reference_price,
                    "linkage_method": (
                        "same_etf_name_and_nearest_prior_effective_date"
                    ),
                }
            )
        output.append(
            {
                "isu_code": code,
                "isu_name": event.get("isu_name"),
                "isin": event.get("isin"),
                "event_type": "cash_distribution",
                "effective_date": effective_date.isoformat(),
                "record_date": record_date.isoformat(),
                "payment_date": event.get("payment_date"),
                "cash_per_share_krw": _decimal_text(
                    event.get("distribution_per_share_krw")
                ),
                "ratio": None,
                "timing_basis": timing_basis,
                "confidence": confidence,
                "status": "confirmed_cash_flow",
                "source_evidence": source_evidence,
                "ex_distribution_reference_price_krw": reference_price,
            }
        )
    return output, used_ex_dates


def _unmatched_ex_date_events(
    ex_date_report: dict[str, Any] | None,
    used: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    if ex_date_report is None:
        return []
    output = []
    for event in _events(ex_date_report, label="KIND ex-date"):
        code = str(event["isu_code"])
        effective_date = str(event["effective_date"])
        if (code, effective_date) in used:
            continue
        output.append(
            {
                "isu_code": code,
                "isu_name": event.get("isu_name"),
                "event_type": "distribution_ex_date_unmatched",
                "effective_date": effective_date,
                "record_date": None,
                "payment_date": None,
                "cash_per_share_krw": None,
                "ratio": None,
                "timing_basis": "exact_kind_ex_distribution_date",
                "confidence": "high",
                "status": "cash_disclosure_link_required",
                "source_evidence": [
                    {
                        "source_type": "krx_kind_ex_distribution_disclosure",
                        "receipt_number": event.get("receipt_number"),
                        "source_url": event.get("source_url"),
                        "reference_price_krw": _decimal_text(
                            event.get("reference_price_krw")
                        ),
                    }
                ],
            }
        )
    return output


def _kis_event_type(reason: str) -> str:
    compact = reason.replace(" ", "")
    if "병합" in compact:
        return "reverse_split"
    if "합병" in compact:
        return "merger"
    if "분할" in compact:
        return "split"
    return "price_adjustment_unclassified"


def _kis_adjustment_events(adjusted_price_root: Path) -> list[dict[str, Any]]:
    output = []
    for path in sorted(adjusted_price_root.glob("*.json")):
        product = _load(path)
        observations = product.get("observations")
        if not isinstance(observations, list):
            raise ValueError(f"KIS adjusted-price cache has no observations: {path}")
        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError(f"KIS observation must be an object: {path}")
            reason = str(observation.get("revaluation_reason") or "").strip()
            ratio = observation.get("split_rate")
            modified = str(observation.get("modified") or "").upper() == "Y"
            if not modified and not reason:
                continue
            event_type = _kis_event_type(reason)
            classified = event_type != "price_adjustment_unclassified"
            output.append(
                {
                    "isu_code": product.get("isu_code"),
                    "isu_name": product.get("isu_name"),
                    "event_type": event_type,
                    "effective_date": observation.get("date"),
                    "record_date": None,
                    "payment_date": None,
                    "cash_per_share_krw": None,
                    "ratio": _decimal_text(ratio),
                    "timing_basis": "kis_adjusted_price_event_field",
                    "confidence": "high" if classified and reason else "low",
                    "status": (
                        "confirmed_from_explicit_reason"
                        if classified and reason
                        else "issuer_verification_required"
                    ),
                    "source_evidence": [
                        {
                            "source_type": "kis_adjusted_daily_itemchartprice",
                            "endpoint": product.get("endpoint"),
                            "FID_ORG_ADJ_PRC": "0",
                            "mod_yn": observation.get("modified"),
                            "prtt_rate": observation.get("split_rate"),
                            "revl_issu_reas": reason,
                            "cache_path": path.as_posix(),
                        }
                    ],
                }
            )
    return output


def build_etf_corporate_event_master(
    *,
    distribution_report: dict[str, Any],
    ex_date_report: dict[str, Any] | None,
    adjusted_price_root: Path,
    source_files: dict[str, str],
    as_of: date,
    kis_dividend_report: dict[str, Any] | None = None,
    fsc_dividend_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cash_events, used_ex_dates = _cash_distribution_events(
        distribution_report, ex_date_report
    )
    unmatched_ex_dates = _unmatched_ex_date_events(ex_date_report, used_ex_dates)
    kis_events = _kis_adjustment_events(adjusted_price_root)
    kis_dividend_references = _kis_dividend_references(kis_dividend_report)
    fsc_dividend_references = _fsc_dividend_references(fsc_dividend_report)
    cross_validation, matched_kis_keys = _cross_validate_cash_events(
        cash_events,
        kis_references=kis_dividend_references,
        fsc_references=fsc_dividend_references,
    )
    eligible_codes = {path.stem for path in adjusted_price_root.glob("*.json")}
    scheduled_kis_events = _scheduled_kis_dividend_events(
        kis_dividend_references,
        matched_keys=matched_kis_keys,
        eligible_codes=eligible_codes,
        as_of=as_of,
    )
    events = sorted(
        [*cash_events, *scheduled_kis_events, *unmatched_ex_dates, *kis_events],
        key=lambda event: (
            str(event.get("effective_date") or ""),
            str(event.get("isu_code") or ""),
            str(event.get("event_type") or ""),
        ),
    )
    timing_counts = Counter(
        event["timing_basis"]
        for event in cash_events
        if isinstance(event.get("timing_basis"), str)
    )
    event_type_counts = Counter(str(event["event_type"]) for event in events)
    ex_date_failures = (
        int(ex_date_report.get("failure_count", 0))
        if ex_date_report is not None
        else None
    )
    return {
        "report_type": "pension_eligible_etf_corporate_event_master",
        "algorithm_input": True,
        "as_of": as_of.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "engine_name": "etf_corporate_event_evidence",
        "engine_version": "2026-07-20.1",
        "source_files": source_files,
        "event_count": len(events),
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "cash_distribution_count": len(cash_events),
        "exact_ex_date_link_count": timing_counts.get(
            "exact_kind_ex_distribution_date", 0
        ),
        "record_date_fallback_count": timing_counts.get("record_date_fallback", 0),
        "unmatched_exact_ex_date_count": len(unmatched_ex_dates),
        "kis_adjustment_event_count": len(kis_events),
        "scheduled_kis_dividend_count": len(scheduled_kis_events),
        "kis_dividend_reference_count": len(kis_dividend_references),
        "fsc_dividend_reference_count": len(fsc_dividend_references),
        **cross_validation,
        "kind_ex_date_failure_count": ex_date_failures,
        "policies": {
            "cash_distribution": (
                "Use the exact KIND ex-distribution effective date when it can be "
                "uniquely linked to a cash disclosure; otherwise retain the record "
                "date as an explicit fallback."
            ),
            "split_merger": (
                "Classify split, reverse split, or merger only when the KIS adjusted "
                "price reason explicitly names the event."
            ),
            "dividend_cross_validation": (
                "KIND remains the calculation authority. KIS KSD schedules and "
                "FSC stock-dividend rows corroborate matching ETF record dates, "
                "amounts, and payment dates; conflicts are never auto-corrected."
            ),
            "scheduled_dividend": (
                "A KIS schedule without a matching KIND disclosure is reference-only "
                "and excluded from historical total-return calculations."
            ),
            "portfolio_scoring": (
                "Dividend amount or yield does not increase ETF quality scores; "
                "distributions are part of total return, not an extra return source."
            ),
            "no_price_jump_inference": True,
        },
        "limitations": [
            "A record-date fallback is not an exact ex-distribution date.",
            "Unclassified KIS adjustments require issuer disclosure verification.",
            "Adjusted prices are not assumed to include cash distributions.",
            "FSC stock-dividend rows are matched only by exact ISIN and record date.",
            "Secondary-source conflicts require review and do not overwrite KIND.",
        ],
        "events": events,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the ETF corporate-event master."
    )
    parser.add_argument("--distributions", type=Path)
    parser.add_argument("--ex-dates", type=Path)
    parser.add_argument("--adjusted-prices", type=Path)
    parser.add_argument("--kis-dividend-schedule", type=Path)
    parser.add_argument("--fsc-stock-dividends", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/cache/events"))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    return parser


def main() -> int:
    args = _parser().parse_args()
    distribution_path = args.distributions or _latest(
        Path("data/cache/kind"), "etf_distributions_*.json"
    )
    ex_date_path = args.ex_dates
    if ex_date_path is None:
        ex_date_path = _widest_ex_date_report(Path("data/cache/kind"))
    adjusted_price_root = args.adjusted_prices or _latest_adjusted_price_root(
        Path("data/cache/kis/adjusted_prices")
    )
    source_files = {
        "kind_distributions": distribution_path.as_posix(),
        "kis_adjusted_prices": adjusted_price_root.as_posix(),
    }
    if ex_date_path is not None:
        source_files["kind_distribution_ex_dates"] = ex_date_path.as_posix()
    if args.kis_dividend_schedule is not None:
        source_files["kis_ksd_dividend_schedule"] = (
            args.kis_dividend_schedule.as_posix()
        )
    if args.fsc_stock_dividends is not None:
        source_files["fsc_stock_dividends"] = args.fsc_stock_dividends.as_posix()
    report = build_etf_corporate_event_master(
        distribution_report=_load(distribution_path),
        ex_date_report=_load(ex_date_path) if ex_date_path is not None else None,
        adjusted_price_root=adjusted_price_root,
        source_files=source_files,
        as_of=args.as_of,
        kis_dividend_report=(
            _load(args.kis_dividend_schedule)
            if args.kis_dividend_schedule is not None
            else None
        ),
        fsc_dividend_report=(
            _load(args.fsc_stock_dividends)
            if args.fsc_stock_dividends is not None
            else None
        ),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    output_path = args.output / f"etf_corporate_events_{args.as_of}.json"
    temporary = output_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(output_path)
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in {"events", "limitations", "policies"}
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
