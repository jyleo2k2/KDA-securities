// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UserPickBenchmarkScreen } from "./UserPickBenchmarkScreen";

const heroes = [
  {
    nickname: "수익률우선",
    scenario_name: "글로벌 주식 중심",
    total_amount_krw: "60980000",
    asset_allocations: [
      { asset_class_code: "global_equity", amount_krw: "42000000", allocation_percent: "68.9", account_count: 2 },
      { asset_class_code: "bond", amount_krw: "18980000", allocation_percent: "31.1", account_count: 1 },
    ],
    past_performance: { trailing_12m_return_pct: "12.4" },
    like_summary: { count: 25 },
  },
  {
    nickname: "인기포트폴리오",
    scenario_name: "채권 혼합",
    total_amount_krw: "40000000",
    asset_allocations: [{ asset_class_code: "bond", amount_krw: "40000000", allocation_percent: "100", account_count: 1 }],
    past_performance: { trailing_12m_return_pct: "6.1" },
    like_summary: { count: 120 },
  },
] as never;

describe("UserPickBenchmarkScreen", () => {
  it("renders demo heroes instead of the static benchmark HTML and preserves the home back action", () => {
    const onBack = vi.fn();

    render(<UserPickBenchmarkScreen heroes={heroes} onBack={onBack} />);

    expect(screen.queryByTitle("투자 벤치마킹하기")).not.toBeInTheDocument();
    expect(screen.getByText("수익률우선")).toBeInTheDocument();
    expect(screen.getByText("글로벌 주식 중심")).toBeInTheDocument();
    expect(screen.getByText("12.4%")).toBeInTheDocument();
    expect(screen.getByText("총 연금자산 60,980,000원")).toBeInTheDocument();
    expect(screen.getByText("글로벌주식 68.9% · 채권 31.1%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "좋아요순" }));
    expect(screen.getAllByTestId("hero-card").map((card) => card.getAttribute("data-hero-name"))).toEqual(["인기포트폴리오", "수익률우선"]);

    fireEvent.click(screen.getByRole("button", { name: "메인 홈으로 돌아가기" }));

    expect(onBack).toHaveBeenCalledOnce();
  });
});
