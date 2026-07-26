// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatTypingAnswer } from "./ChatTypingAnswer";

describe("ChatTypingAnswer", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("skips the engine-answer animation on click and shows narration immediately", () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <ChatTypingAnswer animate intervalMs={50} text="첫 번째 검증 답변입니다." />,
    );

    fireEvent.click(screen.getByRole("button", {
      name: "답변 타이핑을 건너뛰려면 클릭하세요",
    }));
    expect(screen.getByText("첫 번째 검증 답변입니다.")).toBeInTheDocument();

    rerender(
      <ChatTypingAnswer animate={false} intervalMs={50} text="검증된 내레이션입니다." />,
    );
    expect(screen.getByText("검증된 내레이션입니다.")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(500));
    expect(screen.queryByText("첫 번째 검증 답변입니다.")).not.toBeInTheDocument();
  });

  it("shows the complete answer immediately when the injected interval is zero", () => {
    render(<ChatTypingAnswer animate intervalMs={0} text="즉시 표시 답변입니다." />);

    expect(screen.getByText("즉시 표시 답변입니다.")).toBeInTheDocument();
  });

  it("caps long answer animation at two seconds", () => {
    vi.useFakeTimers();
    const text = Array.from({ length: 100 }, (_, index) => `답변${index + 1}`).join(" ");
    render(<ChatTypingAnswer animate intervalMs={50} text={text} />);

    act(() => vi.advanceTimersByTime(2_000));

    expect(screen.getByText(text)).toBeInTheDocument();
  });
});
