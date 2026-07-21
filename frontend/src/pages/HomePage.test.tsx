// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DemoHeroPortfolio, DemoUserFinancialContext } from "../api/types";
import { HomePage } from "./HomePage";

const baseHero = {
  representative_age: 46,
  customer_context: "가상 고객 설명",
  is_demo_login_candidate: true,
  scenario_name: "DC형 방치",
  age_band: "40대",
  risk_profile: "balanced",
  investment_horizon_years: 20,
  total_amount_krw: "60000000.00",
  accounts: [],
  asset_allocations: [
    {
      asset_class_code: "deposit",
      amount_krw: "60000000.00",
      allocation_percent: "100.00",
      account_count: 1,
    },
  ],
  duplicated_asset_classes: [],
  risk_summary: {
    dominant_asset_class: "deposit",
    dominant_asset_percent: "100.00",
    general_risky_asset_percent: "0.00",
    stress_scenario_code: "equity_drawdown",
    estimated_stress_loss_percent: "0.00",
    is_forecast: false,
    requires_rebalancing_review: true,
    policy_label: "연금 코파일럿 자산군 스트레스 정책",
  },
  data_boundary: "mock",
};

const hero = {
  ...baseHero,
  nickname: "박준호(가상)",
  scenario_code: "dc_dormant",
  accounts: [
    {
      account_id: "dc_account",
      account_type: "dc",
      label: "회사 DC",
      holdings: [
        {
          holding_id: "dc_deposit",
          instrument_name: "원리금보장 상품",
          asset_class_code: "deposit",
          amount_krw: "60000000.00",
          risk_treatment: "capital_preservation",
        },
      ],
    },
  ],
} as DemoHeroPortfolio;

const userContext = {
  auth_user_id: "user-1",
  nickname: "박준호(가상)",
  representative_age: 34,
  customer_context: "회사 DC 적립금이 원리금보장 상품에만 머문 방치형 고객",
  scenario_code: "dc_dormant",
  scenario_name: "DC형 방치",
  age_band: "30대",
  risk_profile: "stable",
  investment_horizon_years: 21,
  tax_year: 2026,
  income_basis: "unknown",
  income_amount_krw: "0",
  dc_balance_krw: "60000000",
  irp_balance_krw: "0",
  pension_savings_balance_krw: "0",
  total_pension_balance_krw: "60000000",
  irp_contribution_krw: "0",
  pension_savings_contribution_krw: "0",
  as_of_date: "2026-07-21",
  data_kind: "mock",
  asset_classes: ["deposit"],
  defaulted_fields: [],
} as DemoUserFinancialContext;

describe("HomePage", () => {
  afterEach(cleanup);

  it("shows only the logged-in user's pension data", () => {
    render(<HomePage error={null} hero={hero} loading={false} onAnalyzeHero={vi.fn()} userContext={userContext} />);

    expect(screen.getByText("박준호(가상)님의", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("원리금보장 상품")).toBeInTheDocument();
    expect(screen.getByText("리밸런싱 점검 필요")).toBeInTheDocument();
    expect(screen.queryByText("이서연(가상)")).not.toBeInTheDocument();
  });

  it("sends the logged-in user's scenario to the guide", () => {
    const onAnalyzeHero = vi.fn();
    render(<HomePage error={null} hero={hero} loading={false} onAnalyzeHero={onAnalyzeHero} userContext={userContext} />);

    fireEvent.click(screen.getByRole("button", { name: "내 연금 분석하기" }));

    expect(onAnalyzeHero).toHaveBeenCalledWith("dc_dormant");
  });
});
