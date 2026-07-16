import html
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from backend.app.text_normalization import normalize_search_text

NAVER_NEWS_ENDPOINT = "https://naverapihub.apigw.ntruss.com/search/v1/news"
_HTML_TAG = re.compile(r"<[^>]*>")
_ALLOWED_METADATA_FIELDS = (
    "title",
    "originallink",
    "link",
    "description",
    "pubDate",
)


class NaverNewsApiError(RuntimeError):
    """A sanitized NAVER API HUB transport or response-contract failure."""


class NaverNewsAllItemsRejectedError(NaverNewsApiError):
    """Every returned item failed metadata validation."""

    def __init__(
        self,
        *,
        total: int,
        raw_item_count: int,
        rejected_reasons: tuple[str, ...],
    ) -> None:
        super().__init__("NAVER news response contained no valid items")
        self.total = total
        self.raw_item_count = raw_item_count
        self.rejected_reasons = rejected_reasons

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_reasons)


@dataclass(frozen=True, slots=True)
class NaverNewsItem:
    title: str
    description: str | None
    original_url: str
    portal_url: str | None
    published_at: datetime
    raw_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NaverNewsResponse:
    total: int
    start: int
    display: int
    raw_item_count: int
    items: list[NaverNewsItem]
    rejected_reasons: tuple[str, ...]
    pages_fetched: int = 1

    @property
    def rejected_count(self) -> int:
        return len(self.rejected_reasons)

    @property
    def outcome(self) -> str:
        return "partial" if self.rejected_reasons else "succeeded"


def _plain_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    decoded = html.unescape(value)
    return _HTML_TAG.sub("", decoded).strip()


def _published_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed.tzinfo is not None else None


def _allowed_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field in _ALLOWED_METADATA_FIELDS:
        if field in raw:
            metadata[field] = _plain_text(raw[field])
    return metadata


def fetch_naver_news(
    client: httpx.Client,
    *,
    client_id: str,
    client_secret: str,
    query: str,
    display: int = 10,
    start: int = 1,
    sort: str = "date",
) -> NaverNewsResponse:
    query = normalize_search_text(query)
    if not query:
        raise ValueError("query must not be empty")
    if not 1 <= display <= 100:
        raise ValueError("display must be between 1 and 100")
    if not 1 <= start <= 1000:
        raise ValueError("start must be between 1 and 1000")
    if sort not in {"date", "sim"}:
        raise ValueError("sort must be date or sim")

    try:
        response = client.get(
            NAVER_NEWS_ENDPOINT,
            headers={
                "X-NCP-APIGW-API-KEY-ID": client_id,
                "X-NCP-APIGW-API-KEY": client_secret,
            },
            params={
                "query": query,
                "display": display,
                "start": start,
                "sort": sort,
                "format": "json",
            },
        )
    except httpx.HTTPError as exc:
        raise NaverNewsApiError("NAVER news transport failed") from exc
    if response.status_code != 200:
        raise NaverNewsApiError(f"NAVER news returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise NaverNewsApiError("NAVER news returned invalid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise NaverNewsApiError("NAVER news response contract is invalid")

    raw_items = payload["items"]
    try:
        total = int(payload.get("total", 0))
        actual_start = int(payload.get("start", start))
        actual_display = int(payload.get("display", len(raw_items)))
    except (TypeError, ValueError) as exc:
        raise NaverNewsApiError("NAVER news paging metadata is invalid") from exc
    if actual_display != len(raw_items):
        raise NaverNewsApiError(
            f"NAVER news display mismatch: declared={actual_display}, "
            f"received={len(raw_items)}"
        )

    items: list[NaverNewsItem] = []
    rejected_reasons: list[str] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            rejected_reasons.append("item_not_object")
            continue
        original_url = _plain_text(raw.get("originallink"))
        portal_url = _plain_text(raw.get("link"))
        if not original_url:
            original_url = portal_url
        title = _plain_text(raw.get("title"))
        if not title:
            rejected_reasons.append("missing_title")
            continue
        if not original_url:
            rejected_reasons.append("missing_url")
            continue
        published_at = _published_at(raw.get("pubDate"))
        if published_at is None:
            rejected_reasons.append("invalid_pub_date")
            continue
        items.append(
            NaverNewsItem(
                title=title,
                description=_plain_text(raw.get("description")) or None,
                original_url=original_url,
                portal_url=portal_url or None,
                published_at=published_at,
                raw_metadata=_allowed_metadata(raw),
            )
        )

    if raw_items and not items:
        raise NaverNewsAllItemsRejectedError(
            total=total,
            raw_item_count=len(raw_items),
            rejected_reasons=tuple(rejected_reasons),
        )
    return NaverNewsResponse(
        total=total,
        start=actual_start,
        display=actual_display,
        raw_item_count=len(raw_items),
        items=items,
        rejected_reasons=tuple(rejected_reasons),
    )
