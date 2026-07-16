from pathlib import Path

from pydantic import TypeAdapter

from ..engine import ScenarioPortfolioInput
from .models import ScenarioSummary

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIO_PATH = ROOT / "data" / "mock" / "chatbot_scenarios.json"


class LocalScenarioRepository:
    def __init__(self, path: Path = DEFAULT_SCENARIO_PATH) -> None:
        self._path = path
        adapter = TypeAdapter(list[ScenarioPortfolioInput])
        scenarios = adapter.validate_json(self._path.read_text(encoding="utf-8"))
        self._scenarios = tuple(scenarios)

    def get(self, code: str) -> ScenarioPortfolioInput | None:
        return next(
            (
                scenario
                for scenario in self._scenarios
                if scenario.scenario_code == code
            ),
            None,
        )

    def list(self) -> list[ScenarioSummary]:
        return [
            ScenarioSummary(
                code=scenario.scenario_code,
                name=scenario.name,
                description=scenario.description,
                age_band=scenario.age_band,
                risk_profile=scenario.risk_profile,
                investment_horizon_years=scenario.investment_horizon_years,
            )
            for scenario in self._scenarios
        ]
