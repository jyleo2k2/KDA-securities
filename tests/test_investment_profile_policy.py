from datetime import UTC, date, datetime

from backend.app.investment_profile_policy import assessment_validity


def test_assessment_validity_uses_kst_and_includes_the_last_valid_day() -> None:
    validity = assessment_validity(
        datetime(2026, 1, 13, 15, 0, tzinfo=UTC),
        today=date(2028, 1, 13),
    )

    assert validity.assessed_on == date(2026, 1, 14)
    assert validity.valid_until == date(2028, 1, 13)
    assert validity.is_expired is False


def test_assessment_validity_expires_on_the_day_after_its_last_valid_day() -> None:
    validity = assessment_validity(
        datetime(2026, 1, 13, tzinfo=UTC),
        today=date(2028, 1, 13),
    )

    assert validity.valid_until == date(2028, 1, 12)
    assert validity.is_expired is True


def test_assessment_validity_handles_month_end_and_leap_day() -> None:
    validity = assessment_validity(
        datetime(2024, 2, 29, 3, tzinfo=UTC),
        today=date(2026, 2, 27),
    )

    assert validity.valid_until == date(2026, 2, 27)
    assert validity.is_expired is False
