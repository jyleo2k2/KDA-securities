// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { InvestmentProfileAssessment } from "../api/types";
import { InvestorResultScreen } from "./InvestorResultScreen";

const assessment: InvestmentProfileAssessment = {
  assessed_at: "2026-07-22T00:00:00Z",
  assessed_on: "2026-07-22",
  valid_until: "2028-07-21",
  is_expired: false,
  validity_policy_version: "2026-07-20.1",
  total_score: 25,
  min_score: 10,
  max_score: 56,
  score_percent: "32.61",
  risk_profile: "risk_neutral",
  engine_name: "investor_profile",
  engine_version: "2026-07-22.1",
  rule_version: "shinhan-personal-general-login-union-2026-07-22",
  provisional: false,
  answers: [],
};

describe("InvestorResultScreen", () => {
  it("renders the server-assessed profile, dates, and display name", () => {
    const { container } = render(<InvestorResultScreen assessment={assessment} displayName="김연금" onBack={vi.fn()} onStart={vi.fn()} />);

    expect(screen.getByText("김연금님의 투자성향은")).toBeInTheDocument();
    expect(container.querySelector(".irs-type")).toHaveTextContent("위험중립형");
    expect(screen.getByText(/최근 진단일\s*:\s*2026-07-22/)).toBeInTheDocument();
    expect(screen.getByText(/성향 만료일\s*:\s*2028-07-21/)).toBeInTheDocument();
    expect(screen.getByText(/안정성과 수익의 균형을 고려하며/)).toBeInTheDocument();
    expect(container.querySelectorAll(".irs-grade-row-highlight")).toHaveLength(1);
    expect(container.querySelectorAll(".irs-chart-dot-final")).toHaveLength(1);
  });
});
