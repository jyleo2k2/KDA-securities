"""Provider disclosure and market-news intent handlers."""

import logging
from datetime import UTC, datetime

from ...engine import AccountType, EducationalRiskProfile
from ...etf_theme_repository import EtfThemeRepository
from ...news_event_outcome_repository import (
    NewsEventOutcomeReader,
    NewsEventOutcomeRecord,
)
from ...retrieval.repository import NewsMatch
from ..live_news import LiveMarketNewsSnapshot, LiveNewsUnavailable
from ..models import (
    AnswerBlock,
    AnswerBlockKind,
    AnswerSection,
    ChatIntent,
    ChatNewsItem,
    ChatRequest,
    ChatResponse,
    ConversationContext,
    DataBoundary,
    MarketRegion,
    NewsConversationContext,
    NumericEvidence,
    SectionKind,
    SourceEvidence,
)
from ..news_event_strategy import (
    NEWS_EVENT_POLICY_AS_OF,
    NEWS_EVENT_POLICY_VERSION,
    classify_news_event,
)
from ..query_planner import NewsScopeNotice
from ..routing import NewsFollowUp, NewsFollowUpAction
from ._shared import (
    _ACCOUNT_TYPE_LABELS,
    _RISK_PROFILE_RANKS,
    DisclosureSearch,
    LiveNewsSearch,
    NewsSearch,
    PortfolioUniverseLoader,
    _decimal_text,
    _news_comparison_block,
    _news_metadata_line,
    _news_summary_block,
    _source_ids,
)
from .graceful_decline import GracefulDeclineKind, graceful_decline

logger = logging.getLogger(__name__)

_NEWS_SCOPE_MESSAGES = {
    NewsScopeNotice.UNSUPPORTED_MARKET: (
        "해당 국가 증시 뉴스는 제공하지 않아요. 대신 한국·미국 증시 뉴스를 보여드려요."
    ),
    NewsScopeNotice.PENSION: (
        "연금 제도 뉴스는 제공하지 않아요. 대신 한국·미국 증시 뉴스를 보여드려요."
    ),
}


def _scope_message(scope_notice: NewsScopeNotice | None) -> str | None:
    if scope_notice is NewsScopeNotice.COMPANY:
        return graceful_decline(GracefulDeclineKind.STOCK_NEWS, "").answer
    return _NEWS_SCOPE_MESSAGES[scope_notice] if scope_notice is not None else None


