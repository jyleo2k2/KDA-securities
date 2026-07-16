from typing import Any

KIS_RETIREMENT_NOTICE_URL = (
    "https://www.truefriend.com/pension/nwEtcinfo/Notice.jsp"
    "?cmd=A_NW_33030View&num=47065&subFlag=1"
)
KIS_RETIREMENT_RESTRICTION_URL = (
    "https://www.truefriend.com/pension/nwEtcinfo/Notice.jsp"
    "?cmd=A_NW_33030View&num=46862&subFlag=1"
)
PENSION_SAVINGS_RULE_URL = (
    "https://truefriend.com/pension/nwInvestment/PersonalPensionGuid.jsp"
)
GENERAL_RISK_CAP_RULE_ID = "DC_IRP_GENERAL_RISK_ASSET_CAP"
LOWER_RISK_EXCLUSION_RULE_ID = "DC_IRP_LOWER_RISK_METHOD_CAP_EXCLUSION"


def _retirement_result(
    kis_retirement_product: dict[str, object] | None,
) -> dict[str, Any]:
    if kis_retirement_product is None:
        return {
            "eligible": False,
            "status": "not_on_kis_official_retirement_list",
            "verification_level": "provider_official_list",
            "reason_code": "KIS_RETIREMENT_LIST_ABSENCE",
        }
    limit = int(kis_retirement_product["retirement_investment_limit_percent"])
    legal_rule_ids = [
        GENERAL_RISK_CAP_RULE_ID
        if limit == 70
        else LOWER_RISK_EXCLUSION_RULE_ID
    ]
    return {
        "eligible": True,
        "status": "eligible_at_kis",
        "verification_level": "provider_official_list",
        "max_allocation_percent": limit,
        "cap_treatment": (
            "GENERAL_70" if limit == 70 else "PROVIDER_CONFIRMED_100"
        ),
        "legal_rule_ids": legal_rule_ids,
        "exception_type": (
            None if limit == 70 else "provider_limit_reason_not_inferred"
        ),
        "allocation_bucket": (
            "full_allocation_eligible" if limit == 100 else "general_risky_70_cap"
        ),
        "reason_code": "KIS_RETIREMENT_LIST_EXACT_CODE_MATCH",
        "source_url": KIS_RETIREMENT_NOTICE_URL,
        "kis_official_category": {
            "major": kis_retirement_product["major_category"],
            "middle": kis_retirement_product["middle_category"],
            "minor": kis_retirement_product["minor_category"],
        },
    }


def _pension_savings_result() -> dict[str, Any]:
    return {
        "eligible": True,
        "status": "eligible_by_account_rule",
        "verification_level": "account_rule_not_provider_inventory",
        "max_allocation_percent": 100,
        "allocation_bucket": "no_statutory_aggregate_risk_cap",
        "reason_code": "DOMESTIC_LISTED_NORMAL_ETF",
        "source_url": PENSION_SAVINGS_RULE_URL,
    }


def classify_pension_account_eligibility(
    classification: dict[str, object],
    kis_retirement_product: dict[str, object] | None,
) -> dict[str, dict[str, Any]]:
    leverage_type = str(classification.get("leverage_type") or "unknown")
    if leverage_type in {"leveraged", "inverse"}:
        retirement_prohibited = {
            "eligible": False,
            "status": "ineligible_by_account_rule",
            "verification_level": "provider_official_restriction",
            "reason_code": "RETIREMENT_LEVERAGE_INVERSE_PROHIBITED",
            "source_url": KIS_RETIREMENT_RESTRICTION_URL,
        }
        pension_savings_prohibited = {
            "eligible": False,
            "status": "ineligible_by_account_rule",
            "verification_level": "provider_official_account_rule",
            "reason_code": "PENSION_SAVINGS_LEVERAGE_INVERSE_PROHIBITED",
            "source_url": PENSION_SAVINGS_RULE_URL,
        }
        return {
            "dc": dict(retirement_prohibited),
            "irp": dict(retirement_prohibited),
            "pension_savings": pension_savings_prohibited,
        }

    retirement = _retirement_result(kis_retirement_product)
    return {
        "dc": dict(retirement),
        "irp": dict(retirement),
        "pension_savings": _pension_savings_result(),
    }
