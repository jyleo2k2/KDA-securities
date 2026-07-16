from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pension_portal_api_key: SecretStr | None = None
    krx_api_key: SecretStr | None = None
    kis_app_key: SecretStr | None = None
    kis_app_secret: SecretStr | None = None
    law_open_api_key: SecretStr | None = None
    fsc_fund_product_api_key: SecretStr | None = None
    dart_api_key: SecretStr | None = None
    naver_api_hub_client_id: SecretStr | None = None
    naver_api_hub_client_secret: SecretStr | None = None
    database_url: SecretStr | None = None
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_secret_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
