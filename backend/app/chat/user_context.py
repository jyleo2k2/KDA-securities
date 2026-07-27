"""Authenticated synthetic-user pension context loaded from PostgreSQL."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict

from ..engine import (
    AccountType,
    IncomeBasis,
    IrpDeferredIncomeStatus,
    PensionAccountTaxInput,
    PensionTaxScenarioInput,
    WithdrawalReason,
)
from ..engine.models import SourceChip
from .models import (
    ChatIntent,
    ChatResponse,
    CompletedSurveyProfile,
    ConversationContext,
    DataBoundary,
    NumericEvidence,
    SourceEvidence,
)

_DIRECT_CONTEXT_QUESTION = re.compile(
    r"(?:잔액|현재\s*(?:자산|금액)|올해.{0,8}납입|"
    r"납입.{0,8}(?:금액|얼마)|총\s*급여|종합\s*소득|"
    r"내.{0,8}(?:연금|계좌).{0,8}(?:현황|정보|잔액|납입))"
)

_NEWS_TOPICS_BY_ASSET_CLASS: dict[str, tuple[str, ...]] = {
    "cash": ("monetary_policy", "macro", "fx_rates"),
    "deposit": ("monetary_policy", "macro", "fx_rates"),
    "bond": ("monetary_policy", "macro", "fx_rates", "flows"),
    "global_equity": ("indices", "sector", "earnings", "fx_rates", "macro"),
    "eligible_tdf": ("indices", "flows", "macro", "monetary_policy"),
}


class DemoUserFinancialContext(BaseModel):
    """Server-validated context for one of the six synthetic Auth users."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    auth_user_id: UUID
    benchmark_user_id: str
    nickname: str
    representative_age: int
    customer_context: str
    scenario_code: str
    scenario_name: str
    age_band: str
    risk_profile: str
    investment_horizon_years: int
    tax_year: int
    income_basis: IncomeBasis
    income_amount_krw: Decimal
    dc_balance_krw: Decimal
    irp_balance_krw: Decimal
    pension_savings_balance_krw: Decimal
    total_pension_balance_krw: Decimal
    irp_contribution_krw: Decimal
    pension_savings_contribution_krw: Decimal
    as_of_date: date
    data_kind: str
    asset_classes: tuple[str, ...] = ()
    defaulted_fields: tuple[str, ...] = ()

    @property
    def preferred_news_topics(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                topic
                for asset_class in self.asset_classes
                for topic in _NEWS_TOPICS_BY_ASSET_CLASS.get(asset_class, ())
            )
        )

    def to_pension_tax_input(self) -> PensionTaxScenarioInput:
        income_basis = (
            IncomeBasis.GROSS_SALARY
            if self.income_basis == IncomeBasis.UNKNOWN
            else self.income_basis
        )
        return PensionTaxScenarioInput(
            tax_year=self.tax_year,
            income_basis=income_basis,
            income_amount_krw=self.income_amount_krw,
            pension_savings=PensionAccountTaxInput(
                balance_krw=self.pension_savings_balance_krw,
                current_year_contribution_krw=(self.pension_savings_contribution_krw),
            ),
            irp=PensionAccountTaxInput(
                balance_krw=self.irp_balance_krw,
                current_year_contribution_krw=self.irp_contribution_krw,
            ),
            withdrawal_reason=WithdrawalReason.GENERAL,
            irp_deferred_income_status=IrpDeferredIncomeStatus.UNKNOWN,
        )

    def personalize_survey_profile(
        self,
        profile: CompletedSurveyProfile | None,
    ) -> CompletedSurveyProfile | None:
        """Apply DB-backed age and account scope to a real survey result.

        Risk profile, loss tolerance, and retirement age remain survey inputs.
        The accumulation portfolio engine is validated only through age 54, so
        payout-stage users are not forced into that engine with fabricated data.
        """

        if profile is None or self.representative_age > 54:
            return None
        if profile.retirement_start_age <= self.representative_age:
            return None

        balances = (
            (AccountType.DC, self.dc_balance_krw),
            (AccountType.IRP, self.irp_balance_krw),
            (AccountType.PENSION_SAVINGS, self.pension_savings_balance_krw),
        )
        account_types = [account for account, balance in balances if balance > 0]
        if not account_types:
            return None
        account_type = (
            profile.account_type
            if profile.account_type in account_types
            else account_types[0]
        )
        return CompletedSurveyProfile(
            account_type=account_type,
            account_types=account_types,
            current_age=self.representative_age,
            retirement_start_age=profile.retirement_start_age,
            risk_profile=profile.risk_profile,
            loss_tolerance_percent=profile.loss_tolerance_percent,
        )

    def answers_directly(self, message: str) -> bool:
        return _DIRECT_CONTEXT_QUESTION.search(message) is not None

    def direct_response(self) -> ChatResponse:
        source = SourceEvidence(
            evidence_id="mock:user_context",
            label="내 연금 계좌 정보",
            locator="database://demo-user-financial-context/current",
            publisher="연금 코파일럿 계좌 정보",
            as_of=self.as_of_date,
            data_boundary=DataBoundary.MOCK,
        )
        fields = (
            ("DC 현재 잔액", self.dc_balance_krw),
            ("IRP 현재 잔액", self.irp_balance_krw),
            ("연금저축 현재 잔액", self.pension_savings_balance_krw),
            ("IRP 올해 납입액", self.irp_contribution_krw),
            (
                "연금저축 올해 납입액",
                self.pension_savings_contribution_krw,
            ),
            ("총급여액·종합소득금액", self.income_amount_krw),
        )
        numeric = [
            NumericEvidence(
                label=label,
                value=value,
                unit="KRW",
                evidence_id=source.evidence_id,
                basis="DB 조회값(미조회 항목은 0원)",
            )
            for label, value in fields
        ]
        default_note = (
            f" 확인되지 않은 항목({', '.join(self.defaulted_fields)})은 "
            "승인된 기준에 따라 0원으로 표시했어요."
            if self.defaulted_fields
            else ""
        )
        display_name = self.nickname.replace("(가상)", "").strip()
        answer = (
            f"{display_name}님의 연금 현황입니다. "
            f"DC {self._krw(self.dc_balance_krw)}, "
            f"IRP {self._krw(self.irp_balance_krw)}, "
            f"연금저축 {self._krw(self.pension_savings_balance_krw)}입니다. "
            f"올해 납입액은 IRP {self._krw(self.irp_contribution_krw)}, "
            f"연금저축 {self._krw(self.pension_savings_contribution_krw)}이고, "
            f"소득금액은 {self._krw(self.income_amount_krw)}입니다.{default_note}"
        )
        return ChatResponse(
            intent=ChatIntent.MOCK_PORTFOLIO,
            answer=answer,
            data_mode="authenticated_mock_context",
            sources=[source],
            numeric_evidence=numeric,
            limitations=[],
            conversation_context=ConversationContext(
                scenario_code=self.scenario_code,
                last_intent=ChatIntent.MOCK_PORTFOLIO,
            ),
        )

    @staticmethod
    def _krw(value: Decimal) -> str:
        return f"{value:,.0f}원"


