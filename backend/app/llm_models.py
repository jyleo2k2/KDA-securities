"""LLM 모델 팩토리 - 벤더 중립 배선.

챗봇 내레이터, 토픽 가드, ETF 특징 생성, 뉴스 요약이 같은 규칙으로 모델
객체와 요청 설정을 만든다. 모델 이름 접두사로 벤더를 고르므로 설정에서
이름만 바꾸면 벤더가 바뀐다. 계산은 규칙 엔진이 하고 LLM은 엔진 수치의
서술만 담당하므로 벤더 교체가 응답 수치에 영향을 주지 않는다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

if TYPE_CHECKING:  # pragma: no cover - 타입 검사 전용
    from .settings import Settings

ANTHROPIC = "anthropic"
GOOGLE = "google"

# 모델 이름 접두사 -> 벤더. 접두사를 모르면 anthropic으로 본다(기존 배선과
# 테스트 더미 모델 이름 호환).
_VENDOR_BY_PREFIX = (
    ("claude", ANTHROPIC),
    ("gemini", GOOGLE),
)


def resolve_vendor(model_name: str) -> str:
    """모델 이름에서 벤더를 고른다.

    ``google:gemini-3.5-flash-lite``처럼 벤더를 앞에 붙인 형태도 받는다.
    """

    name = model_name.strip()
    if ":" in name:
        vendor, _, _ = name.partition(":")
        vendor = vendor.strip().lower()
        if vendor in {ANTHROPIC, GOOGLE}:
            return vendor
    lowered = name.lower()
    for prefix, vendor in _VENDOR_BY_PREFIX:
        if lowered.startswith(prefix):
            return vendor
    return ANTHROPIC


def strip_vendor_prefix(model_name: str) -> str:
    """``google:``·``anthropic:`` 접두사를 뗀 실제 모델 이름."""

    name = model_name.strip()
    vendor, sep, rest = name.partition(":")
    if sep and vendor.strip().lower() in {ANTHROPIC, GOOGLE}:
        return rest.strip()
    return name


def required_api_key_name(model_name: str) -> str:
    """해당 모델이 요구하는 환경변수 이름."""

    if resolve_vendor(model_name) == GOOGLE:
        return "GOOGLE_API_KEY"
    return "ANTHROPIC_API_KEY"


def api_key_for_model(model_name: str, settings: Settings) -> str:
    """모델의 벤더에 맞는 API 키. 없으면 빈 문자열."""

    secret = (
        settings.google_api_key
        if resolve_vendor(model_name) == GOOGLE
        else settings.anthropic_api_key
    )
    if secret is None:
        return ""
    return secret.get_secret_value().strip()


def build_model(model_name: str, *, api_key: str) -> Model:
    """벤더에 맞는 pydantic-ai 모델 객체를 만든다."""

    name = strip_vendor_prefix(model_name)
    key = api_key.strip()
    if not name or not key:
        raise ValueError("model_name and api_key are required")
    if resolve_vendor(model_name) == GOOGLE:
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(name, provider=GoogleProvider(api_key=key))
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    return AnthropicModel(name, provider=AnthropicProvider(api_key=key))


def build_model_settings(
    model_name: str,
    *,
    max_tokens: int,
    cache_static_prompt: bool = False,
    thinking: bool = False,
) -> ModelSettings:
    """벤더별 요청 설정.

    ``cache_static_prompt``는 고정부(시스템 프롬프트·도구 정의) 서버측 캐싱을
    뜻한다. Anthropic은 명시 옵션이 필요하고, Gemini는 암묵 캐싱이라 따로
    켤 옵션이 없다.

    ``thinking``이 꺼져 있으면 지연을 줄이기 위해 추론 토큰을 쓰지 않는다.
    """

    if resolve_vendor(model_name) == GOOGLE:
        from pydantic_ai.models.google import GoogleModelSettings

        google_settings = GoogleModelSettings(max_tokens=max_tokens)
        google_settings["google_thinking_config"] = (
            {"include_thoughts": True} if thinking else {"thinking_budget": 0}
        )
        return google_settings

    from pydantic_ai.models.anthropic import AnthropicModelSettings

    anthropic_settings = AnthropicModelSettings(max_tokens=max_tokens)
    if cache_static_prompt:
        anthropic_settings["anthropic_cache_instructions"] = True
        anthropic_settings["anthropic_cache_tool_definitions"] = True
    if thinking:
        anthropic_settings["anthropic_thinking"] = {
            "type": "adaptive",
            "display": "summarized",
        }
    return anthropic_settings
