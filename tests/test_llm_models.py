"""벤더 중립 모델 팩토리 회귀 테스트.

설정에서 모델 이름만 바꿔도 벤더·API 키·요청 설정이 함께 따라가는지 본다.
"""

import pytest
from pydantic import SecretStr

from backend.app.llm_models import (
    ANTHROPIC,
    GOOGLE,
    api_key_for_model,
    build_model,
    build_model_settings,
    required_api_key_name,
    resolve_vendor,
    strip_vendor_prefix,
)
from backend.app.settings import Settings


@pytest.mark.parametrize(
    ("model", "vendor"),
    [
        ("gemini-3.5-flash-lite", GOOGLE),
        ("google:gemini-3.5-flash-lite", GOOGLE),
        ("claude-haiku-4-5", ANTHROPIC),
        ("anthropic:claude-sonnet-5", ANTHROPIC),
        # 알 수 없는 이름은 기존 배선과 같게 anthropic으로 본다.
        ("test-model", ANTHROPIC),
    ],
)
def test_vendor_follows_model_name(model: str, vendor: str) -> None:
    assert resolve_vendor(model) == vendor


def test_vendor_prefix_is_stripped_from_model_name() -> None:
    assert strip_vendor_prefix("google:gemini-3.5-flash-lite") == (
        "gemini-3.5-flash-lite"
    )
    assert strip_vendor_prefix("claude-haiku-4-5") == "claude-haiku-4-5"


def test_required_api_key_name_matches_vendor() -> None:
    assert required_api_key_name("gemini-3.5-flash-lite") == "GOOGLE_API_KEY"
    assert required_api_key_name("claude-haiku-4-5") == "ANTHROPIC_API_KEY"


def test_api_key_is_read_from_the_matching_vendor() -> None:
    settings = Settings(
        _env_file=None,
        anthropic_api_key=SecretStr("anthropic-key"),
        google_api_key=SecretStr("google-key"),
    )

    assert api_key_for_model("gemini-3.5-flash-lite", settings) == "google-key"
    assert api_key_for_model("claude-haiku-4-5", settings) == "anthropic-key"


def test_api_key_is_empty_when_the_vendor_key_is_missing() -> None:
    settings = Settings(
        _env_file=None,
        anthropic_api_key=SecretStr("anthropic-key"),
        google_api_key=None,
    )

    assert api_key_for_model("gemini-3.5-flash-lite", settings) == ""


def test_build_model_returns_the_vendor_specific_client() -> None:
    google_model = build_model("gemini-3.5-flash-lite", api_key="dummy")
    anthropic_model = build_model("claude-haiku-4-5", api_key="dummy")

    assert google_model.system == "google"
    assert google_model.model_name == "gemini-3.5-flash-lite"
    assert anthropic_model.system == "anthropic"
    assert anthropic_model.model_name == "claude-haiku-4-5"


def test_build_model_rejects_a_missing_api_key() -> None:
    with pytest.raises(ValueError):
        build_model("gemini-3.5-flash-lite", api_key="  ")


def test_google_settings_disable_thinking_when_not_requested() -> None:
    settings = build_model_settings(
        "gemini-3.5-flash-lite",
        max_tokens=2500,
        cache_static_prompt=True,
        thinking=False,
    )

    assert settings["max_tokens"] == 2500
    assert settings["google_thinking_config"] == {"thinking_budget": 0}
    # Anthropic 전용 옵션이 Google 요청에 섞이면 400이 난다.
    assert "anthropic_cache_instructions" not in settings
    assert "anthropic_thinking" not in settings


def test_anthropic_settings_keep_prompt_caching_and_thinking() -> None:
    settings = build_model_settings(
        "claude-sonnet-5",
        max_tokens=2500,
        cache_static_prompt=True,
        thinking=True,
    )

    assert settings["anthropic_cache_instructions"] is True
    assert settings["anthropic_cache_tool_definitions"] is True
    assert settings["anthropic_thinking"]["type"] == "adaptive"
    assert "google_thinking_config" not in settings
