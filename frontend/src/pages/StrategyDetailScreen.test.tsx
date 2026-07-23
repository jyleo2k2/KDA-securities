// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategyDetailScreen } from "./StrategyDetailScreen";

afterEach(cleanup);

describe("StrategyDetailScreen", () => {
  it("returns to the strategy list from the back button", () => {
    const onBack = vi.fn();

    render(<StrategyDetailScreen onBack={onBack} />);
    fireEvent.click(screen.getByRole("button", { name: "뒤로 가기" }));

    expect(onBack).toHaveBeenCalledOnce();
  });
});
