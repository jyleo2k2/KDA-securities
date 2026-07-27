// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { sendAuthenticatedChatStream, type ChatStreamResult } from "../api/client";
import type { ChatResponse } from "../api/types";
import { useChatStream } from "./useChatStream";

vi.mock("../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../api/client")>(),
  sendAuthenticatedChatStream: vi.fn(),
}));

const RESPONSE = {
  answer: "최종 답변입니다.",
  conversation_context: null,
} as ChatResponse;

describe("useChatStream", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("keeps the existing SSE callback sequence in stream state before committing the response", async () => {
    let complete!: (result: ChatStreamResult) => void;
    vi.mocked(sendAuthenticatedChatStream).mockImplementation(async (
      _message,
      _accessToken,
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
      accessToken: "access-token",
      authenticatedUserId: "user-1",
      activeSessionId: null,
      conversationContext: null,
      conversationGenerationRef,
      deletingSessionId: null,
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

  it("aborts the in-flight request and reports the stop to the user", async () => {
    let observedSignal: AbortSignal | undefined;
    vi.mocked(sendAuthenticatedChatStream).mockImplementation(async (
      ..._args: Parameters<typeof sendAuthenticatedChatStream>
    ) => {
      observedSignal = _args[12] as AbortSignal | undefined;
      return new Promise<ChatStreamResult>((_resolve, reject) => {
        observedSignal?.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    });
    const { result } = renderHook(() => useChatStream({
      accessToken: "access-token",
      authenticatedUserId: "user-1",
      activeSessionId: null,
      conversationContext: null,
      conversationGenerationRef: { current: 0 },
      deletingSessionId: null,
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
    await waitFor(() => expect(result.current.isSending).toBe(true));

    act(() => result.current.stopStream());

    await waitFor(() => {
      expect(observedSignal?.aborted).toBe(true);
      expect(result.current.isSending).toBe(false);
      expect(result.current.messages.at(-1)?.text).toBe(
        "답변을 멈췄어요. 다시 물어보시면 이어서 도와드릴게요.",
      );
    });
  });

  it("does not send an SSE request without a login session", async () => {
    const onAuthenticatedError = vi.fn();
    const { result } = renderHook(() => useChatStream({
      accessToken: undefined,
      authenticatedUserId: null,
      activeSessionId: null,
      conversationContext: null,
      conversationGenerationRef: { current: 0 },
      deletingSessionId: null,
      selectedScenario: "",
      surveyProfile: null,
      isCurrentOperation: () => true,
      onAuthenticatedError,
      onConversationContext: vi.fn(),
      onComplete: vi.fn(),
      onInputClear: vi.fn(),
      onPersistedSession: vi.fn(),
      onServerReady: vi.fn(),
      onStart: vi.fn(),
      getAuthGeneration: () => 0,
    }));

    await act(async () => {
      await result.current.submitPrompt("IRP 한도를 알려줘");
    });

    expect(sendAuthenticatedChatStream).not.toHaveBeenCalled();
    expect(onAuthenticatedError).toHaveBeenCalledWith(
      "로그인이 필요해요. 로그인 후 다시 질문해 주세요.",
    );
    expect(result.current.messages.map((message) => message.text)).toEqual([
      "IRP 한도를 알려줘",
      "로그인이 필요해요. 로그인 후 다시 질문해 주세요.",
    ]);
  });
});
