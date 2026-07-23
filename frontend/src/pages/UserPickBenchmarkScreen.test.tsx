// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UserPickBenchmarkScreen } from "./UserPickBenchmarkScreen";

describe("UserPickBenchmarkScreen", () => {
  it("renders the supplied benchmark HTML and preserves the home back action", () => {
    const onBack = vi.fn();

    render(<UserPickBenchmarkScreen heroes={[]} onBack={onBack} />);

    expect(screen.getByTitle("투자 벤치마킹하기")).toHaveAttribute("src", "/benchmark-html/투자 벤치마킹.dc.html");

    fireEvent.click(screen.getByRole("button", { name: "메인 홈으로 돌아가기" }));

    expect(onBack).toHaveBeenCalledOnce();
  });
});
