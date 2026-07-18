// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getDemoHeroes } from "../api/client";
import type { DemoHeroPortfolio } from "../api/types";
import { HomePage } from "./HomePage";


vi.mock("../api/client", () => ({
  getDemoHeroes: vi.fn(),
}));

const baseHero = {
  representative_age: 46,
  customer_context: "가상 고객 설명",
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

const heroes = [
  ["박준호(가상)", "dc_dormant"],
  ["이서연(가상)", "tax_contribution_uninvested"],
  ["정민재(가상)", "overlap_risk_concentration"],
  ["김하린(가상)", "young_retirement_distance"],
  ["최지훈(가상)", "family_budget_pressure"],
  ["윤정희(가상)", "pension_payout_transition"],
].map(([nickname, scenario_code]) => ({
  ...baseHero,
  nickname,
  scenario_code,
  ...(scenario_code === "overlap_risk_concentration"
    ? {
        total_amount_krw: "190000000.00",
        scenario_name: "계좌별 중복·위험 편중",
        accounts: [
          {
            account_id: "overlap_dc",
            account_type: "dc",
            label: "회사 DC",
            holdings: [
              {
                holding_id: "dc_global_equity",
                instrument_name: "KODEX 미국S&P500",
                etf_isu_code: "379800",
                asset_class_code: "global_equity",
                amount_krw: "60000000.00",
                risk_treatment: "general_risky",
              },
            ],
          },
        ],
        risk_summary: {
          ...baseHero.risk_summary,
          dominant_asset_class: "global_equity",
          dominant_asset_percent: "68.41",
          general_risky_asset_percent: "68.42",
          estimated_stress_loss_percent: "28.30",
          requires_rebalancing_review: true,
        },
      }
    : {}),
})) as DemoHeroPortfolio[];

describe("HomePage", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.mocked(getDemoHeroes).mockResolvedValue(heroes);
  });

  it("shows all six hero customers and the selected customer's ETF risk view", async () => {
    render(<HomePage onAnalyzeHero={vi.fn()} />);

    expect((await screen.findAllByText("박준호(가상)")).length).toBeGreaterThan(0);
    expect(screen.getByText("윤정희(가상)")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /정민재/ }));

    expect(screen.getByText("KODEX 미국S&P500")).toBeInTheDocument();
    expect(screen.getByText("379800")).toBeInTheDocument();
    expect(screen.getByText("28.30%")).toBeInTheDocument();
    expect(screen.getByText("리밸런싱 점검 필요")).toBeInTheDocument();
  });

  it("sends the selected hero scenario to the guide", async () => {
    const onAnalyzeHero = vi.fn();
    render(<HomePage onAnalyzeHero={onAnalyzeHero} />);

    await screen.findAllByText("박준호(가상)");
    fireEvent.click(screen.getByRole("button", { name: /정민재/ }));
    fireEvent.click(screen.getByRole("button", { name: "이 고객 분석하기" }));

    expect(onAnalyzeHero).toHaveBeenCalledWith("overlap_risk_concentration");
  });
});
