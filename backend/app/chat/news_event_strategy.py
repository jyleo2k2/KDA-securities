"""Deterministic news-event and ETF-theme classification for chat guidance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..engine import EducationalRiskProfile
from ..engine.etf_theme import EtfThemeCatalog, classify_etf_themes

NEWS_EVENT_POLICY_VERSION = "news-event-strategy-v2"
NEWS_EVENT_POLICY_AS_OF = date(2026, 7, 23)

_EVENT_LABELS = {
    "indices": "시장 변동성",
    "monetary_policy": "통화정책",
    "macro": "거시지표",
    "fx_rates": "환율·채권금리",
    "flows": "외국인·기관 수급",
    "earnings": "기업 실적",
    "sector": "산업 섹터",
    "market_rules": "시장 규제·거래제도",
}
_ETF_GROUPS = {
    "indices": "시장대표·저변동 ETF",
    "monetary_policy": "국채·단기채·성장주·은행 ETF",
    "macro": "경기민감·방어주·국채 ETF",
    "fx_rates": "환노출 해외주식·수출주·국채 ETF",
    "flows": "국내 대형주·시장대표 ETF",
    "earnings": "실적 발표 산업·퀄리티·배당 ETF",
    "sector": "산업 섹터 ETF",
    "market_rules": "시장대표·공매도 민감 업종 ETF",
}
_CHECKS = {
    "monetary_policy": "공식 금리 발표와 채권금리 반응을 함께 확인",
    "macro": "공식 통계 발표와 시장 반응이 같은 방향인지 확인",
    "fx_rates": "환헤지 여부와 원화 기준 변동을 함께 확인",
    "flows": "하루 수급만으로 추세를 확정하지 않고 거래대금을 확인",
    "earnings": "공시된 실적과 ETF 구성종목 노출을 확인",
    "market_rules": "시행일·적용 시장·예외 규정을 공식 공시에서 확인",
    "sector": "해당 산업의 ETF 구성종목과 중복 노출을 확인",
    "indices": "가격·거래대금과 기존 목표비중 이탈을 함께 확인",
}


@dataclass(frozen=True, slots=True)
class NewsEventClassification:
    event_labels: tuple[str, ...]
    theme_ids: tuple[str, ...]
    etf_groups: tuple[str, ...]
    check: str


@dataclass(frozen=True, slots=True)
class TacticalSleevePolicy:
    maximum_percent: Decimal
    core_policy: str


_TACTICAL_SLEEVE_POLICIES = {
    EducationalRiskProfile.ACTIVE: TacticalSleevePolicy(
        maximum_percent=Decimal("10"),
        core_policy="기존 코어 비중은 유지하고 전술 슬리브만 후보 ETF로 교체",
    ),
    EducationalRiskProfile.AGGRESSIVE: TacticalSleevePolicy(
        maximum_percent=Decimal("15"),
        core_policy=(
            "기존 코어에서 최대 5%p까지만 전술 슬리브로 옮기되 "
            "전체 위험자산 목표와 계좌 한도는 유지"
        ),
    ),
}


def tactical_sleeve_policy(
    risk_profile: EducationalRiskProfile,
) -> TacticalSleevePolicy | None:
    return _TACTICAL_SLEEVE_POLICIES.get(risk_profile)


def classify_news_event(
    *,
    title: str,
    description: str,
    topics: tuple[str, ...],
    theme_catalog: EtfThemeCatalog | None,
) -> NewsEventClassification:
    normalized_topics = tuple(
        topic for topic in dict.fromkeys(topics) if topic in _EVENT_LABELS
    )
    if not normalized_topics:
        normalized_topics = ("indices",)
    text = " ".join((title, description)).strip()
    theme_ids = (
        classify_etf_themes(
            theme_catalog,
            isu_name=text,
        )
        if theme_catalog is not None
        else ()
    )
    event_labels = tuple(_EVENT_LABELS[topic] for topic in normalized_topics)
    etf_groups = tuple(
        dict.fromkeys(_ETF_GROUPS[topic] for topic in normalized_topics)
    )
    check = " · ".join(dict.fromkeys(_CHECKS[topic] for topic in normalized_topics))
    return NewsEventClassification(
        event_labels=event_labels,
        theme_ids=theme_ids,
        etf_groups=etf_groups,
        check=check,
    )
