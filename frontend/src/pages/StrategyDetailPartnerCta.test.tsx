// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategyDetailScreen } from "./StrategyDetailScreen";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("StrategyDetailScreen partner CTA", () => {
  it("handles a click without changing the current route", () => {
    window.location.hash = "#/strategy-detail?strategy=barbell";
    const onPartnerBrokerClick = vi.fn();

    render(
      <StrategyDetailScreen
        onBack={vi.fn()}
        onPartnerBrokerClick={onPartnerBrokerClick}
      />,
    );

    const button = screen.getByRole("button", {
      name: "제휴 증권사로 이동",
    });
    const routeBeforeClick = window.location.hash;

    fireEvent.click(button);

    expect(onPartnerBrokerClick).toHaveBeenCalledOnce();
    expect(window.location.hash).toBe(routeBeforeClick);
    expect(button).toHaveClass("sd-partner-cta");
  });
});
