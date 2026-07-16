import argparse
import json
from collections import defaultdict, deque
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from backend.app.engine.market_evidence import (
    EtfObservation,
    calculate_historical_etf_metrics,
)
from backend.app.engine.models import SourceChip
from backend.app.ingestion.kis_client import KIS_ADJUSTED_DAILY_PRICE_ENDPOINT
from backend.app.ingestion.krx_client import parse_krx_etf_payload

MAX_OBSERVATIONS = 253
MIN_CANDIDATE_OBSERVATIONS = 253
BLOCKED_NAME_TOKENS = ("레버리지", "인버스", "2X", "-2X")


def _decimal(value: object, *, positive: bool = False) -> Decimal | None:
    if value in {None, "", "-"}:
        return None
    try:
        parsed = Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("KRX numeric field is invalid") from exc
    if not parsed.is_finite() or (positive and parsed <= 0):
        return None
    return parsed


def _load_adjusted_closes(
    cache_root: Path,
    *,
    snapshot_date: date,
    code: str,
) -> dict[date, Decimal] | None:
    path = (
        cache_root
        / "adjusted_prices"
        / snapshot_date.isoformat()
        / f"{code}.json"
    )
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    policy = payload.get("price_policy")
    rows = payload.get("observations")
    if not isinstance(policy, dict) or policy.get("FID_ORG_ADJ_PRC") != "0":
        raise ValueError(f"KIS adjusted price policy is invalid: {path}")
    if not isinstance(rows, list):
        raise ValueError(f"KIS adjusted price observations are invalid: {path}")
    closes = {}
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"KIS adjusted price row {position} must be an object")
        try:
            business_date = date.fromisoformat(row["date"])
            close = Decimal(str(row["adjusted_close"]).replace(",", ""))
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(
                f"KIS adjusted price row {position} is invalid"
            ) from exc
        if not close.is_finite() or close <= 0:
            raise ValueError(
                f"KIS adjusted price row {position} close must be positive"
            )
        closes[business_date] = close
    return closes


def _latest_adjusted_snapshot(cache_root: Path) -> date | None:
    root = cache_root / "adjusted_prices"
    candidates = []
    if root.exists():
        for path in root.iterdir():
            if not path.is_dir():
                continue
            try:
                candidates.append(date.fromisoformat(path.name))
            except ValueError:
                continue
    return max(candidates) if candidates else None


def _overlay_adjusted_closes(
    observations: list[EtfObservation],
    adjusted_closes: dict[date, Decimal],
) -> list[EtfObservation] | None:
    if not observations or any(
        observation.as_of not in adjusted_closes for observation in observations
    ):
        return None
    return [
        observation.model_copy(update={"close": adjusted_closes[observation.as_of]})
        for observation in observations
    ]