def _freshness_limitation(matches) -> str:
    latest = max(item.published_at for item in matches if item.published_at is not None)
    elapsed_seconds = max((datetime.now(UTC) - latest).total_seconds(), 0)
    elapsed_hours = max(1, int((elapsed_seconds + 3599) // 3600))
    if elapsed_hours < 24:
        return f"가장 최신 기사는 약 {elapsed_hours}시간 전 발행됐어요."
    return f"가장 최신 기사는 약 {elapsed_hours // 24}일 전 발행됐어요."


def _live_metadata_response(
    snapshot: LiveMarketNewsSnapshot,
    *,
    scope_notice: NewsScopeNotice | None,
    summaries_by_canonical_url: dict[str, NewsMatch] | None = None,
) -> tuple[ChatResponse, dict[str, tuple[str, ...]]]:
    stored = summaries_by_canonical_url or {}
    sources: list[SourceEvidence] = []
    news_items: list[ChatNewsItem] = []
    content_blocks: list[str] = []
    topics_by_evidence: dict[str, tuple[str, ...]] = {}
    stored_item_ids: list[str] = []
    for index, item in enumerate(snapshot.items):
        summary = stored.get(item.canonical_url)
        evidence_id = (
            f"news:{summary.item_id}"
            if summary is not None
            else f"live-news:{item.item_id}"
        )
        sources.append(
            SourceEvidence(
                evidence_id=evidence_id,
                label=item.title,
                locator=item.original_url,
                publisher=item.publisher,
                as_of=item.published_at,
                data_boundary=(
                    DataBoundary.NEWS_SUMMARY
                    if summary is not None
                    else DataBoundary.NEWS_METADATA
                ),
            )
        )
        if summary is not None:
            stored_item_ids.append(summary.item_id)
            news_items.append(
                ChatNewsItem(
                    evidence_id=evidence_id,
                    title=summary.title,
                    summary_lines=list(summary.summary_lines),
                    original_url=summary.original_url,
                    published_at=summary.published_at,
                )
            )
            content_blocks.append(_news_summary_block(summary, index))
        else:
            news_items.append(
                ChatNewsItem(
                    evidence_id=evidence_id,
                    title=item.title,
                    description=item.description,
                    original_url=item.original_url,
                    published_at=item.published_at,
                )
            )
            content_blocks.append(
                f"- {item.title}: {item.description or 'NAVER 설명 없음'}"
            )
        topics_by_evidence[evidence_id] = item.topics

    matched_count = len(stored_item_ids)
    all_summarized = bool(snapshot.items) and matched_count == len(snapshot.items)
    regions = {item.region for item in snapshot.items}
    market_region = (
        MarketRegion.KR
        if regions == {"kr"}
        else MarketRegion.US
        if regions == {"us"}
        else MarketRegion.ALL
    )
    scope_message = _scope_message(scope_notice)
    if all_summarized:
        answer = "실시간 조회 기사와 일치하는 저장 3줄 요약을 찾았어요."
    elif matched_count:
        answer = (
            "실시간 조회 기사 중 저장된 기사는 3줄 요약으로, "
            "새 기사는 메타데이터로 보여드려요."
        )
    else:
        answer = "NAVER 검색 API에서 최신 증시 뉴스 메타데이터를 조회했어요."
    if scope_message is not None:
        answer = f"{scope_message}\n\n{answer}"
    limitations = [
        (
            "같은 시장의 직전 조회 결과를 짧게 재사용했어요."
            if snapshot.from_cache
            else "이번 질문 시점에 NAVER 검색 API를 조회했어요."
        ),
        (
            "저장된 기사는 수집 시점에 생성한 원문 기반 3줄 요약입니다."
            if matched_count
            else "기사 본문이 아닌 NAVER 제목·설명 메타데이터입니다."
        ),
        "뉴스 사실과 외부 의견은 연결된 원문에서 다시 확인해야 해요.",
    ]
    if not all_summarized:
        limitations.append("새 실시간 기사는 아직 원문 기반 3줄 요약 전입니다.")
    if scope_message is not None:
        limitations.append(scope_message)
    return (
        ChatResponse(
            intent=ChatIntent.NEWS,
            answer=answer,
            data_mode="news_summary" if all_summarized else "news_metadata",
            news_items=news_items,
            sections=[
                AnswerSection(
                    kind=SectionKind.EXTERNAL_OPINION,
                    title=(
                        "실시간 조회와 일치한 저장 뉴스 3줄 요약"
                        if all_summarized
                        else "실시간 NAVER 뉴스와 저장 요약"
                    ),
                    content="\n\n".join(content_blocks),
                    evidence_ids=_source_ids(sources),
                )
            ],
            sources=sources,
            limitations=limitations,
            conversation_context=(
                ConversationContext(
                    news=NewsConversationContext(
                        news_item_ids=stored_item_ids,
                        market_region=market_region,
                        shown_at=datetime.now(UTC),
                    )
                )
                if all_summarized
                else None
            ),
        ),
        topics_by_evidence,
    )


def _stored_summaries_for_live(
    snapshot: LiveMarketNewsSnapshot,
    news: NewsSearch | None,
) -> dict[str, NewsMatch]:
    if news is None:
        return {}
    try:
        return news.summarized_news_by_canonical_urls(
            tuple(item.canonical_url for item in snapshot.items)
        )
    except Exception:
        logger.warning("live_news_summary_lookup_failed", exc_info=True)
        return {}


def disclosure_response(
    request: ChatRequest,
    account_type: AccountType,
    *,
    disclosures: DisclosureSearch | None,
) -> ChatResponse:
    if disclosures is None:
        return ChatResponse(
            intent=ChatIntent.PROVIDER_DISCLOSURE,
            answer=(
                "원격 Supabase에 실제 공시 데이터가 없어 회사·사업자 수치를 "
                "표시하지 않았어요. fixture(테스트용 데이터)를 실제 데이터처럼 "
                "쓰지 않아요."
            ),
            data_mode="unavailable",
            limitations=["DATABASE_URL과 FSS 실적재가 필요합니다."],
        )
    rows = disclosures.search(
        request.message,
        account_type=account_type,
        limit=request.max_results,
    )
    if not rows:
        return ChatResponse(
            intent=ChatIntent.PROVIDER_DISCLOSURE,
            answer="조건에 맞는 최신 실제 공시를 찾지 못했어요.",
            data_mode="official_disclosure",
            limitations=["수집 상태와 질문의 회사명을 확인해 주세요."],
        )
    sources: list[SourceEvidence] = []
    numeric: list[NumericEvidence] = []
    lines: list[str] = []
    for index, row in enumerate(rows, start=1):
        evidence_id = f"disclosure:{index}"
        sources.append(
            SourceEvidence(
                evidence_id=evidence_id,
                label=f"FSS {_ACCOUNT_TYPE_LABELS[row.account_type]} 사업자 공시",
                locator=row.source_locator,
                publisher="금융감독원 통합연금포털",
                as_of=row.period_end,
                data_boundary=DataBoundary.OFFICIAL_DISCLOSURE,
            )
        )
        current_clause = (
            "당기 과거 수익률은 확인되지 않았고"
            if row.earn_rate_current_pct is None
            else (f"당기 과거 수익률은 {_decimal_text(row.earn_rate_current_pct)}%이고")
        )
        three_year_clause = (
            "3년 연환산 수익률도 확인되지 않았어요"
            if row.avg_earn_rate_3y_pct is None
            else (f"3년 연환산 수익률은 {_decimal_text(row.avg_earn_rate_3y_pct)}%예요")
        )
        lines.append(f"{row.company_name}의 {current_clause}, {three_year_clause}.")
        for label, value in (
            ("당기 과거 수익률", row.earn_rate_current_pct),
            ("3년 연환산 수익률", row.avg_earn_rate_3y_pct),
            ("1년 수수료율", row.fee_rate_1y_pct),
        ):
            if value is not None:
                numeric.append(
                    NumericEvidence(
                        label=f"{row.company_name} {label}",
                        value=value,
                        unit="%",
                        evidence_id=evidence_id,
                        basis=f"{row.year}Q{row.quarter} FSS 공시",
                    )
                )
    return ChatResponse(
        intent=ChatIntent.PROVIDER_DISCLOSURE,
        answer="과거 공시를 찾았어요. " + " ".join(lines),
        data_mode="official_disclosure",
        sections=[
            AnswerSection(
                kind=SectionKind.FACT,
                title="회사·사업자 과거 공시",
                content=" ".join(lines),
                evidence_ids=_source_ids(sources),
            )
        ],
        sources=sources,
        numeric_evidence=numeric,
        limitations=[
            "사업자 집계 공시이며 개별 상품 또는 개인 계좌 수익률이 아닙니다.",
            "과거 실적은 미래 수익을 의미하지 않습니다.",
        ],
    )


def news_response(
    request: ChatRequest,
    *,
    search_query: str,
    max_results: int,
    exclude_item_ids: tuple[str, ...] = (),
    preferred_topics: tuple[str, ...] = (),
    scope_notice: NewsScopeNotice | None = None,
    news: NewsSearch | None,
) -> ChatResponse:
    if news is None:
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer=("저장된 뉴스 정보가 없어 최신 뉴스 답변을 만들지 않았어요."),
            data_mode="unavailable",
            limitations=["NAVER 뉴스 수집과 DATABASE_URL이 필요합니다."],
        )
    is_market_news = search_query == "market" or search_query.startswith("market:")
    region = search_query.partition(":")[2] or None
    market_limit = min(max_results, 3)
    matches = (
        news.recent_market_news(
            region=region,
            days=5,
            limit=market_limit,
            exclude_item_ids=exclude_item_ids,
            preferred_topics=preferred_topics,
        )
        if is_market_news
        else news.latest_news(search_query, limit=request.max_results)
    )
    if not matches:
        scope_message = _scope_message(scope_notice)
        answer = (
            "최근 닷새간 요약이 끝난 증시 뉴스를 찾지 못했어요."
            if is_market_news
            else "해당 검색어로 저장된 뉴스 정보를 찾지 못했어요."
        )
        if scope_message is not None:
            answer = f"{scope_message}\n\n{answer}"
        limitations = ["기사 본문을 임의로 생성하지 않습니다."]
        if scope_message is not None:
            limitations.append(scope_message)
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer=answer,
            data_mode="news_summary" if is_market_news else "news_metadata",
            limitations=limitations,
        )
    sources = [
        SourceEvidence(
            evidence_id=f"news:{item.item_id}",
            label=item.title,
            locator=item.original_url,
            publisher="외부 뉴스 원문",
            as_of=item.published_at,
            data_boundary=(
                DataBoundary.NEWS_SUMMARY
                if is_market_news
                else DataBoundary.NEWS_METADATA
            ),
        )
        for item in matches
    ]
    lines = (
        [_news_summary_block(item, index) for index, item in enumerate(matches)]
        if is_market_news
        else [_news_metadata_line(item) for item in matches]
    )
    answer_intro = (
        "최근 증시 뉴스를 찾았어요." if is_market_news else "관련 뉴스를 찾았어요."
    )
    scope_message = _scope_message(scope_notice)
    if scope_message is not None:
        answer_intro = f"{scope_message}\n\n{answer_intro}"
    limitations = (
        [
            "기사 원문에서 수집 시점에 생성한 LLM 3줄 요약입니다.",
            "뉴스 사실과 외부 의견은 연결된 원문에서 다시 확인해야 합니다.",
        ]
        if is_market_news
        else [
            "기사 본문이 아닌 제목·요약·원문 링크 메타데이터입니다.",
            "뉴스 사실과 외부 의견은 원문에서 다시 확인해야 합니다.",
        ]
    )
    if is_market_news:
        limitations.append(_freshness_limitation(matches))
    if is_market_news and len(matches) < market_limit:
        limitations.append(
            "최근 닷새간 저장된 증시 기사가 세 건 미만이라 조회된 기사만 제공합니다."
        )
    if is_market_news and max_results > 3:
        limitations.append("증시 뉴스는 한 번에 최대 세 건까지 제공해요.")
    if is_market_news and preferred_topics:
        limitations.append(
            "로그인 사용자의 가상 목계좌 자산군과 연관된 뉴스 주제를 우선 정렬했습니다."
        )
    if scope_message is not None:
        limitations.append(scope_message)
    return ChatResponse(
        intent=ChatIntent.NEWS,
        answer=answer_intro + "\n\n" + "\n\n".join(lines),
        data_mode="news_summary" if is_market_news else "news_metadata",
        news_items=[
            ChatNewsItem(
                evidence_id=f"news:{item.item_id}",
                title=item.title,
                description=None if is_market_news else item.description,
                summary_lines=(list(item.summary_lines) if is_market_news else []),
                original_url=item.original_url,
                published_at=item.published_at,
            )
            for item in matches
        ],
        sections=[
            AnswerSection(
                kind=SectionKind.EXTERNAL_OPINION,
                title=(
                    "최근 닷새 한국·미국 증시 뉴스 3줄 요약"
                    if is_market_news
                    else "뉴스 검색 메타데이터"
                ),
                content="\n\n".join(lines),
                evidence_ids=_source_ids(sources),
            )
        ],
        sources=sources,
        limitations=limitations,
        conversation_context=(
            ConversationContext(
                news=NewsConversationContext(
                    news_item_ids=[item.item_id for item in matches],
                    market_region=(
                        MarketRegion(region) if region is not None else MarketRegion.ALL
                    ),
                    shown_at=datetime.now(UTC),
                )
            )
            if is_market_news
            else None
        ),
    )


