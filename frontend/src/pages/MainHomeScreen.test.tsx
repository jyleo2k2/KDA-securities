// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DemoHeroPortfolio, InvestmentProfileResponse } from "../api/types";
import { MainHomeScreen } from "./MainHomeScreen";

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
        onOpenStrategyExplore={vi.fn()}
        onOpenUserPick={vi.fn()}
        onResurvey={vi.fn()}
        userContext={null}
      />,
    );

    expect(screen.getByText("사용자 보유 ETF")).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
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
});
