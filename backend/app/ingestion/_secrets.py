"""Shared CLI secret-loading helpers for ingestion collector main() entry points."""

from pydantic import SecretStr


def require_secret(secret: SecretStr | None, name: str) -> str:
    value = secret.get_secret_value().strip() if secret is not None else ""
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def optional_secret(secret: SecretStr | None) -> str | None:
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    return value or None
