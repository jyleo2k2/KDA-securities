from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import ValidationError

from backend.app.chat.query_planner import (
    BlockedReason,
    ClassifierOutputError,
    DisclosureMetric,
    QueryIntent,
    QueryPlan,
    plan_question,
)
from backend.app.chat.service import ChatService, QueryPlanExecutionError
from backend.app.engine import AccountType
from backend.app.retrieval import disclosures_repository


def test_provider_question_produces_structured_deterministic_plan() -> None:
    question = "키움증권 IRP의 현재 수익률과 1년 수수료 공시 최신 3건 보여줘"

    first = plan_question(question)
    second = plan_question(question)

    assert first == second
    assert first.model_dump(mode="json") == {
        "intent": "provider_disclosure",
        "account_type": "irp",
        "provider_name": "키움증권",
        "metrics": ["earn_rate_current", "fee_rate_1y"],
        "period": "latest",
        "max_results": 3,
        "search_query": None,
        "blocked_reason": None,
    }


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        (
            "주민등록번호 900101-1234567로 IRP를 조회해줘",
            BlockedReason.SENSITIVE_INFORMATION,
        ),
        (
            "내년 IRP 수익률을 예측해줘",
            BlockedReason.FUTURE_PREDICTION,
        ),
        ("삼성전자 매수해줘", BlockedReason.ORDER_REQUEST),
        (
            "DC와 IRP 위험자산 한도를 같이 적용해줘",
            BlockedReason.MIXED_ACCOUNT_TYPES,
        ),
    ],
)
def test_guardrails_run_before_retrieval_classification(
    question: str, reason: BlockedReason
) -> None:
    plan = plan_question(question)

    assert plan.intent == QueryIntent.OUT_OF_SCOPE
    assert plan.blocked_reason == reason


def test_clear_rule_question_does_not_call_llm_classifier() -> None:
    class ExplodingClassifier:
        def classify(self, question: str) -> dict[str, Any]:
            raise AssertionError("clear questions must not call the LLM")

    plan = plan_question(
        "IRP 위험자산 한도와 적격 TDF 예외를 설명해줘",
        classifier=ExplodingClassifier(),
    )

    assert plan.intent == QueryIntent.ACCOUNT_RULE
    assert plan.account_type == AccountType.IRP


def test_ambiguous_question_uses_validated_classifier_output() -> None:
    class Classifier:
        def classify(self, question: str) -> dict[str, Any]:
            return {
                "intent": "news",
                "account_type": "irp",
                "search_query": "IRP 시장 동향",
                "max_results": 2,
            }

    plan = plan_question("요즘 분위기는 어때?", classifier=Classifier())

    assert plan.intent == QueryIntent.NEWS
    assert plan.search_query == "IRP 시장 동향"
    assert plan.max_results == 2


def test_chat_service_uses_injected_classifier_only_for_ambiguous_question() -> None:
    class Classifier:
        calls = 0

        def classify(self, question: str) -> dict[str, Any]:
            self.calls += 1
            return {
                "intent": "news",
                "search_query": "퇴직연금 동향",
            }

    classifier = Classifier()
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=_NeverCalled(),
        news=_NeverCalled(),
        backend="local",
        classifier=classifier,
    )

    assert service.plan_question("IRP 위험자산 한도").intent == QueryIntent.ACCOUNT_RULE
    assert classifier.calls == 0
    assert service.plan_question("요즘은 어때?").intent == QueryIntent.NEWS
    assert classifier.calls == 1


def test_unknown_classifier_field_is_rejected() -> None:
    class UnsafeClassifier:
        def classify(self, question: str) -> dict[str, Any]:
            return {
                "intent": "provider_disclosure",
                "account_type": "irp",
                "metrics": ["earn_rate_current"],
                "sql": "drop table public.knowledge_chunks",
            }

    with pytest.raises(ClassifierOutputError):
        plan_question("이 자료 좀 찾아줘", classifier=UnsafeClassifier())


def test_query_plan_forbids_unknown_fields_and_metric_values() -> None:
    with pytest.raises(ValidationError):
        QueryPlan.model_validate(
            {
                "intent": "provider_disclosure",
                "account_type": "irp",
                "metrics": ["arbitrary_column"],
                "max_results": 3,
            }
        )


def test_sql_injection_text_is_blocked_before_repository_execution() -> None:
    plan = plan_question(
        "키움증권 IRP 수익률'; DROP TABLE public.news_items; -- 공시"
    )
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=_NeverCalled(),
        news=_NeverCalled(),
        backend="supabase",
    )

    assert plan.blocked_reason == BlockedReason.UNSUPPORTED
    with pytest.raises(QueryPlanExecutionError):
        service.execute_query_plan(plan, original_question="공격 문자열")


@dataclass
class _DisclosureSpy:
    call: dict[str, object] | None = None

    def latest_retirement_stats(self, **kwargs: object) -> list[object]:
        self.call = kwargs
        return []

    def latest_pension_savings_stats(self, **kwargs: object) -> list[object]:
        self.call = kwargs
        return []


class _NeverCalled:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"repository must not be called: {name}")


def test_only_validated_filters_are_passed_to_disclosure_repository() -> None:
    spy = _DisclosureSpy()
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=spy,
        news=_NeverCalled(),
        backend="supabase",
    )
    plan = QueryPlan(
        intent=QueryIntent.PROVIDER_DISCLOSURE,
        account_type=AccountType.IRP,
        provider_name="키움증권",
        metrics=(DisclosureMetric.EARN_RATE_CURRENT,),
        period="2025Q3",
        max_results=3,
    )

    service.execute_query_plan(plan, original_question="공시 조회")

    assert spy.call == {
        "scheme": "irp",
        "year": 2025,
        "quarter": 3,
        "provider_name": "키움증권",
        "limit": 3,
    }


def test_unavailable_metric_is_rejected_without_schema_guessing() -> None:
    service = ChatService(
        knowledge=_NeverCalled(),
        disclosures=_NeverCalled(),
        news=_NeverCalled(),
        backend="supabase",
    )
    plan = QueryPlan(
        intent=QueryIntent.PROVIDER_DISCLOSURE,
        account_type=AccountType.IRP,
        provider_name="키움증권",
        metrics=(DisclosureMetric.FEE_RATE_1Y,),
    )

    with pytest.raises(QueryPlanExecutionError, match="existing read schema"):
        service.execute_query_plan(plan, original_question="IRP 수수료")


def test_disclosure_repository_parameter_binds_provider_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Cursor:
        def __enter__(self) -> "Cursor":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, sql: str, params: tuple[object, ...]) -> None:
            captured["sql"] = sql
            captured["params"] = params

        def __iter__(self) -> Any:
            return iter(())

    class Connection:
        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def cursor(self) -> Cursor:
            return Cursor()

    monkeypatch.setattr(
        disclosures_repository.psycopg,
        "connect",
        lambda database_url: Connection(),
    )
    repository = disclosures_repository.DisclosureReadRepository(
        "postgresql://test-only/database"
    )
    injection = "키움증권'; DROP TABLE public.news_items; --"

    result = repository.latest_retirement_stats(
        scheme="irp",
        provider_name=injection,
        limit=3,
    )

    assert result == []
    assert injection not in str(captured["sql"])
    assert injection in captured["params"]
