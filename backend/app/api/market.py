"""Read-only API for official KRX ETF daily volume snapshots."""

import logging
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel, ConfigDict

from ..etf_distribution_event_repository import (
    EtfDistributionEventDataset,
    EtfDistributionEventUnavailable,
    PostgresEtfDistributionEventRepository,
)
from ..etf_market_repository import (
    EtfMarketDataUnavailable,
    EtfMarketObservation,
    EtfMarketRepository,
)
from ..ingestion.krx_client import KRX_ETF_DAILY_ENDPOINT
from .deps import get_etf_distribution_event_repository, get_etf_market_repository
from .errors import ApiErrorCode, api_error

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


class EtfDistributionEventOut(BaseModel):
    event_type: str
    effective_date: date
    record_date: date | None
    payment_date: date | None
    cash_per_share_krw: Decimal | None
    ratio: Decimal | None
    timing_basis: str
    confidence: str
    status: str
    source_chips: list[dict[str, str | None]]


class EtfDistributionEventResponse(BaseModel):
    data_boundary: str = "official_distribution_event_data"
    as_of: date
    isu_code: str
    results: list[EtfDistributionEventOut]


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
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "Current KRX ETF market snapshot is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
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
        raise api_error(
            ApiErrorCode.INVALID_DATE_RANGE,
            "from_date must be on or before to_date",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        raise api_error(
            ApiErrorCode.RESOURCE_NOT_FOUND,
            "Requested ETF volume history was not found",
            status.HTTP_404_NOT_FOUND,
        ) from exc
    except psycopg.Error as exc:
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "KRX ETF volume history is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return _history_response(isu_code, observations)


@router.get("/market/etfs/{isu_code}/distribution-events")
def etf_distribution_events(
    repository: Annotated[
        PostgresEtfDistributionEventRepository,
        Depends(get_etf_distribution_event_repository),
    ],
    isu_code: Annotated[str, Path(pattern=r"^[0-9A-Z]{6}$")],
) -> EtfDistributionEventResponse:
    try:
        dataset = repository.latest_for_etf(isu_code)
    except (EtfDistributionEventUnavailable, psycopg.Error) as exc:
        raise api_error(
            ApiErrorCode.DATA_SOURCE_UNAVAILABLE,
            "ETF distribution event data is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    return _distribution_response(isu_code, dataset)


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


def _distribution_response(
    isu_code: str, dataset: EtfDistributionEventDataset
) -> EtfDistributionEventResponse:
    return EtfDistributionEventResponse(
        as_of=dataset.as_of,
        isu_code=isu_code,
        results=[
            EtfDistributionEventOut(
                event_type=str(event["event_type"]),
                effective_date=date.fromisoformat(str(event["effective_date"])),
                record_date=_event_date(event.get("record_date")),
                payment_date=_event_date(event.get("payment_date")),
                cash_per_share_krw=_event_decimal(event.get("cash_per_share_krw")),
                ratio=_event_decimal(event.get("ratio")),
                timing_basis=str(event["timing_basis"]),
                confidence=str(event["confidence"]),
                status=str(event["status"]),
                source_chips=_source_chips(event.get("source_evidence")),
            )
            for event in dataset.events
        ],
    )


def _event_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value is not None else None


def _event_decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _source_chips(value: object) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "source_type": str(item["source_type"]),
            "reference": next(
                (
                    str(item[key])
                    for key in ("source_url", "endpoint", "receipt_number")
                    if isinstance(item.get(key), str) and item[key]
                ),
                None,
            ),
        }
        for item in value
        if isinstance(item, dict) and isinstance(item.get("source_type"), str)
    ]