def live_news_response(
    request: ChatRequest,
    *,
    search_query: str,
    max_results: int,
    preferred_topics: tuple[str, ...] = (),
    scope_notice: NewsScopeNotice | None = None,
    live_news: LiveNewsSearch | None,
    news: NewsSearch | None,
) -> ChatResponse:
    region = search_query.partition(":")[2] or None
    if live_news is not None:
        try:
            snapshot = live_news.fetch_market_news(
                region=region,
                limit=min(max_results, 3),
            )
        except LiveNewsUnavailable:
            logger.warning("live_news_lookup_failed")
        else:
            if snapshot.items:
                response, _ = _live_metadata_response(
                    snapshot,
                    scope_notice=scope_notice,
                    summaries_by_canonical_url=_stored_summaries_for_live(
                        snapshot, news
                    ),
                )
                return response

    stored = news_response(
        request,
        search_query=search_query,
        max_results=max_results,
        preferred_topics=preferred_topics,
        scope_notice=scope_notice,
        news=news,
    )
    return stored.model_copy(
        update={
            "answer": (
                "실시간 NAVER 조회를 사용할 수 없어 최근 저장 뉴스를 보여드려요.\n\n"
                + stored.answer
            ),
            "limitations": [
                *stored.limitations,
                "실시간 조회가 아니라 최근 저장 뉴스 기반입니다.",
            ],
        }
    )


