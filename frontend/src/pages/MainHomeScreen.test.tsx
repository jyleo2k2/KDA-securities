// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DemoHeroPortfolio, InvestmentProfileResponse } from "../api/types";
import { MainHomeScreen } from "./MainHomeScreen";

afterEach(cleanup);

describe("MainHomeScreen", () => {
  afterEach(cleanup);

  it("renders the selected user's holdings instead of fixed preview percentages", () => {
    const hero = {
      total_amount_krw: "1000000",
      accounts: [{
        holdings: [{ instrument_name: "사용자 보유 ETF", amount_krw: "1000000" }],
      }],
      asset_allocations: [],
      risk_summary: { requires_rebalancing_review: false },
    } as unknown as DemoHeroPortfolio;

    render(
      <MainHomeScreen
        error={null}
        hero={hero}
        investmentProfile={null}
        loading={false}
        onOpenChat={vi.fn()}
        onOpenPlanner={vi.fn()}
        onOpenProfile={vi.fn()}
        onOpenStrategyExplore={vi.fn()}
        onOpenUserPick={vi.fn()}
        onResurvey={vi.fn()}
        userContext={null}
      />,
    );

    expect(screen.getByText("사용자 보유 ETF")).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "총 연금 자산 보유 종목 비중" }).querySelector("circle")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "재설문하기" })).not.toBeInTheDocument();
  });

  it("shows the saved investment profile after login", () => {
    const onOpenPlanner = vi.fn();
    const investmentProfile = {
      assessment: {
        assessed_on: "2026-07-22",
        risk_profile: "active",
        is_expired: false,
      },
      preferences: null,
    } as InvestmentProfileResponse;

    render(
      <MainHomeScreen
        error={null}
        hero={null}
        investmentProfile={investmentProfile}
        loading={false}
        onOpenChat={vi.fn()}
        onOpenPlanner={onOpenPlanner}
        onOpenProfile={vi.fn()}
        onOpenStrategyExplore={vi.fn()}
        onOpenUserPick={vi.fn()}
        onResurvey={vi.fn()}
        userContext={null}
      />,
    );

    expect(screen.getByText("저장 투자성향 · 적극투자형 · 2026-07-22 진단")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /완료율 확인하기/ }));
    expect(onOpenPlanner).toHaveBeenCalledOnce();
  });

  it("summarizes the current portfolio composition before diagnosis", () => {
    const hero: DemoHeroPortfolio = {
      nickname: "김하린",
      representative_age: 29,
      customer_context: "은퇴까지 기간이 긴 대표 고객",
      is_demo_login_candidate: true,
      scenario_code: "young_retirement_distance",
      scenario_name: "은퇴까지 기간이 긴 고객",
      age_band: "20s",
      risk_profile: "growth",
      investment_horizon_years: 31,
      total_amount_krw: "23210000",
      accounts: [],
      asset_allocations: [
        { asset_class_code: "domestic_equity", amount_krw: "4667000", allocation_percent: "20.11", account_count: 1 },
        { asset_class_code: "global_equity", amount_krw: "11682000", allocation_percent: "50.33", account_count: 1 },
        { asset_class_code: "cash", amount_krw: "1161000", allocation_percent: "5.00", account_count: 1 },
      ],
      duplicated_asset_classes: [],
      risk_summary: {
        dominant_asset_class: "global_equity",
        dominant_asset_percent: "50.33",
        general_risky_asset_percent: "70.44",
        stress_scenario_code: "equity_drawdown",
        estimated_stress_loss_percent: "-28.18",
        is_forecast: false,
        requires_rebalancing_review: true,
        policy_label: "교육용 규칙 엔진",
      },
      past_performance: {
        metric_code: "portfolio_trailing_12m_return_pct",
        label: "과거 12개월 수익률",
        trailing_12m_return_pct: "8.12",
        period_start: "2025-07-17",
        period_end: "2026-07-16",
        calculation_basis: "계좌잔액 가중 합성수익률",
        source_label: "시연용 합성 데이터",
        data_kind: "MOCK",
        is_forecast: false,
        official_ranking_metric: false,
      },
      like_summary: {
        metric_code: "like_count",
        label: "추천(좋아요)",
        count: 127,
        as_of_date: "2026-07-21",
        data_kind: "MOCK",
        is_synthetic: true,
        performance_based: false,
      },
      data_boundary: "mock",
    };

    render(
      <MainHomeScreen
        error={null}
        hero={hero}
        investmentProfile={null}
        loading={false}
        onOpenChat={vi.fn()}
        onOpenPlanner={vi.fn()}
        onOpenProfile={vi.fn()}
        onOpenStrategyExplore={vi.fn()}
        onOpenUserPick={vi.fn()}
        onResurvey={vi.fn()}
        userContext={null}
      />,
    );

    expect(screen.getByText("포트폴리오 구성")).toBeInTheDocument();
    expect(screen.getByText("글로벌주식 비중이 가장 높고, 전체 주식 비중은 70.4%예요.")).toBeInTheDocument();
    expect(screen.queryByText("시황")).not.toBeInTheDocument();
  });

  it("opens the supplied profile screen from the header icon", () => {
    const onOpenProfile = vi.fn();

    render(
      <MainHomeScreen
        error={null}
        hero={null}
        investmentProfile={null}
        loading={false}
        onOpenChat={vi.fn()}
        onOpenPlanner={vi.fn()}
        onOpenProfile={onOpenProfile}
        onOpenStrategyExplore={vi.fn()}
        onOpenUserPick={vi.fn()}
        onResurvey={vi.fn()}
        userContext={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "프로필 열기" }));
    expect(onOpenProfile).toHaveBeenCalledOnce();
  });
});
