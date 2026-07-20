"""Display-only metadata for the approved educational strategy identifiers."""

from .models import StrategyPresentation

STRATEGY_PRESENTATIONS = {
    "capital_preservation_core": StrategyPresentation(
        strategy_id="capital_preservation_core",
        display_name="안정 중심 전략",
        summary="채권과 현금성 자산을 중심으로 변동성 관리에 초점을 둔 구성입니다.",
        risk_badge="안정형",
        character_key="capital_preservation_core",
    ),
    "defensive_diversified_core": StrategyPresentation(
        strategy_id="defensive_diversified_core",
        display_name="방어 분산 전략",
        summary="주식·채권·현금성 자산을 나눠 담아 분산을 고려한 구성입니다.",
        risk_badge="안정추구형",
        character_key="defensive_diversified_core",
    ),
    "balanced_core_satellite": StrategyPresentation(
        strategy_id="balanced_core_satellite",
        display_name="균형 코어·위성 전략",
        summary="넓게 분산한 핵심 자산에 제한적인 위성 자산을 더하는 구성입니다.",
        risk_badge="위험중립형",
        character_key="balanced_core_satellite",
    ),
    "growth_core_satellite": StrategyPresentation(
        strategy_id="growth_core_satellite",
        display_name="성장 코어·위성 전략",
        summary="주식형 핵심 자산의 비중을 두고 위성 자산으로 분산하는 구성입니다.",
        risk_badge="적극투자형",
        character_key="growth_core_satellite",
    ),
    "barbell_growth_tactical": StrategyPresentation(
        strategy_id="barbell_growth_tactical",
        display_name="테마 집중 전략",
        summary="유망 산업·테마에 비중을 실어 성장을 추구하는 구성입니다.",
        risk_badge="공격투자형",
        character_key="barbell_growth_tactical",
    ),
}


def get_strategy_presentation(strategy_id: str) -> StrategyPresentation:
    """Return the display metadata for a validated educational strategy id."""

    try:
        return STRATEGY_PRESENTATIONS[strategy_id]
    except KeyError as exc:
        raise ValueError("strategy_id has no presentation metadata") from exc
