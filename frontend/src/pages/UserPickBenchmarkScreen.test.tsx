// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DemoHeroPortfolio } from "../api/types";
import { UserPickBenchmarkScreen } from "./UserPickBenchmarkScreen";

function hero(
  nickname: string,
  scenarioCode: string,
  returnPct: string,
  likes: number,
): DemoHeroPortfolio {
  return {
    nickname,
    representative_age: 35,
    customer_context: "대표고객 목데이터",
    is_demo_login_candidate: false,
    scenario_code: scenarioCode,
    scenario_name: `${nickname} 시나리오`,
    age_band: "30대",
    risk_profile: "risk_neutral",
    investment_horizon_years: 20,
    total_amount_krw: "12340000",
    accounts: [],
    asset_allocations: [
      { asset_class_code: "domestic_equity", amount_krw: "7404000", allocation_percent: "60", account_count: 1 },
      { asset_class_code: "bond", amount_krw: "4936000", allocation_percent: "40", account_count: 1 },
    ],
    duplicated_asset_classes: [],
    risk_summary: { dominant_asset_class: "domestic_equity", dominant_asset_percent: "60", general_risky_asset_percent: "60", stress_scenario_code: "equity_drawdown", estimated_stress_loss_percent: "0", is_forecast: false, requires_rebalancing_review: false, policy_label: "목데이터" },
    past_performance: { metric_code: "mock", label: "과거 12개월 수익률", trailing_12m_return_pct: returnPct, period_start: "2025-01-01", period_end: "2025-12-31", calculation_basis: "목데이터", source_label: "대표고객 목데이터", data_kind: "MOCK", is_forecast: false, official_ranking_metric: false },
    like_summary: { metric_code: "mock", label: "좋아요", count: likes, as_of_date: "2026-07-22", data_kind: "MOCK", is_synthetic: true, performance_based: false },
    data_boundary: "mock",
  };
}

describe("UserPickBenchmarkScreen", () => {
  it("renders cards from supplied representative customers instead of hardcoded portfolios", () => {
    const topHero = hero("김대표", "hero-top", "8.4", 12);
    const lowerHero = hero("이대표", "hero-lower", "-1.2", 25);
    render(<UserPickBenchmarkScreen currentHero={topHero} heroes={[lowerHero, topHero]} onBack={vi.fn()} />);

    expect(screen.getAllByText("김대표").length).toBeGreaterThan(0);
    expect(screen.getByText("이대표")).toBeInTheDocument();
    expect(screen.getAllByText("+8.4%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("-1.2%").length).toBeGreaterThan(0);
    expect(screen.queryByText("직업군")).not.toBeInTheDocument();
    expect(screen.queryByText("운용기간순")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /김대표/ }));
    expect(screen.getAllByRole("button", { name: "닫기" }).length).toBeGreaterThan(0);
    expect(screen.getByText(/미래 수익을 예측하지 않습니다/)).toBeInTheDocument();
  });
});
