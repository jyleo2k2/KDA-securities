from datetime import UTC, datetime

from backend.app.portfolio_cache_upgrade import upgrade_portfolio_examples_payload


def _legacy_report() -> dict[str, object]:
    return {
        "engine_version": "2026-07-16.3",
        "generated_at": "2026-07-16T04:52:58+00:00",
        "scenario_count": 1,
        "scenarios": [
            {
                "engine_version": "2026-07-16.3",
                "planning_return": {
                    "engine_version": "2026-07-16.3",
                    "coverage_weight_percent": "100.0000",
                    "net_planning_return_percent": "4.9100",
                    "components": [
                        {
                            "target_percent": "60.0000",
                            "uncertainty_discount_percent": "0.2500",
                            "net_planning_return_percent": "4.9000",
                        },
                        {
                            "target_percent": "40.0000",
                            "uncertainty_discount_percent": "0.1000",
                            "net_planning_return_percent": "4.9250",
                        },
                    ],
                },
                "portfolio_risk": {"engine_version": "2026-07-16.3"},
                "rebalancing": {"status": "not_requested"},
                "unchanged": {"candidate_codes": ["EQ", "CASH"]},
            }
        ],
    }


def test_upgrade_adds_only_current_schema_fields_and_migration_metadata() -> None:
    source = _legacy_report()
    migrated_at = datetime(2026, 7, 18, 3, 0, tzinfo=UTC)

    upgraded = upgrade_portfolio_examples_payload(source, migrated_at=migrated_at)

    scenario = upgraded["scenarios"][0]
    planning = scenario["planning_return"]
    assert planning["conservative_planning_return_percent"] == "4.9100"
    assert planning["base_planning_return_percent"] == "5.1000"
    assert scenario["rebalancing"]["drift_threshold_percent_points"] == "5"
    assert upgraded["engine_version"] == "2026-07-16.4"
    assert scenario["engine_version"] == "2026-07-16.4"
    assert planning["engine_version"] == "2026-07-16.4"
    assert scenario["portfolio_risk"]["engine_version"] == "2026-07-16.4"
    assert upgraded["generated_at"] == source["generated_at"]
    assert upgraded["schema_migration"] == {
        "source_engine_version": "2026-07-16.3",
        "target_engine_version": "2026-07-16.4",
        "migrated_at": "2026-07-18T03:00:00+00:00",
        "method": "derived_missing_fields_without_portfolio_reselection",
    }
    assert scenario["unchanged"] == source["scenarios"][0]["unchanged"]
    assert "conservative_planning_return_percent" not in (
        source["scenarios"][0]["planning_return"]
    )


def test_base_return_uses_components_before_aggregate_rounding() -> None:
    source = _legacy_report()
    planning = source["scenarios"][0]["planning_return"]
    planning["net_planning_return_percent"] = "4.9100"
    planning["components"] = [
        {
            "target_percent": "80.0000",
            "uncertainty_discount_percent": "0.0000",
            "net_planning_return_percent": "4.9100",
        },
        {
            "target_percent": "20.0000",
            "uncertainty_discount_percent": "0.0001",
            "net_planning_return_percent": "4.9102",
        },
    ]

    upgraded = upgrade_portfolio_examples_payload(
        source,
        migrated_at=datetime(2026, 7, 18, 3, 0, tzinfo=UTC),
    )

    assert (
        upgraded["scenarios"][0]["planning_return"][
            "base_planning_return_percent"
        ]
        == "4.9101"
    )
