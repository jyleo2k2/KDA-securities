"""API-level validity policy for stored investor-profile assessments."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

PROFILE_VALIDITY_MONTHS = 24
PROFILE_VALIDITY_POLICY_VERSION = "2026-07-20.1"
KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class AssessmentValidity:
    assessed_on: date
    valid_until: date
    is_expired: bool


def assessment_validity(
    assessed_at: datetime,
    *,
    today: date | None = None,
) -> AssessmentValidity:
    assessed_on = assessed_at.astimezone(KST).date()
    valid_until = _add_months(assessed_on, PROFILE_VALIDITY_MONTHS) - date.resolution
    current_day = today or datetime.now(UTC).astimezone(KST).date()
    return AssessmentValidity(
        assessed_on=assessed_on,
        valid_until=valid_until,
        is_expired=current_day > valid_until,
    )


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year, month = divmod(month_index, 12)
    year += value.year
    month += 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))
