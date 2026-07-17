"""Upgrade the saved educational-portfolio report without reselecting products."""

from copy import deepcopy
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .engine.educational_portfolio import ENGINE_VERSION

SOURCE_ENGINE_VERSION = "2026-07-16.3"
DRIFT_THRESHOLD_PERCENT_POINTS = Decimal("5")
PERCENT_QUANTUM = Decimal("0.0001")


def _percent_text(value: Decimal) -> str:
    return format(value.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP), "f")


def _set_engine_version(value: Any) -> None:
    if isinstance(value, dict):
        if "engine_version" in value:
            value["engine_version"] = ENGINE_VERSION
        for child in value.values():
            _set_engine_version(child)
    elif isinstance(value, list):
        for child in value:
            _set_engine_version(child)


def _upgrade_planning_return(planning: dict[str, Any]) -> None:
    raw_net = planning.get("net_planning_return_percent")
    if raw_net is None:
        planning["conservative_planning_return_percent"] = None
        planning["base_planning_return_percent"] = None
        return

    net = Decimal(str(raw_net))
    components = planning.get("components")
    if not isinstance(components, list):
        raise ValueError("planning_return.components must be a list")
    coverage = Decimal(str(planning.get("coverage_weight_percent") or "0"))
    if coverage <= 0:
        raise ValueError("planning return coverage must be positive")
    weighted_net = sum(
        (
            Decimal(str(component["target_percent"]))
            * Decimal(str(component["net_planning_return_percent"]))
            for component in components
        ),
        Decimal("0"),
    ) / coverage
    weighted_uncertainty = sum(
        (
            Decimal(str(component["target_percent"]))
            * Decimal(str(component["uncertainty_discount_percent"]))
            for component in components
        ),
        Decimal("0"),
    ) / coverage
    planning["conservative_planning_return_percent"] = _percent_text(net)
    planning["base_planning_return_percent"] = _percent_text(
        weighted_net + weighted_uncertainty
    )


def upgrade_portfolio_examples_payload(
    payload: dict[str, Any], *, migrated_at: datetime
) -> dict[str, Any]:
    """Add the three 2026-07-16.4 fields while preserving prior selections."""

    source_version = str(payload.get("engine_version") or "")
    if source_version != SOURCE_ENGINE_VERSION:
        raise ValueError(
            f"expected source engine {SOURCE_ENGINE_VERSION}, got {source_version}"
        )
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("portfolio report must contain scenarios")

    upgraded = deepcopy(payload)
    for scenario in upgraded["scenarios"]:
        if not isinstance(scenario, dict):
            raise ValueError("portfolio scenario must be an object")
        planning = scenario.get("planning_return")
        rebalancing = scenario.get("rebalancing")
        if not isinstance(planning, dict) or not isinstance(rebalancing, dict):
            raise ValueError("scenario planning_return and rebalancing are required")
        _upgrade_planning_return(planning)
        rebalancing["drift_threshold_percent_points"] = format(
            DRIFT_THRESHOLD_PERCENT_POINTS,
            "f",
        )

    _set_engine_version(upgraded)
    upgraded["engine_version"] = ENGINE_VERSION
    upgraded["schema_migration"] = {
        "source_engine_version": source_version,
        "target_engine_version": ENGINE_VERSION,
        "migrated_at": migrated_at.isoformat(),
        "method": "derived_missing_fields_without_portfolio_reselection",
    }
    return upgraded
