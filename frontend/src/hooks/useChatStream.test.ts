// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { sendAuthenticatedChatStream, sendChatStream } from "../api/client";
import type { ChatResponse } from "../api/types";
import { useChatStream } from "./useChatStream";

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  sendAuthenticatedChatStream: vi.fn(),
  sendChatStream: vi.fn(),
}));

const RESPONSE: ChatResponse = {
  intent: "account_rule",
  answer: "IRP의 위험자산 한도는 70%예요.",
  narration_mode: "deterministic",
  data_mode: "verified_knowledge",
  numeric_evidence: [],
  news_items: [],
  sections: [],
  sources: [],
  visualizations: [],
  suggested_follow_ups: [],
  engine_results: [],
  limitations: [],
  conversation_context: null,
};

describe("useChatStream", () => {
  it("sends the authenticated stream and appends its final answer", async () => {
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: true,
      session_id: "session-1",
      response: RESPONSE,
    });
    const onResponse = vi.fn();
    const onStart = vi.fn();
    const onSettled = vi.fn();
    const { result } = renderHook(() => useChatStream({
      accessToken: "access-token",
      authenticatedUserId: "user-1",
      activeSessionId: null,
      conversationContext: null,
      selectedScenario: "",
      surveyProfile: null,
      blocked: false,
      onResponse,
      onAuthenticatedError: vi.fn(),
      onServerReady: vi.fn(),
      onStart,
      onSettled,
    }));

    await act(async () => {
      await result.current.submitPrompt("IRP 위험자산 한도를 알려줘");
    });

    expect(sendAuthenticatedChatStream).toHaveBeenCalledWith(
      "IRP 위험자산 한도를 알려줘",
      "access-token",
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
      undefined,
      undefined,
      expect.any(String),
      null,
      undefined,
      null,
      undefined,
    );
    expect(sendChatStream).not.toHaveBeenCalled();
    expect(result.current.messages.map((message) => message.text)).toEqual([
      "IRP 위험자산 한도를 알려줘",
      RESPONSE.answer,
    ]);
    expect(onResponse).toHaveBeenCalledWith(RESPONSE, expect.objectContaining({
      session_id: "session-1",
    }));
    expect(onStart).toHaveBeenCalledOnce();
    expect(onSettled).toHaveBeenCalledOnce();
  });
});
