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
    expect(screen.getByRole("heading", { name: "핵심 용어 풀이" })).toBeInTheDocument();
    expect(screen.getByText("팩터")).toBeInTheDocument();
    expect(screen.getByText(/회사를 고를 때 보는 공통 특징/)).toBeInTheDocument();
    expect(screen.getByText("최소변동성")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "연금계좌 자산배분 예시" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "큰 자산군 비중 예시" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "주식 ETF 60%" })).toBeInTheDocument();
    expect(screen.getByText("주식 안에서는 ETF 분야도 나눠 봐요")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "주식 ETF 분야 비중 예시" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "반도체 20%" })).toBeInTheDocument();
    expect(screen.getByText(/막대 크기는 이해를 돕기 위한 예시예요/)).toBeInTheDocument();
    expect(document.querySelector(".sd-operation-guide")).toHaveTextContent("전략의 운용 방식");
    expect(document.querySelector(".sd-account-guide")).toHaveTextContent("연금계좌에는 이렇게 나눠요");
  });

  it("shows allocation details when a bar segment is selected", () => {
    render(<StrategyDetailScreen onBack={vi.fn()} />);

    const stockSegment = screen.getByRole("button", { name: "주식 ETF 60% 자세히 보기" });
    fireEvent.click(stockSegment);

    expect(stockSegment).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("주식 ETF 60%");
    expect(screen.getByRole("status")).toHaveTextContent("성장 기회를 담당하지만 가격 변동이 큰 자산이에요.");
    expect(screen.getByRole("button", { name: "채권 ETF 30% 자세히 보기" })).toHaveClass("is-dimmed");

    const semiconductorSegment = screen.getByRole("button", { name: "반도체 주식 ETF 안에서 20% 자세히 보기" });
    fireEvent.click(semiconductorSegment);

    expect(stockSegment).toHaveAttribute("aria-pressed", "false");
    expect(semiconductorSegment).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("주식 ETF 안에서 20% · 전체 자산 기준 12%");

    fireEvent.click(semiconductorSegment);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("falls back to the first strategy when the hash has no valid id", () => {
    window.location.hash = "#/strategy-detail";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("시장 베타 전략");
  });
});
