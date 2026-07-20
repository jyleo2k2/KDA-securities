"""Authenticated pension-account reads from the common account structure."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from ..auth import require_supabase_user_id
from ..pension_accounts_repository import (
    PensionAccountRepository,
    UserPensionPortfolio,
)
from .deps import get_pension_account_repository

router = APIRouter(tags=["pension-accounts"])


@router.get("/me/pension-accounts", response_model=UserPensionPortfolio)
def pension_accounts(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        PensionAccountRepository,
        Depends(get_pension_account_repository),
    ],
) -> UserPensionPortfolio:
    return repository.get(owner_id)
