// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  deleteAllChatSessions,
  deleteChatSession,
  getChatCards,
  getChatSessions,
  getScenarios,
  getStoredChatMessages,
  sendAuthenticatedChatStream,
} from "../api/client";
import type { ChatCard, ChatResponse, ChatSessionSummary } from "../api/types";
import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import {
  ETF_THEME_CARDS,
  filterChatCards,
  GuidePage,
} from "./GuidePage";

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {
    status: number;

    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  deleteAllChatSessions: vi.fn(),
  deleteChatSession: vi.fn(),
  getChatCards: vi.fn(),
  getChatSessions: vi.fn(),
  getScenarios: vi.fn(),
  getStoredChatMessages: vi.fn(),
  sendAuthenticatedChatStream: vi.fn(),
}));

const SESSION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const CHAT_SESSION: ChatSessionSummary = {
  session_id: SESSION_ID,
  title: "IRP 규칙",
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
};

function renderGuide(
  onSignOut = vi.fn().mockResolvedValue(undefined),
  onOpenPlanner?: () => void,
): ReturnType<typeof render> {
  const auth = {
    session: { access_token: "access-token", user: { id: "user-1", email: "owner@example.com" } },
    loading: false,
    configured: true,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  } as unknown as SupabaseAuthState;
  return render(<GuidePage auth={auth} onOpenPlanner={onOpenPlanner} onSignOut={onSignOut} surveyProfile={null} userContext={null} />);
}
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

