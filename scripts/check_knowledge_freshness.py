"""Monitor approved RAG review dates and official-source fingerprints.

This command never edits approved documents or engine rules. It produces a
review report and a reusable fingerprint state so a scheduled workflow can
surface official-source changes for human approval.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
from trafilatura import extract

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.ingestion.knowledge import DEFAULT_MANIFEST, load_approved_documents
from backend.app.retrieval.knowledge_policy import is_allowed_official_source_url

MAX_SOURCE_BYTES = 8 * 1024 * 1024
USER_AGENT = "pension-copilot-rag-governance/1.0"
_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class SourceCheck:
    url: str
    document_ids: tuple[str, ...]
    status: str
    final_url: str | None = None
    content_type: str | None = None
    sha256: str | None = None
    previous_sha256: str | None = None
    error: str | None = None


def _read_manifest(path: Path, *, today: date) -> tuple[dict[str, Any], ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise ValueError("knowledge manifest schema_version must be 2")
    documents = payload.get("documents")
    if not isinstance(documents, list) or not all(
        isinstance(document, dict) for document in documents
    ):
        raise ValueError("knowledge manifest documents must be objects")

    # Reuse the ingestion validator. Expired entries are deliberately skipped
    # there, while this monitor still reports their dates from the raw metadata.
    load_approved_documents(path, today=today, skip_expired=True)
    return tuple(documents)


def evaluate_review_schedule(
    documents: tuple[dict[str, Any], ...],
    *,
    today: date,
    warn_days: int,
) -> tuple[dict[str, str | int], ...]:
    reviews: list[dict[str, str | int]] = []
    warning_date = today + timedelta(days=warn_days)
    for document in documents:
        document_id = str(document["document_id"])
        due_date = date.fromisoformat(str(document["review_due_date"]))
        if due_date < today:
            status = "expired"
        elif due_date <= warning_date:
            status = "due_soon"
        else:
            status = "current"
        reviews.append(
            {
                "document_id": document_id,
                "review_due_date": due_date.isoformat(),
                "days_remaining": (due_date - today).days,
                "status": status,
            }
        )
    return tuple(
        sorted(
            reviews,
            key=lambda item: (item["review_due_date"], item["document_id"]),
        )
    )


def _normalize_payload(payload: bytes, content_type: str) -> bytes:
    lowered = content_type.lower()
    if not any(token in lowered for token in ("html", "text", "json", "xml")):
        return payload
    decoded = payload.decode("utf-8", errors="replace")
    if "html" in lowered:
        decoded = extract(
            decoded,
            include_comments=False,
            include_tables=True,
            fast=True,
        ) or _HTML_TAG.sub(" ", decoded)
        decoded = html.unescape(decoded)
    return _WHITESPACE.sub(" ", decoded).strip().encode("utf-8")


def _load_state(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("knowledge source state schema_version must be 1")
    sources = payload.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("knowledge source state must contain sources")
    return {
        str(url): {str(key): str(value) for key, value in metadata.items()}
        for url, metadata in sources.items()
        if isinstance(metadata, dict)
    }


def check_official_sources(
    source_documents: dict[str, tuple[str, ...]],
    *,
    previous_state: dict[str, dict[str, str]],
    client: httpx.Client,
) -> tuple[tuple[SourceCheck, ...], dict[str, dict[str, str]]]:
    checks: list[SourceCheck] = []
    next_state = {
        url: previous_state[url]
        for url in source_documents
        if url in previous_state
    }
    for url in sorted(source_documents):
        previous = previous_state.get(url, {})
        previous_sha = previous.get("sha256")
        try:
            if not is_allowed_official_source_url(url):
                raise ValueError("source URL is outside the approved allowlist")
            with client.stream("GET", url) as response:
                response.raise_for_status()
                final_url = str(response.url)
                if not is_allowed_official_source_url(final_url):
                    raise ValueError("source redirected outside the approved allowlist")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        raise ValueError("source response exceeded 8 MiB")
                    chunks.append(chunk)
                content_type = response.headers.get("content-type", "")
            normalized = _normalize_payload(b"".join(chunks), content_type)
            if not normalized:
                raise ValueError("source response contains no reviewable content")
            digest = sha256(normalized).hexdigest()
            status = (
                "baseline_created"
                if previous_sha is None
                else "unchanged"
                if previous_sha == digest
                else "changed"
            )
            next_state[url] = {
                "sha256": digest,
                "final_url": final_url,
                "content_type": content_type,
            }
            checks.append(
                SourceCheck(
                    url=url,
                    document_ids=source_documents[url],
                    status=status,
                    final_url=final_url,
                    content_type=content_type,
                    sha256=digest,
                    previous_sha256=previous_sha,
                )
            )
        except (httpx.HTTPError, ValueError) as error:
            checks.append(
                SourceCheck(
                    url=url,
                    document_ids=source_documents[url],
                    status="unavailable",
                    previous_sha256=previous_sha,
                    error=str(error),
                )
            )
    return tuple(checks), next_state


def build_report(
    documents: tuple[dict[str, Any], ...],
    reviews: tuple[dict[str, str | int], ...],
    source_checks: tuple[SourceCheck, ...],
    *,
    today: date,
) -> dict[str, Any]:
    expired = [item for item in reviews if item["status"] == "expired"]
    due_soon = [item for item in reviews if item["status"] == "due_soon"]
    changed = [item for item in source_checks if item.status == "changed"]
    unavailable = [item for item in source_checks if item.status == "unavailable"]
    baselined = [item for item in source_checks if item.status == "baseline_created"]
    requires_review = bool(expired or due_soon or changed or unavailable)
    return {
        "schema_version": 1,
        "checked_on": today.isoformat(),
        "requires_review": requires_review,
        "summary": {
            "document_count": len(documents),
            "source_count": len(source_checks),
            "expired_count": len(expired),
            "due_soon_count": len(due_soon),
            "changed_source_count": len(changed),
            "unavailable_source_count": len(unavailable),
            "baseline_created_count": len(baselined),
        },
        "reviews": list(reviews),
        "sources": [asdict(item) for item in source_checks],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "## RAG 공식 출처·검토기한 점검",
        "",
        f"- 점검일: {report['checked_on']}",
        f"- 승인 문서: {summary['document_count']}개",
        f"- 공식 출처: {summary['source_count']}개",
        f"- 만료: {summary['expired_count']}개",
        f"- 30일 이내 검토: {summary['due_soon_count']}개",
        f"- 내용 지문 변경: {summary['changed_source_count']}개",
        f"- 조회 실패: {summary['unavailable_source_count']}개",
        "",
        "변경을 자동 반영하지 않습니다. 공식 원문을 사람이 대조한 뒤 승인 PR에서 "
        "문서·매니페스트·영향받는 규칙 엔진 버전과 테스트를 함께 갱신하세요.",
    ]
    reviews = [item for item in report["reviews"] if item["status"] != "current"]
    sources = [
        item
        for item in report["sources"]
        if item["status"] in {"changed", "unavailable"}
    ]
    if reviews:
        lines.extend(["", "### 검토기한", ""])
        lines.extend(
            f"- `{item['document_id']}`: {item['review_due_date']} "
            f"({item['status']}, {item['days_remaining']}일)"
            for item in reviews[:30]
        )
    if sources:
        lines.extend(["", "### 공식 출처 신호", ""])
        lines.extend(
            f"- {item['status']}: {item['url']} "
            f"(`{', '.join(item['document_ids'])}`)"
            for item in sources[:30]
        )
    return "\n".join(lines) + "\n"


def _source_documents(
    documents: tuple[dict[str, Any], ...],
) -> dict[str, tuple[str, ...]]:
    mapping: dict[str, set[str]] = {}
    for document in documents:
        document_id = str(document["document_id"])
        for url in document["official_source_urls"]:
            mapping.setdefault(str(url), set()).add(document_id)
    return {url: tuple(sorted(document_ids)) for url, document_ids in mapping.items()}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check approved RAG review dates and official source fingerprints."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--state-in", type=Path)
    parser.add_argument("--state-out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--warn-days", type=int, default=30)
    parser.add_argument("--today", type=date.fromisoformat)
    parser.add_argument("--skip-source-check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    today = args.today or date.today()
    if args.warn_days < 1:
        raise SystemExit("--warn-days must be at least 1")
    documents = _read_manifest(args.manifest.resolve(), today=today)
    reviews = evaluate_review_schedule(
        documents, today=today, warn_days=args.warn_days
    )
    previous_state = _load_state(args.state_in)
    if args.skip_source_check:
        source_checks: tuple[SourceCheck, ...] = ()
        next_state = previous_state
    else:
        with httpx.Client(
            follow_redirects=True,
            timeout=20.0,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            source_checks, next_state = check_official_sources(
                _source_documents(documents),
                previous_state=previous_state,
                client=client,
            )
    report = build_report(documents, reviews, source_checks, today=today)

    state_payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": next_state,
    }
    for path in (args.state_out, args.report, args.markdown_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.state_out.write_text(
        json.dumps(state_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
