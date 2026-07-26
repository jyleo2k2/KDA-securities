"""Strict parsing with narrow compatibility for known stored chat responses."""

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from .models import ChatIntent, ChatResponse, VisualizationKind

_LEGACY_PORTFOLIO_DATA_MODES = frozenset(
    {
        "engine_educational_planning",
        "engine_multi_account_planning",
    }
)
_NUMERIC_EVIDENCE_ERROR = "numeric claims require matching NumericEvidence"


def parse_stored_chat_response(value: Any) -> ChatResponse:
    """Parse a stored response, repairing only the known schema-v1 chart defect."""

    try:
        return ChatResponse.model_validate(value)
    except ValidationError as exc:
        if not _only_numeric_evidence_errors(exc):
            raise
        repaired = _repair_legacy_portfolio_visualization_evidence(value)
        return ChatResponse.model_validate(repaired)


def _only_numeric_evidence_errors(exc: ValidationError) -> bool:
    errors = exc.errors(include_url=False)
    return bool(errors) and all(
        error.get("type") == "value_error"
        and _NUMERIC_EVIDENCE_ERROR in str(error.get("msg", ""))
        for error in errors
    )


def _repair_legacy_portfolio_visualization_evidence(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if value.get("intent") != ChatIntent.EDUCATIONAL_PORTFOLIO.value:
        return value
    if value.get("data_mode") not in _LEGACY_PORTFOLIO_DATA_MODES:
        return value
    evaluations = value.get("educational_portfolio_evaluations")
    if not isinstance(evaluations, list) or not evaluations:
        return value

    repaired = deepcopy(value)
    numeric_evidence = repaired.get("numeric_evidence")
    visualizations = repaired.get("visualizations")
    sources = repaired.get("sources")
    if not isinstance(numeric_evidence, list):
        return value
    if not isinstance(visualizations, list) or not isinstance(sources, list):
        return value
    source_ids = {
        source.get("evidence_id")
        for source in sources
        if isinstance(source, dict)
        and isinstance(source.get("evidence_id"), str)
    }

    repaired_any = False
    for visualization in visualizations:
        if not isinstance(visualization, dict):
            return value
        if visualization.get("kind") != VisualizationKind.SLEEVE_ALLOCATION.value:
            continue
        evidence_ids = visualization.get("evidence_ids")
        items = visualization.get("items")
        title = visualization.get("title")
        if (
            visualization.get("data_boundary") != "engine"
            or not isinstance(evidence_ids, list)
            or len(evidence_ids) != 1
            or not isinstance(evidence_ids[0], str)
            or not evidence_ids[0].startswith("engine:educational_portfolio")
            or evidence_ids[0] not in source_ids
            or not isinstance(items, list)
            or not items
            or not isinstance(title, str)
        ):
            return value
        evidence_id = evidence_ids[0]
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("label"), str)
                or item.get("value") is None
                or item.get("unit") != "%"
                or item.get("role") != "segment"
            ):
                return value
            numeric_evidence.append(
                {
                    "label": f"{title} · {item['label']}",
                    "value": item["value"],
                    "unit": item["unit"],
                    "evidence_id": evidence_id,
                    "basis": "계좌별 목표 자산배분 합계",
                }
            )
        repaired_any = True

    if not repaired_any:
        return value
    repaired["numeric_evidence"] = numeric_evidence
    return repaired
