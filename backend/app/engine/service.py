from typing import Protocol
from uuid import UUID

from .models import PortfolioInput, RiskCapEvaluation
from .portfolio import evaluate_risk_cap


class EngineRunRecorder(Protocol):
    def record(
        self,
        evaluation: RiskCapEvaluation,
        *,
        owner_id: UUID | None = None,
    ) -> UUID: ...


def evaluate_risk_cap_with_audit(
    portfolio: PortfolioInput,
    *,
    recorder: EngineRunRecorder | None = None,
    owner_id: UUID | None = None,
) -> RiskCapEvaluation:
    evaluation = evaluate_risk_cap(portfolio)
    if recorder is not None:
        recorder.record(evaluation, owner_id=owner_id)
    return evaluation
