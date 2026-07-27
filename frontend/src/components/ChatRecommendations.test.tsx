// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatQuestionRecommendations } from "./ChatRecommendations";

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
        name: "연금계좌와 운용 방법을 물어보세요",
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
});
