from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from .naver_news import NaverNewsItem

SELECTION_POLICY_VERSION = "market-news-v1"
MAX_DAILY_ARTICLES = 20
MIN_SELECTION_SCORE = 70
SEMANTIC_DUPLICATE_THRESHOLD = 0.90


@dataclass(frozen=True, slots=True)
class MarketQuery:
    query: str
    region: str
    topic: str


MARKET_QUERIES = (
    MarketQuery("한국 증시", "kr", "indices"),
    MarketQuery("코스피 코스닥", "kr", "indices"),
    MarketQuery("외국인 수급 증시", "kr", "flows"),
    MarketQuery("한국은행 금리 증시", "kr", "monetary_policy"),
    MarketQuery("원달러 환율 증시", "kr", "fx_rates"),
    MarketQuery("한국 기업 실적 증시", "kr", "earnings"),
    MarketQuery("한국 증시 규제 거래소", "kr", "market_rules"),
    MarketQuery("미국 증시", "us", "indices"),
    MarketQuery("뉴욕 증시 S&P500 나스닥", "us", "indices"),
    MarketQuery("연준 FOMC 증시", "us", "monetary_policy"),
    MarketQuery("미국 CPI 증시", "us", "macro"),
    MarketQuery("미국 고용 증시", "us", "macro"),
    MarketQuery("미국 기업 실적 증시", "us", "earnings"),
    MarketQuery("미국 증시 규제 거래소", "us", "market_rules"),
)

# NAVER 검색 결과 중 원문 발행 주체를 도메인으로 확인할 수 있는 매체만 허용한다.
# 값의 두 번째 원소는 출처 신뢰도 점수(15점 만점)다.
_PUBLISHERS: dict[str, tuple[str, int]] = {
    "yna.co.kr": ("연합뉴스", 15),
    "newsis.com": ("뉴시스", 15),
    "reuters.com": ("로이터", 15),
    "bloomberg.com": ("블룸버그", 15),
    "mk.co.kr": ("매일경제", 15),
    "hankyung.com": ("한국경제", 15),
    "sedaily.com": ("서울경제", 15),
    "edaily.co.kr": ("이데일리", 15),
    "asiae.co.kr": ("아시아경제", 12),
    "fnnews.com": ("파이낸셜뉴스", 12),
    "mt.co.kr": ("머니투데이", 12),
    "bizwatch.co.kr": ("비즈워치", 12),
    "businesspost.co.kr": ("비즈니스포스트", 12),
    "thebell.co.kr": ("더벨", 12),
    "etnews.com": ("전자신문", 12),
    "chosun.com": ("조선일보", 12),
    "joongang.co.kr": ("중앙일보", 12),
    "donga.com": ("동아일보", 12),
    "hani.co.kr": ("한겨레", 12),
    "khan.co.kr": ("경향신문", 12),
    "kbs.co.kr": ("KBS", 12),
    "imbc.com": ("MBC", 12),
    "sbs.co.kr": ("SBS", 12),
    "ytn.co.kr": ("YTN", 12),
    "jtbc.co.kr": ("JTBC", 12),
}

_TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
}
_TITLE_NOISE = re.compile(
    r"\[[^\]]{1,30}\]|\([^)]{1,20}\)|(?<![가-힣])(?:속보|단독|종합)(?![가-힣])",
    re.I,
)
_NON_WORD = re.compile(r"[^0-9a-z가-힣]+", re.I)
_NUMBER = re.compile(r"\d[\d,.]*(?:%|원|달러|명|건|배|포인트)?")
_MARKET_ANCHOR = re.compile(
    r"증시|주가|코스피|코스닥|나스닥|S\s*&\s*P|다우|상장|시가총액|"
    r"외국인|기관\s*수급|환율|국채|금리|연준|한국은행|FOMC|CPI|"
    r"고용|실적|매출|영업이익|반도체|거래소",
    re.I,
)
_IMPACT_HIGH = re.compile(
    r"금리|기준금리|연준|FOMC|한국은행|CPI|물가|고용|환율|국채|"
    r"관세|제재|전쟁|규제|거래소|서킷브레이커|실적|영업이익|M&A|인수합병",
    re.I,
)
_IMPACT_MEDIUM = re.compile(
    r"외국인|기관|수급|반도체|자동차|바이오|은행|에너지|공급망|"
    r"코스피|코스닥|나스닥|S\s*&\s*P|다우",
    re.I,
)
_ATTRIBUTION = re.compile(
    r"발표|공시|밝혔|결정|집계|통계|보고서|의결|확정|기록|전망",
    re.I,
)
_EXCLUDED = re.compile(
    r"추천주|종목\s*추천|매수\s*추천|목표가|유망주|급등주|대박|"
    r"찌라시|카더라|루머|체험단|이벤트|세미나|광고|"
    r"보험|부동산|아파트|연금저축|퇴직연금|IRP",
    re.I,
)
_CRYPTO = re.compile(r"비트코인|이더리움|가상자산|암호화폐", re.I)
_TOPIC_PATTERNS = {
    "indices": re.compile(r"증시|코스피|코스닥|나스닥|S\s*&\s*P|다우", re.I),
    "monetary_policy": re.compile(r"연준|FOMC|한국은행|기준금리|금리", re.I),
    "macro": re.compile(r"CPI|물가|고용|GDP|소비|제조업", re.I),
    "fx_rates": re.compile(r"환율|원[·/]?달러|국채|채권\s*금리", re.I),
    "flows": re.compile(r"외국인|기관|수급|순매수|순매도", re.I),
    "earnings": re.compile(r"실적|매출|영업이익|순이익|어닝", re.I),
    "sector": re.compile(r"반도체|자동차|바이오|은행|에너지|공급망", re.I),
    "market_rules": re.compile(r"규제|거래소|상장|공매도|관세|제재", re.I),
}
_EVENT_STOPWORDS = {
    "한국",
    "미국",
    "증시",
    "시장",
    "주가",
    "관련",
    "오늘",
    "전망",
    "기자",
    "종합",
    "속보",
}


class BatchEmbedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class MarketNewsCandidate:
    item: NaverNewsItem
    search_query: str
    region: str
    topics: tuple[str, ...]
    publisher: str
    canonical_url: str
    normalized_title_hash: str
    event_fingerprint: str
    score: int
    reasons: tuple[str, ...]
    embedding: tuple[float, ...] = ()

    @property
    def embedding_text(self) -> str:
        description = self.item.description or ""
        return f"{self.item.title}\n{description}".strip()


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in _TRACKING_QUERY_KEYS
        ]
    )
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.casefold(), parsed.netloc.casefold(), path, query, "")
    )


def _publisher(url: str) -> tuple[str, int] | None:
    hostname = (urlsplit(url).hostname or "").casefold()
    for domain, publisher in _PUBLISHERS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return publisher
    return None


def _is_naver_news_url(url: str | None) -> bool:
    hostname = (urlsplit(url or "").hostname or "").casefold()
    return hostname == "n.news.naver.com"


def _normalized_title(title: str) -> str:
    without_noise = _TITLE_NOISE.sub(" ", title.casefold())
    return " ".join(_NON_WORD.sub(" ", without_noise).split())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event_fingerprint(title: str, region: str, published_at: datetime) -> str:
    tokens = [
        token
        for token in _normalized_title(title).split()
        if len(token) > 1 and token not in _EVENT_STOPWORDS
    ]
    core = " ".join(sorted(dict.fromkeys(tokens))[:12])
    event_day = published_at.astimezone(UTC).date().isoformat()
    return _sha256(f"{region}|{event_day}|{core}")


def build_candidate(
    item: NaverNewsItem,
    query: MarketQuery,
    *,
    now: datetime | None = None,
) -> MarketNewsCandidate | None:
    reference_time = now or datetime.now(UTC)
    if reference_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    age = reference_time - item.published_at.astimezone(reference_time.tzinfo)
    if age < timedelta(minutes=-5) or age > timedelta(hours=24):
        return None
    if not _is_naver_news_url(item.portal_url):
        return None
    canonical_url = canonicalize_url(item.original_url)
    publisher = _publisher(canonical_url)
    if not canonical_url or publisher is None:
        return None

    text = f"{item.title} {item.description or ''}"
    if _EXCLUDED.search(text):
        return None
    if _CRYPTO.search(text) and not _MARKET_ANCHOR.search(text):
        return None
    if not _MARKET_ANCHOR.search(text):
        return None

    topics = tuple(
        topic for topic, pattern in _TOPIC_PATTERNS.items() if pattern.search(text)
    )
    if not topics:
        return None

    relevance = 20
    if _IMPACT_HIGH.search(text):
        impact = 30
    elif _IMPACT_MEDIUM.search(text):
        impact = 22
    else:
        impact = 15
    has_number = _NUMBER.search(text) is not None
    has_attribution = _ATTRIBUTION.search(text) is not None
    specificity = 15 if has_number and has_attribution else 10 if has_number else 6
    publisher_name, reliability = publisher
    hours = max(age.total_seconds() / 3600, 0)
    freshness = 10 if hours <= 6 else 8 if hours <= 12 else 6
    novelty = 10
    score = relevance + impact + specificity + reliability + freshness + novelty
    if score < MIN_SELECTION_SCORE:
        return None

    reasons = (
        f"market_impact:{impact}",
        f"direct_relevance:{relevance}",
        f"factual_specificity:{specificity}",
        f"source_reliability:{reliability}",
        f"freshness:{freshness}",
        f"novelty:{novelty}",
    )
    normalized_title = _normalized_title(item.title)
    return MarketNewsCandidate(
        item=item,
        search_query=query.query,
        region=query.region,
        topics=tuple(dict.fromkeys((query.topic, *topics))),
        publisher=publisher_name,
        canonical_url=canonical_url,
        normalized_title_hash=_sha256(normalized_title),
        event_fingerprint=_event_fingerprint(
            item.title, query.region, item.published_at
        ),
        score=score,
        reasons=reasons,
    )