def event_strategy_response(
    request: ChatRequest,
    *,
    search_query: str,
    max_results: int,
    preferred_topics: tuple[str, ...] = (),
    scope_notice: NewsScopeNotice | None = None,
    live_news: LiveNewsSearch | None,
    news: NewsSearch | None,
    theme_repository: EtfThemeRepository | None,
    portfolio_universe_loader: PortfolioUniverseLoader | None,
    news_event_outcomes: NewsEventOutcomeReader | None,
) -> ChatResponse:
    region = search_query.partition(":")[2] or None
    live_snapshot: LiveMarketNewsSnapshot | None = None
    topics_by_evidence: dict[str, tuple[str, ...]] = {}
    if live_news is not None:
        try:
            live_snapshot = live_news.fetch_market_news(
                region=region,
                limit=min(max_results, 3),
            )
        except LiveNewsUnavailable:
            logger.warning("live_news_lookup_failed")

    if live_snapshot is not None and live_snapshot.items:
        base, topics_by_evidence = _live_metadata_response(
            live_snapshot,
            scope_notice=scope_notice,
            summaries_by_canonical_url=_stored_summaries_for_live(live_snapshot, news),
        )
        base = base.model_copy(
            update={
                "answer": (
                    "NAVER 검색 API에서 최신 증시 뉴스 메타데이터를 조회했어요. "
                    "규칙 기반으로 이벤트와 ETF 산업·테마를 분류했어요."
                ),
                "data_mode": "live_news_event_strategy",
            }
        )
        scope_message = _scope_message(scope_notice)
        if scope_message is not None:
            base = base.model_copy(
                update={"answer": f"{scope_message}\n\n{base.answer}"}
            )
        return attach_event_strategy(
            base,
            request=request,
            topics_by_evidence=topics_by_evidence,
            theme_repository=theme_repository,
            portfolio_universe_loader=portfolio_universe_loader,
            news_event_outcomes=news_event_outcomes,
        )

    stored = news_response(
        request,
        search_query=search_query,
        max_results=max_results,
        preferred_topics=preferred_topics,
        scope_notice=scope_notice,
        news=news,
    )
    if not stored.news_items:
        return stored.model_copy(
            update={
                "answer": (
                    "실시간 NAVER 조회와 저장 뉴스 조회에서 모두 "
                    "사용 가능한 증시 뉴스를 찾지 못했어요."
                ),
                "limitations": [
                    *stored.limitations,
                    "뉴스를 임의로 생성해 이벤트 전략을 만들지 않아요.",
                ],
            }
        )
    stored = stored.model_copy(
        update={
            "data_mode": "stored_news_event_strategy",
            "answer": (
                "실시간 NAVER 조회를 사용할 수 없어 최근 저장 뉴스를 "
                "이벤트와 ETF 산업·테마로 분류했어요."
            ),
            "limitations": [
                *stored.limitations,
                "실시간 조회가 아니라 최근 저장 뉴스 기반입니다.",
            ],
        }
    )
    return attach_event_strategy(
        stored,
        request=request,
        topics_by_evidence=topics_by_evidence,
        theme_repository=theme_repository,
        portfolio_universe_loader=portfolio_universe_loader,
        news_event_outcomes=news_event_outcomes,
    )


