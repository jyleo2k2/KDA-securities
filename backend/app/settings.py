from functools import lru_cache
from pathlib import Path
from uuid import UUID

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
    # 세액 계산·계좌 비교처럼 설명 품질이 값을 하는 인텐트에만 쓰는 상위 모델.
    # 비우면 anthropic_model 하나로만 동작한다.
    anthropic_narration_upgraded_model: str = "claude-sonnet-5"
    anthropic_topic_guard_model: str = "claude-haiku-4-5"
    enable_claude_narration: bool = False
    enable_claude_topic_guard: bool = False
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
    database_pool_max_size: int = Field(default=5, ge=2, le=15)
    supabase_url: str | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_secret_key: SecretStr | None = None
    # 시연·테스트 전용 계정: 설문(투자성향) 결과를 저장하지 않고 응답만 돌려준다.
    # 쉼표로 구분한 Supabase auth user id 목록.
    ephemeral_investment_profile_owner_ids: str = ""
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ]
    )


    def ephemeral_investment_profile_owner_id_set(self) -> frozenset[UUID]:
        """설문 결과를 저장하지 않을 소유자 id 집합."""
        return frozenset(
            UUID(token.strip())
            for token in self.ephemeral_investment_profile_owner_ids.split(",")
            if token.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
