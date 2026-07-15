import re

_REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")),
    ("resident_number", re.compile(r"(?<!\d)\d{6}-?[1-8]\d{6}(?!\d)")),
    ("card_number", re.compile(r"(?<!\d)(?:\d[ -]?){15}\d(?!\d)")),
    (
        "phone_number",
        re.compile(
            r"(?<!\d)(?:01[0-9][ -]?\d{3,4}[ -]?\d{4}|"
            r"0(?:2|[3-6][1-5]|70)[ -]?\d{3,4}[ -]?\d{4})(?!\d)"
        ),
    ),
    ("account_number", re.compile(r"(?<!\d)\d{3,6}-\d{2,6}-\d{3,8}(?!\d)")),
)


def redact_sensitive_text(value: str) -> tuple[str, list[str]]:
    """Replace common direct identifiers before a message is stored or processed."""
    redactions: list[str] = []
    redacted = value
    for label, pattern in _REDACTION_PATTERNS:
        redacted, count = pattern.subn(f"[{label}]", redacted)
        if count:
            redactions.append(label)
    return redacted, redactions
