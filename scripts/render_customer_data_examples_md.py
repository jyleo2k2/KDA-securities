"""Render the exhaustive customer mock-data examples for team review."""

# ruff: noqa: E501 -- Korean prose and generated Markdown table rows are clearer intact.

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MOCK_DIR = ROOT / "data" / "mock"
OUTPUT_PATH = ROOT / "docs" / "30_스펙" / "고객_목데이터_전체_예시.md"

FIELD_DESCRIPTIONS = {
    "schema_version": "예시 문서 계약 버전",
    "user_id": "1만 명 합성 고객 식별자",
    "age": "현재 만 나이",
    "age_group": "연령대 코드",
    "employment_type": "고용 형태",
    "gross_salary_krw": "근로자 총급여액",
    "comprehensive_income_krw": "자영업자·프리랜서 종합소득금액",
    "tax_credit_income_basis": "세액공제율 판정에 사용한 소득 기준",
    "tax_credit_income_amount_krw": "세액공제율 판정 소득금액",
    "tax_year": "귀속 연도",
    "pension_tax_credit_rate_pct": "지방소득세 효과를 포함한 세액공제율",
    "total_tax_credit_eligible_contribution_krw": "IRP·연금저축 합산 세액공제 대상 납입액",
    "estimated_pension_tax_credit_krw": "예상 연금계좌 세액공제액",
    "planned_pension_start_age": "계획 연금 수령 시작 나이",
    "planned_receipt_years": "계획 수령 기간",
    "planned_annual_total_pension_receipt_krw": "전체 계좌 연간 예상 수령액",
    "planned_annual_personal_pension_receipt_krw": "IRP·연금저축 연간 예상 수령액",
    "planned_low_rate_pension_tax_pct": "계획상 저율 연금소득세율",
    "planned_receipt_tax_treatment": "예상 수령 세제 처리 분류",
    "risk_profile": "투자성향 코드",
    "preferred_management_type": "선호 운용 유형",
    "retirement_fund_attitude": "퇴직자산 운용 태도",
    "investment_readiness": "투자 이해·준비 수준",
    "payout_preference": "연금·일시금 수령 선호",
    "primary_outside_asset": "연금 외 주된 자산 유형",
    "mock_scenario": "합성 행동 시나리오",
    "data_kind": "실데이터·목데이터 구분",
    "source_ids": "통계 보정값·가정 식별자 목록",
    "pension_savings_contribution_krw": "당해연도 연금저축펀드 납입액",
    "irp_contribution_krw": "당해연도 개인 IRP 납입액",
    "account_id": "계좌 식별자",
    "account_type": "계좌 유형",
    "balance_krw": "현재 계좌 잔액",
    "monthly_contribution_krw": "연간 납입액의 월 환산값",
    "annual_contribution_krw": "당해연도 계좌 납입액",
    "contribution_status": "납입 활성 상태",
    "contribution_frequency": "합성 납입 주기",
    "account_open_year": "계좌 개설 연도",
    "contribution_years": "현재까지 가입·납입 기간",
    "planned_contribution_years_at_receipt": "수령개시 시점 예상 가입기간",
    "pension_receipt_eligibility": "계획 기준 연금수령 요건 분류",
    "tax_credit_eligible_contribution_krw": "이 계좌의 세액공제 대상 납입액",
    "estimated_tax_credit_krw": "이 계좌의 예상 세액공제액",
    "planned_annual_pension_receipt_krw": "이 계좌의 연간 예상 수령액",
    "risky_asset_ratio": "일반 위험자산 비율",
    "safe_asset_ratio": "안전자산 비율",
    "cash_ratio": "현금성 자산 비율",
    "trailing_12m_return_pct": "기준일까지의 과거 12개월 합성 수익률",
    "return_period_end": "과거 수익률 기준일",
    "asset_class": "자산군 코드",
    "weight": "계좌 내 보유 비중",
    "amount_krw": "보유 평가금액",
    "auth_user_id": "시연 로그인용 Supabase Auth UUID",
    "benchmark_user_id": "연결된 1만 명 합성 고객 식별자",
    "scenario_code": "대표 고객 시나리오 코드",
    "nickname": "시연용 가상 고객명",
    "representative_age": "대표 고객 표시 나이",
    "age_band": "대표 고객 표시 연령대",
    "login_id": "시연 로그인 ID",
    "customer_context": "대표 고객 상황 설명",
    "name": "시나리오 표시명",
    "description": "시나리오 설명",
    "investment_horizon_years": "은퇴까지 남은 투자기간",
    "label": "계좌 표시명",
    "holding_id": "상세 보유자산 식별자",
    "instrument_name": "ETF 또는 자산 표시명",
    "asset_class_code": "엔진용 자산군 코드",
    "risk_treatment": "위험한도 계산상 처리 방식",
    "statutory_exception": "DC·IRP 위험자산 한도의 법정 예외 유형",
    "etf_isu_code": "KRX ETF 종목코드",
}

