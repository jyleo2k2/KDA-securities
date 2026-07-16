from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from trafilatura import extract

MAX_ARTICLE_BYTES = 2_000_000
MAX_ARTICLE_CHARS = 30_000
MIN_ARTICLE_CHARS = 200
MAX_REDIRECTS = 3


class NewsArticleFetchError(RuntimeError):
    """Expected publisher-page failure represented by a stable error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ExtractedNewsArticle:
    text: str
    content_sha256: str
    final_url: str


def _assert_public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise NewsArticleFetchError("invalid_url")
    if parsed.username or parsed.password:
        raise NewsArticleFetchError("invalid_url")
    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise NewsArticleFetchError("dns_failed") from exc
    if not addresses:
        raise NewsArticleFetchError("dns_failed")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise NewsArticleFetchError("non_public_address")


def extract_article_text(html: str) -> str:
    try:
        extracted = extract(
            html,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    except Exception as exc:
        raise NewsArticleFetchError("article_parse_failed") from exc
    normalized = re.sub(r"[ \t]+", " ", extracted or "")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if len(normalized) < MIN_ARTICLE_CHARS:
        raise NewsArticleFetchError("article_too_short")
    return normalized


def fetch_news_article(
    client: httpx.Client,
    url: str,
) -> ExtractedNewsArticle:
    current_url = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        _assert_public_url(current_url)
        try:
            with client.stream(
                "GET",
                current_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; PensionCopilotNewsBot/1.0; "
                        "+https://github.com/jyleo2k2/KDA-securities)"
                    ),
                    "Accept": "text/html,application/xhtml+xml",
                },
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location or redirect_count == MAX_REDIRECTS:
                        raise NewsArticleFetchError("redirect_failed")
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code >= 400:
                    raise NewsArticleFetchError("publisher_http_error")
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type.lower():
                    raise NewsArticleFetchError("unsupported_content_type")
                encoding = response.charset_encoding or "utf-8"
                chunks: list[bytes] = []
                total_bytes = 0
                for chunk in response.iter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > MAX_ARTICLE_BYTES:
                        raise NewsArticleFetchError("article_too_large")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise NewsArticleFetchError("publisher_request_failed") from exc

        html = b"".join(chunks).decode(encoding, errors="replace")
        text = extract_article_text(html)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ExtractedNewsArticle(
            text=text[:MAX_ARTICLE_CHARS],
            content_sha256=digest,
            final_url=current_url,
        )
    raise NewsArticleFetchError("redirect_failed")
