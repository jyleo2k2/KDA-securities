from scripts.validate_demo_investor_profiles import validate


def test_demo_investor_profiles_follow_score_and_portfolio_contract() -> None:
    summary = validate()

    assert summary == {
        "profiles": {
            "stable": 2,
            "stable_seeking": 1,
            "active": 1,
            "aggressive": 1,
            "risk_neutral": 1,
        },
        "candidate_profiles": [
            "active",
            "aggressive",
            "risk_neutral",
            "stable",
            "stable_seeking",
        ],
        "unique_investment_reasons": 6,
        "unique_portfolio_opinion_reviews": 6,
        "unique_representative_etf_theme_reviews": 6,
        "validated_accounts": 13,
    }
