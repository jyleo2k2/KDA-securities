"""Validate the six demo investor assessments and profile-led portfolios."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "data" / "mock"

PROFILE_BY_SCORE = (
    (16, "stable", "16점 이하"),
    (24, "stable_seeking", "17~24점"),
    (32, "risk_neutral", "25~32점"),
    (40, "active", "33~40점"),
    (56, "aggressive", "41점 이상"),
)
LEGACY_RISK_PROFILE_MAP = {
    "stable": "conservative",
    "stable_seeking": "conservative",
    "risk_neutral": "balanced",
    "active": "growth",
    "aggressive": "growth",
}
RISKY_ASSET_CLASSES = {"domestic_equity", "global_equity"}


def _load(name: str) -> object:
    return json.loads((MOCK_DIR / name).read_text(encoding="utf-8"))


def _expected_profile(score: int) -> tuple[str, str]:
    for upper, profile, band in PROFILE_BY_SCORE:
        if score <= upper:
            return profile, band
    raise ValueError(f"score exceeds the published maximum: {score}")


def _assert_sentence_count(reason: str) -> None:
    sentence_count = sum(reason.count(mark) for mark in (".", "!", "?"))
    if sentence_count not in {1, 2}:
        raise AssertionError("investment reason must contain one or two sentences")


def _financial_share_score(percent: int) -> int:
    if percent <= 9:
        return 1
    if percent <= 19:
        return 2
    if percent <= 29:
        return 3
    if percent <= 49:
        return 4
    return 5


def validate() -> dict[str, object]:
    profile_payload = _load("demo_investor_profiles.json")
    manifest = _load("demo_scenario_users.json")
    scenarios = _load("chatbot_scenarios.json")
    assert isinstance(profile_payload, dict)
    assert isinstance(manifest, dict)
    assert isinstance(scenarios, list)

    profiles = profile_payload["profiles"]
    users = manifest["users"]
    profiles_by_code = {item["scenario_code"]: item for item in profiles}
    users_by_code = {item["scenario_code"]: item for item in users}
    scenarios_by_code = {item["scenario_code"]: item for item in scenarios}
    assert len(profiles_by_code) == len(users_by_code) == len(scenarios_by_code) == 6
    assert set(profiles_by_code) == set(users_by_code) == set(scenarios_by_code)

    reasons: list[str] = []
    opinion_reviews: list[str] = []
    etf_theme_reviews: list[str] = []
    profile_counts: Counter[str] = Counter()
    candidate_profiles: set[str] = set()
    for code, profile in profiles_by_code.items():
        score = sum(answer["score"] for answer in profile["answers"])
        assert score == profile["total_score"]
        expected_profile, expected_band = _expected_profile(score)
        assert profile["investor_profile"] == expected_profile
        assert profile["score_band"] == expected_band
        assert len({answer["question_code"] for answer in profile["answers"]}) == 11
        financial_shares = profile["financial_product_shares_percent"]
        assert set(financial_shares) == {
            "guaranteed",
            "investment",
            "loan",
            "other",
        }
        assert sum(financial_shares.values()) == 100
        answers_by_code = {
            answer["question_code"]: answer for answer in profile["answers"]
        }
        assert answers_by_code["q3_investment_product_share"]["score"] == (
            _financial_share_score(financial_shares["investment"])
        )
        assert answers_by_code["q3_loan_product_share"]["score"] == (
            _financial_share_score(financial_shares["loan"])
        )
        if answers_by_code["q4_experienced_product"]["score"] == 0:
            assert profile["non_scored_answers"][
                "vulnerable_financial_consumer"
            ] is True

        reason = profile["investment_reason"].strip()
        assert reason
        _assert_sentence_count(reason)
        reasons.append(reason)
        opinion_review = profile["portfolio_opinion_review"].strip()
        assert opinion_review
        _assert_sentence_count(opinion_review)
        assert opinion_review != reason
        opinion_reviews.append(opinion_review)
        representative_codes = profile["representative_etf_isu_codes"]
        assert 1 <= len(representative_codes) <= 2
        assert len(representative_codes) == len(set(representative_codes))
        representative_theme = profile["representative_etf_theme"].strip()
        assert representative_theme
        etf_theme_review = profile["representative_etf_theme_review"].strip()
        assert etf_theme_review
        _assert_sentence_count(etf_theme_review)
        etf_theme_reviews.append(etf_theme_review)
        profile_counts[expected_profile] += 1
        if users_by_code[code]["is_demo_login_candidate"]:
            candidate_profiles.add(expected_profile)

        scenario = scenarios_by_code[code]
        assert scenario["risk_profile"] == LEGACY_RISK_PROFILE_MAP[expected_profile]
        accounts_by_type = {
            account["account_type"]: account for account in scenario["accounts"]
        }
        etf_names_by_code = {
            holding["etf_isu_code"]: holding["instrument_name"]
            for account in scenario["accounts"]
            for holding in account["holdings"]
            if holding.get("etf_isu_code")
        }
        assert set(representative_codes).issubset(etf_names_by_code)
        combined_review = f"{opinion_review} {etf_theme_review}"
        assert all(
            etf_names_by_code[isu_code] in combined_review
            for isu_code in representative_codes
        )
        assert set(profile["portfolio_allocations"]) == set(accounts_by_type)
        for account_type, allocations in profile["portfolio_allocations"].items():
            assert sum(allocations.values()) == 100
            target_risky = sum(
                percent
                for asset_class, percent in allocations.items()
                if asset_class in RISKY_ASSET_CLASSES
            )
            account = accounts_by_type[account_type]
            total = sum(Decimal(item["amount_krw"]) for item in account["holdings"])
            risky = sum(
                Decimal(item["amount_krw"])
                for item in account["holdings"]
                if item["asset_class_code"] in RISKY_ASSET_CLASSES
            )
            actual_risky = risky / total * Decimal("100")
            assert abs(actual_risky - Decimal(target_risky)) < Decimal("0.01")
            if account_type in {"dc", "irp"}:
                assert target_risky <= 70

    assert len(set(reasons)) == 6
    assert len(set(opinion_reviews)) == 6
    assert len(set(etf_theme_reviews)) == 6
    assert candidate_profiles == {
        "stable",
        "stable_seeking",
        "risk_neutral",
        "active",
        "aggressive",
    }
    assert profile_counts == Counter(
        {
            "stable": 2,
            "stable_seeking": 1,
            "risk_neutral": 1,
            "active": 1,
            "aggressive": 1,
        }
    )
    excluded = [
        users_by_code[code]
        for code, profile in profiles_by_code.items()
        if not users_by_code[code]["is_demo_login_candidate"]
        and profile["investor_profile"] == "stable"
    ]
    assert len(excluded) == 1
    assert excluded[0]["scenario_code"] == "pension_payout_transition"

    return {
        "profiles": dict(profile_counts),
        "candidate_profiles": sorted(candidate_profiles),
        "unique_investment_reasons": len(set(reasons)),
        "unique_portfolio_opinion_reviews": len(set(opinion_reviews)),
        "unique_representative_etf_theme_reviews": len(set(etf_theme_reviews)),
        "validated_accounts": sum(len(item["accounts"]) for item in scenarios),
    }


def main() -> None:
    print(json.dumps(validate(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