def embed_candidates(
    candidates: list[MarketNewsCandidate], embedder: BatchEmbedder
) -> list[MarketNewsCandidate]:
    if not candidates:
        return []
    vectors = embedder.embed([candidate.embedding_text for candidate in candidates])
    if len(vectors) != len(candidates):
        raise ValueError("embedder returned an unexpected vector count")
    embedded: list[MarketNewsCandidate] = []
    for candidate, vector in zip(candidates, vectors, strict=True):
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"{EMBEDDING_MODEL} must return {EMBEDDING_DIMENSIONS} dimensions"
            )
        embedded.append(replace(candidate, embedding=tuple(vector)))
    return embedded


def _similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def select_market_candidates(
    candidates: list[MarketNewsCandidate],
    *,
    existing_urls: set[str] | None = None,
    existing_title_hashes: set[str] | None = None,
    existing_event_fingerprints: set[str] | None = None,
    existing_embeddings: list[tuple[float, ...]] | None = None,
    limit: int | None = MAX_DAILY_ARTICLES,
) -> list[MarketNewsCandidate]:
    if limit is not None and not 1 <= limit <= MAX_DAILY_ARTICLES:
        raise ValueError(f"limit must be between 1 and {MAX_DAILY_ARTICLES}")
    urls = existing_urls or set()
    title_hashes = existing_title_hashes or set()
    events = existing_event_fingerprints or set()
    stored_vectors = existing_embeddings or []

    exact_unique: dict[tuple[str, str], MarketNewsCandidate] = {}
    for candidate in candidates:
        if (
            candidate.canonical_url in urls
            or candidate.normalized_title_hash in title_hashes
            or candidate.event_fingerprint in events
        ):
            continue
        key = (candidate.canonical_url, candidate.normalized_title_hash)
        previous = exact_unique.get(key)
        if previous is None or (candidate.score, candidate.item.published_at) > (
            previous.score,
            previous.item.published_at,
        ):
            exact_unique[key] = candidate

    ranked = sorted(
        exact_unique.values(),
        key=lambda candidate: (candidate.score, candidate.item.published_at),
        reverse=True,
    )
    selected: list[MarketNewsCandidate] = []
    publisher_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()
    selected_events: set[str] = set()

    def try_add(candidate: MarketNewsCandidate) -> bool:
        primary_topic = candidate.topics[0]
        if publisher_counts[candidate.publisher] >= 3:
            return False
        if topic_counts[primary_topic] >= 3:
            return False
        if candidate.event_fingerprint in selected_events:
            return False
        if any(
            _similarity(candidate.embedding, vector) >= SEMANTIC_DUPLICATE_THRESHOLD
            for vector in (*stored_vectors, *(item.embedding for item in selected))
        ):
            return False
        selected.append(candidate)
        publisher_counts[candidate.publisher] += 1
        topic_counts[primary_topic] += 1
        selected_events.add(candidate.event_fingerprint)
        return True

    for region in ("kr", "us"):
        for candidate in ranked:
            if candidate.region != region:
                continue
            if sum(item.region == region for item in selected) >= 8:
                break
            try_add(candidate)
    for candidate in ranked:
        if limit is not None and len(selected) >= limit:
            break
        if candidate not in selected:
            try_add(candidate)
    return selected if limit is None else selected[:limit]
