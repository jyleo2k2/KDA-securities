// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { sendChatStream, type ChatStreamResult } from "../api/client";
import type { ChatResponse } from "../api/types";
import { useChatStream } from "./useChatStream";

vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(),
  sendChatStream: vi.fn(),
}));

const RESPONSE = {
  answer: "최종 답변입니다.",
  conversation_context: null,
} as ChatResponse;

describe("useChatStream", () => {
  it("keeps the existing SSE callback sequence in stream state before committing the response", async () => {
    let complete!: (result: ChatStreamResult) => void;
    vi.mocked(sendChatStream).mockImplementation(async (
      _message,
      onPhase,
      onAnswerDelta,
      onNarrationUpdate,
    ) => {
      onPhase("엔진 답변을 확인하고 있습니다.");
      onAnswerDelta("엔진 답변");
      onNarrationUpdate("내레이션 답변");
      return new Promise<ChatStreamResult>((resolve) => {
        complete = resolve;
      });
    });
    const conversationGenerationRef = { current: 0 };
    const { result } = renderHook(() => useChatStream({
      accessToken: undefined,
      authenticatedUserId: null,
      activeSessionId: null,
      conversationContext: null,
      conversationGenerationRef,
      deletingSessionId: null,
      pensionTaxInput: undefined,
      selectedScenario: "",
      surveyProfile: null,
      isCurrentOperation: () => true,
      onAuthenticatedError: vi.fn(),
      onConversationContext: vi.fn(),
      onComplete: vi.fn(),
      onInputClear: vi.fn(),
      onPersistedSession: vi.fn(),
      onServerReady: vi.fn(),
      onStart: vi.fn(),
      getAuthGeneration: () => 0,
    }));

    act(() => {
      void result.current.submitPrompt("IRP 한도를 알려줘");
    });

    await waitFor(() => {
      expect(result.current.sendingStage).toBe("엔진 답변을 확인하고 있습니다.");
      expect(result.current.streamingAnswer).toBe("내레이션 답변");
      expect(result.current.streamingAnswerIsNarration).toBe(true);
    });

    act(() => complete({ response: RESPONSE }));

    await waitFor(() => {
      expect(result.current.isSending).toBe(false);
      expect(result.current.messages.map((message) => message.text)).toEqual([
        "IRP 한도를 알려줘",
        "최종 답변입니다.",
      ]);
    });
  });
});
