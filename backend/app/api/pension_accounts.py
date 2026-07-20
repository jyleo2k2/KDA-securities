"""Pension-account reads and static link-screen metadata."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ..auth import require_supabase_user_id
from ..pension_accounts_repository import (
    PensionAccountRepository,
    UserPensionPortfolio,
)
from .deps import get_pension_account_repository

router = APIRouter(tags=["pension-accounts"])


class AccountLinkOption(BaseModel):
    """Display-only account metadata; ``db`` is deliberately not an engine type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Literal["dc", "irp", "pension_savings", "db"]
    display_name: str
    category_label: str
    diagnosable: bool
    description: str | None = None


class AccountLinkOptionsResponse(BaseModel):
    """Static MVP metadata for the pension-account link screen."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    options: tuple[AccountLinkOption, ...]
    notice: str
    data_boundary: Literal["mock"] = "mock"


_ACCOUNT_LINK_OPTIONS = (
    AccountLinkOption(
        code="dc",
        display_name="DC\ud615 \ud1f4\uc9c1\uc5f0\uae08",
        category_label="\uc9c1\uc811 \uc6b4\uc6a9 \uacc4\uc88c",
        diagnosable=True,
    ),
    AccountLinkOption(
        code="irp",
        display_name="IRP",
        category_label="\uac1c\uc778 \uc5f0\uae08\uacc4\uc88c",
        diagnosable=True,
    ),
    AccountLinkOption(
        code="pension_savings",
        display_name="\uc5f0\uae08\uc800\ucd95",
        category_label="\uac1c\uc778 \uc5f0\uae08\uacc4\uc88c",
        diagnosable=True,
    ),
    AccountLinkOption(
        code="db",
        display_name="DB\ud615 \ud1f4\uc9c1\uc5f0\uae08",
        category_label="\ud68c\uc0ac \uc6b4\uc6a9 \uacc4\uc88c",
        diagnosable=False,
        description=(
            "\uac00\uc785 \uc5ec\ubd80\ub9cc "
            "\ud655\uc778\ud558\uba70 \uc6b4\uc6a9 "
            "\uc9c4\ub2e8\uc5d0\uc11c\ub294 "
            "\uc81c\uc678\ub429\ub2c8\ub2e4."
        ),
    ),
)

_ACCOUNT_LINK_NOTICE = (
    "\ud604\uc7ac MVP\ub294 \ubaa9\ub370\uc774\ud130 "
    "\uae30\ubc18 \uc870\ud68c\xb7\ubd84\uc11d "
    "\ud654\uba74\uc785\ub2c8\ub2e4. \uc2e4\uc81c "
    "\uacc4\uc88c \uc5f0\uacb0, \uacc4\uc88c \uc774\uc804, "
    "\uc790\ub3d9 \ub9e4\ub9e4\ub294 \ubc1c\uc0dd\ud558\uc9c0 "
    "\uc54a\uc2b5\ub2c8\ub2e4."
)


@router.get("/accounts/link-options", response_model=AccountLinkOptionsResponse)
def account_link_options() -> AccountLinkOptionsResponse:
    """Return static display metadata without authentication or database access."""

    return AccountLinkOptionsResponse(
        options=_ACCOUNT_LINK_OPTIONS,
        notice=_ACCOUNT_LINK_NOTICE,
    )


@router.get("/me/pension-accounts", response_model=UserPensionPortfolio)
def pension_accounts(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        PensionAccountRepository,
        Depends(get_pension_account_repository),
    ],
) -> UserPensionPortfolio:
    return repository.get(owner_id)
