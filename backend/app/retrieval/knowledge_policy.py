"""Shared allowlist and personal-data checks for verified knowledge."""

import re

ALLOWED_KNOWLEDGE_SOURCE_CODES = frozenset(
    {
        "project_verified_knowledge",
        "retirement_pension_official_rules",
    }
)
ALLOWED_KNOWLEDGE_DOCUMENT_TYPES = frozenset(
    {"official_guide", "regulation", "research"}
)

_SENSITIVE_PATTERNS = (
    re.compile(r"(?<!\d)\d{6}-?[1-8]\d{6}(?!\d)"),
    re.compile(r"(?<!\d)01[016789]-?\d{3,4}-?\d{4}(?!\d)"),
    re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I),
    re.compile(
        r"(?:계좌\s*번호|account\s*(?:number|no))\s*[:：]?\s*[0-9][0-9-]{7,}",
        re.I,
    ),
)


def contains_sensitive_personal_data(text: str) -> bool:
    """Detect identifiers that must never enter the verified-knowledge corpus."""
    return any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)


def canonical_project_source_url(source_path: str) -> str:
    """Return the single canonical locator for a repository document."""
    normalized_path = source_path.replace("\\", "/").lstrip("/")
    return f"project://{normalized_path}"


def canonicalize_source_url(source_url: str) -> str:
    """Treat legacy section fragments as the same underlying source document."""
    return source_url.partition("#")[0].rstrip("/")