def attach_event_strategy(
    response: ChatResponse,
    *,
    request: ChatRequest,
    topics_by_evidence: dict[str, tuple[str, ...]],
    theme_repository: EtfThemeRepository | None,
    portfolio_universe_loader: PortfolioUniverseLoader | None,
    news_event_outcomes: NewsEventOutcomeReader | None,
) -> ChatResponse:
    policy_source_id = "policy:live_news_event_strategy"
    catalog = theme_repository.catalog if theme_repository is not None else None
    rows: list[list[str]] = []
    news_source_ids: list[str] = []
    theme_ids: list[str] = []
    for item in response.news_items:
        classification = classify_news_event(
            title=item.title,
            description=(item.description or " ".join(item.summary_lines)),
            topics=topics_by_evidence.get(item.evidence_id, ()),
            theme_catalog=catalog,
        )
        theme_names = []
        if theme_repository is not None:
            theme_names = [
                theme.name
                for theme_id in classification.theme_ids
                if (theme := theme_repository.get(theme_id)) is not None
            ]
        etf_labels = theme_names or list(classification.etf_groups)
        theme_ids.extend(classification.theme_ids)
        rows.append(
            [
                item.title,
                " · ".join(classification.event_labels),
                " · ".join(etf_labels),
                classification.check,
            ]
        )
        news_source_ids.append(item.evidence_id)

    survey = request.survey_profile or (
        request.conversation_context.survey_profile
        if request.conversation_context is not None
        else None
    )
    tactical_allowed = (
        survey is not None
        and _RISK_PROFILE_RANKS[survey.risk_profile]
        >= _RISK_PROFILE_RANKS[EducationalRiskProfile.ACTIVE]
    )
    if tactical_allowed:
        strategy_intro = (
            "현재 설문 성향 범위에서 전술 관찰 가이드를 제공해요. "
            "뉴스만으로 상품이나 비중을 결정하지 않아요."
        )
        strategy_items = [
            "기존 장기 코어 배분과 규칙 엔진 목표비중을 먼저 유지",
            "공식 발표·가격·거래대금·ETF 구성종목을 함께 확인",
            "상품 비교는 별도 ETF 테마 정보에서 확인하고 뉴스와 연결해 개인화하지 않기",
            "계좌별 위험자산 한도와 사용자 투자성향을 먼저 적용",
            "리밸런싱은 목표비중 이탈과 신규 납입금 기준으로 별도 계산",
        ]
    elif survey is None:
        strategy_intro = (
            "투자성향 설문이 없어 이벤트·테마 분류만 제공해요. "
            "공격형 전술 운용 가이드는 성향 확인 뒤에 연결해요."
        )
        strategy_items = [
            "뉴스 단독 매수·매도 금지",
            "공식 발표와 ETF 구성종목을 먼저 확인",
        ]
    else:
        strategy_intro = (
            "현재 설문 성향보다 공격적인 이벤트 전술은 제안하지 않아요. "
            "뉴스와 ETF 산업·테마 분류만 참고용으로 제공해요."
        )
        strategy_items = [
            "장기 코어 배분과 정기 리밸런싱 원칙 유지",
            "뉴스 단독 매수·매도 금지",
        ]

    policy_source = SourceEvidence(
        evidence_id=policy_source_id,
        label=f"뉴스 이벤트 전략 가이드 정책 {NEWS_EVENT_POLICY_VERSION}",
        locator="backend/app/chat/news_event_strategy.py",
        publisher="연금 코파일럿 규칙 정책",
        as_of=NEWS_EVENT_POLICY_AS_OF,
        data_boundary=DataBoundary.ENGINE,
    )
    outcome_rows = (
        news_event_outcomes.list_for_theme_ids(tuple(dict.fromkeys(theme_ids)))
        if news_event_outcomes is not None and theme_ids
        else []
    )
    outcome_section, outcome_sources = _historical_outcome_section(outcome_rows)
    sections = [
        *response.sections,
        AnswerSection(
            kind=SectionKind.SERVICE_EXPLANATION,
            title="이벤트·ETF 산업/테마 분류",
            content=(
                "기사 메타데이터와 기존 ETF 테마 카탈로그를 규칙으로 "
                "연결한 관찰 목록입니다."
            ),
            evidence_ids=[*news_source_ids, policy_source_id],
            blocks=[
                AnswerBlock(
                    kind=AnswerBlockKind.TABLE,
                    headers=["뉴스", "이벤트", "ETF 산업·테마", "추가 확인"],
                    rows=rows,
                )
            ],
        ),
        outcome_section,
        AnswerSection(
            kind=SectionKind.SERVICE_EXPLANATION,
            title="이벤트 드리븐 운용 가이드",
            content=strategy_intro,
            evidence_ids=[policy_source_id],
            blocks=[
                AnswerBlock(
                    kind=AnswerBlockKind.BULLETS,
                    title="운용 체크",
                    items=strategy_items,
                )
            ],
        ),
    ]
    return response.model_copy(
        update={
            "sections": sections,
            "sources": [*response.sources, policy_source, *outcome_sources],
            "limitations": [
                *response.limitations,
                (
                    "이벤트 분류는 상품 추천·목표비중·방향성·수익률 예측이나 "
                    "자동운용 신호가 아닙니다."
                ),
            ],
            "conversation_context": ConversationContext(
                account_type=(survey.account_type if survey is not None else None),
                last_intent=ChatIntent.NEWS,
                survey_profile=survey,
            ),
        }
    )


