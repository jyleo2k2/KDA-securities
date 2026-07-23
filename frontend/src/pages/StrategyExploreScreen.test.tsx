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
    const activeCard = screen.getByRole("button", { name: `1번째 전략: ${STRATEGIES[0].name}` });

    fireEvent.click(activeCard);

    expect(window.location.hash).toBe(`#/strategy-detail?strategy=${STRATEGIES[0].id}`);
  });

  it("restores the last viewed strategy as the centered card", () => {
    sessionStorage.setItem("se-active-strategy", STRATEGIES[2].id);

    render(<StrategyExploreScreen onBack={() => {}} />);

    expect(screen.getByLabelText(`3번째 전략: ${STRATEGIES[2].name}`)).toHaveAttribute("tabindex", "0");
  });
});
