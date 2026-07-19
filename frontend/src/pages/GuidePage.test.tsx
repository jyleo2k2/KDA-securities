// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteChatSession,
  getChatSessions,
  getMyPensionContext,
  getScenarios,
  getStoredChatMessages,
} from "../api/client";
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
    vi.mocked(getChatSessions).mockResolvedValue([
      {
        session_id: SESSION_ID,
        title: "IRP 규칙",
        created_at: "2026-07-19T00:00:00Z",
        updated_at: "2026-07-19T00:00:00Z",
      },
    ]);
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
  });

  it("keeps the session when confirmation is cancelled", async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    render(<GuidePage surveyProfile={null} />);

    fireEvent.click(await screen.findByRole("button", { name: "대화 삭제: IRP 규칙" }));

    expect(deleteChatSession).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "대화 삭제: IRP 규칙" })).toBeInTheDocument();
  });
});
