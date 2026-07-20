"""Build ETF style planning-return ranges from local verified inputs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from statistics import median
from typing import Any

from backend.app.engine.educational_portfolio import (
    CMA_ASSUMPTIONS_PERCENT,
    CMA_POLICY_ID,
    CMA_SOURCE_AS_OF,
    _cma_mapping,
    _uncertainty_discount,
)
from backend.app.engine.models import SourceChip
from backend.app.engine.style_planning_return import (
    ENGINE_NAME,
    ENGINE_VERSION,
    POLICY_VERSION,
    MacroRevisionSignals,
    StylePlanningReturnInput,
    calculate_style_planning_return,
    style_macro_sensitivities,
)

TRADING_DAYS_PER_YEAR = Decimal("252")
HISTORICAL_PERIODS = ("5y", "3y", "1y")
PREFERRED_MINIMUM_PEERS = 5
DEFAULT_RETURN_ROOT = Path("data/cache/returns")
DEFAULT_OUTLOOK_PATH = Path(
    "data/reference/macro_outlook_scenarios_2026-07-20.json"
)
DEFAULT_OUTPUT_ROOT = Path("data/cache/planning_returns")


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _latest_return_master(root: Path) -> Path:
    paths = sorted(root.glob("pension_etf_cost_return_master_*.json"))
    if not paths:
        raise FileNotFoundError("ETF cost-return master cache is unavailable")
    return paths[-1]


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _annualized_total_return(
    product: dict[str, Any], period: str
) -> Decimal | None:
    row = (product.get("returns") or {}).get(period) or {}
    if row.get("status") != "complete":
        return None
    total_return = _decimal(row.get("distribution_reinvested_total_return_percent"))
    observation_count = row.get("observation_count")
    if (
        total_return is None
        or total_return <= Decimal("-100")
        or not isinstance(observation_count, int)
        or observation_count < 2
    ):
        return None
    with localcontext() as context:
        context.prec = 28
        years = Decimal(observation_count - 1) / TRADING_DAYS_PER_YEAR
        growth = Decimal("1") + total_return / Decimal("100")
        annualized = ((growth.ln() / years).exp() - Decimal("1")) * Decimal(
            "100"
        )
    return annualized


def _region_bucket(region: str) -> str:
    if region in {"south_korea", "united_states"}:
        return region
    return "global"


def _group_keys(classification: dict[str, Any]) -> tuple[str, str, str]:
    asset_class = str(classification.get("asset_class") or "unknown")
    strategy = str(classification.get("strategy") or "unspecified")
    region = _region_bucket(str(classification.get("region") or "global"))
    return (
        f"{asset_class}:{strategy}:{region}",
        f"{asset_class}:{strategy}:all",
        f"{asset_class}:all:all",
    )


def _history_pools(
    products: list[dict[str, Any]],
) -> dict[tuple[str, str], list[Decimal]]:
    pools: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    for product in products:
        classification = product.get("classification") or {}
        for period in HISTORICAL_PERIODS:
            annualized = _annualized_total_return(product, period)
            if annualized is None:
                continue
            for key in _group_keys(classification):
                pools[(key, period)].append(annualized)
    return pools


def _peer_history(
    classification: dict[str, Any],
    pools: dict[tuple[str, str], list[Decimal]],
) -> tuple[str, str, list[Decimal]]:
    keys = _group_keys(classification)
    for period in HISTORICAL_PERIODS:
        for key in keys:
            values = pools.get((key, period), [])
            if len(values) >= PREFERRED_MINIMUM_PEERS:
                return key, period, values
    for period in reversed(HISTORICAL_PERIODS):
        candidates = [
            (key, pools.get((key, period), []))
            for key in keys
            if pools.get((key, period))
        ]
        if candidates:
            key, values = max(candidates, key=lambda item: len(item[1]))
            return key, period, values
    raise ValueError("ETF style has no usable historical total-return peers")


def _macro_region(classification: dict[str, Any]) -> str:
    return _region_bucket(str(classification.get("region") or "global"))


def _macro_signals(
    outlook: dict[str, Any], region: str
) -> MacroRevisionSignals:
    payload = outlook["regional_revision_signals"][region]
    return MacroRevisionSignals(
        region=region,
        growth_revision_percent_point=Decimal(
            payload["growth_revision_percent_point"]
        ),
        inflation_revision_percent_point=Decimal(
            payload["inflation_revision_percent_point"]
        ),
        policy_rate_revision_percent_point=Decimal(
            payload["policy_rate_revision_percent_point"]
        ),
        uncertainty_level=str(payload["uncertainty_level"]),
        missing_signal_ids=list(payload.get("missing_signal_ids") or []),
    )


def _macro_source(outlook: dict[str, Any], region: str) -> SourceChip:
    source_id = {
        "south_korea": "bok_outlook_2026_05",
        "united_states": "fomc_sep_2026_06",
        "global": "imf_weo_update_2026_07",
    }[region]
    source = next(
        item
        for item in outlook["source_observations"]
        if item["source_id"] == source_id
    )
    return SourceChip(
        label=f"{source['publisher']} 공식 전망 수정",
        reference=source["reference"],
        as_of=date.fromisoformat(source["as_of"]),
    )


def _cost(product: dict[str, Any]) -> tuple[Decimal, list[str]]:
    cost_data = product.get("cost") or {}
    effective = _decimal(cost_data.get("effective_total_cost_percent"))
    if effective is not None:
        return effective, []
    stated = _decimal(cost_data.get("kis_total_expense_ratio_percent"))
    if stated is not None:
        return stated, ["effective_total_cost_missing_uses_kis_stated_expense"]
    return Decimal("0"), ["verified_cost_missing_zero_placeholder"]


def _style_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["classification_style_key"]].append(row)
    summaries = []
    for style_key, items in sorted(grouped.items()):
        summaries.append(
            {
                "style_key": style_key,
                "etf_count": len(items),
                "median_conservative_planning_return_percent": str(
                    median(
                        Decimal(item["conservative_planning_return_percent"])
                        for item in items
                    )
                ),
                "median_net_planning_return_percent": str(
                    median(
                        Decimal(item["net_planning_return_percent"])
                        for item in items
                    )
                ),
                "median_optimistic_planning_return_percent": str(
                    median(
                        Decimal(item["optimistic_planning_return_percent"])
                        for item in items
                    )
                ),
            }
        )
    return summaries


def build_style_planning_report(
    *, return_master_path: Path, outlook_path: Path
) -> dict[str, Any]:
    master = _load(return_master_path)
    outlook = _load(outlook_path)
    products = list(master.get("products") or [])
    pools = _history_pools(products)
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    history_source = SourceChip(
        label="ETF 계좌별 총수익·비용 마스터",
        reference=return_master_path.as_posix(),
        as_of=date.fromisoformat(master["as_of"]),
    )
    cma_source = SourceChip(
        label="J.P. Morgan 2026 Long-Term Capital Market Assumptions",
        reference=(
            "https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/"
            "portfolio-insights/ltcma/noindex/ltcma-full-report.pdf"
        ),
        as_of=CMA_SOURCE_AS_OF,
    )
    policy_source = SourceChip(
        label="ETF 스타일 계획수익률 결합 정책",
        reference="backend/app/engine/style_planning_return.py",
        as_of=date.fromisoformat(outlook["as_of"]),
    )

    for product in products:
        classification = product.get("classification") or {}
        code = str(product.get("isu_code") or "")
        try:
            cma_code, proxy_used, mapping_warnings = _cma_mapping(classification)
            peer_key, historical_period, historical_values = _peer_history(
                classification, pools
            )
        except ValueError as exc:
            excluded.append({"isu_code": code, "reason": str(exc)})
            continue
        region = _macro_region(classification)
        macro_source = _macro_source(outlook, region)
        cost, cost_warnings = _cost(product)
        asset_class = str(classification.get("asset_class") or "unknown")
        strategy = str(classification.get("strategy") or "unspecified")
        evaluation = calculate_style_planning_return(
            StylePlanningReturnInput(
                etf_code=code,
                style_key=peer_key,
                cma_assumption_code=cma_code,
                cma_percent=CMA_ASSUMPTIONS_PERCENT[cma_code],
                historical_annualized_return_percent=median(historical_values),
                historical_period=historical_period,
                historical_peer_count=len(historical_values),
                macro_signals=_macro_signals(outlook, region),
                macro_sensitivities=style_macro_sensitivities(
                    asset_class=asset_class,
                    strategy=strategy,
                ),
                uncertainty_discount_percent=_uncertainty_discount(classification),
                annual_cost_drag_percent=cost,
                sources=[cma_source, history_source, macro_source, policy_source],
            )
        )
        payload = evaluation.model_dump(mode="json")
        rows.append(
            {
                "isu_code": code,
                "isu_name": product.get("isu_name"),
                "classification_style_key": _group_keys(classification)[0],
                "asset_class": asset_class,
                "strategy": strategy,
                "region": classification.get("region"),
                "cma_proxy_used": proxy_used,
                "gross_planning_return_percent": payload[
                    "gross_planning_return_percent"
                ],
                "net_planning_return_percent": payload[
                    "net_planning_return_percent"
                ],
                "conservative_planning_return_percent": payload[
                    "conservative_planning_return_percent"
                ],
                "optimistic_planning_return_percent": payload[
                    "optimistic_planning_return_percent"
                ],
                "is_forecast": False,
                "warnings": list(
                    dict.fromkeys(
                        mapping_warnings + cost_warnings + payload["warnings"]
                    )
                ),
                "calculation": payload,
            }
        )

    return {
        "report_type": "etf_style_planning_return_ranges",
        "engine_name": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "policy_version": POLICY_VERSION,
        "cma_policy_id": CMA_POLICY_ID,
        "as_of": master["as_of"],
        "generated_at": datetime.now(UTC).isoformat(),
        "usage_label": "educational_planning_assumption_not_return_forecast",
        "return_master_path": return_master_path.as_posix(),
        "macro_outlook_path": outlook_path.as_posix(),
        "input_product_count": len(products),
        "estimated_product_count": len(rows),
        "excluded_product_count": len(excluded),
        "style_count": len({row["classification_style_key"] for row in rows}),
        "historical_peer_preferred_minimum": PREFERRED_MINIMUM_PEERS,
        "style_summaries": _style_summary(rows),
        "etf_estimates": rows,
        "excluded_products": excluded,
        "limitations": [
            "These are educational planning ranges, not return predictions.",
            (
                "Historical style returns are annualized, median-aggregated, "
                "shrunk toward CMA, and capped."
            ),
            (
                "Macro adjustments use bounded official forecast revisions, "
                "not current-level market timing."
            ),
            "Scenario endpoints have no probability attached.",
            "Past performance does not indicate future performance.",
        ],
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
        description="Build CMA, style-history, and macro-scenario planning ranges."
    )
    parser.add_argument("--return-master", type=Path)
    parser.add_argument("--return-root", type=Path, default=DEFAULT_RETURN_ROOT)
    parser.add_argument("--outlook", type=Path, default=DEFAULT_OUTLOOK_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return_master_path = args.return_master or _latest_return_master(args.return_root)
    report = build_style_planning_report(
        return_master_path=return_master_path,
        outlook_path=args.outlook,
    )
    output_path = args.output / f"etf_style_planning_returns_{report['as_of']}.json"
    _write_json(output_path, report)
    print(
        json.dumps(
            {
                "as_of": report["as_of"],
                "estimated_product_count": report["estimated_product_count"],
                "excluded_product_count": report["excluded_product_count"],
                "style_count": report["style_count"],
                "output_path": output_path.as_posix(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["estimated_product_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
