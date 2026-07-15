"""Builders mirroring the three seed mock scenarios (supabase/seed.sql)."""

from decimal import Decimal

from backend.app.engine.diagnostics import AccountHolding, AccountInput
from backend.app.engine.models import (
    AccountType,
    AssetClass,
    RiskTreatment,
    StatutoryException,
)


def dc_dormant_account() -> AccountInput:
    return AccountInput(
        account_id="dc_dormant/dc",
        account_type=AccountType.DC,
        holdings=[
            AccountHolding(
                holding_id="deposit-1",
                instrument_name="원리금보장 모형",
                asset_class=AssetClass.DEPOSIT,
                amount_krw=Decimal("60000000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            )
        ],
    )


def uninvested_irp_account() -> AccountInput:
    return AccountInput(
        account_id="tax_contribution_uninvested/irp",
        account_type=AccountType.IRP,
        holdings=[
            AccountHolding(
                holding_id="cash-1",
                instrument_name="IRP 현금성 모형",
                asset_class=AssetClass.CASH,
                amount_krw=Decimal("30000000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            )
        ],
    )


def uninvested_pension_savings_account() -> AccountInput:
    return AccountInput(
        account_id="tax_contribution_uninvested/pension_savings",
        account_type=AccountType.PENSION_SAVINGS,
        holdings=[
            AccountHolding(
                holding_id="cash-1",
                instrument_name="연금저축 현금성 모형",
                asset_class=AssetClass.CASH,
                amount_krw=Decimal("20000000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            )
        ],
    )


def overlap_dc_account() -> AccountInput:
    return AccountInput(
        account_id="overlap_risk_concentration/dc",
        account_type=AccountType.DC,
        holdings=[
            AccountHolding(
                holding_id="global-equity-1",
                instrument_name="글로벌주식형 모형",
                asset_class=AssetClass.GLOBAL_EQUITY,
                amount_krw=Decimal("60000000"),
                risk_treatment=RiskTreatment.GENERAL_RISKY,
            ),
            AccountHolding(
                holding_id="tdf-1",
                instrument_name="적격 TDF 모형",
                asset_class=AssetClass.ELIGIBLE_TDF,
                amount_krw=Decimal("20000000"),
                risk_treatment=RiskTreatment.STATUTORY_EXCEPTION,
                statutory_exception=StatutoryException.ELIGIBLE_TDF,
            ),
            AccountHolding(
                holding_id="deposit-1",
                instrument_name="원리금보장 모형",
                asset_class=AssetClass.DEPOSIT,
                amount_krw=Decimal("20000000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            ),
        ],
    )


def overlap_irp_account() -> AccountInput:
    return AccountInput(
        account_id="overlap_risk_concentration/irp",
        account_type=AccountType.IRP,
        holdings=[
            AccountHolding(
                holding_id="global-equity-1",
                instrument_name="글로벌주식형 모형",
                asset_class=AssetClass.GLOBAL_EQUITY,
                amount_krw=Decimal("34000000"),
                risk_treatment=RiskTreatment.GENERAL_RISKY,
            ),
            AccountHolding(
                holding_id="bond-1",
                instrument_name="채권형 모형",
                asset_class=AssetClass.BOND,
                amount_krw=Decimal("16000000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            ),
        ],
    )


def overlap_pension_savings_account() -> AccountInput:
    return AccountInput(
        account_id="overlap_risk_concentration/pension_savings",
        account_type=AccountType.PENSION_SAVINGS,
        holdings=[
            AccountHolding(
                holding_id="global-equity-1",
                instrument_name="글로벌주식형 모형",
                asset_class=AssetClass.GLOBAL_EQUITY,
                amount_krw=Decimal("36000000"),
                risk_treatment=RiskTreatment.GENERAL_RISKY,
            ),
            AccountHolding(
                holding_id="cash-1",
                instrument_name="현금성 모형",
                asset_class=AssetClass.CASH,
                amount_krw=Decimal("4000000"),
                risk_treatment=RiskTreatment.CAPITAL_PRESERVATION,
            ),
        ],
    )
