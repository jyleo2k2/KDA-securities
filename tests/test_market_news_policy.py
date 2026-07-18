from datetime import UTC, datetime, timedelta

import pytest

from backend.app.ingestion.market_news_policy import (
    MARKET_QUERIES,
    SEMANTIC_DUPLICATE_THRESHOLD,
    MarketNewsCandidate,
    build_candidate,
    canonicalize_url,
    embed_candidates,
    select_market_candidates,
)
from backend.app.ingestion.naver_news import NaverNewsItem

NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)


def _item(
    title: str,
    *,
    original_url: str = "https://www.yna.co.kr/view/AKR1?utm_source=test",
    portal_url: str = "https://n.news.naver.com/mnews/article/001/0001",
    published_at: datetime = NOW - timedelta(hours=2),
) -> NaverNewsItem:
    return NaverNewsItem(
        title=title,
        description=("한국은행이 기준금리를 발표했고 코스피는 2% 움직였다고 집계했다."),
        original_url=original_url,
        portal_url=portal_url,
        published_at=published_at,
        raw_metadata={},
    )


def _vector(index: int) -> tuple[float, ...]:
    values = [0.0] * 1024
    values[index] = 1.0
    return tuple(values)


def _candidate(
    index: int,
    *,
    region: str,
    publisher: str,
    topic: str,
    embedding: tuple[float, ...] | None = None,
) -> MarketNewsCandidate:
    item = NaverNewsItem(
        title=f"시장 사건 {index}",
        description="공식 발표와 시장 반응",
        original_url=f"https://example.test/{index}",
        portal_url=f"https://n.news.naver.com/{index}",
        published_at=NOW - timedelta(minutes=index),
        raw_metadata={},
    )
    return MarketNewsCandidate(
        item=item,
        search_query="시장 뉴스",
        region=region,
        topics=(topic,),
        publisher=publisher,
        canonical_url=f"https://example.test/{index}",
        normalized_title_hash=f"{index:064x}",
        event_fingerprint=f"{index + 1000:064x}",
        score=100 - index,
        reasons=("market_impact:30",),
        embedding=embedding or _vector(index),
    )


def test_build_candidate_enforces_age_naver_host_publisher_and_quality() -> None:
    query = MARKET_QUERIES[3]
    candidate = build_candidate(
        _item("한국은행 기준금리 발표에 코스피 2% 변동"),
        query,
        now=NOW,
    )

    assert candidate is not None
    assert candidate.region == "kr"
    assert candidate.publisher == "연합뉴스"
    assert candidate.score >= 70
    assert len(candidate.reasons) == 6
    assert "utm_source" not in candidate.canonical_url

    assert (
        build_candidate(
            _item(
                "한국은행 기준금리 발표에 코스피 2% 변동",
                portal_url="https://publisher.example/article",
            ),
            query,
            now=NOW,
        )
        is None
    )
    assert (
        build_candidate(
            _item(
                "한국은행 기준금리 발표에 코스피 2% 변동",
                published_at=NOW - timedelta(hours=25),
            ),
            query,
            now=NOW,
        )
        is None
    )
    assert (
        build_candidate(
            _item("오늘의 급등주 매수 추천 이벤트"),
            query,
            now=NOW,
        )
        is None
    )


def test_canonicalize_url_keeps_article_identity_and_removes_tracking() -> None:
    canonical = canonicalize_url(
        "HTTPS://WWW.MK.CO.KR/news/stock/1/?id=7&utm_campaign=daily#top"
    )

    assert canonical == "https://www.mk.co.kr/news/stock/1?id=7"


def test_embed_candidates_requires_bge_m3_dimension() -> None:
    candidate = _candidate(1, region="kr", publisher="연합뉴스", topic="indices")

    class BadEmbedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    with pytest.raises(ValueError, match="1024"):
        embed_candidates([candidate], BadEmbedder())


def test_selection_blocks_exact_and_semantic_duplicates_and_balances_regions() -> None:
    topics = ("indices", "flows", "macro", "earnings", "fx_rates", "market_rules")
    publishers = ("연합뉴스", "뉴시스", "매일경제", "한국경제", "서울경제", "KBS")
    candidates = [
        _candidate(
            index,
            region="kr" if index < 10 else "us",
            publisher=publishers[index % len(publishers)],
            topic=topics[index % len(topics)],
        )
        for index in range(20)
    ]
    semantic_duplicate = _candidate(
        20,
        region="us",
        publisher="YTN",
        topic="macro",
        embedding=candidates[0].embedding,
    )
    assert (
        sum(
            left * right
            for left, right in zip(
                semantic_duplicate.embedding, candidates[0].embedding, strict=True
            )
        )
        >= SEMANTIC_DUPLICATE_THRESHOLD
    )

    selected = select_market_candidates(
        [*candidates, semantic_duplicate],
        existing_urls={candidates[1].canonical_url},
        existing_title_hashes={candidates[2].normalized_title_hash},
        existing_event_fingerprints={candidates[3].event_fingerprint},
        limit=20,
    )

    assert candidates[1] not in selected
    assert candidates[2] not in selected
    assert candidates[3] not in selected
    assert semantic_duplicate not in selected
    assert sum(item.region == "kr" for item in selected) >= 7
    assert sum(item.region == "us" for item in selected) >= 8
    assert all(
        sum(item.publisher == publisher for item in selected) <= 3
        for publisher in publishers
    )
