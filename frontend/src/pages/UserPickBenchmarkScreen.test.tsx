// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UserPickBenchmarkScreen } from "./UserPickBenchmarkScreen";

afterEach(cleanup);

describe("UserPickBenchmarkScreen", () => {
  it("renders the supplied benchmark HTML", () => {
    render(<UserPickBenchmarkScreen onBack={vi.fn()} />);

    expect(screen.getByTitle("투자 벤치마킹하기")).toHaveAttribute("src", "/benchmark-html/투자 벤치마킹.dc.html");
  });

  it("leaves to home only on the list back message from the iframe", () => {
    const onBack = vi.fn();
    render(<UserPickBenchmarkScreen onBack={onBack} />);
    const iframe = screen.getByTitle("투자 벤치마킹하기") as HTMLIFrameElement;

    // 다른 출처/타입 메시지는 무시한다.
    window.dispatchEvent(new MessageEvent("message", { data: { type: "benchmark-html-back" }, source: window }));
    expect(onBack).not.toHaveBeenCalled();

    // iframe(목록 뒤로가기)에서 온 메시지만 홈으로 나간다.
    window.dispatchEvent(new MessageEvent("message", { data: { type: "benchmark-html-back" }, source: iframe.contentWindow }));
    expect(onBack).toHaveBeenCalledOnce();
  });
});
