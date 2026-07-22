// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { calculatePension } from "../api/client";
import type { CompletedSurveyProfile } from "../api/types";
import { PensionPlannerPage } from "./PensionPlannerPage";

vi.mock("../api/client", () => ({
  calculatePension: vi.fn(),
}));

const profile: CompletedSurveyProfile = {
  account_type: "irp",
  current_age: 35,
  retirement_start_age: 60,
  risk_profile: "risk_neutral",
  loss_tolerance_percent: "20",
};

describe("PensionPlannerPage", () => {
  it("calculates the approved scenario from the minimum inputs", async () => {
    vi.mocked(calculatePension).mockResolvedValue({
      headline: {
        total_krw: "50000000",
        total_principal_krw: "40000000",
        total_gain_krw: "10000000",
        monthly_payout_pretax_krw: "200000",
        monthly_payout_after_tax_krw: "189000",
        contribution_years: 25,
      },
      yearly: [{ year_index: 25, age: 60, cumulative_principal_krw: "40000000", cumulative_gain_krw: "10000000", balance_krw: "50000000" }],
      strategies: [{ strategy_id: "balanced_core_satellite", presentation: { strategy_id: "balanced_core_satellite", display_name: "균형 코어·위성 전략", summary: "분산 구성입니다.", risk_badge: "위험중립형", character_key: "balanced_core_satellite" }, risk_profile: "risk_neutral", net_annual_return_percent: "4.0", growth_percent: "50", safe_percent: "40", cash_percent: "10", within_profile: true, default_visible: true }],
      tax: { withholding_rate_percent_by_year: ["5.5"], effective_rate_percent: "5.5", annual_payout_krw: "2400000", exceeds_annual_15m_threshold: false, deferred_severance_excluded: true },
      assumption: { version: "test", scenario: "base", source: { label: "승인 가정", reference: "https://example.com/assumption", as_of: "2026-07-20" }, notice: "교육용 가정입니다." },
      warnings: [],
    });
    render(<PensionPlannerPage profile={profile} userContext={null} onBack={vi.fn()} onOpenProfile={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("현재 연금자산 잔액"), { target: { value: "10000000" } });
    fireEvent.change(screen.getByLabelText("월 납입액"), { target: { value: "300000" } });
    fireEvent.click(screen.getByRole("button", { name: "수령 계획 계산" }));

    await waitFor(() => expect(calculatePension).toHaveBeenCalledWith(expect.objectContaining({
      current_age: 35,
      current_balance_krw: "10000000",
      monthly_contribution_krw: "300000",
      account_type: "irp",
      risk_profile: "risk_neutral",
      scenario: "base",
    })));
    expect(await screen.findByRole("heading", { name: "가정 시나리오 결과" })).toBeInTheDocument();
    expect(screen.getByText("50,000,000원")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /균형 코어·위성 전략/ }));
    await waitFor(() => expect(calculatePension).toHaveBeenLastCalledWith(expect.objectContaining({ strategy_id: "balanced_core_satellite" })));
  });
});
