"""Authenticated persistence and retrieval of investor-profile assessments."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, model_validator

from ..auth import require_supabase_user_id
from ..engine.models import RiskProfile
from ..engine.profile import ProfileSurveyInput, evaluate_profile
from ..investment_profile_policy import (
    PROFILE_VALIDITY_POLICY_VERSION,
    assessment_validity,
)
from ..investment_profile_repository import (
    InvestmentProfileAnswer,
    InvestmentProfilePreferences,
    InvestmentProfilePreferencesInput,
    InvestmentProfileRepository,
    StoredInvestmentProfile,
)
from .deps import get_investment_profile_repository

router = APIRouter(tags=["investment-profile"])


class InvestmentProfileSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    survey: ProfileSurveyInput
    investment_advice_desired: bool
    investor_information_provided: bool

    @model_validator(mode="after")
    def reject_advice_without_information(self) -> "InvestmentProfileSubmission":
        if (
            self.investment_advice_desired
            and not self.investor_information_provided
        ):
            raise ValueError(
                "investment advice requires investor information confirmation"
            )
        return self

    def preferences(self) -> InvestmentProfilePreferencesInput:
        return InvestmentProfilePreferencesInput(
            investment_advice_desired=self.investment_advice_desired,
            investor_information_provided=self.investor_information_provided,
        )


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessed_at: datetime
    total_score: int
    min_score: int
    max_score: int
    score_percent: Decimal
    risk_profile: RiskProfile
    engine_name: str
    engine_version: str
    rule_version: str
    provisional: bool
    answers: list[InvestmentProfileAnswer]
    assessed_on: date
    valid_until: date
    is_expired: bool
    validity_policy_version: str = PROFILE_VALIDITY_POLICY_VERSION


class InvestmentProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: AssessmentResponse | None
    preferences: InvestmentProfilePreferences | None


def _response(stored: StoredInvestmentProfile | None) -> InvestmentProfileResponse:
    if stored is None:
        return InvestmentProfileResponse(assessment=None, preferences=None)
    validity = assessment_validity(stored.assessment.assessed_at)
    return InvestmentProfileResponse(
        assessment=AssessmentResponse(
            **stored.assessment.model_dump(exclude={"assessment_id", "owner_id"}),
            assessed_on=validity.assessed_on,
            valid_until=validity.valid_until,
            is_expired=validity.is_expired,
        ),
        preferences=stored.preferences,
    )


@router.post("/me/investment-profile", response_model=InvestmentProfileResponse)
def save_investment_profile(
    submission: InvestmentProfileSubmission,
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        InvestmentProfileRepository, Depends(get_investment_profile_repository)
    ],
) -> InvestmentProfileResponse:
    return _response(
        repository.record(
            owner_id=owner_id,
            survey=submission.survey,
            evaluation=evaluate_profile(submission.survey),
            preferences=submission.preferences(),
        )
    )


@router.get("/me/investment-profile", response_model=InvestmentProfileResponse)
def get_investment_profile(
    owner_id: Annotated[UUID, Depends(require_supabase_user_id)],
    repository: Annotated[
        InvestmentProfileRepository, Depends(get_investment_profile_repository)
    ],
) -> InvestmentProfileResponse:
    return _response(repository.get_latest(owner_id))
