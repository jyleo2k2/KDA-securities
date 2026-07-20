"""Build a non-adopted structural ensemble candidate report for current ETFs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from backend.app.engine.models import SourceChip
from backend.app.engine.structural_return_ensemble import (
    CmaEstimate,
    EquilibriumPrior,
    StructuralEnsembleInput,
    StructuralEstimate,
    calculate_structural_ensemble,
)

DEFAULT_STYLE_REPORT_PATH = Path(
    "data/cache/planning_returns/etf_style_planning_returns_2026-07-20.json"
)
DEFAULT_REFERENCE_PATH = Path(
    "data/reference/structural_ensemble_cma_inputs_2026-07-20.json"
)
DEFAULT_OUTPUT_PATH = Path(
    "data/cache/planning_returns/"
    "etf_structural_ensemble_candidates_2026-07-20.json"
)
DEFAULT_STRUCTURAL_EVIDENCE_PATH = Path(
    "data/cache/planning_returns/structural_market_evidence_latest.json"
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _cma_estimates(
    reference: dict[str, Any], assumption_code: str
) -> list[CmaEstimate]:
    sources = reference["sources"]
    estimates = []
    for item in reference["assumptions"].get(assumption_code) or []:
        source = sources[item["provider"]]
        estimates.append(
            CmaEstimate(
                provider=item["provider"],
                expected_return_percent=Decimal(item["percent"]),
                source=SourceChip(
                    label=source["label"],
                    reference=source["reference"],
                    as_of=date.fromisoformat(source["as_of"]),
                ),
            )
        )
    if not estimates:
        raise ValueError(f"no CMA inputs for assumption code: {assumption_code}")
    return estimates


def _source_chip(payload: dict[str, Any]) -> SourceChip:
    return SourceChip(
        label=payload["label"],
        reference=payload["reference"],
        as_of=date.fromisoformat(payload["as_of"]),
    )


def _market_inputs(
    evidence: dict[str, Any] | None, assumption_code: str
) -> tuple[StructuralEstimate | None, EquilibriumPrior | None]:
    if evidence is None:
        return None, None
    item = (evidence.get("asset_inputs") or {}).get(assumption_code)
    if not isinstance(item, dict):
        return None, None
    source = _source_chip(item["source"])
    structural = StructuralEstimate(
        expected_return_percent=Decimal(item["structural_estimate_percent"]),
        method=item["structural_method"],
        source=source,
    )
    equilibrium = None
    if item.get("equilibrium_prior_percent") is not None:
        equilibrium = EquilibriumPrior(
            expected_return_percent=Decimal(item["equilibrium_prior_percent"]),
            view_confidence=Decimal(item["view_confidence"]),
            source=source,
        )
    return structural, equilibrium


def build_candidate_report(
    *,
    style_report_path: Path = DEFAULT_STYLE_REPORT_PATH,
    reference_path: Path = DEFAULT_REFERENCE_PATH,
    structural_evidence_path: Path | None = DEFAULT_STRUCTURAL_EVIDENCE_PATH,
) -> dict[str, Any]:
    style_report = _load(style_report_path)
    reference = _load(reference_path)
    evidence = (
        _load(structural_evidence_path)
        if structural_evidence_path is not None and structural_evidence_path.exists()
        else None
    )
    estimates = []
    style_values: dict[str, list[Decimal]] = defaultdict(list)
    multi_provider_count = 0
    structural_input_count = 0
    equilibrium_input_count = 0

    for item in style_report.get("etf_estimates") or []:
        old_calculation = item["calculation"]
        old_input = old_calculation["evaluated_input"]
        cma_estimates = _cma_estimates(
            reference, old_input["cma_assumption_code"]
        )
        structural, equilibrium = _market_inputs(
            evidence, old_input["cma_assumption_code"]
        )
        evaluation = calculate_structural_ensemble(
            StructuralEnsembleInput(
                asset_code=old_input["cma_assumption_code"],
                horizon_years=10,
                cma_estimates=cma_estimates,
                structural_estimate=structural,
                equilibrium_prior=equilibrium,
                annual_cost_drag_percent=Decimal(
                    old_input["annual_cost_drag_percent"]
                ),
            )
        )
        if len(cma_estimates) >= 2:
            multi_provider_count += 1
        if structural is not None:
            structural_input_count += 1
        if equilibrium is not None:
            equilibrium_input_count += 1
        estimates.append(
            {
                "isu_code": item["isu_code"],
                "isu_name": item["isu_name"],
                "asset_class": item["asset_class"],
                "strategy": item["strategy"],
                "region": item["region"],
                "style_key": item["classification_style_key"],
                "cma_proxy_used": item["cma_proxy_used"],
                "calculation": evaluation.model_dump(mode="json"),
                "is_forecast": False,
            }
        )
        style_values[item["classification_style_key"]].append(
            evaluation.net_planning_return_percent
        )

    summaries = [
        {
            "style_key": style_key,
            "etf_count": len(values),
            "median_net_candidate_percent": str(median(values)),
        }
        for style_key, values in sorted(style_values.items())
    ]
    return {
        "report_type": "structural_ensemble_candidate_readiness",
        "generated_at": datetime.now(UTC).isoformat(),
        "as_of": style_report.get("as_of"),
        "usage_label": "unvalidated_candidate_not_forecast",
        "is_forecast": False,
        "adoption_authorized": False,
        "estimated_product_count": len(estimates),
        "multi_cma_product_count": multi_provider_count,
        "single_cma_product_count": len(estimates) - multi_provider_count,
        "structural_input_product_count": structural_input_count,
        "equilibrium_input_product_count": equilibrium_input_count,
        "full_input_product_count": 0,
        "style_count": len(summaries),
        "style_summaries": summaries,
        "etf_estimates": estimates,
        "input_paths": {
            "style_report": str(style_report_path),
            "cma_reference": str(reference_path),
            "structural_market_evidence": (
                str(structural_evidence_path)
                if structural_evidence_path is not None
                else None
            ),
        },
        "missing_inputs": [
            "검증 게이트를 통과한 통계 도전모델",
            "구조식이 없는 자산군의 독립 빌딩블록",
            "당시 배포본 아카이브에 기반한 다중 빈티지 외부표본 검증",
        ],
        "limitations": [
            "복수 CMA가 있는 코드는 동일 정의 공급자 중앙값을 사용한다.",
            "미국 주식·미국 채권 3종만 공식 구조적 입력이 연결됐다.",
            "검증된 통계 도전모델이 없어 완성 앙상블이 아니다.",
            "독립 워크포워드 검증 전이므로 기존 계획수익률을 교체하지 않는다.",
            "미래 실현수익률 예측이나 매매 신호가 아니다."
        ],
    }


def run(output_path: Path = DEFAULT_OUTPUT_PATH) -> dict[str, Any]:
    report = build_candidate_report()
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
                "multi_cma_product_count": report["multi_cma_product_count"],
                "structural_input_product_count": report[
                    "structural_input_product_count"
                ],
                "full_input_product_count": report["full_input_product_count"],
                "adoption_authorized": report["adoption_authorized"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
