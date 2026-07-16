"""Aggregate-only endpoints for the anonymous pension benchmark."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ..benchmark_repository import BenchmarkRepository
from .deps import get_benchmark_repository

router = APIRouter(tags=["benchmark"])

BENCHMARK_SOURCE_LABEL = "통계 모델 기반 익명 목데이터"
BENCHMARK_NOTICE = (
    "이 화면은 발표·학습용 통계 모델 목데이터의 집계입니다. "
    "실제 고객이나 개인 계좌 정보를 뜻하지 않으며, 개인 식별 정보는 제공하지 않습니다."
)


class BenchmarkDistributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    count: int


class BenchmarkAccountTypeStatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_type: str
    account_count: int
    mean_balance_krw: Decimal
    mean_monthly_contribution_krw: Decimal
    mean_risky_asset_ratio_percent: Decimal


class BenchmarkSummaryResponse(BaseModel):
    data_boundary: str = "mock"
    source_label: str = BENCHMARK_SOURCE_LABEL
    notice: str = BENCHMARK_NOTICE
    user_count: int
    account_count: int
    holding_count: int
    age_groups: list[BenchmarkDistributionOut]
    risk_profiles: list[BenchmarkDistributionOut]
    account_type_stats: list[BenchmarkAccountTypeStatOut]


@router.get("/benchmark/summary", response_model=BenchmarkSummaryResponse)
def benchmark_summary(
    repository: Annotated[BenchmarkRepository, Depends(get_benchmark_repository)],
) -> BenchmarkSummaryResponse:
    """Return aggregate statistics only; no account or user records leave the API."""

    summary = repository.get_summary()
    return BenchmarkSummaryResponse(
        user_count=summary.user_count,
        account_count=summary.account_count,
        holding_count=summary.holding_count,
        age_groups=summary.age_groups,
        risk_profiles=summary.risk_profiles,
        account_type_stats=summary.account_type_stats,
    )
