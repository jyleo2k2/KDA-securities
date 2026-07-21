"""Low-latency NAVER market-news lookup for explicit live strategy questions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import Lock

import httpx

from ..ingestion.market_news_policy import MarketQuery, build_candidate
from ..ingestion.naver_news import NaverNewsApiError, fetch_naver_news

LIVE_NEWS_CACHE_TTL = timedelta(seconds=60)
LIVE_MARKET_QUERIES = (
    MarketQuery("한국 증시", "kr", "indices"),
    MarketQuery("미국 증시", "us", "indices"),
)


class LiveNewsUnavailable(RuntimeError):
    """A sanitized live-news lookup failure."""


@dataclass(frozen=True, slots=True)
class LiveMarketNewsItem:
    item_id: str
    canonical_url: str
    title: str
    description: str | None
    original_url: str
    published_at: datetime
    publisher: str
    region: str
    topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LiveMarketNewsSnapshot:
    items: tuple[LiveMarketNewsItem, ...]
    fetched_at: datetime
    from_cache: bool = False


class NaverLiveNewsSearch:
    """Fetch two broad market queries and reuse them for at most 60 seconds."""

    def __init__(self, *, client_id: str, client_secret: str) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise ValueError("NAVER live-news credentials are required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._cache: dict[str, LiveMarketNewsSnapshot] = {}
        self._lock = Lock()

    def fetch_market_news(
        self,
        *,
        region: str | None,
        limit: int,
    ) -> LiveMarketNewsSnapshot:
        if region not in {None, "kr", "us"}:
            raise ValueError("region must be kr, us or None")
        if not 1 <= limit <= 3:
            raise ValueError("live-news limit must be between 1 and 3")
        now = datetime.now(UTC)
        cache_key = region or "all"
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None and now - cached.fetched_at <= LIVE_NEWS_CACHE_TTL:
                return replace(cached, from_cache=True)

        queries = tuple(
            query
            for query in LIVE_MARKET_QUERIES
            if region is None or query.region == region
        )
        candidates = []
        failures = 0
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            for query in queries:
                try:
                    response = fetch_naver_news(
                        client,
                        client_id=self._client_id,
                        client_secret=self._client_secret,
                        query=query.query,
                        display=50,
                        start=1,
                        sort="date",
                    )
                except NaverNewsApiError:
                    failures += 1
                    continue
                for item in response.items:
                    candidate = build_candidate(item, query, now=now)
                    if candidate is not None:
                        candidates.append(candidate)

        if failures == len(queries):
            raise LiveNewsUnavailable("NAVER live-news lookup failed")

        unique = {}
        for candidate in candidates:
            previous = unique.get(candidate.canonical_url)
            if previous is None or (
                candidate.score,
                candidate.item.published_at,
            ) > (previous.score, previous.item.published_at):
                unique[candidate.canonical_url] = candidate
        ranked = sorted(
            unique.values(),
            key=lambda candidate: (candidate.score, candidate.item.published_at),
            reverse=True,
        )[:limit]
        snapshot = LiveMarketNewsSnapshot(
            items=tuple(
                LiveMarketNewsItem(
                    item_id=candidate.normalized_title_hash,
                    canonical_url=candidate.canonical_url,
                    title=candidate.item.title,
                    description=candidate.item.description,
                    original_url=candidate.item.original_url,
                    published_at=candidate.item.published_at,
                    publisher=candidate.publisher,
                    region=candidate.region,
                    topics=candidate.topics,
                )
                for candidate in ranked
            ),
            fetched_at=now,
        )
        with self._lock:
            self._cache[cache_key] = snapshot
        return snapshot
