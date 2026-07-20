import argparse
import json
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.engine.educational_portfolio import (
    EducationalPortfolioInput,
    RiskProfile,
    build_educational_portfolio,
)
from backend.app.engine.models import AccountType
from backend.app.portfolio_universe_repository import (
    PortfolioUniverseRepository,
)

REPRESENTATIVE_AGES = (25, 35, 45, 52)
RETIREMENT_START_AGES = (55, 60)
LOSS_TOLERANCE = {
    RiskProfile.STABLE: Decimal("8"),
    RiskProfile.STABLE_SEEKING: Decimal("12"),
    RiskProfile.RISK_NEUTRAL: Decimal("20"),
    RiskProfile.ACTIVE: Decimal("28"),
    RiskProfile.AGGRESSIVE: Decimal("40"),
}


def summarize_portfolio_risk_coverage(
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(
        scenario["portfolio_risk"]["status"] for scenario in scenarios
    )
    observation_counts = [
        scenario["portfolio_risk"]["observation_count"] for scenario in scenarios
    ]
    return {
        "status_counts": dict(sorted(status_counts.items())),
        "minimum_observation_count": min(observation_counts, default=0),
        "maximum_observation_count": max(observation_counts, default=0),
        "stress_scenario_result_count": sum(
            len(scenario["portfolio_risk"]["stress_scenarios"])
            for scenario in scenarios
        ),
        "missing_source_count": sum(
            not scenario["portfolio_risk"]["sources"] for scenario in scenarios
        ),
    }


def build_portfolio_examples(
    *,
    return_root: Path,
    krx_root: Path,
    adjusted_price_root: Path,
    event_root: Path,
    as_of: date,
) -> dict[str, Any]:
    scenarios = []
    account_counts = {}
    cap_violation_count = 0
    missing_candidate_sleeves = []
    universe_history_source_counts: Counter[str] = Counter()
    candidate_history_source_counts: Counter[str] = Counter()
    for account in AccountType:
        repository = PortfolioUniverseRepository.from_latest_cache(
            account,
            return_root=return_root,
            krx_root=krx_root,
            adjusted_price_root=adjusted_price_root,
            event_root=event_root,
        )
        universe_history_source_counts.update(repository.history_sources.values())
        account_scenarios = 0
        for age in REPRESENTATIVE_AGES:
            for retirement_start_age in RETIREMENT_START_AGES:
                for profile in RiskProfile:
                    request = EducationalPortfolioInput(
                        account_type=account,
                        age=age,
                        retirement_start_age=retirement_start_age,
                        risk_profile=profile,
                        loss_tolerance_percent=LOSS_TOLERANCE[profile],
                    )
                    evaluation = build_educational_portfolio(
                        request,
                        products=repository.products,
                        histories=repository.histories,
                        source_as_of=repository.as_of,
                        history_sources=repository.history_sources,
                        history_as_of=repository.latest_history_as_of,
                        score_cache=repository.score_cache,
                    )
                    candidate_history_source_counts.update(
                        candidate.price_history_source
                        for candidate in evaluation.candidates
                    )
                    target_sleeves = {
                        item.sleeve for item in evaluation.target_sleeves
                    }
                    candidate_sleeves = {
                        item.sleeve for item in evaluation.candidates
                    }
                    missing = sorted(target_sleeves.difference(candidate_sleeves))
                    if missing:
                        missing_candidate_sleeves.append(
                            {
                                "account_type": account.value,
                                "age": age,
                                "retirement_start_age": retirement_start_age,
                                "risk_profile": profile.value,
                                "sleeves": missing,
                            }
                        )
                    if account in {
                        AccountType.DC,
                        AccountType.IRP,
                    } and evaluation.final_general_risk_target_percent > Decimal("70"):
                        cap_violation_count += 1
                    scenarios.append(evaluation.model_dump(mode="json"))
                    account_scenarios += 1
        account_counts[account.value] = account_scenarios

    return {
        "report_type": "educational_pension_portfolio_examples",
        "as_of": as_of.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "engine_name": "educational_pension_portfolio",
        "engine_version": "2026-07-16.4",
        "representative_ages": REPRESENTATIVE_AGES,
        "retirement_start_ages": RETIREMENT_START_AGES,
        "risk_profiles": [profile.value for profile in RiskProfile],
        "account_types": [account.value for account in AccountType],
        "scenario_count": len(scenarios),
        "scenario_counts_by_account": account_counts,
        "risk_cap_violation_count": cap_violation_count,
        "missing_candidate_sleeve_count": len(missing_candidate_sleeves),
        "missing_candidate_sleeves": missing_candidate_sleeves,
        "universe_history_source_counts": dict(
            sorted(universe_history_source_counts.items())
        ),
        "candidate_history_source_counts": dict(
            sorted(candidate_history_source_counts.items())
        ),
        "portfolio_risk_coverage": summarize_portfolio_risk_coverage(scenarios),
        "limitations": [
            "These are educational examples, not individualized advice.",
            "Historical returns are excluded from ETF candidate ranking.",
            "Historical total returns are used only for risk measurement.",
            "CMA produces a planning assumption, never a return forecast.",
            "CMA is reviewed annually and is not frozen for 30 years.",
            "No trade order or automatic rebalancing is produced.",
        ],
        "scenarios": scenarios,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build age, risk-style, and account educational portfolios."
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--return-root", type=Path, default=Path("data/cache/returns"))
    parser.add_argument("--krx-root", type=Path, default=Path("data/raw/krx"))
    parser.add_argument(
        "--adjusted-price-root",
        type=Path,
        default=Path("data/cache/kis/adjusted_prices"),
    )
    parser.add_argument(
        "--event-root", type=Path, default=Path("data/cache/events")
    )
    parser.add_argument("--output", type=Path, default=Path("data/cache/portfolios"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = build_portfolio_examples(
        return_root=args.return_root,
        krx_root=args.krx_root,
        adjusted_price_root=args.adjusted_price_root,
        event_root=args.event_root,
        as_of=args.as_of,
    )
    output_path = args.output / (f"educational_portfolio_examples_{args.as_of}.json")
    _write_json(output_path, report)
    print(
        json.dumps(
            {
                "as_of": report["as_of"],
                "scenario_count": report["scenario_count"],
                "scenario_counts_by_account": report["scenario_counts_by_account"],
                "risk_cap_violation_count": report["risk_cap_violation_count"],
                "missing_candidate_sleeve_count": report[
                    "missing_candidate_sleeve_count"
                ],
                "universe_history_source_counts": report[
                    "universe_history_source_counts"
                ],
                "candidate_history_source_counts": report[
                    "candidate_history_source_counts"
                ],
                "portfolio_risk_coverage": report["portfolio_risk_coverage"],
                "output_path": output_path.as_posix(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if report["risk_cap_violation_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
