import html
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

NAVER_NEWS_ENDPOINT = "https://naverapihub.apigw.ntruss.com/search/v1/news"
_HIGHLIGHT_TAG = re.compile(r"</?b>", flags=re.IGNORECASE)


class NaverNewsApiError(RuntimeError):
    """A sanitized NAVER API HUB transport or response-contract failure."""


@dataclass(frozen=True, slots=True)
class NaverNewsItem:
    title: str
    description: str | None
    original_url: str
    portal_url: str | None
    published_at: datetime | None
    raw_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NaverNewsResponse:
    total: int
    start: int
    display: int
    items: list[NaverNewsItem]
    rejected_count: int = 0
    rejected_reasons: tuple[str, ...] = ()


def _plain_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return html.unescape(_HIGHLIGHT_TAG.sub("", value)).strip()


def _published_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None


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
    query = query.strip()
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

    items: list[NaverNewsItem] = []
    rejected_reasons: list[str] = []
    for index, raw in enumerate(payload["items"]):
        if not isinstance(raw, dict):
            rejected_reasons.append(f"item[{index}]: not_an_object")
            continue
        original_url = _plain_text(raw.get("originallink"))
        portal_url = _plain_text(raw.get("link"))
        title = _plain_text(raw.get("title"))
        published_at = _published_at(raw.get("pubDate"))
        if not title or not original_url or not portal_url or published_at is None:
            rejected_reasons.append(f"item[{index}]: missing_required_metadata")
            continue
        safe_raw_metadata = {
            key: raw[key]
            for key in ("title", "originallink", "link", "description", "pubDate")
            if key in raw
        }
        items.append(
            NaverNewsItem(
                title=title,
                description=_plain_text(raw.get("description")) or None,
                original_url=original_url,
                portal_url=portal_url,
                published_at=published_at,
                raw_metadata=safe_raw_metadata,
            )
        )

    try:
        total = int(payload.get("total", 0))
        actual_start = int(payload.get("start", start))
        actual_display = int(payload.get("display", len(items)))
    except (TypeError, ValueError) as exc:
        raise NaverNewsApiError("NAVER news paging metadata is invalid") from exc
    received_count = len(payload["items"])
    if actual_display != received_count:
        raise NaverNewsApiError(
            f"NAVER news display mismatch: declared={actual_display}, "
            f"received={received_count}"
        )
    if received_count and not items:
        raise NaverNewsApiError("NAVER news response has no valid metadata items")
    return NaverNewsResponse(
        total,
        actual_start,
        actual_display,
        items,
        len(rejected_reasons),
        tuple(rejected_reasons),
    )
