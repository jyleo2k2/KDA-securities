"""Read-only API for sanitized official macro observations."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..macro_evidence import (
    MacroEvidenceRepository,
    MacroEvidenceSnapshot,
    MacroEvidenceUnavailable,
)
from .deps import get_macro_evidence_repository

router = APIRouter(tags=["macro"])


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
