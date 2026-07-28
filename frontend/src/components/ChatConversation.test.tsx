// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CHAT_PROMPT_CANDIDATES } from "../chatPromptCandidates";
import { ChatComposer, ChatMessageList } from "./ChatConversation";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ChatComposer", () => {
  it("keeps one random example for the lifetime of the mounted composer", () => {
    const random = vi.spyOn(Math, "random").mockReturnValue(0);
    const props = {
      deletingSessionId: null,
      input: "",
      isSending: false,
      onChange: vi.fn(),
      onKeyDown: vi.fn(),
      onStop: vi.fn(),
      onSubmit: vi.fn(),
      textareaRef: createRef<HTMLTextAreaElement>(),
    };
    const { rerender } = render(<ChatComposer {...props} />);

    expect(screen.getByLabelText("질문 입력")).toHaveAttribute(
      "placeholder",
      `예: ${CHAT_PROMPT_CANDIDATES[0]}`,
    );

    random.mockReturnValue(0.999999);
    rerender(<ChatComposer {...props} input="다시 렌더링" />);

    expect(screen.getByLabelText("질문 입력")).toHaveAttribute(
      "placeholder",
      `예: ${CHAT_PROMPT_CANDIDATES[0]}`,
    );
  });
});

describe("ChatMessageList", () => {
  it("keeps the Yeongeumi identity beside assistant messages", () => {
    render(
      <ChatMessageList
        conversationEndRef={createRef<HTMLDivElement>()}
        conversationKey={null}
        deletingSessionId={null}
        isSending={false}
        latestMessageRef={createRef<HTMLDivElement>()}
        messages={[{
          id: "assistant-1",
          role: "assistant",
          text: "연금계좌 차이를 설명해 드릴게요.",
          createdAt: new Date("2026-07-28T00:00:00Z"),
        }]}
        onRetry={vi.fn()}
        renderMessage={(message) => <p>{message.text}</p>}
        renderStreamingAnswer={() => null}
        sendingStage="답변 준비 중"
      />,
    );

    expect(screen.getByText("연그미")).toBeInTheDocument();
    expect(document.querySelector(".assistant-avatar img")).toHaveAttribute(
      "src",
      expect.stringContaining("piggy-clean"),
    );
  });
});
