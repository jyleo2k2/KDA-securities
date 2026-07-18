"""Shared filesystem helpers for ingestion collectors: atomic writes, glob lookups."""

import hashlib
import json
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def atomic_write_json(path: Path, payload: Any, *, default: Any = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True, default=default
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def latest_matching(directory: Path, pattern: str) -> Path:
    candidates = sorted(directory.glob(pattern))
    if not candidates:
        raise FileNotFoundError(f"no matching file found under {directory}")
    return candidates[-1]
