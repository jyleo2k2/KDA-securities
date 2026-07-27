"""Aggregate-only endpoints for the anonymous pension benchmark."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from ..auth import require_supabase_user_id
from ..benchmark_follow_repository import (
    BenchmarkFollowRepository,
    BenchmarkFollowState,
    UnknownBenchmarkPortfolioError,
)
from ..benchmark_repository import BenchmarkRepository
from .deps import get_benchmark_follow_repository, get_benchmark_repository

router = APIRouter(tags=["benchmark"])

BENCHMARK_SOURCE_LABEL = "통계 모델 기반 익명 계좌 데이터"
BENCHMARK_NOTICE = (
    "이 화면은 통계 모델 기반 계좌 데이터의 집계입니다. "
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


class BenchmarkFollowPreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    following: bool


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


@router.get(
    "/me/benchmark-follows",
    response_model=list[BenchmarkFollowState],
)
def benchmark_follow_states(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        BenchmarkFollowRepository,
        Depends(get_benchmark_follow_repository),
    ],
) -> list[BenchmarkFollowState]:
    return repository.list_states(owner_id)


@router.put(
    "/me/benchmark-follows/{portfolio_id}",
    response_model=BenchmarkFollowState,
)
def update_benchmark_follow(
    portfolio_id: str,
    preference: BenchmarkFollowPreferenceInput,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        BenchmarkFollowRepository,
        Depends(get_benchmark_follow_repository),
    ],
) -> BenchmarkFollowState:
    try:
        return repository.set_following(
            owner_id,
            portfolio_id=portfolio_id,
            following=preference.following,
        )
    except UnknownBenchmarkPortfolioError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 이용자 포트폴리오를 찾을 수 없어요.",
        ) from exc
