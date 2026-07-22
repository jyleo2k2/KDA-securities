from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pension_portal_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-4-5"
    enable_claude_narration: bool = False
    enable_etf_product_feature_generation: bool = True
    narration_cache_path: Path = Path("data/cache/narration_cache.json")
    news_summary_model: str = "claude-sonnet-5"
    news_summary_prompt_version: str = "news-summary-v3"
    krx_api_key: SecretStr | None = None
    kis_app_key: SecretStr | None = None
    kis_app_secret: SecretStr | None = None
    law_open_api_key: SecretStr | None = None
    fsc_fund_product_api_key: SecretStr | None = None
    fsc_stock_dividend_api_key: SecretStr | None = None
    dart_api_key: SecretStr | None = None
    bok_ecos_api_key: SecretStr | None = None
    kosis_api_key: SecretStr | None = None
    fred_api_key: SecretStr | None = None
    macro_evidence_report_path: Path = Path(
        "data/cache/macro/macro_evidence_latest.json"
    )
    naver_api_hub_client_id: SecretStr | None = None
    naver_api_hub_client_secret: SecretStr | None = None
    database_url: SecretStr | None = None
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_secret_key: SecretStr | None = None
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