def build_market_evidence_report(
    raw_root: Path,
    kis_adjusted_cache_root: Path = Path("data/cache/kis"),
) -> dict[str, Any]:
    histories: dict[str, deque[EtfObservation]] = defaultdict(
        lambda: deque(maxlen=MAX_OBSERVATIONS)
    )
    metadata: dict[str, dict[str, str]] = {}
    latest_response_date: date | None = None
    latest_universe_codes: set[str] = set()
    files = sorted((raw_root / "etf_bydd_trd").glob("*/*/*.json"))
    if not files:
        raise ValueError(f"no KRX ETF raw files found under {raw_root}")

    nonempty_dates = 0
    latest_date: date | None = None
    for path in files:
        base_date = date.fromisoformat(
            f"{path.stem[0:4]}-{path.stem[4:6]}-{path.stem[6:8]}"
        )
        payload = json.loads(path.read_bytes())
        response = parse_krx_etf_payload(payload, base_date=base_date)
        if latest_response_date is None or base_date > latest_response_date:
            latest_response_date = base_date
            latest_universe_codes = {
                row["ISU_CD"] for row in response.records
            }
        usable_for_date = 0
        for row in response.records:
            close = _decimal(row["TDD_CLSPRC"], positive=True)
            trading_value = _decimal(row["ACC_TRDVAL"])
            if close is None or trading_value is None:
                continue
            usable_for_date += 1
            nav = _decimal(row["NAV"], positive=True)
            net_assets = _decimal(
                row["INVSTASST_NETASST_TOTAMT"],
                positive=True,
            )
            benchmark_close = _decimal(row["OBJ_STKPRC_IDX"], positive=True)
            code = row["ISU_CD"]
            histories[code].append(
                EtfObservation(
                    as_of=base_date,
                    close=close,
                    nav=nav,
                    trading_value_krw=trading_value,
                    net_assets_krw=net_assets,
                    benchmark_close=benchmark_close,
                )
            )
            metadata[code] = {
                "isu_name": row["ISU_NM"],
                "benchmark_name": row["IDX_IND_NM"],
            }
        if usable_for_date:
            nonempty_dates += 1
            latest_date = max(latest_date or base_date, base_date)

    products: list[dict[str, Any]] = []
    excluded_not_currently_listed_count = 0
    kis_adjusted_price_product_count = 0
    krx_close_fallback_product_count = 0
    adjusted_snapshot_date = _latest_adjusted_snapshot(
        kis_adjusted_cache_root
    )
    for code, observations in sorted(histories.items()):
        if code not in latest_universe_codes:
            excluded_not_currently_listed_count += 1
            continue
        if (
            len(observations) < MIN_CANDIDATE_OBSERVATIONS
            or observations[-1].as_of != latest_date
        ):
            continue
        product_metadata = metadata[code]
        metric_observations = list(observations)
        adjusted_closes = (
            _load_adjusted_closes(
                kis_adjusted_cache_root,
                snapshot_date=adjusted_snapshot_date,
                code=code,
            )
            if adjusted_snapshot_date is not None
            else None
        )
        adjusted_observations = (
            _overlay_adjusted_closes(metric_observations, adjusted_closes)
            if adjusted_closes is not None
            else None
        )
        if adjusted_observations is not None:
            metric_observations = adjusted_observations
            kis_adjusted_price_product_count += 1
            source = SourceChip(
                label="한투 수정주가 + KRX ETF 일별매매정보",
                reference=KIS_ADJUSTED_DAILY_PRICE_ENDPOINT,
                as_of=latest_date,
            )
            warnings = [
                "price_returns_use_kis_adjusted_close_fid_org_adj_prc_0",
                "cash_distributions_not_assumed_in_kis_adjusted_close",
            ]
        else:
            krx_close_fallback_product_count += 1
            source = None
            warnings = ["kis_adjusted_price_unavailable_krx_close_fallback"]
        metrics = calculate_historical_etf_metrics(
            metric_observations,
            source=source,
            additional_warnings=warnings,
        )
        name_upper = product_metadata["isu_name"].upper()
        usable_on_report_date = metrics.history_end == latest_date
        products.append(
            {
                "isu_code": code,
                **product_metadata,
                "active_on_report_date": True,
                "usable_on_report_date": usable_on_report_date,
                "blocked_name_pattern": any(
                    token in name_upper for token in BLOCKED_NAME_TOKENS
                ),
                "eligibility_status": "verification_required",
                "historical_metrics": metrics.model_dump(mode="json"),
            }
        )

    product_codes = {product["isu_code"] for product in products}

    return {
        "report_type": "current_listed_historical_market_evidence",
        "source": "KIS adjusted prices joined to KRX statistical information",
        "as_of": latest_date.isoformat() if latest_date else None,
        "raw_file_count": len(files),
        "nonempty_trading_dates": nonempty_dates,
        "product_count": len(products),
        "current_listed_universe_count": len(latest_universe_codes),
        "excluded_insufficient_observations_count": len(
            latest_universe_codes.difference(product_codes)
        ),
        "excluded_not_currently_listed_count": (
            excluded_not_currently_listed_count
        ),
        "minimum_candidate_observations": MIN_CANDIDATE_OBSERVATIONS,
        "metric_window_max_observations": MAX_OBSERVATIONS,
        "kis_adjusted_price_product_count": kis_adjusted_price_product_count,
        "krx_close_fallback_product_count": krx_close_fallback_product_count,
        "kis_adjusted_snapshot_date": (
            adjusted_snapshot_date.isoformat()
            if adjusted_snapshot_date is not None
            else None
        ),
        "price_policy": {
            "preferred_source": "KIS inquire-daily-itemchartprice",
            "FID_ORG_ADJ_PRC": "0",
            "fallback_source": "KRX ETF daily close",
        },
        "limitations": [
            "historical evidence only; no future return forecast",
            "KRX daily API does not provide product fees or distributions",
            "account eligibility requires a separate verified product master",
            "name-pattern blocking is a quarantine signal, not eligibility proof",
            "listed status and a usable closing-price observation are separate",
            "products with fewer than 253 usable observations are excluded",
            "KIS adjusted close is not treated as cash-distribution total return",
        ],
        "products": products,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build deterministic historical ETF evidence from KRX raw files."
    )
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/krx"))
    parser.add_argument(
        "--kis-adjusted-cache-root",
        type=Path,
        default=Path("data/cache/kis"),
    )
    parser.add_argument("--output", type=Path, default=Path("data/cache/krx"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = build_market_evidence_report(
        args.raw_root,
        args.kis_adjusted_cache_root,
    )
    as_of = report["as_of"] or "unknown"
    output_path = args.output / f"etf_market_evidence_{as_of}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(output_path)
    print(
        json.dumps(
            {
                "as_of": report["as_of"],
                "product_count": report["product_count"],
                "output_path": output_path.as_posix(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
