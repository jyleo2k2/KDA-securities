// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteChatSession,
  getChatCards,
  getChatSessions,
  getMyPensionContext,
  getScenarios,
  getStoredChatMessages,
  sendAuthenticatedChatStream,
} from "../api/client";
import type { ChatCard, ChatSessionSummary } from "../api/types";
import { useSupabaseAuth } from "../auth/useSupabaseAuth";
import {
  ETF_THEME_CARDS,
  filterChatCards,
  GuidePage,
  TypingAnswer,
} from "./GuidePage";

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  deleteChatSession: vi.fn(),
  getChatCards: vi.fn(),
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
    vi.mocked(getChatCards).mockResolvedValue({ cards: [] });
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

  it("shows BOK, KOSIS, and FRED observations as a macro evidence card", async () => {
    vi.mocked(getChatCards).mockResolvedValue({
      cards: [{
        card_id: "macro_evidence",
        title: "거시환경 근거",
        message: "BOK·KOSIS·FRED 거시환경 근거를 보여줘.",
        intent: "macro_evidence",
        conditions: [],
        priority: 25,
        preview: null,
      }],
    });
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      response: {
        intent: "macro_evidence",
        answer: "공식 거시환경 관측값입니다.",
        narration_mode: "deterministic",
        data_mode: "official_macro_observations",
        numeric_evidence: [
          { label: "한국은행 기준금리", value: "2.75", unit: "%", evidence_id: "macro:kr_base_rate", basis: "공식 API 최신 관측값" },
          { label: "65세 여성 기대수명", value: "23.6", unit: "년", evidence_id: "macro:life", basis: "공식 API 최신 관측값" },
          { label: "미국 10년 국채금리", value: "4.57", unit: "%", evidence_id: "macro:us_treasury_10y", basis: "공식 API 최신 관측값" },
        ],
        sources: [
          { evidence_id: "macro:kr_base_rate", label: "한국은행 기준금리", locator: "https://ecos.bok.or.kr/api/", data_boundary: "official_statistics", publisher: "한국은행 ECOS", as_of: "2026-07-17" },
          { evidence_id: "macro:life", label: "65세 여성 기대수명", locator: "https://kosis.kr/openapi/", data_boundary: "official_statistics", publisher: "국가데이터처 KOSIS", as_of: "2023-01-01" },
          { evidence_id: "macro:us_treasury_10y", label: "미국 10년 국채금리", locator: "https://fred.stlouisfed.org/", data_boundary: "official_statistics", publisher: "Federal Reserve Bank of St. Louis", as_of: "2026-07-16" },
        ],
        news_items: [],
        sections: [],
        visualizations: [],
        engine_results: [],
        limitations: ["계획수익률과 목표비중에 직접 사용하지 않습니다."],
        conversation_context: null,
      },
    } as unknown as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    render(<GuidePage surveyProfile={null} />);

    fireEvent.click(await screen.findByRole("button", {
      name: /BOK·KOSIS·FRED 거시환경 근거를 보여줘/,
    }));

    const card = await screen.findByLabelText("거시환경 근거 카드");
    expect(within(card).getByText("BOK")).toBeInTheDocument();
    expect(within(card).getByText("KOSIS")).toBeInTheDocument();
    expect(within(card).getByText("FRED")).toBeInTheDocument();
    expect(within(card).getByText("2.75%")).toBeInTheDocument();
    expect(within(card).getByText("23.6년")).toBeInTheDocument();
    expect(within(card).getByText("4.57%")).toBeInTheDocument();
    expect(within(card).getAllByText(/공식 출처/)).toHaveLength(3);
  });

  it("separates question and ETF theme cards on the empty chat screen", async () => {
    render(<GuidePage surveyProfile={null} />);

    expect(await screen.findByRole("heading", {
      name: "챗봇에게 무엇이든 물어보세요",
    })).toBeInTheDocument();
    const sectorCards = await screen.findByLabelText("ETF 섹터 카드");
    expect(within(sectorCards).getAllByRole("button")).toHaveLength(
      ETF_THEME_CARDS.length,
    );
    expect(within(sectorCards).getByRole("button", {
      name: "반도체 ETF 테마 설명 보기",
    })).toBeInTheDocument();
  });
});

describe("filterChatCards", () => {
  it("hides unknown and unmet conditions, then sorts by priority", () => {
    const cards: ChatCard[] = [
      {
        card_id: "always",
        title: "항상",
        message: "오늘 국내 증시 뉴스 알려줘.",
        intent: "news",
        conditions: [],
        priority: 20,
        preview: null,
      },
      {
        card_id: "survey",
        title: "설문",
        message: "내 나이에 맞는 연금 저축 전략을 알려줘.",
        intent: "educational_portfolio",
        conditions: ["requires_survey"],
        priority: 10,
        preview: null,
      },
      {
        card_id: "unknown",
        title: "미지",
        message: "테스트",
        intent: "news",
        conditions: ["future_condition" as never],
        priority: 1,
        preview: null,
      },
    ];

    expect(filterChatCards(cards, {
      hasScenario: false,
      hasSurvey: true,
      hasAuth: false,
    }).map((card) => card.card_id)).toEqual(["survey", "always"]);
  });
});

describe("TypingAnswer", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("skips the engine-answer animation on click and shows narration immediately", () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <TypingAnswer animate intervalMs={50} text="첫 번째 검증 답변입니다." />,
    );

    fireEvent.click(screen.getByRole("button", {
      name: "답변 타이핑을 건너뛰려면 클릭하세요",
    }));
    expect(screen.getByText("첫 번째 검증 답변입니다.")).toBeInTheDocument();

    rerender(
      <TypingAnswer animate={false} intervalMs={50} text="검증된 내레이션입니다." />,
    );
    expect(screen.getByText("검증된 내레이션입니다.")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(500));
    expect(screen.queryByText("첫 번째 검증 답변입니다.")).not.toBeInTheDocument();
  });

  it("shows the complete answer immediately when the injected interval is zero", () => {
    render(<TypingAnswer animate intervalMs={0} text="즉시 표시 답변입니다." />);

    expect(screen.getByText("즉시 표시 답변입니다.")).toBeInTheDocument();
  });
});
