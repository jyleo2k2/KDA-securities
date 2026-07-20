from backend.app.portfolio_examples_report import (
    summarize_portfolio_risk_coverage,
)


def _scenario(
    *,
    status: str,
    observation_count: int,
    stress_count: int,
    has_sources: bool,
) -> dict:
    return {
        "portfolio_risk": {
            "status": status,
            "observation_count": observation_count,
            "stress_scenarios": [{} for _ in range(stress_count)],
            "sources": ([{}] if has_sources else []),
        }
    }


def test_summarize_portfolio_risk_coverage_reports_gaps() -> None:
    summary = summarize_portfolio_risk_coverage(
        [
            _scenario(
                status="complete",
                observation_count=252,
                stress_count=3,
                has_sources=True,
            ),
            _scenario(
                status="insufficient_common_history",
                observation_count=40,
                stress_count=3,
                has_sources=False,
            ),
        ]
    )

    assert summary == {
        "status_counts": {
            "complete": 1,
            "insufficient_common_history": 1,
        },
        "minimum_observation_count": 40,
        "maximum_observation_count": 252,
        "stress_scenario_result_count": 6,
        "missing_source_count": 1,
    }


def test_summarize_portfolio_risk_coverage_handles_no_scenarios() -> None:
    assert summarize_portfolio_risk_coverage([]) == {
        "status_counts": {},
        "minimum_observation_count": 0,
        "maximum_observation_count": 0,
        "stress_scenario_result_count": 0,
        "missing_source_count": 0,
    }