DETAILED_HOLDING_FIELDS = (
    "holding_id",
    "instrument_name",
    "asset_class_code",
    "amount_krw",
    "risk_treatment",
    "statutory_exception",
    "etf_isu_code",
)


def _escape(value: Any) -> str:
    if value is None:
        return "`null`"
    if value == "":
        return '`""` (빈 값)'
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    rendered = str(value).replace("|", "\\|").replace("\n", "<br>")
    return f"`{rendered}`"


def _field_table(
    record: Mapping[str, Any], *, fields: Iterable[str] | None = None
) -> list[str]:
    selected_fields = tuple(fields) if fields is not None else tuple(record)
    lines = ["| 필드 | 저장값 | 의미 |", "|---|---|---|"]
    for field in selected_fields:
        lines.append(
            f"| `{field}` | {_escape(record.get(field))} | "
            f"{FIELD_DESCRIPTIONS.get(field, '저장 필드')} |"
        )
    return lines


def _money(value: Any) -> str:
    return f"{int(value):,}원"


def _holding_details(holdings: list[dict[str, Any]], *, detailed: bool) -> list[str]:
    lines: list[str] = []
    fields = DETAILED_HOLDING_FIELDS if detailed else None
    for index, holding in enumerate(holdings, start=1):
        label = holding.get("instrument_name") or holding.get("asset_class")
        lines.extend(
            [
                f"#### 보유자산 {index}. {label}",
                "",
                *_field_table(holding, fields=fields),
                "",
            ]
        )
    return lines


def _account_details(accounts: list[dict[str, Any]], *, detailed: bool) -> list[str]:
    lines: list[str] = []
    for index, account in enumerate(accounts, start=1):
        account_fields = {key: value for key, value in account.items() if key != "holdings"}
        account_name = account.get("label") or account.get("account_type")
        lines.extend(
            [
                "<details>",
                f"<summary><strong>계좌 {index}. {account_name} — "
                f"{len(account['holdings'])}개 보유자산</strong></summary>",
                "",
                "### 계좌 필드 전체",
                "",
                *_field_table(account_fields),
                "",
                "### 보유자산 필드 전체",
                "",
                *_holding_details(account["holdings"], detailed=detailed),
                "</details>",
                "",
            ]
        )
    return lines


def _issuer_overview(
    manifest: list[dict[str, Any]], scenarios: list[dict[str, Any]]
) -> list[str]:
    identity_by_code = {item["scenario_code"]: item for item in manifest}
    lines = [
        "| 대표 고객 | 시나리오 | ETF 운용사 | ETF 수 |",
        "|---|---|---|---:|",
    ]
    for scenario in scenarios:
        etf_holdings = [
            holding
            for account in scenario["accounts"]
            for holding in account["holdings"]
            if holding.get("etf_isu_code")
        ]
        issuers = sorted({holding["instrument_name"].split()[0] for holding in etf_holdings})
        nickname = identity_by_code[scenario["scenario_code"]]["nickname"]
        lines.append(
            f"| {nickname} | `{scenario['scenario_code']}` | "
            f"{', '.join(issuers)} | {len(etf_holdings)} |"
        )
    return lines


