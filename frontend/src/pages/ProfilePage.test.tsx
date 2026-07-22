// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { InvestmentProfileResponse } from "../api/types";
import { ProfilePage } from "./ProfilePage";

describe("ProfilePage", () => {
  it("shows the latest saved investment profile and its dates", () => {
    const investmentProfile = {
      assessment: {
        assessed_at: "2026-07-22T04:30:07.229204+00:00",
        assessed_on: "2026-07-22",
        valid_until: "2028-07-21",
        is_expired: false,
        risk_profile: "stable_seeking",
      },
      preferences: null,
    } as InvestmentProfileResponse;

    render(<ProfilePage investmentProfile={investmentProfile} onResurvey={vi.fn()} userContext={null} />);

    expect(screen.getByText("안정추구형")).toBeInTheDocument();
    expect(screen.getByText("2028-07-21", { exact: false })).toBeInTheDocument();
  });
});