class DemoUserContextRepository:
    def __init__(
        self, database_url: str, *, pool: ConnectionPool | None = None
    ) -> None:
        if not database_url:
            raise ValueError("database_url is required")
        self._database_url = database_url
        self._pool = pool

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if self._pool is None:
            with psycopg.connect(self._database_url) as connection:
                yield connection
            return
        with self._pool.connection() as connection:
            yield connection

    def get(self, auth_user_id: UUID) -> DemoUserFinancialContext | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                with latest_snapshots as (
                    select distinct on (snapshot.account_id)
                        snapshot.account_id,
                        snapshot.id,
                        snapshot.market_value_krw
                    from public.account_snapshots as snapshot
                    order by
                        snapshot.account_id,
                        snapshot.as_of_date desc,
                        snapshot.captured_at desc
                )
                select
                    context.auth_user_id,
                    context.benchmark_user_id,
                    context.nickname,
                    context.representative_age,
                    context.customer_context,
                    scenario.code,
                    scenario.name,
                    scenario.age_band,
                    scenario.risk_profile,
                    scenario.investment_horizon_years,
                    context.tax_year,
                    context.gross_salary_krw,
                    context.comprehensive_income_krw,
                    context.irp_contribution_krw,
                    context.pension_savings_contribution_krw,
                    context.as_of_date,
                    context.data_kind,
                    coalesce(
                        sum(snapshot.market_value_krw)
                            filter (where account.account_type = 'dc'),
                        0
                    ) as dc_balance_krw,
                    coalesce(
                        sum(snapshot.market_value_krw)
                            filter (where account.account_type = 'irp'),
                        0
                    ) as irp_balance_krw,
                    coalesce(
                        sum(snapshot.market_value_krw)
                            filter (where account.account_type = 'pension_savings'),
                        0
                    ) as pension_savings_balance_krw,
                    coalesce(sum(snapshot.market_value_krw), 0) as total_balance_krw,
                    count(account.id) filter (where account.account_type = 'dc'),
                    count(account.id) filter (where account.account_type = 'irp'),
                    count(account.id)
                        filter (where account.account_type = 'pension_savings'),
                    coalesce(
                        (
                            select array_agg(distinct asset.code order by asset.code)
                            from public.pension_accounts as holding_account
                            join latest_snapshots as holding_snapshot
                              on holding_snapshot.account_id = holding_account.id
                            join public.account_holding_snapshots as holding
                              on holding.snapshot_id = holding_snapshot.id
                            join public.asset_classes as asset
                              on asset.id = holding.asset_class_id
                            where holding_account.scenario_id = scenario.id
                              and holding_account.data_kind = 'mock'
                              and holding_account.origin = 'synthetic'
                        ),
                        array[]::text[]
                    ) as asset_classes
                from public.demo_user_financial_context as context
                join public.mock_scenarios as scenario
                  on scenario.id = context.scenario_id
                left join public.pension_accounts as account
                  on account.scenario_id = scenario.id
                 and account.data_kind = 'mock'
                 and account.origin = 'synthetic'
                left join latest_snapshots as snapshot
                  on snapshot.account_id = account.id
                where context.auth_user_id = %s
                group by
                    context.auth_user_id,
                    context.benchmark_user_id,
                    context.nickname,
                    context.representative_age,
                    context.customer_context,
                    scenario.id,
                    scenario.code,
                    scenario.name,
                    scenario.age_band,
                    scenario.risk_profile,
                    scenario.investment_horizon_years,
                    context.tax_year,
                    context.gross_salary_krw,
                    context.comprehensive_income_krw,
                    context.irp_contribution_krw,
                    context.pension_savings_contribution_krw,
                    context.as_of_date,
                    context.data_kind
                """,
                (auth_user_id,),
            )
            row = cursor.fetchone()
        return self._context_from_row(row) if row is not None else None

    def get_nickname(self, auth_user_id: UUID) -> str | None:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                select nullif(btrim(nickname), '')
                from public.user_profiles
                where user_id = %s
                """,
                (auth_user_id,),
            )
            row = cursor.fetchone()
        return row[0] if row is not None else None

    @staticmethod
    def _context_from_row(row: Any) -> DemoUserFinancialContext:
        gross_salary = row[11]
        comprehensive_income = row[12]
        if gross_salary is not None:
            income_basis = IncomeBasis.GROSS_SALARY
            income_amount = gross_salary
        elif comprehensive_income is not None:
            income_basis = IncomeBasis.COMPREHENSIVE_INCOME
            income_amount = comprehensive_income
        else:
            income_basis = IncomeBasis.UNKNOWN
            income_amount = Decimal("0")

        defaulted: list[str] = []
        if gross_salary is None and comprehensive_income is None:
            defaulted.append("income_amount_krw")
        if row[13] is None:
            defaulted.append("irp_contribution_krw")
        if row[14] is None:
            defaulted.append("pension_savings_contribution_krw")
        if row[21] == 0:
            defaulted.append("dc_balance_krw")
        if row[22] == 0:
            defaulted.append("irp_balance_krw")
        if row[23] == 0:
            defaulted.append("pension_savings_balance_krw")

        return DemoUserFinancialContext(
            auth_user_id=row[0],
            benchmark_user_id=row[1],
            nickname=row[2],
            representative_age=row[3],
            customer_context=row[4],
            scenario_code=row[5],
            scenario_name=row[6],
            age_band=row[7],
            risk_profile=row[8],
            investment_horizon_years=row[9],
            tax_year=row[10],
            income_basis=income_basis,
            income_amount_krw=income_amount,
            irp_contribution_krw=row[13] or Decimal("0"),
            pension_savings_contribution_krw=row[14] or Decimal("0"),
            as_of_date=row[15],
            data_kind=row[16],
            dc_balance_krw=row[17],
            irp_balance_krw=row[18],
            pension_savings_balance_krw=row[19],
            total_pension_balance_krw=row[20],
            asset_classes=tuple(row[24]),
            defaulted_fields=tuple(defaulted),
        )


