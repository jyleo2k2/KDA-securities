// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getChatSessions, getStoredChatMessages } from "../api/client";
import type { ChatSessionSummary, StoredChatMessage } from "../api/types";
import { ProfileChatHistoryScreen } from "./ProfileChatHistoryScreen";

vi.mock("../api/client", () => ({
  getChatSessions: vi.fn(),
  getStoredChatMessages: vi.fn(),
}));

const OWNER_A_SESSION: ChatSessionSummary = {
  session_id: "session-a",
  title: "연금 계좌 비중 점검",
  created_at: "2026-07-26T01:00:00Z",
  updated_at: "2026-07-26T01:10:00Z",
};

function storedMessage(
  messageId: string,
  role: StoredChatMessage["role"],
  content: string,
): StoredChatMessage {
  return {
    message_id: messageId,
    question_message_id: null,
    role,
    content,
    response: null,
    model_name: null,
    created_at: "2026-07-26T01:05:00Z",
    evidence: [],
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProfileChatHistoryScreen", () => {
  it("loads an owner session and shows only the user-visible conversation", async () => {
    vi.mocked(getChatSessions).mockResolvedValue([OWNER_A_SESSION]);
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      storedMessage("user-1", "user", "내 연금 비중을 알려줘"),
      storedMessage("assistant-1", "assistant", "현재 자산 비중을 정리해드릴게요."),
      storedMessage("system-1", "system", "내부 지시문"),
    ]);

    render(<ProfileChatHistoryScreen accessToken="owner-a-token" onBack={vi.fn()} />);

    fireEvent.click(await screen.findByRole("button", { name: /연금 계좌 비중 점검/ }));

    expect(await screen.findByText("내 연금 비중을 알려줘")).toBeInTheDocument();
    expect(screen.getByText("현재 자산 비중을 정리해드릴게요.")).toBeInTheDocument();
    expect(screen.queryByText("내부 지시문")).not.toBeInTheDocument();
    expect(getStoredChatMessages).toHaveBeenCalledWith("session-a", "owner-a-token");
  });

  it("clears the previous account history and reloads for a new token", async () => {
    vi.mocked(getChatSessions)
      .mockResolvedValueOnce([OWNER_A_SESSION])
      .mockResolvedValueOnce([{
        session_id: "session-b",
        title: "세액공제 확인",
        created_at: "2026-07-27T01:00:00Z",
        updated_at: "2026-07-27T01:10:00Z",
      }]);

    const { rerender } = render(
      <ProfileChatHistoryScreen accessToken="owner-a-token" onBack={vi.fn()} />,
    );
    expect(await screen.findByText("연금 계좌 비중 점검")).toBeInTheDocument();

    rerender(<ProfileChatHistoryScreen accessToken="owner-b-token" onBack={vi.fn()} />);

    await waitFor(() => {
      expect(screen.queryByText("연금 계좌 비중 점검")).not.toBeInTheDocument();
      expect(screen.getByText("세액공제 확인")).toBeInTheDocument();
    });
    expect(getChatSessions).toHaveBeenLastCalledWith("owner-b-token");
  });

  it("returns to the session list before leaving the screen", async () => {
    const onBack = vi.fn();
    vi.mocked(getChatSessions).mockResolvedValue([OWNER_A_SESSION]);
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      storedMessage("user-1", "user", "질문"),
    ]);

    render(<ProfileChatHistoryScreen accessToken="owner-a-token" onBack={onBack} />);
    fireEvent.click(await screen.findByRole("button", { name: /연금 계좌 비중 점검/ }));
    expect(await screen.findByText("질문")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "뒤로 가기" }));
    expect(await screen.findByText("연금 계좌 비중 점검")).toBeInTheDocument();
    expect(onBack).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "뒤로 가기" }));
    expect(onBack).toHaveBeenCalledOnce();
  });
});
