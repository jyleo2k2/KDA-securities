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
import type { ChatCard, ChatResponse, ChatSessionSummary } from "../api/types";
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
const RECOMMENDED_CHAT_CARDS: ChatCard[] = [
  {
    card_id: "news_market",
    title: "오늘 증시 뉴스",
    message: "오늘 증시 뉴스 알려줘.",
    intent: "news",
    conditions: [],
    priority: 10,
    preview: null,
  },
  {
    card_id: "tax_credit",
    title: "연금세액공제",
    message: "올해 받을 수 있는 연금세액공제가 궁금해.",
    intent: "pension_tax",
    conditions: [],
    priority: 20,
    preview: null,
  },
  {
    card_id: "withdrawal_tax",
    title: "중도해지 세금",
    message: "연금계좌를 중도에 해지하면 어떻게 돼?",
    intent: "account_rule",
    conditions: [],
    priority: 30,
    preview: null,
  },
  {
    card_id: "account_diff",
    title: "연금계좌별 차이",
    message: "DC형, IRP, 연금저축은 뭐가 달라?",
    intent: "account_rule",
    conditions: [],
    priority: 40,
    preview: null,
  },
  {
    card_id: "edu_portfolio",
    title: "맞춤형 포트폴리오",
    message: "내 상황에 맞는 연금저축전략을 알려줘.",
    intent: "educational_portfolio",
    conditions: [],
    priority: 50,
    preview: null,
  },
];
const THEME_RESPONSE: ChatResponse = {
  intent: "etf_theme",
  answer: "조선 테마를 초보자도 이해하기 쉽게 설명했습니다.",
  data_mode: "theme_overview",
  narration_mode: "deterministic",
  sections: [
    {
      kind: "service_explanation",
      title: "조선 테마란?",
      content: "선박과 조선 기자재 기업을 담는 테마입니다.",
      evidence_ids: [],
      blocks: [],
    },
  ],
  news_items: [],
  visualizations: [],
  suggested_follow_ups: [
    {
      follow_up_id: "theme_representative_companies",
      label: "테마 대표기업",
      message: "조선 테마 대표기업은 뭐야?",
    },
    {
      follow_up_id: "theme_pros_cons",
      label: "테마 장단점",
      message: "조선 테마 ETF에 투자할 때 장단점을 알려줘",
    },
    {
      follow_up_id: "theme_products",
      label: "테마 ETF상품",
      message: "조선 테마 ETF상품 3개를 보여줘",
    },
  ],
  sources: [],
  numeric_evidence: [],
  engine_results: [],
  limitations: [],
  conversation_context: null,
};

const REPRESENTATIVE_COMPANY_RESPONSE: ChatResponse = {
  ...THEME_RESPONSE,
  answer: "반도체 테마를 이해하기 위한 대표기업 3곳입니다.",
  data_mode: "theme_representative_companies",
  sections: [
    {
      kind: "service_explanation",
      title: "반도체 테마 대표기업 3곳",
      content: "테마의 서로 다른 역할을 이해하기 위한 대표 사례입니다.",
      evidence_ids: [],
      blocks: [
        {
          kind: "callout",
          title: "Samsung Electronics",
          text: "테마에서의 역할: 메모리 반도체를 만들고 시스템반도체 생산도 담당합니다. 메모리와 파운드리를 함께 보유해 공급망의 여러 단계를 보여줍니다.\n\n쉽게 말하면: 데이터를 저장하는 메모리 칩을 대량 생산하고 다른 회사가 설계한 칩도 대신 만들어 주는 회사입니다.",
          items: [],
          headers: [],
          rows: [],
        },
        {
          kind: "callout",
          title: "NVIDIA",
          text: "테마에서의 역할: AI 연산용 칩을 설계하고 관련 소프트웨어를 제공합니다. AI 반도체 수요를 보여주는 대표 사례입니다.\n\n쉽게 말하면: AI 계산을 빠르게 처리하도록 돕는 칩과 프로그램을 만드는 회사입니다.",
          items: [],
          headers: [],
          rows: [],
        },
        {
          kind: "callout",
          title: "TSMC",
          text: "테마에서의 역할: 여러 반도체 설계회사의 칩을 위탁 생산합니다. 설계와 생산이 나뉘는 구조를 보여주는 대표 사례입니다.\n\n쉽게 말하면: 다른 회사가 설계한 반도체를 첨단 공장에서 대신 만들어 주는 회사입니다.",
          items: [],
          headers: [],
          rows: [],
        },
      ],
    },
  ],
  suggested_follow_ups: [],
};