def apply_demo_context_evidence(
    response: ChatResponse,
    context: DemoUserFinancialContext,
) -> ChatResponse:
    """Relabel server-injected values without changing engine calculations."""

    replacement_id = "mock:user_context"
    original_source_ids = {source.evidence_id for source in response.sources}
    uses_financial_context = bool(
        original_source_ids.intersection({"user:pension_tax", replacement_id})
    )
    uses_news_personalization = (
        response.intent == ChatIntent.NEWS and bool(context.preferred_news_topics)
    )
    uses_demo_context = uses_financial_context or uses_news_personalization or bool(
        original_source_ids.intersection({"mock:scenario"})
    )
    sources = []
    for source in response.sources:
        if source.evidence_id == "user:pension_tax":
            sources.append(
                source.model_copy(
                    update={
                        "evidence_id": replacement_id,
                        "label": "내 연금 계좌 정보",
                        "locator": ("database://demo-user-financial-context/current"),
                        "publisher": "연금 코파일럿 계좌 정보",
                        "as_of": context.as_of_date,
                        "data_boundary": DataBoundary.MOCK,
                    }
                )
            )
        elif source.evidence_id == "mock:scenario":
            sources.append(
                source.model_copy(
                    update={
                        "label": "내 연금 계좌 현황",
                        "locator": "database://mock-scenarios/current",
                        "publisher": "연금 코파일럿 계좌 정보",
                        "as_of": context.as_of_date,
                    }
                )
            )
        else:
            sources.append(source)
    if uses_news_personalization and replacement_id not in original_source_ids:
        sources.append(
            SourceEvidence(
                evidence_id=replacement_id,
                label="내 연금 계좌 자산군",
                locator="database://demo-user-financial-context/current",
                publisher="연금 코파일럿 계좌 정보",
                as_of=context.as_of_date,
                data_boundary=DataBoundary.MOCK,
            )
        )

    numeric = [
        item.model_copy(
            update={
                "evidence_id": (
                    replacement_id
                    if item.evidence_id == "user:pension_tax"
                    else item.evidence_id
                ),
                "basis": (
                    "내 연금 계좌 정보"
                    if item.evidence_id == "user:pension_tax"
                    else item.basis
                ),
            }
        )
        for item in response.numeric_evidence
    ]
    sections = [
        section.model_copy(
            update={
                "evidence_ids": list(
                    dict.fromkeys(
                        [
                            replacement_id if item == "user:pension_tax" else item
                            for item in section.evidence_ids
                        ]
                        + ([replacement_id] if uses_news_personalization else [])
                    )
                )
            }
        )
        for section in response.sections
    ]
    visualizations = [
        visualization.model_copy(
            update={
                "evidence_ids": [
                    replacement_id if item == "user:pension_tax" else item
                    for item in visualization.evidence_ids
                ]
            }
        )
        for visualization in response.visualizations
    ]
    scenario_evaluation = response.scenario_evaluation
    if scenario_evaluation is not None:
        scenario_evaluation = scenario_evaluation.model_copy(
            update={
                "source": SourceChip(
                    label="내 연금 계좌 현황",
                    reference="database://mock-scenarios/current",
                    as_of=context.as_of_date,
                )
            }
        )

    limitations = list(response.limitations)
    mock_notice = "로그인한 사용자의 계좌 정보를 사용했습니다."
    if uses_demo_context and mock_notice not in limitations:
        limitations.append(mock_notice)
    if uses_financial_context and context.defaulted_fields:
        limitations.append(
            "확인되지 않은 금액은 승인된 기준에 따라 0원으로 처리했어요."
        )

    return response.model_copy(
        update={
            "data_mode": (
                "authenticated_mock_context_engine"
                if response.intent == ChatIntent.PENSION_TAX
                else response.data_mode
            ),
            "sources": sources,
            "numeric_evidence": numeric,
            "sections": sections,
            "visualizations": visualizations,
            "scenario_evaluation": scenario_evaluation,
            "limitations": limitations,
        }
    )