def render_document(
    examples: dict[str, Any],
    manifest: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
) -> str:
    benchmark = examples["benchmark_customer_example"]
    representative = examples["representative_customer_example"]
    identity = representative["demo_identity"]
    common = representative["benchmark_contract"]
    detailed = representative["detailed_etf_portfolio"]
    counts = examples["contract_counts"]

    benchmark_balance = sum(int(account["balance_krw"]) for account in benchmark["accounts"])
    representative_balance = sum(
        int(account["balance_krw"]) for account in common["accounts"]
    )
    detailed_balance = sum(
        int(holding["amount_krw"])
        for account in detailed["accounts"]
        for holding in account["holdings"]
    )
    pension_contribution = int(common["customer"]["pension_savings_contribution_krw"])
    irp_contribution = int(common["customer"]["irp_contribution_krw"])

    lines = [
        "# 고객 목데이터 전체 예시 — 팀 공유용",
        "",
        "> 이 문서는 실제 고객정보가 아닌 완전 합성(`MOCK`) 데이터입니다. "
        "`data/mock/customer_data_examples.json`에서 자동 생성하며, 수기 수정하지 않습니다.",
        "",
        "## 한눈에 보는 결론",
        "",
        "- 1만 명 고객은 각자 **사용자 29개 필드**, 보유 계좌별 **계좌 23개 필드**, "
        "보유자산별 **6개 필드**를 가집니다.",
        "- 대표 고객 6명은 1만 명 중 실제 기준 고객에 연결되어 위 공통 필드를 "
        "전부 그대로 가지며, 시연용 로그인 정보와 실제 적격 ETF 상세 보유내역을 추가로 가집니다.",
        "- 아래에는 일반 고객 `USR00001` 한 명과 대표 고객 "
        f"`{identity['nickname']}` 한 명의 저장 정보를 생략 없이 나열했습니다.",
        "- 모든 금액은 원 단위이고, 빈 문자열은 해당 고용형태에 적용되지 않는 소득 필드입니다.",
        "",
        "## 데이터 계약",
        "",
        "| 구분 | 필드 수 | 적용 범위 |",
        "|---|---:|---|",
        f"| 고객 | {counts['customer_columns']} | 1만 명과 대표 6명 모두 |",
        f"| 계좌 | {counts['account_columns_excluding_nested_holdings']} | 모든 DC·IRP·연금저축펀드 계좌 |",
        f"| 공통 보유자산 | {counts['benchmark_holding_columns']} | 1만 명 자산군 수준 보유내역 |",
        f"| 대표 고객 상세 보유자산 | {counts['detailed_etf_holding_columns']} | "
        "대표 6명의 ETF·현금·원리금보장 상세내역 |",
        "",
        "세액공제율은 근로자의 총급여가 5,500만 원 이하이거나 비근로자의 "
        "종합소득금액이 4,500만 원 이하이면 16.5%, 그 밖에는 13.2%입니다. "
        "실제 연간 납입액은 연금저축과 개인 IRP 합산 1,800만 원 이하이고, "
        "세액공제 대상은 연금저축 600만 원·합산 900만 원 한도입니다.",
        "",
        "## 대표 6명 ETF 운용사 분산 확인",
        "",
        *_issuer_overview(manifest, scenarios),
        "",
        "6명 전체에는 KODEX·TIGER·ACE·RISE·SOL·HANARO가 모두 남아 있습니다. "
        "고객별 시나리오와 자산구성에 맞춰 일부 운용사만 보유할 수 있으며, "
        "모든 고객에게 여섯 운용사를 억지로 동일 배분하지는 않습니다.",
        "",
        "---",
        "",
        "## 예시 1 — 1만 명 일반 고객 `USR00001`",
        "",
        f"이 고객은 계좌 {len(benchmark['accounts'])}개, 보유자산 "
        f"{sum(len(account['holdings']) for account in benchmark['accounts'])}개, "
        f"총잔액 {_money(benchmark_balance)}을 가진 합성 고객입니다.",
        "",
        "### 고객 필드 29개 전체",
        "",
        *_field_table(benchmark["customer"]),
        "",
        "### 계좌 및 보유자산 전체",
        "",
        *_account_details(benchmark["accounts"], detailed=False),
        "---",
        "",
        f"## 예시 2 — 대표 고객 `{identity['nickname']}`",
        "",
        f"대표 고객 `{identity['nickname']}`는 1만 명 중 `{identity['benchmark_user_id']}`를 "
        "선택해 시연용으로 상세화한 고객입니다. 공통 원본 계약은 그대로 유지하고, "
        "로그인·시나리오 정보와 ETF 단위 포트폴리오를 덧붙였습니다.",
        "",
        "### 시연 로그인·시나리오 연결 정보 전체",
        "",
        *_field_table(identity),
        "",
        "### 1만 명 공통 고객 필드 29개 전체",
        "",
        *_field_table(common["customer"]),
        "",
        "### 1만 명 공통 계좌 및 자산군 보유내역 전체",
        "",
        f"공통 원본은 계좌 {len(common['accounts'])}개, 보유자산 "
        f"{sum(len(account['holdings']) for account in common['accounts'])}개, "
        f"총잔액 {_money(representative_balance)}입니다.",
        "",
        *_account_details(common["accounts"], detailed=False),
        "### 시연용 상세 ETF 포트폴리오 메타데이터 전체",
        "",
        *_field_table({key: value for key, value in detailed.items() if key != "accounts"}),
        "",
        "### 시연용 상세 계좌 및 ETF 보유내역 전체",
        "",
        "상세 포트폴리오는 공통 원본 계좌의 잔액·자산군 금액을 바꾸지 않고 "
        "ETF 종목 단위로 분해한 것입니다. `statutory_exception`과 `etf_isu_code`는 "
        "선택 필드이지만, 아래 표에서는 없는 값도 `null`로 표시해 7개 필드를 모두 보여줍니다.",
        "",
        *_account_details(detailed["accounts"], detailed=True),
        "## 정합성 확인 결과",
        "",
        "| 검증 항목 | 결과 |",
        "|---|---|",
        f"| 대표 고객 공통 계좌 잔액 합계 | {_money(representative_balance)} |",
        f"| 대표 고객 상세 보유자산 합계 | {_money(detailed_balance)} |",
        f"| 상세화 전후 잔액 일치 | {'일치' if representative_balance == detailed_balance else '불일치'} |",
        f"| 연금저축 당해연도 납입액 | {_money(pension_contribution)} / 계좌 한도 6,000,000원 이내 |",
        f"| 개인 IRP 당해연도 납입액 | {_money(irp_contribution)} |",
        f"| 두 계좌 실제 납입 합계 | {_money(pension_contribution + irp_contribution)} / 18,000,000원 이내 |",
        f"| 세액공제 대상 합계 | {_money(common['customer']['total_tax_credit_eligible_contribution_krw'])} / 9,000,000원 이내 |",
        f"| 적용 세액공제율 | {common['customer']['pension_tax_credit_rate_pct']}% |",
        f"| 예상 세액공제액 | {_money(common['customer']['estimated_pension_tax_credit_krw'])} |",
        "| DC·IRP 위험자산 한도 | 각 계좌 `risky_asset_ratio` 70% 이하 |",
        "| 연금저축 위험자산 한도 | DC·IRP의 70% 총량 한도를 적용하지 않음 |",
        "",
        "> 예상 세액공제액은 교육용 계산값이며 실제 환급액을 보장하지 않습니다. "
        "수익률 필드는 과거 실적을 참고한 합성값으로 미래 수익 예측값이 아닙니다.",
        "",
        "## 재생성",
        "",
        "```powershell",
        "uv run python scripts/build_demo_customer_portfolios.py",
        "uv run python scripts/render_customer_data_examples_md.py",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    examples = json.loads(
        (MOCK_DIR / "customer_data_examples.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (MOCK_DIR / "demo_scenario_users.json").read_text(encoding="utf-8")
    )["users"]
    scenarios = json.loads(
        (MOCK_DIR / "chatbot_scenarios.json").read_text(encoding="utf-8")
    )
    OUTPUT_PATH.write_text(
        render_document(examples, manifest, scenarios), encoding="utf-8"
    )
    print(f"wrote {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
