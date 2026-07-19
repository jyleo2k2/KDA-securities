// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteChatSession,
  getChatSessions,
  getMyPensionContext,
  getScenarios,
  getStoredChatMessages,
  sendAuthenticatedChatStream,
} from "../api/client";
import type { ChatSessionSummary } from "../api/types";
import { useSupabaseAuth } from "../auth/useSupabaseAuth";
import { GuidePage } from "./GuidePage";

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  deleteChatSession: vi.fn(),
  getChatSessions: vi.fn(),
  getMyPensionContext: vi.fn(),
  getScenarios: vi.fn(),
  getStoredChatMessages: vi.fn(),
  sendAuthenticatedChatStream: vi.fn(),
  sendChatStream: vi.fn(),
}));

vi.mock("../auth/useSupabaseAuth", () => ({
  useSupabaseAuth: vi.fn(),
}));

const SESSION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const CHAT_SESSION: ChatSessionSummary = {
  session_id: SESSION_ID,
  title: "IRP 규칙",
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
};

describe("GuidePage chat history deletion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useSupabaseAuth).mockReturnValue({
      session: {
        access_token: "access-token",
        user: { id: "user-1", email: "owner@example.com" },
      },
      loading: false,
      configured: true,
      error: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
    } as unknown as ReturnType<typeof useSupabaseAuth>);
    vi.mocked(getScenarios).mockResolvedValue([]);
    vi.mocked(getChatSessions).mockResolvedValue([CHAT_SESSION]);
    vi.mocked(getMyPensionContext).mockResolvedValue({
      scenario_code: "",
    } as Awaited<ReturnType<typeof getMyPensionContext>>);
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      {
        message_id: "message-1",
        question_message_id: null,
        role: "user",
        content: "저장된 질문",
        response: null,
        model_name: null,
        created_at: "2026-07-19T00:00:00Z",
        evidence: [],
      },
    ]);
    vi.mocked(deleteChatSession).mockResolvedValue(undefined);
    vi.mocked(sendAuthenticatedChatStream).mockReset();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("confirms deletion, disables controls, removes the row, and clears the active chat", async () => {
    let finishDelete: (() => void) | undefined;
    vi.mocked(deleteChatSession).mockImplementation(
      () => new Promise<void>((resolve) => { finishDelete = resolve; }),
    );
    render(<GuidePage surveyProfile={null} />);

    const openButton = await screen.findByRole("button", { name: /^IRP 규칙/ });
    fireEvent.click(openButton);
    expect(await screen.findByText("저장된 질문")).toBeInTheDocument();

    const deleteButton = screen.getByRole("button", { name: "대화 삭제: IRP 규칙" });
    const composer = screen.getByLabelText("질문 입력");
    fireEvent.click(deleteButton);

    expect(window.confirm).toHaveBeenCalled();
    expect(deleteChatSession).toHaveBeenCalledWith(SESSION_ID, "access-token");
    expect(openButton).toBeDisabled();
    expect(deleteButton).toBeDisabled();

    finishDelete?.();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "대화 삭제: IRP 규칙" })).not.toBeInTheDocument();
      expect(screen.queryByText("저장된 질문")).not.toBeInTheDocument();
    });
    expect(await screen.findByRole("status")).toHaveTextContent("대화가 삭제되었습니다.");
    await waitFor(() => expect(composer).toHaveFocus());
  });

  it("keeps the session when confirmation is cancelled", async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    render(<GuidePage surveyProfile={null} />);

    fireEvent.click(await screen.findByRole("button", { name: "대화 삭제: IRP 규칙" }));

    expect(deleteChatSession).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "대화 삭제: IRP 규칙" })).toBeInTheDocument();
  });

  it("blocks composer submit and retry while deleting the active session", async () => {
    vi.mocked(sendAuthenticatedChatStream).mockRejectedValue(
      new Error("전송 실패"),
    );
    vi.mocked(deleteChatSession).mockImplementation(
      () => new Promise<void>(() => undefined),
    );
    render(<GuidePage surveyProfile={null} />);

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    await screen.findByText("저장된 질문");
    const composer = screen.getByLabelText("질문 입력");
    fireEvent.change(composer, { target: { value: "첫 질문" } });
    fireEvent.submit(composer.closest("form")!);
    await screen.findAllByText("전송 실패");
    const retryButton = screen.getByRole("button", { name: /다시 시도/ });

    fireEvent.click(screen.getByRole("button", { name: "대화 삭제: IRP 규칙" }));

    await waitFor(() => expect(deleteChatSession).toHaveBeenCalledTimes(1));
    expect(composer).toBeDisabled();
    expect(screen.getByRole("button", { name: "질문 보내기" })).toBeDisabled();
    expect(retryButton).toBeDisabled();

    fireEvent.submit(composer.closest("form")!);
    fireEvent.click(retryButton);
    expect(sendAuthenticatedChatStream).toHaveBeenCalledTimes(1);
  });

  it("does not restore a deleted row from an older session refresh", async () => {
    let finishRefresh: ((sessions: ChatSessionSummary[]) => void) | undefined;
    vi.mocked(getChatSessions)
      .mockResolvedValueOnce([CHAT_SESSION])
      .mockImplementationOnce(() => new Promise((resolve) => {
        finishRefresh = resolve;
      }));
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: true,
      session_id: SESSION_ID,
      response: {
        intent: "account_rule",
        answer: "저장 답변",
        narration_mode: "deterministic",
        data_mode: "verified_knowledge",
        numeric_evidence: [],
        news_items: [],
        sections: [],
        sources: [],
        warnings: [],
        visualizations: [],
        limitations: [],
        conversation_context: null,
      },
    } as unknown as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    render(<GuidePage surveyProfile={null} />);

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    await screen.findByText("저장된 질문");
    const composer = screen.getByLabelText("질문 입력");
    fireEvent.change(composer, { target: { value: "새 질문" } });
    fireEvent.submit(composer.closest("form")!);
    await waitFor(() => expect(getChatSessions).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByRole("button", { name: "대화 삭제: IRP 규칙" }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "대화 삭제: IRP 규칙" })).not.toBeInTheDocument();
    });

    await act(async () => {
      finishRefresh?.([CHAT_SESSION]);
      await Promise.resolve();
    });
    expect(screen.queryByRole("button", { name: "대화 삭제: IRP 규칙" })).not.toBeInTheDocument();
  });
});
