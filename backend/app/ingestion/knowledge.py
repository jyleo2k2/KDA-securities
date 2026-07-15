"""Manifest-only ingestion for approved verified-knowledge Markdown."""

import json
from datetime import date
from hashlib import sha256
from pathlib import Path

from ..retrieval.knowledge_policy import (
    ALLOWED_KNOWLEDGE_DOCUMENT_TYPES,
    ALLOWED_KNOWLEDGE_SOURCE_CODES,
    canonical_project_source_url,
    contains_sensitive_personal_data,
)
from ..retrieval.knowledge_repository import KnowledgeDocumentInput

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = ROOT / "data" / "knowledge" / "approved_documents.json"
DEFAULT_CHUNK_CHARS = 1800
_ALLOWED_ROOTS = (
    ROOT / "docs" / "20_리서치",
    ROOT / "docs" / "40_규제",
)


class KnowledgeManifestError(ValueError):
    pass


def _is_allowed_path(path: Path) -> bool:
    return any(path.is_relative_to(root.resolve()) for root in _ALLOWED_ROOTS)


def _markdown_blocks(content: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    heading = ""
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append((heading, "\n".join(paragraph).strip()))
            paragraph.clear()

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            heading = stripped.lstrip("#").strip()
        elif not stripped:
            flush()
        else:
            paragraph.append(line.rstrip())
    flush()
    return [(block_heading, body) for block_heading, body in blocks if body]


def _split_text(text: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    remaining = text.strip()
    while len(remaining) > max_chars:
        split_at = remaining.rfind("\n", 0, max_chars + 1)
        if split_at < max_chars // 2:
            split_at = remaining.rfind(" ", 0, max_chars + 1)
        if split_at < max_chars // 2:
            split_at = max_chars
        pieces.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def chunk_markdown(
    content: str, *, max_chars: int = DEFAULT_CHUNK_CHARS
) -> tuple[str, ...]:
    if max_chars < 500:
        raise ValueError("max_chars must be at least 500")
    rendered_blocks: list[str] = []
    for heading, body in _markdown_blocks(content):
        prefix = f"{heading}\n" if heading else ""
        available = max_chars - len(prefix)
        if available < 100:
            raise ValueError("heading is too long for the configured chunk size")
        rendered_blocks.extend(
            f"{prefix}{piece}" for piece in _split_text(body, available)
        )

    chunks: list[str] = []
    current = ""
    for block in rendered_blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = block
    if current:
        chunks.append(current)
    if not chunks:
        raise KnowledgeManifestError("approved document produced no chunks")
    return tuple(chunks)


def _required_text(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeManifestError(f"document field {key!r} is required")
    return value.strip()


def _load_entry(entry: dict[str, object], *, max_chars: int) -> KnowledgeDocumentInput:
    source_code = _required_text(entry, "source_code")
    document_type = _required_text(entry, "document_type")
    license_status = _required_text(entry, "license_status")
    data_boundary = _required_text(entry, "data_boundary")
    source_path = _required_text(entry, "path")
    source_url = _required_text(entry, "source_url")

    if source_code not in ALLOWED_KNOWLEDGE_SOURCE_CODES:
        raise KnowledgeManifestError("source_code is not approved for RAG ingestion")
    if document_type not in ALLOWED_KNOWLEDGE_DOCUMENT_TYPES:
        raise KnowledgeManifestError("document_type is not approved for RAG ingestion")
    if license_status != "permitted":
        raise KnowledgeManifestError("license_status must be permitted")
    if data_boundary != "verified_knowledge":
        raise KnowledgeManifestError("data_boundary must be verified_knowledge")
    if entry.get("contains_personal_data") is not False:
        raise KnowledgeManifestError("contains_personal_data must be false")
    if entry.get("is_mock") is not False:
        raise KnowledgeManifestError("is_mock must be false")
    expected_source_url = canonical_project_source_url(source_path)
    if source_url != expected_source_url:
        raise KnowledgeManifestError("source_url must match the approved document path")

    path = (ROOT / source_path).resolve()
    if path.suffix.lower() != ".md" or not _is_allowed_path(path):
        raise KnowledgeManifestError(
            "document path is outside approved knowledge roots"
        )
    if not path.is_file():
        raise KnowledgeManifestError(f"approved document does not exist: {source_path}")
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise KnowledgeManifestError(
            f"failed to read approved document: {source_path}"
        ) from error
    if contains_sensitive_personal_data(content):
        raise KnowledgeManifestError(
            "personal identifier detected in approved document"
        )

    content_hash = sha256(content.encode("utf-8")).hexdigest()
    approved_hash = _required_text(entry, "content_sha256").lower()
    if approved_hash != content_hash:
        raise KnowledgeManifestError("approved document content_sha256 does not match")

    as_of_text = entry.get("as_of_date")
    try:
        as_of_date = date.fromisoformat(as_of_text) if as_of_text else None
    except (TypeError, ValueError) as error:
        raise KnowledgeManifestError("as_of_date must use YYYY-MM-DD") from error
    metadata = {
        "contains_personal_data": False,
        "data_boundary": "verified_knowledge",
        "is_mock": False,
        "knowledge_kind": "project_verified_document",
        "source_path": source_path,
    }
    return KnowledgeDocumentInput(
        source_code=source_code,
        document_type=document_type,
        title=_required_text(entry, "title"),
        publisher=_required_text(entry, "publisher"),
        source_url=source_url,
        license_status=license_status,
        content=content,
        chunks=chunk_markdown(content, max_chars=max_chars),
        as_of_date=as_of_date,
        content_hash=content_hash,
        metadata=metadata,
    )


def load_approved_documents(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    max_chars: int = DEFAULT_CHUNK_CHARS,
) -> tuple[KnowledgeDocumentInput, ...]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise KnowledgeManifestError("failed to read knowledge manifest") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise KnowledgeManifestError("knowledge manifest schema_version must be 1")
    entries = payload.get("documents")
    if not isinstance(entries, list) or not entries:
        raise KnowledgeManifestError("knowledge manifest must list documents")
    if not all(isinstance(entry, dict) for entry in entries):
        raise KnowledgeManifestError("knowledge manifest documents must be objects")
    documents = tuple(_load_entry(entry, max_chars=max_chars) for entry in entries)
    document_keys = {
        (document.source_code, document.source_url) for document in documents
    }
    if len(document_keys) != len(documents):
        raise KnowledgeManifestError("knowledge manifest documents must be unique")
    return documents
