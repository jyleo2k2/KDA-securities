from datetime import date

from backend.app.chat.knowledge import LocalMarkdownKnowledgeRepository
from backend.app.chat.models import ChatIntent, ChatRequest
from backend.app.chat.scenarios import LocalScenarioRepository
from backend.app.chat.service import ChatService
from backend.app.etf_distribution_event_repository import EtfDistributionEventDataset


class FakeDistributionEvents:
    def __init__(self) -> None:
        self.isu_codes: list[str] = []

    def latest_for_etf(self, isu_code: str) -> EtfDistributionEventDataset:
        self.isu_codes.append(isu_code)
        return EtfDistributionEventDataset(
            as_of=date(2026, 7, 23),
            events=[
                {
                    "event_type": "cash_distribution",
                    "effective_date": "2026-07-20",
                    "record_date": "2026-07-20",
                    "payment_date": "2026-07-23",
                    "cash_per_share_krw": "125",
                    "ratio": None,
                    "timing_basis": "kind",
                    "confidence": "high",
                    "status": "confirmed_cash_flow",
                    "source_evidence": [
                        {
                            "source_type": "kind_cash_distribution",
                            "source_url": "https://example.test/kind/069500",
                        }
                    ],
                }
            ],
        )


def _service(events: FakeDistributionEvents | None = None) -> ChatService:
    return ChatService(
        knowledge=LocalMarkdownKnowledgeRepository(),
        scenarios=LocalScenarioRepository(),
        distribution_events=events,  # type: ignore[arg-type]
    )


def test_distribution_question_with_isu_code_returns_official_event_and_source(
) -> None:
    events = FakeDistributionEvents()

    response = _service(events).ask(
        ChatRequest(message="069500 분배금과 지급일 알려줘")
    )

    assert response.intent == ChatIntent.ETF_DISTRIBUTION
    assert response.data_mode == "official_distribution_event"
    assert events.isu_codes == ["069500"]
    assert response.sections[0].blocks[0].items == [
        "확정 현금분배 · 기준일 2026-07-20 · 지급일 2026-07-23 · 주당 125원"
    ]
    assert response.sources[0].label == "KIND ETF 현금분배 공시"
    assert response.numeric_evidence[0].value == 125


def test_distribution_question_without_isu_code_requests_code_without_guessing(
) -> None:
    response = _service().ask(ChatRequest(message="ETF 분배금 지급일 알려줘"))

    assert response.intent == ChatIntent.ETF_DISTRIBUTION
    assert response.data_mode == "distribution_code_required"
    assert "6자리" in response.answer
