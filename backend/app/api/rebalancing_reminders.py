"""Authenticated rebalancing-review reminder API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ..auth import require_supabase_user_id
from ..rebalancing_reminder_repository import (
    RebalancingReminderRepository,
    RebalancingReminderState,
)
from .deps import get_rebalancing_reminder_repository

router = APIRouter(tags=["rebalancing-reminders"])


class RebalancingReminderPreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


@router.get(
    "/me/rebalancing-reminder", response_model=RebalancingReminderState
)
def get_rebalancing_reminder(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        RebalancingReminderRepository, Depends(get_rebalancing_reminder_repository)
    ],
) -> RebalancingReminderState:
    return repository.get_state(owner_id)


@router.put(
    "/me/rebalancing-reminder", response_model=RebalancingReminderState
)
def update_rebalancing_reminder(
    preference: RebalancingReminderPreferenceInput,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        RebalancingReminderRepository, Depends(get_rebalancing_reminder_repository)
    ],
) -> RebalancingReminderState:
    return repository.update_enabled(owner_id, enabled=preference.enabled)


@router.post(
    "/me/rebalancing-reminder/complete", response_model=RebalancingReminderState
)
def complete_rebalancing_review(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        RebalancingReminderRepository, Depends(get_rebalancing_reminder_repository)
    ],
) -> RebalancingReminderState:
    return repository.record_review_completion(owner_id)
