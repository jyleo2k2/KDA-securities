"""Shared allowlist and personal-data checks for verified knowledge."""

import re
from urllib.parse import urlparse

ALLOWED_KNOWLEDGE_SOURCE_CODES = frozenset(
    {
        "project_verified_knowledge",
        "retirement_pension_official_rules",
    }
)
ALLOWED_KNOWLEDGE_DOCUMENT_TYPES = frozenset(
    {"official_guide", "regulation", "research"}
)
ALLOWED_OFFICIAL_SOURCE_HOSTS = frozenset(
    {
        "100lifeplan.fss.or.kr",
        "easylaw.go.kr",
        "fsc.go.kr",
        "g.nts.go.kr",
        "esg.krx.co.kr",
        "institute.nps.or.kr",
        "kind.krx.co.kr",
        "law.go.kr",
        "main.kotsa.or.kr",
        "moel.go.kr",
        "open.krx.co.kr",
        "reits.molit.go.kr",
        "regulation.krx.co.kr",
        "www.dapa.go.kr",
        "www.fsc.go.kr",
        "www.korea.kr",
        "www.law.go.kr",
        "www.moel.go.kr",
        "www.motir.go.kr",
        "www.nist.gov",
        "www.nts.go.kr",
        "www.kpx.or.kr",
        "www.spglobal.com",
    }
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

# Invisible controls can hide instructions from reviewers. These are rejected instead
# of normalized so the committed source remains byte-for-byte reviewable.
_HIDDEN_RAG_CONTROLS = frozenset({"\u200b", "\u200c", "\u200d", "\ufeff"})
_RAG_INSTRUCTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?", re.I),
    re.compile(r"이전\s*(?:의\s*)?지시(?:사항)?(?:을|를)?\s*무시"),
    re.compile(r"시스템\s*프롬프트(?:를|을)?\s*(?:무시|변경|공개)"),
)


def contains_sensitive_personal_data(text: str) -> bool:
    """Detect identifiers that must never enter the verified-knowledge corpus."""
    return any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)


def is_allowed_official_source_url(source_url: str) -> bool:
    """Allow only HTTPS pages from the project's reviewed public institutions."""
    parsed = urlparse(source_url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_OFFICIAL_SOURCE_HOSTS
        and bool(parsed.path)
        and not parsed.username
        and not parsed.password
    )


def contains_unsafe_rag_content(text: str) -> bool:
    """Reject hidden controls and obvious instructions aimed at the RAG consumer."""
    return any(character in text for character in _HIDDEN_RAG_CONTROLS) or any(
        pattern.search(text) for pattern in _RAG_INSTRUCTION_PATTERNS
    )


def canonical_project_source_url(source_path: str) -> str:
    """Return the single canonical locator for a repository document."""
    normalized_path = source_path.replace("\\", "/").lstrip("/")
    return f"project://{normalized_path}"


def canonicalize_source_url(source_url: str) -> str:
    """Treat legacy section fragments as the same underlying source document."""
    return source_url.partition("#")[0].rstrip("/")
