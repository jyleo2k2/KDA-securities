"""Build accuracy-first ETF style planning assumptions from verified caches."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from backend.app.engine.evidence_gated_planning_return import (
    EvidenceGatedPlanningReturnInput,
    OverlayValidationEvidence,
    calculate_evidence_gated_planning_return,
)

DEFAULT_STYLE_REPORT_PATH = Path(
    "data/cache/planning_returns/etf_style_planning_returns_2026-07-20.json"
)
DEFAULT_BACKTEST_PATH = Path(
    "data/cache/planning_returns/etf_style_backtest_2026-07-20.json"
)
DEFAULT_LONG_VALIDATION_PATH = Path(
    "data/cache/planning_returns/cma_long_horizon_validation_2025-09-30.json"
)
DEFAULT_OUTPUT_PATH = Path(
    "data/cache/planning_returns/"
    "etf_accuracy_first_planning_returns_2026-07-20.json"
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _validation_evidence(
    backtest: dict[str, Any],
    long_validation: dict[str, Any],
) -> OverlayValidationEvidence:
    holdout = backtest["model_comparison"]["holdout"]
    cma = holdout["cma_only"]["style_vintage_level"]
    candidate = holdout["combined"]["style_vintage_level"]
    independent_long_horizon = (
        long_validation.get("scope", {}).get("evidence_independence")
        == "independent_multi_vintage"
        and long_validation.get("decision", {}).get("general_cma_accuracy")
        == "validated"
    )
    return OverlayValidationEvidence(
        short_horizon_holdout_passed=bool(
            backtest["adoption_gate"]["short_horizon_gate_passed"]
        ),
        holdout_vintage_count=int(backtest["scope"]["holdout_vintage_count"]),
        long_horizon_independent_validation_passed=independent_long_horizon,
        cma_holdout_mae_percent_point=Decimal(cma["mae_percent_point"]),
        candidate_holdout_mae_percent_point=Decimal(candidate["mae_percent_point"]),
        cma_holdout_rmse_percent_point=Decimal(cma["rmse_percent_point"]),
        candidate_holdout_rmse_percent_point=Decimal(candidate["rmse_percent_point"]),
    )


def build_accuracy_first_report(
    *,
    style_report_path: Path = DEFAULT_STYLE_REPORT_PATH,
    backtest_path: Path = DEFAULT_BACKTEST_PATH,
    long_validation_path: Path = DEFAULT_LONG_VALIDATION_PATH,
) -> dict[str, Any]:
    style_report = _load(style_report_path)
    backtest = _load(backtest_path)
    long_validation = _load(long_validation_path)
    validation = _validation_evidence(backtest, long_validation)

    estimates = []
    style_values: dict[str, list[tuple[Decimal, Decimal, Decimal]]] = defaultdict(list)
    for item in style_report.get("etf_estimates") or []:
        calculation = item["calculation"]
        inputs = calculation["evaluated_input"]
        evaluation = calculate_evidence_gated_planning_return(
            EvidenceGatedPlanningReturnInput(
                etf_code=item["isu_code"],
                style_key=item["classification_style_key"],
                cma_percent=Decimal(inputs["cma_percent"]),
                candidate_historical_adjustment_percent_point=Decimal(
                    calculation["historical_adjustment_percent_point"]
                ),
                candidate_macro_adjustment_percent_point=Decimal(
                    calculation["macro_adjustment_percent_point"]
                ),
                annual_cost_drag_percent=Decimal(
                    inputs["annual_cost_drag_percent"]
                ),
                diagnostic_band_width_percent_point=Decimal(
                    calculation["range_width_percent_point"]
                ),
                validation=validation,
                sources=inputs["sources"],
            )
        )
        serialized = evaluation.model_dump(mode="json")
        estimates.append(
            {
                "isu_code": item["isu_code"],
                "isu_name": item["isu_name"],
                "asset_class": item["asset_class"],
                "strategy": item["strategy"],
                "region": item["region"],
                "style_key": item["classification_style_key"],
                "cma_proxy_used": item["cma_proxy_used"],
                "calculation": serialized,
                "is_forecast": False,
            }
        )
        style_values[item["classification_style_key"]].append(
            (
                evaluation.conservative_planning_return_percent,
                evaluation.net_planning_return_percent,
                evaluation.optimistic_planning_return_percent,
            )
        )

    summaries = []
    for style_key, values in sorted(style_values.items()):
        summaries.append(
            {
                "style_key": style_key,
                "etf_count": len(values),
                "median_conservative_planning_return_percent": str(
                    median(value[0] for value in values)
                ),
                "median_net_planning_return_percent": str(
                    median(value[1] for value in values)
                ),
                "median_optimistic_planning_return_percent": str(
                    median(value[2] for value in values)
                ),
            }
        )

    return {
        "report_type": "accuracy_first_style_planning_assumptions",
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": style_report.get("as_of"),
        "usage_label": "educational_long_term_planning_assumption_not_forecast",
        "is_forecast": False,
        "central_rule": "approved_asset_class_cma_minus_verified_annual_cost",
        "overlay_rule": (
            "history_and_macro_adjustment_only_after_three_holdout_vintages_"
            "and_independent_long_horizon_validation"
        ),
        "validation_evidence": validation.model_dump(mode="json"),
        "overlay_adopted": bool(
            estimates and estimates[0]["calculation"]["overlay_gate_passed"]
        ),
        "estimated_product_count": len(estimates),
        "style_count": len(summaries),
        "style_summaries": summaries,
        "etf_estimates": estimates,
        "input_paths": {
            "style_report": str(style_report_path),
            "rolling_backtest": str(backtest_path),
            "long_horizon_validation": str(long_validation_path),
        },
        "limitations": [
            "미래 실현수익률 예측 또는 확률구간이 아니다.",
            "중앙 계획가정은 현재 공개 CMA와 검증 비용에 의존한다.",
            "과거 수익률과 거시전망은 채택 게이트 통과 전 중앙값을 바꾸지 않는다.",
            "진단 범위는 불확실성 설명용이며 실제 손실 한도를 뜻하지 않는다.",
        ],
    }


def run(output_path: Path = DEFAULT_OUTPUT_PATH) -> dict[str, Any]:
    report = build_accuracy_first_report()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    report = run(args.output)
    print(
        json.dumps(
            {
                "estimated_product_count": report["estimated_product_count"],
                "style_count": report["style_count"],
                "overlay_adopted": report["overlay_adopted"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
