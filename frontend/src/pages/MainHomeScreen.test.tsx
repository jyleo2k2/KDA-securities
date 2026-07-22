// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { InvestmentProfileResponse } from "../api/types";
import { MainHomeScreen } from "./MainHomeScreen";

describe("MainHomeScreen", () => {
  it("shows the saved investment profile after login", () => {
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
        onOpenStrategyExplore={vi.fn()}
        onOpenUserPick={vi.fn()}
        onResurvey={vi.fn()}
        userContext={null}
      />,
    );

    expect(screen.getByText("저장 투자성향 · 적극투자형 · 2026-07-22 진단")).toBeInTheDocument();
  });
});
