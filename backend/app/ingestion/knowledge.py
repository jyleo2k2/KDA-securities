import re
from dataclasses import replace
from typing import Protocol

from backend.app.retrieval.knowledge_repository import (
    KnowledgeDocumentInput,
    KnowledgeRunHandle,
    KnowledgeSourceInput,
)

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ACCOUNT_DATA = re.compile(
    r"(?:주민등록번호|계좌번호|account[_ -]?number|owner_id|user_id)",
    re.IGNORECASE,
)
_FORBIDDEN_LOCATORS = ("user://", "account://", "data/mock/", "scenario_fixtures")


class KnowledgeRepository(Protocol):
    def start_run(self, source: KnowledgeSourceInput) -> KnowledgeRunHandle: ...

    def complete_document(
        self, handle: KnowledgeRunHandle, document: KnowledgeDocumentInput
    ) -> object: ...

    def fail_run(self, run_id: object, error: Exception) -> None: ...


def chunk_markdown(content: str, *, max_chars: int = 1800) -> tuple[str, ...]:
    """Split Markdown by headings, then by paragraphs without losing heading context."""
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    text = content.strip()
    if not text:
        raise ValueError("knowledge content must not be empty")

    sections: list[tuple[str, list[str]]] = []
    heading = ""
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        match = _HEADING.match(block.splitlines()[0])
        if match:
            if paragraphs:
                sections.append((heading, paragraphs))
            heading = match.group(2).strip()
            remainder = "\n".join(block.splitlines()[1:]).strip()
            paragraphs = [remainder] if remainder else []
        else:
            paragraphs.append(block)
    if paragraphs or heading:
        sections.append((heading, paragraphs))

    chunks: list[str] = []
    for section_heading, section_paragraphs in sections:
        prefix = f"제목: {section_heading}\n\n" if section_heading else ""
        current = prefix.rstrip()
        for paragraph in section_paragraphs:
            parts = [
                paragraph[index : index + max_chars - len(prefix)]
                for index in range(0, len(paragraph), max_chars - len(prefix))
            ]
            for part in parts:
                candidate = f"{current}\n\n{part}".strip()
                if len(candidate) > max_chars and current.strip() != prefix.strip():
                    chunks.append(current.strip())
                    current = f"{prefix}{part}".strip()
                else:
                    current = candidate
        if current.strip() and current.strip() != prefix.strip():
            chunks.append(current.strip())
    if not chunks:
        raise ValueError("knowledge content produced no chunks")
    return tuple(chunks)


def validate_knowledge_document(document: KnowledgeDocumentInput) -> None:
    locator = document.source_url.replace("\\", "/").lower()
    if any(marker in locator for marker in _FORBIDDEN_LOCATORS):
        raise ValueError("user account or mock data cannot be loaded into RAG")
    if document.document_type == "news":
        raise ValueError("news metadata must use news_items, not knowledge RAG")
    if document.license_status != "permitted":
        raise ValueError("full RAG content requires license_status=permitted")
    if not document.publisher.strip() or not document.source_url.strip():
        raise ValueError("publisher and source_url are required")
    if document.published_at is None and document.as_of_date is None:
        raise ValueError("published_at or as_of_date is required")
    if _ACCOUNT_DATA.search(document.content):
        raise ValueError("possible user account data detected in RAG content")


def ingest_knowledge_document(
    repository: KnowledgeRepository,
    *,
    source: KnowledgeSourceInput,
    document: KnowledgeDocumentInput,
    max_chunk_chars: int = 1800,
) -> object:
    handle = repository.start_run(source)
    try:
        prepared = replace(
            document,
            chunks=chunk_markdown(document.content, max_chars=max_chunk_chars),
        )
        validate_knowledge_document(prepared)
        return repository.complete_document(handle, prepared)
    except Exception as exc:
        repository.fail_run(handle.run_id, exc)
        raise
