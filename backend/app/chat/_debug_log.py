"""로컬 디버깅 전용 챗 교환 로거 (임시물 — 디버깅 끝나면 삭제할 것).

이 서비스는 마이데이터 실계좌 연동을 최종 전제로 설계한다(헌장 §데이터 전제).
이 로거는 그 실연동 시 흐를 질문·답변 데이터를 개발 중에 관찰·디버깅하기 위한
개발자 도구다. 질문·답변 전문을 남기므로 다음 운영 규칙을 지킨다.

- 기본값 OFF다. 환경변수 `CHAT_DEBUG_LOG=1`일 때만 파일에 쓴다.
- 출력 파일은 `data/cache/chat_debug.jsonl`이며 `data/cache/`는 `.gitignore`
  대상이라 커밋되지 않는다. 로그 파일을 외부로 공유하지 않는다.
- 실계좌 연동 단계에서 개인정보 취급이 필요하면 보존기간·마스킹 정책을
  별도로 정한다. 이 임시 로거는 그 정책 확정 전 개발 디버깅에만 켠다.

되돌리기(원상복구): 이 파일을 삭제하고, `backend/app/api/chat.py`의 import 1줄과
`log_chat_exchange(...)` 호출 2곳을 제거하면 끝이다. 프로덕션 로직에는 섞지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEBUG_LOG_ENV = "CHAT_DEBUG_LOG"
_DEBUG_LOG_PATH = Path("data/cache/chat_debug.jsonl")
_WRITE_LOCK = threading.Lock()


def _enabled() -> bool:
    return os.environ.get(_DEBUG_LOG_ENV, "").strip() in {"1", "true", "TRUE", "yes"}


def _coerce(value: Any) -> Any:
    """model_dump 등이 실패해도 로깅이 요청을 깨지 않도록 안전 변환한다."""
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)


def log_chat_exchange(
    *,
    message: str,
    response: Any,
    latency_ms: float | None = None,
    persisted: bool | None = None,
) -> None:
    """환경변수가 켜져 있을 때만 챗 교환 한 건을 JSONL 한 줄로 남긴다.

    로깅 실패는 절대 요청 처리에 영향을 주지 않는다(모든 예외를 삼킨다).
    """
    if not _enabled():
        return
    try:
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "message": message,
            "intent": _coerce(
                getattr(getattr(response, "intent", None), "value", None)
            ),
            "narration_mode": _coerce(getattr(response, "narration_mode", None)),
            "model_name": _coerce(getattr(response, "model_name", None)),
            "data_mode": _coerce(getattr(response, "data_mode", None)),
            "answer": _coerce(getattr(response, "answer", None)),
            "limitations": _coerce(list(getattr(response, "limitations", []) or [])),
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
            "persisted": persisted,
        }
        line = json.dumps(record, ensure_ascii=False)
        with _WRITE_LOCK:
            _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception:  # noqa: BLE001 — 디버그 로깅은 요청을 절대 깨지 않는다
        logger.warning("chat_debug_log_failed")
