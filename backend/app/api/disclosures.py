"""Read endpoints for normalized FSS disclosure snapshots (실데이터)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from ..retrieval.disclosures_repository import DisclosureReadRepository
from .deps import get_disclosures_repository

router = APIRouter(tags=["disclosures"])

DISCLOSURE_SOURCE_LABEL = "금융감독원 통합연금포털 OpenAPI 공시"


class PensionSavingsStatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    quarter: int
    area_name_raw: str
    company_name_raw: str
    reserve_krw: Decimal | None
    earn_rate_1y: Decimal | None
    avg_earn_rate_3y: Decimal | None
    fee_rate_1y: Decimal | None
    quality_flags: list[str]
    observed_at: datetime


class PensionSavingsDisclosureResponse(BaseModel):
    source_label: str
    year: int | None
    quarter: int | None
    results: list[PensionSavingsStatOut]


class RetirementStatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    quarter: int
    scheme: str
    area_name_raw: str
    company_name_raw: str
    reserve_krw: Decimal | None
    earn_rate_current: Decimal | None
    avg_earn_rate_3y: Decimal | None
    avg_earn_rate_5y: Decimal | None
    quality_flags: list[str]
    observed_at: datetime


class RetirementDisclosureResponse(BaseModel):
    source_label: str
    scheme: str | None
    year: int | None
    quarter: int | None
    results: list[RetirementStatOut]


@router.get(
    "/disclosures/pension-savings",
    response_model=PensionSavingsDisclosureResponse,
)
def pension_savings_disclosures(
    repository: Annotated[
        DisclosureReadRepository, Depends(get_disclosures_repository)
    ],
    year: int | None = Query(None, ge=2000, le=2100),
    quarter: int | None = Query(None, ge=1, le=4),
    limit: int = Query(100, ge=1, le=500),
) -> PensionSavingsDisclosureResponse:
    stats = repository.latest_pension_savings_stats(
        year=year, quarter=quarter, limit=limit
    )
    return PensionSavingsDisclosureResponse(
        source_label=DISCLOSURE_SOURCE_LABEL,
        year=year,
        quarter=quarter,
        results=[PensionSavingsStatOut.model_validate(stat) for stat in stats],
    )


@router.get("/disclosures/retirement", response_model=RetirementDisclosureResponse)
def retirement_disclosures(
    repository: Annotated[
        DisclosureReadRepository, Depends(get_disclosures_repository)
    ],
    scheme: Literal["db", "dc", "irp"] | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    quarter: int | None = Query(None, ge=1, le=4),
    limit: int = Query(100, ge=1, le=500),
) -> RetirementDisclosureResponse:
    stats = repository.latest_retirement_stats(
        scheme=scheme, year=year, quarter=quarter, limit=limit
    )
    return RetirementDisclosureResponse(
        source_label=DISCLOSURE_SOURCE_LABEL,
        scheme=scheme,
        year=year,
        quarter=quarter,
        results=[RetirementStatOut.model_validate(stat) for stat in stats],
    )
