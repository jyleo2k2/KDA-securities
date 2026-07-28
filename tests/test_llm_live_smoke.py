"""벤더에 실제로 한 번 붙여 보는 스모크 테스트.

왜 필요한가
----------
단위 테스트는 "설정 딕셔너리에 무엇이 담겼는가"까지만 본다. 그 딕셔너리를
벤더가 받아주는지는 확인하지 않는다. 실제로 `google_thinking_config`에
`thinking_budget=0`을 담았을 때 gemini-3.5-flash-lite가 400
INVALID_ARGUMENT로 거절했는데, 단위 테스트 13건은 전부 통과했다.
그때 사용자에게는 오류가 아니라 결정론 답변이 나가므로 화면으로도
알아채기 어렵다(내레이터가 예외를 폴백으로 흡수한다).

그래서 운영과 같은 방식으로 Agent를 만들어 한 번 호출한다. API 키가 없으면
건너뛴다. 호출 1회 비용은 실측 단가 기준 $0.0004 수준이다.
"""

import os

import pytest

from backend.app.chat.narrator import ClaudeNarrator
from backend.app.llm_models import api_key_for_model, resolve_vendor
from backend.app.settings import Settings

LIVE_MODELS = ["gemini-3.5-flash-lite"]


def _api_key(model: str) -> str:
    """환경변수 우선, 없으면 루트 .env를 읽는 Settings에서 가져온다."""

    try:
        key = api_key_for_model(model, Settings())
    except Exception:  # noqa: BLE001 — 키 미설정은 skip 사유이지 실패가 아니다
        key = ""
    if key.strip():
        return key.strip()
    env_name = "GOOGLE_API_KEY" if resolve_vendor(model) == "google" else (
        "ANTHROPIC_API_KEY"
    )
    return os.environ.get(env_name, "").strip()


@pytest.mark.parametrize("model", LIVE_MODELS)
def test_narrator_agent_reaches_the_vendor(model: str) -> None:
    key = _api_key(model)
    if not key:
        pytest.skip(f"{model} 벤더 API 키가 없어 실호출을 건너뛴다")

    narrator = ClaudeNarrator(api_key=key, model=model)
    result = narrator.agent.run_sync(
        "검증 답변:\n"
        "DC형과 IRP는 위험자산을 70%까지 담을 수 있어요.\n\n"
        "제한사항:\n제도가 바뀌면 달라질 수 있어요."
    )

    # 400이 나면 여기까지 오지 못한다. 문구 품질은 가드가 따로 판정하므로
    # 여기서는 "벤더가 우리 요청을 받아들였다"만 확인한다.
    assert result.output.narration.strip()
