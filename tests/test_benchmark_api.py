from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.api.deps import get_benchmark_repository
from backend.app.benchmark_repository import (
    BenchmarkAccountTypeStat,
    BenchmarkDistribution,
    BenchmarkSummary,
)
from backend.app.main import app


class FakeBenchmarkRepository:
    def get_summary(self) -> BenchmarkSummary:
        return BenchmarkSummary(
            user_count=10_000,
            account_count=16_900,
            holding_count=79_381,
            age_groups=[BenchmarkDistribution(code="20s", count=1_190)],
            risk_profiles=[BenchmarkDistribution(code="STABLE_SEEKING", count=5_010)],
            account_type_stats=[
                BenchmarkAccountTypeStat(
                    account_type="DC",
                    account_count=5_000,
                    mean_balance_krw=Decimal("12345678"),
                    mean_monthly_contribution_krw=Decimal("200000"),
                    mean_risky_asset_ratio_percent=Decimal("42.5"),
                )
            ],
        )


def test_benchmark_summary_is_aggregate_mock_data_only() -> None:
    app.dependency_overrides[get_benchmark_repository] = FakeBenchmarkRepository
    try:
        with TestClient(app) as client:
            response = client.get("/benchmark/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_boundary"] == "mock"
    assert payload["user_count"] == 10_000
    assert payload["account_type_stats"][0]["mean_balance_krw"] == "12345678"
    assert "user_id" not in payload
    assert "account_id" not in payload
    assert "password" not in payload