def _historical_outcome_section(
    rows: list[NewsEventOutcomeRecord],
) -> tuple[AnswerSection, list[SourceEvidence]]:
    if not rows:
        return (
            AnswerSection(
                kind=SectionKind.SERVICE_EXPLANATION,
                title="과거 뉴스 이벤트 성과 검증",
                content=(
                    "현재 테마와 일치하는 검증 완료 과거 이벤트 표본이 아직 없어 "
                    "수익률 수치를 표시하지 않습니다."
                ),
                blocks=[
                    AnswerBlock(
                        kind=AnswerBlockKind.CALLOUT,
                        text=(
                            "표본이 적거나 원본·총수익률 근거가 없으면 "
                            "결과를 만들지 않습니다."
                        ),
                    )
                ],
            ),
            [],
        )
    sources: list[SourceEvidence] = []
    table_rows: list[list[str]] = []
    for row in rows:
        evidence_id = (
            f"news-event-outcome:{row.event_key}:{row.isu_code}:{row.horizon_months}"
        )
        sources.append(
            SourceEvidence(
                evidence_id=evidence_id,
                label=f"과거 뉴스 이벤트 성과 · {row.event_source_label}",
                locator=row.event_source_url,
                publisher="공식 기사·검증 총수익률 원장",
                as_of=row.history_source_as_of or row.event_source_as_of,
                data_boundary=DataBoundary.ENGINE,
            )
        )
        table_rows.append(
            [
                row.occurred_on.isoformat(),
                row.isu_name,
                f"{row.horizon_months}개월",
                f"{row.total_return_percent:.2f}%",
                f"{row.maximum_drawdown_percent:.2f}%",
                f"{row.peer_median_total_return_percent:.2f}%",
                str(row.peer_sample_count),
            ]
        )
    evidence_ids = [source.evidence_id for source in sources]
    return (
        AnswerSection(
            kind=SectionKind.SERVICE_EXPLANATION,
            title="과거 뉴스 이벤트 성과 검증",
            content=(
                "아래는 과거 이벤트 뒤의 실현 총수익률과 최대낙폭입니다. "
                "미래 수익 예측이나 자동 비중 변경에는 사용하지 않습니다."
            ),
            evidence_ids=evidence_ids,
            blocks=[
                AnswerBlock(
                    kind=AnswerBlockKind.TABLE,
                    headers=[
                        "이벤트일",
                        "ETF",
                        "기간",
                        "총수익률",
                        "최대낙폭",
                        "비교군 중앙값",
                        "표본",
                    ],
                    rows=table_rows,
                )
            ],
        ),
        sources,
    )


