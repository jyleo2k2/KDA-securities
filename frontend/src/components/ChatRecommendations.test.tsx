// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChatCard } from "../api/types";
import { ChatQuestionRecommendations } from "./ChatRecommendations";

const CARDS: ChatCard[] = [
  {
    card_id: "news_market",
    title: "오늘 증시 뉴스",
    message: "오늘 증시 뉴스 알려줘.",
    intent: "news",
    conditions: [],
    priority: 10,
    preview: null,
  },
];

describe("ChatQuestionRecommendations", () => {
  it("describes the supported pension question scope", () => {
    render(
      <ChatQuestionRecommendations
        cards={[]}
        isLoading={false}
        onRetry={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "이런 질문부터 시작해 보세요",
      }),
    ).toBeInTheDocument();
  });

  it("reserves three card slots while recommendations load", () => {
    render(
      <ChatQuestionRecommendations
        cards={[]}
        isLoading
        onRetry={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("챗봇 추천 질문 로딩")).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(document.querySelectorAll(".chat-question-skeleton")).toHaveLength(3);
  });

  it("scrolls the rail when dragged without submitting a question", () => {
    const onSubmit = vi.fn();
    const { container } = render(
      <ChatQuestionRecommendations
        cards={CARDS}
        isLoading={false}
        onRetry={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    const rail = screen.getByLabelText("챗봇 추천 질문");
    Object.assign(rail, {
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn(),
      setPointerCapture: vi.fn(),
    });
    fireEvent.pointerDown(rail, { button: 0, clientX: 160, pointerId: 1, pointerType: "mouse" });
    fireEvent.pointerMove(rail, { clientX: 100, pointerId: 1, pointerType: "mouse" });
    fireEvent.pointerUp(rail, { clientX: 100, pointerId: 1, pointerType: "mouse" });
    fireEvent.click(within(container).getByRole("button", { name: /오늘 증시 뉴스/ }));

    expect(rail.scrollLeft).toBe(60);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits the question when a card is clicked", () => {
    const onSubmit = vi.fn();
    const { container } = render(
      <ChatQuestionRecommendations
        cards={CARDS}
        isLoading={false}
        onRetry={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(within(container).getByRole("button", { name: /오늘 증시 뉴스/ }));

    expect(onSubmit).toHaveBeenCalledWith("오늘 증시 뉴스 알려줘.");
  });
});