const STRUCTURED_PORTFOLIO_RESPONSE: ChatResponse = {
  ...THEME_RESPONSE,
  intent: "educational_portfolio",
  answer: "위험중립형 연금 운용 전략을 정리했어요.",
  data_mode: "engine_educational_planning",
  sections: [
    {
      kind: "service_explanation",
      title: "위험중립형 투자전략",
      content: "35년의 장기 운용기간을 고려한 전략이에요. 목표비중을 확인해 보세요.",
      evidence_ids: [],
      blocks: [
        {
          kind: "table",
          title: "목표 포트폴리오",
          text: "",
          items: [],
          headers: ["자산군", "목표비중", "엔진 편입 후보"],
          rows: [["국내외 주식", "28.0%", "TIGER 예시 · KODEX 예시"]],
        },
        {
          kind: "bullets",
          title: "운용 원칙",
          text: "",
          items: ["분기마다 목표비중 이탈을 점검해요."],
          headers: [],
          rows: [],
        },
      ],
    },
  ],
  limitations: ["상품 선택과 주문은 사용자가 직접 해요."],
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

const THEME_CANDIDATES_RESPONSE: ChatResponse = {
  ...THEME_RESPONSE,
  answer: "자동차테마에서 거래가 가장 활발하고 수수료가 저렴한 ETF 3개를 보여드리겠습니다.",
  data_mode: "theme_candidates",
  sections: [
    {
      kind: "service_explanation",
      title: "자동차 테마 ETF상품",
      content: "",
      evidence_ids: [],
      blocks: [
        {
          kind: "callout",
          title: "1. KODEX 자동차",
          text: "연간 수수료율(운용보수): 0.45%\n\n하루 평균 거래대금: 229억원\n\n상품 특징: KRX 자동차지수를 추종하는 국내 대표 자동차 ETF입니다.",
          items: [],
          headers: [],
          rows: [],
        },
      ],
    },
  ],
  numeric_evidence: [
    {
      label: "KODEX 자동차 하루 평균 거래대금",
      value: "22900000000",
      unit: "원",
      evidence_id: "candidate-volume",
      basis: "관측기간 중앙값",
    },
  ],
  suggested_follow_ups: [],
};

const THEME_HOLDINGS_RESPONSE: ChatResponse = {
  ...THEME_RESPONSE,
  answer: "직전에 소개한 반도체 테마 ETF 3개의 구성종목 비중 TOP3입니다.",
  data_mode: "theme_component_holdings",
  sections: ["TIGER 반도체TOP10", "KODEX 반도체", "HANARO Fn K-반도체"].map(
    (name) => ({
      kind: "fact",
      title: `${name} 구성종목 TOP3`,
      content: "",
      evidence_ids: [`kis:components:${name}`],
      blocks: [{
        kind: "table",
        title: null,
        text: "",
        items: [],
        headers: ["구성종목", "구성비중"],
        rows: [
          ["삼성전자", "28.75%"],
          ["SK하이닉스", "26.66%"],
          ["SK스퀘어", "22.65%"],
        ],
      }],
    }),
  ),
  numeric_evidence: [{
    label: "TIGER 반도체TOP10 삼성전자 구성 비중",
    value: "28.75",
    unit: "%",
    evidence_id: "kis:components:TIGER 반도체TOP10",
    basis: "KIS etf_cnfg_issu_rlim 원문 필드",
  }],
  sources: [],
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
    vi.mocked(getScenarios).mockResolvedValue([]);
    vi.mocked(getChatCards).mockResolvedValue({ cards: [] });
    vi.mocked(getChatSessions).mockResolvedValue([CHAT_SESSION]);
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
    vi.mocked(deleteAllChatSessions).mockResolvedValue(undefined);
    vi.mocked(sendAuthenticatedChatStream).mockReset();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the attached pension-helper conversation shell", async () => {
    renderGuide();

    expect(await screen.findByText("막막한 노후 준비,", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "새 대화 시작" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("연금에 대해 무엇이든 물어보세요.")).toBeInTheDocument();
    expect(screen.getAllByText(/실제 투자·가입 결정은 본인의 판단과 전문가 상담/)).toHaveLength(2);
  });

  it("confirms deletion, disables controls, removes the row, and clears the active chat", async () => {
    let finishDelete: (() => void) | undefined;
    vi.mocked(deleteChatSession).mockImplementation(
      () => new Promise<void>((resolve) => { finishDelete = resolve; }),
    );
    renderGuide();

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

  it("does not retry server readiness after an authentication failure", async () => {
    const setTimeoutSpy = vi.spyOn(window, "setTimeout");
    vi.mocked(getScenarios).mockRejectedValue(new ApiError(401, "Unauthorized"));
    renderGuide();

    expect(await screen.findByText("API 연결 필요")).toBeInTheDocument();
    expect(getScenarios).toHaveBeenCalledOnce();
    expect(setTimeoutSpy).not.toHaveBeenCalledWith(expect.any(Function), 3000);
    expect(setTimeoutSpy).not.toHaveBeenCalledWith(expect.any(Function), 6000);
    expect(setTimeoutSpy).not.toHaveBeenCalledWith(expect.any(Function), 12000);
  });

  it("does not load protected endpoints without a session", async () => {
    const anonymousAuth = {
      session: null,
      loading: false,
      configured: true,
      error: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
    } as unknown as SupabaseAuthState;
    render(<GuidePage auth={anonymousAuth} onSignOut={vi.fn()} surveyProfile={null} userContext={null} />);

    await waitFor(() => expect(getChatCards).toHaveBeenCalledOnce());
    expect(getScenarios).not.toHaveBeenCalled();
    expect(getChatSessions).not.toHaveBeenCalled();
  });

  it("keeps stored conversations when logging out", async () => {
    const onSignOut = vi.fn().mockResolvedValue(undefined);
    renderGuide(onSignOut);
    await screen.findByText("IRP 규칙");
    fireEvent.click(screen.getAllByRole("button", { name: "로그아웃" })[0]);
    await waitFor(() => expect(onSignOut).toHaveBeenCalledOnce());
    expect(deleteChatSession).not.toHaveBeenCalled();
  });

  it("falls back to owned per-session deletion while an older API is deployed", async () => {
    vi.mocked(deleteAllChatSessions).mockRejectedValue(
      new ApiError(405, "Method Not Allowed"),
    );
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: "전체 삭제" }));

    await waitFor(() => {
      expect(deleteAllChatSessions).toHaveBeenCalledWith("access-token");
      expect(deleteChatSession).toHaveBeenCalledWith(SESSION_ID, "access-token");
    });
    expect(await screen.findByRole("status")).toHaveTextContent("모든 대화");
  });

  it("labels an unsummarized live headline without implying a three-line summary", async () => {
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      session_id: null,
      response: {
        ...THEME_RESPONSE,
        intent: "news",
        answer: "NAVER 검색 API에서 최신 증시 뉴스 메타데이터를 조회했어요.",
        data_mode: "news_metadata",
        news_items: [
          {
            evidence_id: "live-news:headline-1",
            title: "장중 코스피 움직임",
            description: "장중 시장 움직임을 전한 NAVER 검색 설명입니다.",
            summary_lines: [],
            original_url: "https://example.test/live/1",
            published_at: "2026-07-21T01:00:00Z",
          },
        ],
      },
    });
    renderGuide();

    const composer = screen.getByLabelText("질문 입력");
    fireEvent.change(composer, { target: { value: "실시간 증시 뉴스 보여줘" } });
    fireEvent.submit(composer.closest("form")!);

    expect(await screen.findByText("실시간 헤드라인 · 3줄 요약 전"))
      .toBeInTheDocument();
    expect(screen.queryByText("첫 번째 뉴스 · 3줄 요약")).not.toBeInTheDocument();
  });

  it("keeps the session when confirmation is cancelled", async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    renderGuide();

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
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    await screen.findByText("저장된 질문");
    const composer = screen.getByLabelText("질문 입력");
    fireEvent.change(composer, { target: { value: "첫 질문" } });
    fireEvent.submit(composer.closest("form")!);
    await screen.findAllByText("요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.");
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

  it("keeps educational portfolio answers focused by hiding duplicate numeric evidence cards", async () => {
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      response: {
        intent: "educational_portfolio",
        answer: "설문 결과에 맞는 투자전략을 정리했어요.",
        narration_mode: "deterministic",
        data_mode: "engine_educational_planning",
        numeric_evidence: [
          { label: "수령 개시까지 운용기간", value: "27", unit: "년", evidence_id: "engine:portfolio", basis: "엔진 계산" },
          { label: "equity_drawdown 스트레스 손실 추정치", value: "20", unit: "%", evidence_id: "engine:portfolio", basis: "엔진 시나리오" },
        ],
        news_items: [],
        sections: [{
          kind: "service_explanation",
          title: "위험중립형 투자전략",
          content: "목표 자산배분과 운용 원칙을 확인하세요.",
          evidence_ids: ["engine:portfolio"],
        }],
        sources: [],
        warnings: [],
        visualizations: [],
        limitations: [],
        conversation_context: null,
      },
    } as unknown as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    renderGuide();

    const composer = screen.getByLabelText("질문 입력");
    fireEvent.change(composer, { target: { value: "내 성향에 맞는 포트폴리오를 보여줘" } });
    fireEvent.submit(composer.closest("form")!);

    expect(await screen.findByText(/위험중립형 투자전략/)).toBeInTheDocument();
    expect(screen.getByText("연금 운용전략")).toBeInTheDocument();
    expect(screen.queryByLabelText("수치 근거")).not.toBeInTheDocument();
    expect(screen.queryByText("검증 답변")).not.toBeInTheDocument();
    expect(screen.queryByText("equity_drawdown 스트레스 손실 추정치")).not.toBeInTheDocument();
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
    renderGuide();

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
    renderGuide();

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

  it("shows six numeric evidence cards first and expands the remaining cards", async () => {
    const response: ChatResponse = {
      ...THEME_RESPONSE,
      numeric_evidence: Array.from({ length: 7 }, (_, index) => ({
        label: `카드 수치 ${index + 1}`,
        value: String(index + 1),
        unit: "%",
        evidence_id: `evidence:${index + 1}`,
        basis: "표시 순서 테스트",
      })),
    };
    vi.mocked(getChatCards).mockResolvedValue({
      cards: [RECOMMENDED_CHAT_CARDS[0]],
    });
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      session_id: null,
      response,
    } as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /오늘 증시 뉴스/ }));

    await screen.findByText("카드 수치 6");
    expect(screen.queryByText("카드 수치 7")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", {
      name: "숫자 근거 전체 7개 보기",
    });
    fireEvent.click(toggle);

    expect(await screen.findByText("카드 수치 7")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "숫자 근거 접기" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("numbers each news summary line and submits the selected market question", async () => {
    const response: ChatResponse = {
      ...THEME_RESPONSE,
      intent: "news",
      data_mode: "news_summary",
      news_items: [
        {
          evidence_id: "news:semiconductor",
          title: "반도체 시장 뉴스",
          original_url: "https://example.test/semiconductor",
          summary_lines: ["핵심 사건입니다.", "주요 수치와 원인입니다.", "영향과 불확실성입니다."],
        },
      ],
      sections: [
        {
          kind: "external_opinion",
          title: "중복 뉴스 요약",
          content: "뉴스 카드에 이미 표시된 요약입니다.",
          evidence_ids: ["news:semiconductor"],
          blocks: [],
        },
      ],
      suggested_follow_ups: [
        {
          follow_up_id: "news_region_kr",
          label: "한국증시 뉴스",
          message: "한국증시 뉴스 알려줘",
        },
        {
          follow_up_id: "news_region_us",
          label: "미국증시 뉴스",
          message: "미국증시 뉴스 알려줘",
        },
      ],
    };
    vi.mocked(getChatCards).mockResolvedValue({ cards: [RECOMMENDED_CHAT_CARDS[0]] });
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      session_id: null,
      response,
    } as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /오늘 증시 뉴스/ }));

    const newsList = await screen.findByLabelText("뉴스 목록");
    expect(screen.getByText("증시 뉴스")).toBeInTheDocument();
    expect(within(newsList).getByText("1.", { exact: true })).toBeInTheDocument();
    expect(within(newsList).getByText("2.", { exact: true })).toBeInTheDocument();
    expect(within(newsList).getByText("3.", { exact: true })).toBeInTheDocument();
    const followUps = screen.getByLabelText("이어서 물어보기");
    expect(within(followUps).queryByRole("button", { name: /첫 번째 뉴스 자세히/ })).not.toBeInTheDocument();
    expect(within(followUps).queryByRole("button", { name: /다른 뉴스 더 보기/ })).not.toBeInTheDocument();
    expect(screen.queryByText("중복 뉴스 요약")).not.toBeInTheDocument();

    fireEvent.click(within(followUps).getByRole("button", { name: "한국증시 뉴스" }));

    await waitFor(() => {
      expect(vi.mocked(sendAuthenticatedChatStream).mock.calls.at(-1)?.[0]).toBe(
        "한국증시 뉴스 알려줘",
      );
    });
  });

  it("renders the three home recommendation cards without a carousel", async () => {
    vi.mocked(getChatCards).mockResolvedValue({ cards: RECOMMENDED_CHAT_CARDS });
    renderGuide();

    const recommendationGrid = await screen.findByLabelText("챗봇 추천 질문");
    const buttons = within(recommendationGrid).getAllByRole("button");

    expect(buttons).toHaveLength(3);
    expect(buttons.map((button) => button.textContent)).toEqual(
      RECOMMENDED_CHAT_CARDS.map(
        (card) => `추천 질문${card.title}${card.message}`,
      ),
    );
    expect(recommendationGrid).toHaveClass("chat-question-grid");
    expect(recommendationGrid.querySelector(".design-prompt-icon")).toBeNull();
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
      renderGuide();

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
    renderGuide();

    expect(await screen.findByRole("heading", {
      name: "챗봇에게 무엇이든 물어보세요",
    })).toBeInTheDocument();
    const sectorCards = await screen.findByLabelText("ETF 섹터 카드");
    expect(ETF_THEME_CARDS).toHaveLength(21);
    expect(ETF_THEME_CARDS.map((card) => card.number)).toEqual(
      Array.from({ length: 21 }, (_, index) => index + 1),
    );
    expect(ETF_THEME_CARDS.map((card) => card.title)).not.toEqual(
      expect.arrayContaining(["AI·소프트웨어", "코리아밸류업", "ESG"]),
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
      name: "자동차·모빌리티 ETF 테마 설명 보기",
    })).not.toBeInTheDocument();

    const moreButton = within(sectorCards).getByRole("button", {
      name: "나머지 ETF 테마 16개 더보기",
    });
    expect(initialButtons[5]).toBe(moreButton);
    expect(moreButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(moreButton);

    expect(within(sectorCards).getAllByRole("button", {
      name: /ETF 테마 설명 보기$/,
    })).toHaveLength(21);
    expect(within(sectorCards).getByRole("button", {
      name: "조선 ETF 테마 설명 보기",
    })).toBeInTheDocument();
    expect(within(sectorCards).getByRole("button", {
      name: "채권 ETF 테마 설명 보기",
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
    expect(within(sectorCards).queryByRole("button", {
      name: "채권 ETF 테마 설명 보기",
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
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    const themeSection = (await screen.findByText(/조선 테마란/)).closest("details");
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
    renderGuide();

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

  it("opens ETF product details without rendering the large numeric evidence grid", async () => {
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      {
        message_id: "candidate-question",
        question_message_id: null,
        role: "user",
        content: "자동차테마 ETF상품 3개를 보여줘",
        response: null,
        model_name: null,
        created_at: "2026-07-20T00:00:00Z",
        evidence: [],
      },
      {
        message_id: "candidate-answer",
        question_message_id: "candidate-question",
        role: "assistant",
        content: THEME_CANDIDATES_RESPONSE.answer,
        response: THEME_CANDIDATES_RESPONSE,
        model_name: null,
        created_at: "2026-07-20T00:00:01Z",
        evidence: [],
      },
    ]);
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    const sectionTitle = await screen.findByText("자동차 테마 ETF상품");
    const productSection = sectionTitle.closest("details");
    const productCard = screen.getByText("1. KODEX 자동차").closest(".answer-callout");

    expect(productSection).toHaveAttribute("open");
    expect(productSection?.closest(".answer-content")?.querySelector(".number-grid"))
      .not.toBeInTheDocument();
    expect(productCard?.querySelectorAll("p")).toHaveLength(3);
    expect(productCard?.querySelector(".answer-callout-copy")).toBeInTheDocument();
    expect(productSection?.closest(".answer-content")).toHaveStyle("--theme-paragraph-gap: 10pt");
  });

  it("shows three ETF TOP3 tables without numeric cards or issue codes", async () => {
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      {
        message_id: "holdings-question",
        question_message_id: null,
        role: "user",
        content: "반도체 ETF 구성종목 비중을 보여줘",
        response: null,
        model_name: null,
        created_at: "2026-07-20T00:00:00Z",
        evidence: [],
      },
      {
        message_id: "holdings-answer",
        question_message_id: "holdings-question",
        role: "assistant",
        content: THEME_HOLDINGS_RESPONSE.answer,
        response: THEME_HOLDINGS_RESPONSE,
        model_name: null,
        created_at: "2026-07-20T00:00:01Z",
        evidence: [],
      },
    ]);
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    const titles = await screen.findAllByText(/구성종목 TOP3$/);
    const answer = titles[0].closest(".answer-content");

    expect(titles).toHaveLength(3);
    expect(answer).toHaveClass("holdings-answer-content");
    expect(answer?.querySelector(".number-grid")).not.toBeInTheDocument();
    expect(screen.queryByText("종목코드")).not.toBeInTheDocument();
    titles.forEach((title) => expect(title.closest("details")).toHaveAttribute("open"));
    within(answer as HTMLElement).getAllByRole("table").forEach((table) => {
      expect(within(table).getAllByRole("columnheader").map((header) => header.textContent))
        .toEqual(["구성종목", "구성비중"]);
      expect(within(table).getAllByRole("row")).toHaveLength(4);
    });
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
    renderGuide();

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

  it("keeps educational portfolio sections and limitations collapsed until opened", async () => {
    vi.mocked(getStoredChatMessages).mockResolvedValue([
      {
        message_id: "portfolio-question",
        question_message_id: null,
        role: "user",
        content: "포트폴리오를 보여줘",
        response: null,
        model_name: null,
        created_at: "2026-07-20T00:00:00Z",
        evidence: [],
      },
      {
        message_id: "portfolio-answer",
        question_message_id: "portfolio-question",
        role: "assistant",
        content: STRUCTURED_PORTFOLIO_RESPONSE.answer,
        response: STRUCTURED_PORTFOLIO_RESPONSE,
        model_name: null,
        created_at: "2026-07-20T00:00:01Z",
        evidence: [],
      },
    ]);
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
    const preview = await screen.findByText(
      "위험중립형 투자전략 — 35년의 장기 운용기간을 고려한 전략이에요.",
    );
    const section = preview.closest("details");
    const limitations = screen.getByText("확인할 점 1가지 보기").closest("details");

    expect(section).not.toHaveAttribute("open");
    expect(section?.querySelector(".answer-table-wrap")).not.toBeNull();
    expect(section?.querySelectorAll(".answer-bullets li")).toHaveLength(1);
    expect(limitations).not.toHaveAttribute("open");

    fireEvent.click(preview.closest("summary")!);
    fireEvent.click(screen.getByText("확인할 점 1가지 보기").closest("summary")!);

    expect(section).toHaveAttribute("open");
    expect(limitations).toHaveAttribute("open");
  });
});

describe("GuidePage pension planner entry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getScenarios).mockResolvedValue([]);
    vi.mocked(getChatCards).mockResolvedValue({ cards: [] });
    vi.mocked(getChatSessions).mockResolvedValue([]);
    vi.mocked(getStoredChatMessages).mockResolvedValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it("opens the existing profile planner from the chat home card", () => {
    const onOpenPlanner = vi.fn();
    renderGuide(undefined, onOpenPlanner);

    expect(screen.getByText("규칙 엔진 가정")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "연금 수령 계획 시나리오 열기" }));

    expect(onOpenPlanner).toHaveBeenCalledOnce();
  });

  it("opens the planner instead of resending its dedicated follow-up", async () => {
    const onOpenPlanner = vi.fn();
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      session_id: null,
      response: {
        ...THEME_RESPONSE,
        intent: "account_rule",
        data_mode: "pension_planner_redirect",
        suggested_follow_ups: [{
          follow_up_id: "open_pension_planner",
          label: "연금계산기 열기",
          message: "연금계산기 열기",
        }],
      },
    } as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    vi.mocked(getChatCards).mockResolvedValue({ cards: [RECOMMENDED_CHAT_CARDS[0]] });
    renderGuide(undefined, onOpenPlanner);

    fireEvent.click(await screen.findByRole("button", { name: /오늘 증시 뉴스/ }));
    fireEvent.click(await screen.findByRole("button", { name: "연금계산기 열기" }));

    expect(onOpenPlanner).toHaveBeenCalledOnce();
    expect(sendAuthenticatedChatStream).toHaveBeenCalledTimes(1);
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

