// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DemoHeroPortfolio, DemoUserFinancialContext } from "../api/types";
import { HomePage } from "./HomePage";
const hero = { nickname: "박준호(가상)", representative_age: 34, customer_context: "DC 방치", is_demo_login_candidate: true, scenario_code: "dc_dormant", scenario_name: "DC형 방치", age_band: "30대", risk_profile: "balanced", investment_horizon_years: 21, total_amount_krw: "60000000", accounts: [{ account_id: "dc", account_type: "dc", label: "회사 DC", holdings: [{ holding_id: "deposit", instrument_name: "원리금보장 상품", asset_class_code: "deposit", amount_krw: "60000000", risk_treatment: "capital_preservation" }] }], asset_allocations: [{ asset_class_code: "deposit", amount_krw: "60000000", allocation_percent: "100", account_count: 1 }], duplicated_asset_classes: [], risk_summary: { dominant_asset_class: "deposit", dominant_asset_percent: "100", general_risky_asset_percent: "0", stress_scenario_code: "equity_drawdown", estimated_stress_loss_percent: "0", is_forecast: false, requires_rebalancing_review: true, policy_label: "정책" }, past_performance: { metric_code: "balance_weighted_trailing_12m_mock_return", label: "과거 12개월 계좌잔액 가중 합성수익률", trailing_12m_return_pct: "7.72", period_start: "2025-01-01", period_end: "2025-12-31", calculation_basis: "계좌잔액 가중", source_label: "data/mock/accounts.csv 합성 계좌 수익률", data_kind: "MOCK", is_forecast: false, official_ranking_metric: false }, like_summary: { metric_code: "synthetic_demo_like_count", label: "추천(좋아요)", count: 126, as_of_date: "2026-07-21", data_kind: "MOCK", is_synthetic: true, performance_based: false }, data_boundary: "mock" } as DemoHeroPortfolio;
const context = { auth_user_id: "user-1", nickname: "박준호(가상)", representative_age: 34, customer_context: "DC 방치", scenario_code: "dc_dormant", scenario_name: "DC형 방치", age_band: "30대", risk_profile: "stable", investment_horizon_years: 21, tax_year: 2026, income_basis: "unknown", income_amount_krw: "0", dc_balance_krw: "60000000", irp_balance_krw: "0", pension_savings_balance_krw: "0", total_pension_balance_krw: "60000000", irp_contribution_krw: "0", pension_savings_contribution_krw: "0", as_of_date: "2026-07-21", data_kind: "mock", asset_classes: ["deposit"], defaulted_fields: [] } as DemoUserFinancialContext;
describe("HomePage", () => { afterEach(cleanup); it("shows only the logged-in user's data", () => { render(<HomePage error={null} hero={hero} investmentProfile={null} loading={false} onAnalyzeHero={vi.fn()} userContext={context} />); expect(screen.getByText("박준호님의", { exact: false })).toBeInTheDocument(); expect(screen.getByText("원리금보장 상품")).toBeInTheDocument(); expect(screen.getByText("2026-07-21 기준 계좌 현황입니다.")).toBeInTheDocument(); }); it("shows the saved investment profile instead of the demo scenario label", () => { render(<HomePage error={null} hero={hero} investmentProfile={{ assessment: { risk_profile: "active" } as never, preferences: null }} loading={false} onAnalyzeHero={vi.fn()} userContext={context} />); expect(screen.getByText("적극투자형", { exact: false })).toBeInTheDocument(); }); it("sends the logged-in scenario", () => { const onAnalyzeHero = vi.fn(); render(<HomePage error={null} hero={hero} investmentProfile={null} loading={false} onAnalyzeHero={onAnalyzeHero} userContext={context} />); fireEvent.click(screen.getByRole("button", { name: "내 연금 분석하기" })); expect(onAnalyzeHero).toHaveBeenCalledWith("dc_dormant"); }); });

describe("HomePage allocation detail", () => {
  it("toggles the selected asset detail", () => {
    render(<HomePage error={null} hero={hero} investmentProfile={null} loading={false} onAnalyzeHero={vi.fn()} userContext={context} />);
    const slice = screen.getByRole("button", { name: "원리금보장 100%" });
    fireEvent.click(slice);
    expect(screen.getByText("원리금보장 상세")).toBeInTheDocument();
    expect(screen.getByText(/회사 DC \(DC\) · 원리금보장 상품/)).toBeInTheDocument();
    fireEvent.click(slice);
    expect(screen.queryByText("원리금보장 상세")).not.toBeInTheDocument();
  });
});
