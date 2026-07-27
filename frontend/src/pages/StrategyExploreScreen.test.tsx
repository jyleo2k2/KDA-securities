// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StrategyExploreScreen } from "./StrategyExploreScreen";
import { STRATEGIES } from "./strategyExplore/strategies";

afterEach(() => {
  cleanup();
  window.location.hash = "";
  sessionStorage.clear();
});

describe("StrategyExploreScreen", () => {
  it("opens detail for the active card when the top image is tapped", () => {
    render(<StrategyExploreScreen onBack={() => {}} />);
    const activeCard = screen.getByRole("button", { name: `1번째 전략 상세 보기: ${STRATEGIES[0].name}` });

    expect(document.querySelector(".se-brand-name")).toHaveTextContent("연금 KDA");
    expect(document.querySelector(".se-brandc")).toHaveTextContent("연금 KDA");
    expect(document.querySelector(".se-headline")).toHaveTextContent("연금 KDA와 제휴하는");
    expect(document.querySelector(".se-headline")).toHaveTextContent("증권사들의 전략들로 연금을 꾸려봐요!");
    expect(document.querySelector(".se-headline br")).not.toBeNull();
    expect(document.documentElement.style.getPropertyValue("--se-accent")).toBe(STRATEGIES[0].accent);
    fireEvent.click(activeCard);

    expect(window.location.hash).toBe(`#/strategy-detail?strategy=${STRATEGIES[0].id}`);
  });

  it("centers a side card when tapped instead of opening detail", () => {
    render(<StrategyExploreScreen onBack={() => {}} />);
    // 비활성 카드는 부모 li가 aria-hidden이라 role 질의가 안 되므로 라벨로 직접 찾는다.
    const sideCard = screen.getByLabelText(`2번째 전략 선택: ${STRATEGIES[1].name}`);
    fireEvent.click(sideCard);

    // 옆 카드 탭은 상세를 열지 않고 가운데로만 옮긴다.
    expect(window.location.hash).toBe("");
    expect(screen.getByLabelText(`2번째 전략 상세 보기: ${STRATEGIES[1].name}`)).toHaveAttribute("tabindex", "0");
    expect(document.documentElement.style.getPropertyValue("--se-accent")).toBe(STRATEGIES[1].accent);
  });

  it("restores the last viewed strategy as the centered card", () => {
    sessionStorage.setItem("se-active-strategy", STRATEGIES[2].id);

    render(<StrategyExploreScreen onBack={() => {}} />);

    expect(screen.getByLabelText(`3번째 전략 상세 보기: ${STRATEGIES[2].name}`)).toHaveAttribute("tabindex", "0");
  });
});
