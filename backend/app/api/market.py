"""Read-only API for official KRX ETF daily volume snapshots."""

import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict

from ..etf_market_repository import (
    EtfMarketDataUnavailable,
    EtfMarketObservation,
    EtfMarketRepository,
)
from ..ingestion.krx_client import KRX_ETF_DAILY_ENDPOINT
from .deps import get_etf_market_repository

router = APIRouter(tags=["market"])
logger = logging.getLogger(__name__)

KRX_ETF_SOURCE_LABEL = "한국거래소 ETF 일별매매정보"


class EtfMarketObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_date: date
    isu_code: str
    isu_name: str
    close_price_krw: Decimal
    fluctuation_rate_percent: Decimal | None
    nav_krw: Decimal | None
    trading_volume: int
    trading_value_krw: Decimal
    market_cap_krw: Decimal | None
    net_assets_krw: Decimal | None
    benchmark_name: str | None


class EtfMarketSnapshotResponse(BaseModel):
    data_boundary: str = "official_market_data"
    source_label: str = KRX_ETF_SOURCE_LABEL
    source_url: str = KRX_ETF_DAILY_ENDPOINT
    as_of: date
    total_count: int
    result_count: int
    results: list[EtfMarketObservationOut]


class EtfVolumeHistoryResponse(BaseModel):
    data_boundary: str = "official_market_data"
    source_label: str = KRX_ETF_SOURCE_LABEL
    source_url: str = KRX_ETF_DAILY_ENDPOINT
    isu_code: str
    isu_name: str
    from_date: date
    to_date: date
    results: list[EtfMarketObservationOut]


@router.get("/market/etfs", response_model=EtfMarketSnapshotResponse)
def list_etf_market_snapshot(
    repository: Annotated[EtfMarketRepository, Depends(get_etf_market_repository)],
    as_of: Annotated[date | None, Query()] = None,
    sort_by: Annotated[
        Literal["trading_volume", "trading_value", "net_assets"],
        Query(alias="sort"),
    ] = "trading_volume",
    order: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=2000)] = 2000,
) -> EtfMarketSnapshotResponse:
    """Return every normalized ETF on the latest trading day, up to `limit`."""

    try:
        snapshot = repository.list_snapshot(
            as_of=as_of,
            sort_by=sort_by,
            order=order,
            limit=limit,
        )
    except (EtfMarketDataUnavailable, psycopg.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Current KRX ETF market snapshot is unavailable",
        ) from exc
    return EtfMarketSnapshotResponse(
        as_of=snapshot.as_of,
        total_count=snapshot.total_count,
        result_count=len(snapshot.results),
        results=[
            EtfMarketObservationOut.model_validate(result)
            for result in snapshot.results
        ],
    )


@router.get(
    "/market/etfs/{isu_code}/volume-history",
    response_model=EtfVolumeHistoryResponse,
)
def etf_volume_history(
    repository: Annotated[EtfMarketRepository, Depends(get_etf_market_repository)],
    isu_code: Annotated[str, Path(pattern=r"^[0-9A-Z]{6}$")],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 253,
) -> EtfVolumeHistoryResponse:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from_date must be on or before to_date",
        )
    try:
        observations = repository.volume_history(
            isu_code,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )
    except KeyError as exc:
        logger.warning("etf_volume_history_not_found isu_code=%s", isu_code)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested ETF volume history was not found",
        ) from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KRX ETF volume history is unavailable",
        ) from exc
    return _history_response(isu_code, observations)


def _history_response(
    isu_code: str,
    observations: list[EtfMarketObservation],
) -> EtfVolumeHistoryResponse:
    return EtfVolumeHistoryResponse(
        isu_code=isu_code,
        isu_name=observations[-1].isu_name,
        from_date=observations[0].base_date,
        to_date=observations[-1].base_date,
        results=[
            EtfMarketObservationOut.model_validate(result) for result in observations
        ],
    )
