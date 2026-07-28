import json

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from backend.app.api.deps import _chat_topic_guard, get_chat_topic_guard
from backend.app.chat.models import ChatIntent
from backend.app.chat.query_planner import BlockedReason, plan_question
from backend.app.chat.topic_guard import (
    TOPIC_GUARD_MAX_OUTPUT_TOKENS,
    ClaudeTopicGuard,
    TopicGuardDecision,
    TopicGuardRoute,
)
from backend.app.settings import Settings


def _fake_guard_model(
    payload: dict[str, object],
    calls: list[str] | None = None,
) -> FunctionModel:
    def respond(messages, info) -> ModelResponse:
        if calls is not None:
            calls.append("called")
        return ModelResponse(
            parts=[TextPart(json.dumps(payload, ensure_ascii=False))]
        )

    return FunctionModel(respond)


def test_topic_guard_decision_requires_consistent_allowed_route() -> None:
    with pytest.raises(ValidationError):
        TopicGuardDecision(allowed=True, route=TopicGuardRoute.UNSUPPORTED)
    with pytest.raises(ValidationError):
        TopicGuardDecision(allowed=False, route=TopicGuardRoute.ACCOUNT_RULE)


def test_topic_guard_dependency_uses_dedicated_small_model() -> None:
    _chat_topic_guard.cache_clear()
    settings = Settings(
        _env_file=None,
        anthropic_api_key=SecretStr("test-key"),
        chat_model="claude-sonnet-5",
        topic_guard_model="claude-haiku-4-5",
        enable_llm_topic_guard=True,
    )

    guard = get_chat_topic_guard(settings)

    assert guard is not None
    assert guard._model == "claude-haiku-4-5"


def test_topic_guard_uses_small_structured_output_and_reuses_cache() -> None:
    guard = ClaudeTopicGuard(api_key="test-key", model="claude-haiku-4-5")
    calls: list[str] = []

    with guard.agent.override(
        model=_fake_guard_model(
            {"allowed": True, "route": "account_rule"},
            calls,
        )
    ):
        first = guard.classify("노후에 받는 돈은 언제부터 꺼내 써?")
        second = guard.classify("노후에 받는 돈은 언제부터 꺼내 써?")

    assert first == TopicGuardDecision(
        allowed=True,
        route=TopicGuardRoute.ACCOUNT_RULE,
    )
    assert second == first
    assert calls == ["called"]
    assert guard.agent.model_settings["max_tokens"] == TOPIC_GUARD_MAX_OUTPUT_TOKENS
    assert TOPIC_GUARD_MAX_OUTPUT_TOKENS == 64


@pytest.mark.parametrize(
    "message",
    [
        "오늘 밥 뭐 먹었어?",
        "배고프다 밥은 먹었니",
        "너 이름이 뭐야?",
        "너 몇 살이야?",
        "안녕 반가워",
        "오늘 뭐 해?",
        "고마워 잘했어",
        "오늘 너무 피곤해",
        "심심해",
        "농담 하나 해줘",
        "오늘 날씨 어때?",
        "다음에 봐",
        "비트코인 지금 사도 돼?",
        "신용대출 금리 낮은 곳 알려줘",
        "파이썬 for문 알려줘",
        "김치찌개 레시피 알려줘",
        "서울 부산 KTX 요금 알려줘",
    ],
)
def test_topic_guard_short_circuits_obvious_off_topic_without_llm(
    message: str,
) -> None:
    guard = ClaudeTopicGuard(api_key="test-key", model="claude-haiku-4-5")

    class MustNotRun:
        def run_sync(self, prompt):
            raise AssertionError("obvious off-topic must not call the LLM")

    guard.agent = MustNotRun()

    assert guard.classify(message) == TopicGuardDecision(
        allowed=False,
        route=TopicGuardRoute.UNSUPPORTED,
    )


def test_topic_guard_refines_only_unsupported_plan() -> None:
    guard = ClaudeTopicGuard(api_key="test-key", model="claude-haiku-4-5")
    message = "노후에 받는 돈은 언제부터 꺼내 써?"
    unsupported = plan_question(message)
    assert unsupported.blocked_reason is BlockedReason.UNSUPPORTED

    with guard.agent.override(
        model=_fake_guard_model(
            {"allowed": True, "route": "account_rule"}
        )
    ):
        refined = guard.refine_plan(message, unsupported)

    assert refined.intent is ChatIntent.ACCOUNT_RULE
    assert refined.blocked_reason is None
    assert refined.normalized_message == unsupported.normalized_message
    assert refined.account_types == ()
    assert refined.account_rule_topic is None


@pytest.mark.parametrize(
    ("route", "expected_intent", "expected_tax_flag"),
    [
        (
            TopicGuardRoute.PENSION_TAX_CREDIT,
            ChatIntent.PENSION_TAX,
            "requests_tax_credit",
        ),
        (
            TopicGuardRoute.PENSION_WITHDRAWAL_TAX,
            ChatIntent.PENSION_TAX,
            "requests_withdrawal_tax",
        ),
        (
            TopicGuardRoute.EDUCATIONAL_PORTFOLIO,
            ChatIntent.EDUCATIONAL_PORTFOLIO,
            None,
        ),
        (TopicGuardRoute.NEWS, ChatIntent.NEWS, None),
    ],
)
def test_topic_guard_routes_to_existing_valid_plans(
    route: TopicGuardRoute,
    expected_intent: ChatIntent,
    expected_tax_flag: str | None,
) -> None:
    guard = ClaudeTopicGuard(api_key="test-key", model="claude-haiku-4-5")
    unsupported = plan_question("기존 룰에 없는 표현")

    with guard.agent.override(
        model=_fake_guard_model(
            {"allowed": True, "route": route.value}
        )
    ):
        refined = guard.refine_plan(unsupported.normalized_message, unsupported)

    assert refined.intent is expected_intent
    assert refined.blocked_reason is None
    assert refined.account_types == ()
    if expected_tax_flag is not None:
        assert getattr(refined, expected_tax_flag) is True


def test_topic_guard_never_overrides_deterministic_safety_block() -> None:
    guard = ClaudeTopicGuard(api_key="test-key", model="claude-haiku-4-5")
    blocked = plan_question("내 주민번호 900101-1234567로 연금 봐줘")
    assert blocked.blocked_reason is BlockedReason.SENSITIVE_INFORMATION

    class MustNotRun:
        def run_sync(self, prompt):
            raise AssertionError("safety blocks must not reach the topic guard")

    guard.agent = MustNotRun()
    assert guard.refine_plan(blocked.normalized_message, blocked) is blocked


def test_topic_guard_keeps_unsupported_when_llm_rejects_topic() -> None:
    guard = ClaudeTopicGuard(api_key="test-key", model="claude-haiku-4-5")
    unsupported = plan_question("김치찌개 맛있게 끓이는 법")

    with guard.agent.override(
        model=_fake_guard_model(
            {"allowed": False, "route": "unsupported"}
        )
    ):
        refined = guard.refine_plan(unsupported.normalized_message, unsupported)

    assert refined is unsupported
