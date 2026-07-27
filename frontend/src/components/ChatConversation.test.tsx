// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CHAT_PROMPT_CANDIDATES } from "../chatPromptCandidates";
import { ChatComposer } from "./ChatConversation";

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
