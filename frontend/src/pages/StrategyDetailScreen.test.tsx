// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategyDetailScreen } from "./StrategyDetailScreen";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("StrategyDetailScreen", () => {
  it("returns to the strategy list from the back button", () => {
    const onBack = vi.fn();

    render(<StrategyDetailScreen onBack={onBack} />);
    fireEvent.click(screen.getByRole("button", { name: "뒤로 가기" }));

    expect(onBack).toHaveBeenCalledOnce();
  });

  it("renders the strategy selected in the hash query", () => {
    window.location.hash = "#/strategy-detail?strategy=factor";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("팩터 전략");
    expect(screen.getByRole("heading", { name: "낯선 말 쉽게 보기" })).toBeInTheDocument();
    expect(screen.getByText("팩터")).toBeInTheDocument();
    expect(screen.getByText(/회사를 고를 때 보는 공통 특징/)).toBeInTheDocument();
    expect(screen.getByText("최소변동성")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "연금 돈을 나눠 담는 모습" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /주식 ETF, 채권 ETF, 현금성 자산/ })).toBeInTheDocument();
    expect(screen.getByText("주식 안에서는 ETF 분야도 나눠 봐요")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /넓은 시장, 반도체, 바이오 헬스케어/ })).toBeInTheDocument();
    expect(screen.getByText(/막대 크기는 이해를 돕기 위한 예시예요/)).toBeInTheDocument();
  });

  it("falls back to the first strategy when the hash has no valid id", () => {
    window.location.hash = "#/strategy-detail";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("시장 베타 전략");
  });
});
