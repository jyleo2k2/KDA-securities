import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize_search_text(value: str) -> str:
    """Return a stable display-and-storage form for user search text."""

    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip()