def news_follow_up_response(
    request: ChatRequest,
    follow_up: NewsFollowUp,
    *,
    news: NewsSearch | None,
) -> ChatResponse:
    context = request.conversation_context
    news_context = context.news if context is not None else None
    if news_context is None:
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer="현재 세션에서 먼저 표시된 증시 뉴스가 없어요.",
            data_mode="news_follow_up",
            limitations=["먼저 증시 뉴스를 요청해 주세요."],
        )
    if follow_up.action == NewsFollowUpAction.CLARIFY:
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer=(
                "현재 세션에 여러 뉴스가 있어요. "
                "첫 번째, 두 번째처럼 확인할 기사를 지정해 주세요."
            ),
            data_mode="news_follow_up",
            limitations=["여러 기사 중 대상을 임의로 선택하지 않아요."],
            conversation_context=ConversationContext(news=news_context),
        )
    if news is None:
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer="저장된 뉴스 데이터에 연결할 수 없어요.",
            data_mode="unavailable",
            limitations=["DATABASE_URL과 저장된 뉴스 데이터가 필요해요."],
            conversation_context=ConversationContext(news=news_context),
        )

    selected = [
        (index, news_context.news_item_ids[index]) for index in follow_up.item_indexes
    ]
    matches = news.news_by_ids(tuple(item_id for _, item_id in selected))
    matches_by_id = {item.item_id: item for item in matches}
    ordered = [
        (index, matches_by_id[item_id])
        for index, item_id in selected
        if item_id in matches_by_id
    ]
    if len(ordered) != len(selected):
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer=(
                "세션에서 참조한 뉴스가 현재 저장소에 없어 다시 불러오지 "
                "못했어요. 최신 증시 뉴스를 다시 요청해 주세요."
            ),
            data_mode="unavailable",
            limitations=["만료된 뉴스 내용을 임의로 복원하지 않아요."],
            conversation_context=ConversationContext(news=news_context),
        )
    if any(len(item.summary_lines) != 3 for _, item in ordered):
        return ChatResponse(
            intent=ChatIntent.NEWS,
            answer="검증된 3줄 요약이 없어 후속 비교를 만들지 않았어요.",
            data_mode="unavailable",
            limitations=["기사 내용을 임의로 보완하지 않아요."],
            conversation_context=ConversationContext(news=news_context),
        )

    sources = [
        SourceEvidence(
            evidence_id=f"news:{item.item_id}",
            label=item.title,
            locator=item.original_url,
            publisher="외부 뉴스 원문",
            as_of=item.published_at,
            data_boundary=DataBoundary.NEWS_SUMMARY,
        )
        for _, item in ordered
    ]
    if follow_up.action == NewsFollowUpAction.SOURCE:
        lines = [
            (
                f"{index + 1}번째 뉴스 — {item.title}\n"
                "발행일: "
                + (
                    item.published_at.date().isoformat()
                    if item.published_at is not None
                    else "확인되지 않음"
                )
                + f"\n원문 링크: {item.original_url}"
            )
            for index, item in ordered
        ]
        title = "뉴스 출처와 발행일"
    elif follow_up.action == NewsFollowUpAction.COMPARE:
        lines = [_news_comparison_block(item, index) for index, item in ordered]
        lines.insert(
            0,
            "기사별 검증된 메타데이터와 요약을 같은 항목으로 나란히 비교해요.",
        )
        title = "세션 뉴스 비교"
    else:
        lines = [_news_summary_block(item, index) for index, item in ordered]
        title = "선택한 뉴스 다시 보기"
    focus_id = selected[0][1] if len(selected) == 1 else None
    updated_news_context = news_context.model_copy(
        update={"focus_news_item_id": focus_id}
    )
    answer = "\n\n".join(lines)
    return ChatResponse(
        intent=ChatIntent.NEWS,
        answer=answer,
        data_mode="news_follow_up",
        news_items=[
            ChatNewsItem(
                evidence_id=f"news:{item.item_id}",
                title=item.title,
                summary_lines=list(item.summary_lines),
                original_url=item.original_url,
                published_at=item.published_at,
            )
            for _, item in ordered
        ],
        sections=[
            AnswerSection(
                kind=SectionKind.EXTERNAL_OPINION,
                title=title,
                content=answer,
                evidence_ids=_source_ids(sources),
            )
        ],
        sources=sources,
        limitations=[
            "이 세션에서 앞서 보여드린 뉴스만 다시 조회했어요.",
            "뉴스 사실과 외부 의견은 연결된 원문에서 다시 확인해야 해요.",
        ],
        conversation_context=ConversationContext(news=updated_news_context),
    )
