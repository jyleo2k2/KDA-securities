"""Shared CLI secret-loading helpers for ingestion collector main() entry points."""

from pydantic import SecretStr

from ..llm_models import api_key_for_model, required_api_key_name
from ..settings import Settings


def require_secret(secret: SecretStr | None, name: str) -> str:
    value = secret.get_secret_value().strip() if secret is not None else ""
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def require_model_api_key(model: str, settings: Settings) -> str:
    """모델의 벤더에 맞는 API 키를 읽는다.

    모델 이름만 바꿨는데 다른 벤더의 키를 요구해 조용히 실패하는 일을 막는다.
    """

    value = api_key_for_model(model, settings)
    if not value:
        raise SystemExit(f"{required_api_key_name(model)} is required")
    return value


def optional_secret(secret: SecretStr | None) -> str | None:
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    return value or None
