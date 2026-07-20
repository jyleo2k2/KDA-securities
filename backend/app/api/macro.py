"""Read-only API for sanitized official macro observations."""

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ..engine.models import AccountType
from ..etf_universe_database import PortfolioUniverseLoadError
from ..macro_evidence import (
    MacroAnalogRegimeSnapshot,
    MacroEvidenceRepository,
    MacroEvidenceSnapshot,
    MacroEvidenceUnavailable,
    attach_etf_outcomes,
)
from ..settings import Settings, get_settings
from .deps import get_macro_evidence_repository, get_portfolio_universe_repository

router = APIRouter(tags=["macro"])


class MacroAnalogEtfOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_type: AccountType
    isu_codes: list[str] = Field(min_length=1, max_length=8)


@router.get("/macro/evidence", response_model=MacroEvidenceSnapshot)
def macro_evidence(
    repository: Annotated[
        MacroEvidenceRepository, Depends(get_macro_evidence_repository)
    ],
) -> MacroEvidenceSnapshot:
    try:
        return repository.latest()
    except MacroEvidenceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Current macro evidence is not available",
        ) from exc


@router.get("/macro/analog-regimes", response_model=MacroAnalogRegimeSnapshot)
def macro_analog_regimes(
    repository: Annotated[
        MacroEvidenceRepository, Depends(get_macro_evidence_repository)
    ],
) -> MacroAnalogRegimeSnapshot:
    try:
        return repository.analog_regimes()
    except MacroEvidenceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Historical macro regime evidence is not available",
        ) from exc


@router.post(
    "/macro/analog-regimes/etf-outcomes",
    response_model=MacroAnalogRegimeSnapshot,
)
def macro_analog_regime_etf_outcomes(
    request: MacroAnalogEtfOutcomeRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    macro_repository: Annotated[
        MacroEvidenceRepository, Depends(get_macro_evidence_repository)
    ],
) -> MacroAnalogRegimeSnapshot:
    database_url = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None
        else ""
    )
    try:
        snapshot = macro_repository.analog_regimes()
        etf_repository = get_portfolio_universe_repository(
            request.account_type,
            database_url,
        )
        return attach_etf_outcomes(
            snapshot,
            repository=etf_repository,
            isu_codes=request.isu_codes,
        )
    except MacroEvidenceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Historical macro regime evidence is not available",
        ) from exc
    except (
        FileNotFoundError,
        ValueError,
        PortfolioUniverseLoadError,
        psycopg.Error,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ETF total-return history is not available",
        ) from exc