const THEME_CONSIDERATIONS_RESPONSE: ChatResponse = {
  ...THEME_RESPONSE,
  answer: "반도체 테마 ETF에 투자할 때의 이점 3개와 위험 3개를 쉽게 정리했습니다.",
  data_mode: "theme_investment_considerations",
  sections: [
    {
      kind: "service_explanation",
      title: "반도체 테마 ETF 장단점",
      content: "이점과 손실 가능성을 키울 수 있는 위험을 같이 확인해 보세요.",
      evidence_ids: [],
      blocks: [
        {
          kind: "bullets",
          title: "투자할 때의 이점 3가지",
          text: "",
          items: [
            "인공지능과 데이터센터 성장의 수혜를 받을 수 있습니다.",
            "반도체 공급망에 분산 투자할 수 있습니다.",
            "높은 기술력을 갖춘 기업에 접근할 수 있습니다.",
          ],
          headers: [],
          rows: [],
        },
        {
          kind: "bullets",
          title: "주의할 위험 3가지",
          text: "",
          items: [
            "재고와 설비투자 순환에 따라 실적 변동이 크게 나타날 수 있습니다.",
            "미세공정 경쟁과 대규모 투자 실패가 기업 수익성을 훼손할 수 있습니다.",
            "수출규제와 지정학적 공급망 재편의 영향을 크게 받을 수 있습니다.",
          ],
          headers: [],
          rows: [],
        },
      ],
    },
  ],
  suggested_follow_ups: [],
  limitations: [
    "테마 편입은 상품의 미래 성과를 뜻하지 않습니다.",
    "수익률을 예측하지 않습니다.",
  ],
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
        macro_regime_etf_outcomes: {
          engine_name: "historical_macro_regime_etf_outcomes",
          engine_version: "test",
          policy_version: "test",
          outcome_start_rule: "first_trading_day_of_month_after_regime",
          boundary_lag_days: 7,
          groups: [{
            regime_period: "2024-01-01",
            distance: "0.2500",
            etfs: [{
              isu_code: "069500",
              isu_name: "KODEX 200",
              history_source: "kis_adjusted_close_plus_kind_cash_distribution",
              source: {
                label: "한투 수정주가·KIND 현금분배 반영 원화 총수익지수",
                reference: "https://openapi.koreainvestment.com/",
                as_of: "2025-02-03",
              },
              history_start: "2024-02-01",
              history_end: "2025-02-03",
              horizons: [{
                horizon_months: 3,
                start_date: "2024-02-01",
                end_date: "2024-05-01",
                total_return_percent: "10.0000",
                maximum_drawdown_percent: "25.0000",
              }],
              gaps: [
                { horizon_months: 6, reason: "end_observation_unavailable" },
                { horizon_months: 12, reason: "end_observation_unavailable" },
              ],
            }],
          }],
          is_forecast: false,
          planning_return_input: false,
          allocation_weight_input: false,
          rebalancing_trigger_input: false,
          limitations: ["historical_similarity_does_not_imply_future_return"],
        },
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
    const outcomeCard = screen.getByLabelText("과거 유사국면 ETF 근거 카드");
    expect(within(outcomeCard).getByText("2024년 1월 유사국면")).toBeInTheDocument();
    expect(within(outcomeCard).getByText("KODEX 200")).toBeInTheDocument();
    expect(within(outcomeCard).getByText("10.0000%")).toBeInTheDocument();
    expect(within(outcomeCard).getByText("최대낙폭 -25%")).toBeInTheDocument();
    expect(within(outcomeCard).getAllByText("관측 부족")).toHaveLength(2);
    expect(within(outcomeCard).getByText(/KIND 현금분배/)).toBeInTheDocument();
  });

  it("renders only the five requested recommendation cards without spark icons", async () => {
    vi.mocked(getChatCards).mockResolvedValue({ cards: RECOMMENDED_CHAT_CARDS });
    render(<GuidePage surveyProfile={null} />);

    const carousel = await screen.findByLabelText("챗봇 추천 질문");
    const buttons = within(carousel).getAllByRole("button");

    expect(buttons).toHaveLength(5);
    expect(buttons.map((button) => button.textContent)).toEqual(
      RECOMMENDED_CHAT_CARDS.map(
        (card) => `추천 질문${card.title}${card.message}`,
      ),
    );
    expect(carousel.querySelector(".design-prompt-icon")).toBeNull();
  });

  it.each(RECOMMENDED_CHAT_CARDS)(
    "sends the exact message when $title is clicked",
    async (card) => {
      vi.mocked(getChatCards).mockResolvedValue({ cards: [card] });
      vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
        response: THEME_RESPONSE,
        persisted: false,
        session_id: null,
      });
      render(<GuidePage surveyProfile={null} />);

      const carousel = await screen.findByLabelText("챗봇 추천 질문");
      fireEvent.click(within(carousel).getByRole("button", { name: new RegExp(card.title) }));

      await waitFor(() => {
        expect(vi.mocked(sendAuthenticatedChatStream).mock.calls[0]?.[0]).toBe(
          card.message,
        );
      });
    },
  );

  it("separates question and ETF theme cards on the empty chat screen", async () => {
    render(<GuidePage surveyProfile={null} />);

    expect(await screen.findByRole("heading", {
      name: "챗봇에게 무엇이든 물어보세요",
    })).toBeInTheDocument();
    const sectorCards = await screen.findByLabelText("ETF 섹터 카드");
    expect(ETF_THEME_CARDS).toHaveLength(23);
    expect(ETF_THEME_CARDS.map((card) => card.number)).toEqual(
      Array.from({ length: 23 }, (_, index) => index + 1),
    );
    const initialButtons = within(sectorCards).getAllByRole("button");
    expect(initialButtons).toHaveLength(6);
    expect(within(sectorCards).getAllByRole("button", {
      name: /ETF 테마 설명 보기$/,
    })).toHaveLength(5);
    expect(within(sectorCards).getByRole("button", {
      name: "반도체 ETF 테마 설명 보기",
    })).toBeInTheDocument();
    expect(within(sectorCards).queryByRole("button", {
      name: "건설·기계·인프라 ETF 테마 설명 보기",
    })).not.toBeInTheDocument();

    const moreButton = within(sectorCards).getByRole("button", {
      name: "나머지 ETF 테마 18개 더보기",
    });
    expect(initialButtons[5]).toBe(moreButton);
    expect(moreButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(moreButton);

    expect(within(sectorCards).getAllByRole("button", {
      name: /ETF 테마 설명 보기$/,
    })).toHaveLength(23);
    expect(within(sectorCards).getByRole("button", {
      name: "조선 ETF 테마 설명 보기",
    })).toBeInTheDocument();
    const collapseButton = within(sectorCards).getByRole("button", {
      name: "ETF 테마 목록 접기",
    });
    expect(collapseButton).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(collapseButton);

    expect(within(sectorCards).getAllByRole("button")).toHaveLength(6);
    expect(within(sectorCards).queryByRole("button", {
      name: "조선 ETF 테마 설명 보기",
    })).not.toBeInTheDocument();
  });

  it("places ETF follow-ups below the theme section and hides a clicked question", async () => {
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      {
        message_id: "theme-question",
        question_message_id: null,
        role: "user",
        content: "조선 테마가 뭐야?",
        response: null,
        model_name: null,
        created_at: "2026-07-20T00:00:00Z",
        evidence: [],
      },
      {
        message_id: "theme-answer",
        question_message_id: "theme-question",
        role: "assistant",
        content: THEME_RESPONSE.answer,
        response: THEME_RESPONSE,
        model_name: null,
        created_at: "2026-07-20T00:00:01Z",
        evidence: [],
      },
    ]);
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      response: THEME_RESPONSE,
      persisted: false,
      session_id: null,
    });
    render(<GuidePage surveyProfile={null} />);

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    const themeSection = (await screen.findByText("조선 테마란?")).closest("details");
    const followUps = screen.getByLabelText("이어서 물어보기");
    expect(themeSection?.nextElementSibling).toBe(followUps);
    expect(within(followUps).getByRole("button", {
      name: /테마 ETF상품/,
    })).toBeInTheDocument();

    fireEvent.click(within(followUps).getByRole("button", { name: /테마 대표기업/ }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /테마 대표기업/ })).not.toBeInTheDocument();
    });
    expect(vi.mocked(sendAuthenticatedChatStream).mock.calls[0]?.[0]).toBe(
      "조선 테마 대표기업은 뭐야?",
    );
  });

  it("renders representative companies as two readable labeled paragraphs", async () => {
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      {
        message_id: "company-question",
        question_message_id: null,
        role: "user",
        content: "반도체 테마 대표기업은 뭐야?",
        response: null,
        model_name: null,
        created_at: "2026-07-20T00:00:00Z",
        evidence: [],
      },
      {
        message_id: "company-answer",
        question_message_id: "company-question",
        role: "assistant",
        content: REPRESENTATIVE_COMPANY_RESPONSE.answer,
        response: REPRESENTATIVE_COMPANY_RESPONSE,
        model_name: null,
        created_at: "2026-07-20T00:00:01Z",
        evidence: [],
      },
    ]);
    render(<GuidePage surveyProfile={null} />);

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    const companyName = await screen.findByText("Samsung Electronics");
    const companyCard = companyName.closest(".answer-callout");

    expect(companyName.tagName).toBe("STRONG");
    expect(companyCard).not.toBeNull();
    const roleLabel = within(companyCard as HTMLElement).getByText("테마에서의 역할:");
    const plainLabel = within(companyCard as HTMLElement).getByText("쉽게 말하면:");
    expect(roleLabel.tagName).toBe("STRONG");
    expect(plainLabel.tagName).toBe("STRONG");
    expect(companyCard?.querySelectorAll("p")).toHaveLength(2);
    expect(within(companyCard as HTMLElement).queryByText("대표 사례로 보는 이유:"))
      .not.toBeInTheDocument();
  });

  it("keeps every ETF theme paragraph as a separate uniformly spaced item", async () => {
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      {
        message_id: "considerations-question",
        question_message_id: null,
        role: "user",
        content: "반도체 테마 ETF 장단점을 알려줘",
        response: null,
        model_name: null,
        created_at: "2026-07-20T00:00:00Z",
        evidence: [],
      },
      {
        message_id: "considerations-answer",
        question_message_id: "considerations-question",
        role: "assistant",
        content: THEME_CONSIDERATIONS_RESPONSE.answer,
        response: THEME_CONSIDERATIONS_RESPONSE,
        model_name: null,
        created_at: "2026-07-20T00:00:01Z",
        evidence: [],
      },
    ]);
    render(<GuidePage surveyProfile={null} />);

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    const answerLead = await screen.findByText(THEME_CONSIDERATIONS_RESPONSE.answer);
    const answerContent = answerLead.closest(".answer-content");
    const riskHeading = screen.getByText("주의할 위험 3가지");
    const riskList = riskHeading.parentElement?.querySelector(".answer-bullets");
    const limitations = answerContent?.querySelectorAll(".limitation-box p");

    expect(answerContent).toHaveClass("theme-answer-content");
    expect(answerContent).toHaveStyle("--theme-paragraph-gap: 10pt");
    expect(riskHeading.parentElement).toHaveClass("answer-bullet-block");
    expect(riskList?.querySelectorAll("li")).toHaveLength(3);
    expect(within(riskList as HTMLElement).getByText(
      "미세공정 경쟁과 대규모 투자 실패가 기업 수익성을 훼손할 수 있습니다.",
    ).tagName).toBe("LI");
    expect(within(riskList as HTMLElement).getByText(
      "수출규제와 지정학적 공급망 재편의 영향을 크게 받을 수 있습니다.",
    ).tagName).toBe("LI");
    expect(limitations).toHaveLength(2);
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
