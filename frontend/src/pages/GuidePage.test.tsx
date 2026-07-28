// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
import { CHAT_PROMPT_CANDIDATES } from "../chatPromptCandidates";
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
  getRebalancingReminder: vi.fn().mockResolvedValue({ profile_required: true, enabled: false, risk_profile: null, cadence: null, last_reviewed_at: null, next_review_at: null, is_due: false }),
  getChatSessions: vi.fn(),
  getScenarios: vi.fn(),
  getStoredChatMessages: vi.fn(),
  updateRebalancingReminder: vi.fn(),
  completeRebalancingReview: vi.fn(),
  sendAuthenticatedChatStream: vi.fn(),
}));

const SESSION_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const CHAT_SESSION: ChatSessionSummary = {
  session_id: SESSION_ID,
  title: "IRP 규칙",
  created_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:00:00Z",
};
const PREVIOUS_SESSION: ChatSessionSummary = {
  session_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  title: "지난 대화",
  created_at: "2026-07-18T00:00:00Z",
  updated_at: "2026-07-18T00:00:00Z",
};

function renderGuide(
  onSignOut = vi.fn().mockResolvedValue(undefined),
  onOpenPlanner?: () => void,
  portfolioDiagnosis?: {
    onConsumed?: () => void;
    requestId: string;
  },
  onOpenProfile?: () => void,
  initialHistoryOpen = false,
): ReturnType<typeof render> {
  const auth = {
    session: { access_token: "access-token", user: { id: "user-1", email: "owner@example.com" } },
    loading: false,
    configured: true,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  } as unknown as SupabaseAuthState;
  return render(
    <GuidePage
      auth={auth}
      initialHistoryOpen={initialHistoryOpen}
      onOpenPlanner={onOpenPlanner}
      onOpenProfile={onOpenProfile}
      onPortfolioDiagnosisConsumed={portfolioDiagnosis?.onConsumed}
      onSignOut={onSignOut}
      portfolioDiagnosisRequestId={portfolioDiagnosis?.requestId}
      surveyProfile={null}
      userContext={null}
    />,
  );
}

async function openHistory(): Promise<void> {
  const previousCalls = vi.mocked(getChatSessions).mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "지난 대화 열기" }));
  await waitFor(() => {
    expect(getChatSessions).toHaveBeenCalledTimes(previousCalls + 1);
  });
}

async function openStoredSession(): Promise<void> {
  await openHistory();
  fireEvent.click(await screen.findByRole("button", { name: /^IRP 규칙/ }));
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

  it("submits the portfolio recommendation card once for a home diagnosis entry", async () => {
    const onConsumed = vi.fn();
    vi.mocked(getChatCards).mockResolvedValue({ cards: RECOMMENDED_CHAT_CARDS });
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      session_id: null,
      response: STRUCTURED_PORTFOLIO_RESPONSE,
    });

    renderGuide(undefined, undefined, {
      onConsumed,
      requestId: "portfolio-diagnosis-request-1",
    });

    await waitFor(() => {
      expect(sendAuthenticatedChatStream).toHaveBeenCalledTimes(1);
    });
    expect(vi.mocked(sendAuthenticatedChatStream).mock.calls[0]?.[0]).toBe(
      RECOMMENDED_CHAT_CARDS.find((card) => card.card_id === "edu_portfolio")?.message,
    );
    expect(onConsumed).toHaveBeenCalledOnce();

    await screen.findByText(STRUCTURED_PORTFOLIO_RESPONSE.answer);
    expect(sendAuthenticatedChatStream).toHaveBeenCalledTimes(1);
  });

  it("renders the attached Canvas-2 conversation shell", async () => {
    renderGuide();

    expect(await screen.findByText("고객님 ! 막막한 노후 준비,", { exact: false })).toBeInTheDocument();
    const historyButton = screen.getByRole("button", { name: "지난 대화 열기" });
    const historySidebar = screen.getByRole("complementary");
    expect(historyButton).toBeInTheDocument();
    expect(historySidebar).not.toHaveClass("sidebar-open");
    expect(getChatSessions).not.toHaveBeenCalled();

    fireEvent.click(historyButton);
    expect(historySidebar).toHaveClass("sidebar-open");
    await waitFor(() => expect(getChatSessions).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByRole("button", { name: "지난 대화 닫기" }));
    expect(historySidebar).not.toHaveClass("sidebar-open");
    expect(screen.getByAltText("프로필")).toBeInTheDocument();
    expect(CHAT_PROMPT_CANDIDATES.map((candidate) => `예: ${candidate}`)).toContain(
      screen.getByLabelText("질문 입력").getAttribute("placeholder"),
    );
    expect(screen.getByText(/AI 답변은 투자 판단을 돕는 정보이며, 미래 수익을 보장하지 않습니다/)).toBeInTheDocument();
  });

  it("opens the saved conversation list on a chat history entry", async () => {
    renderGuide(undefined, undefined, undefined, undefined, true);

    expect(screen.getByRole("complementary")).toHaveClass("sidebar-open");
    expect(screen.getByRole("button", { name: "지난 대화 닫기" })).toBeInTheDocument();
    await waitFor(() => expect(getChatSessions).toHaveBeenCalledOnce());
  });

  it("opens the profile screen from the top-right profile button", async () => {
    const onOpenProfile = vi.fn();
    renderGuide(undefined, undefined, undefined, onOpenProfile);

    const historySidebar = screen.getByRole("complementary");
    fireEvent.click(await screen.findByRole("button", {
      name: "로그인됨 · 프로필 화면 열기",
    }));

    expect(onOpenProfile).toHaveBeenCalledOnce();
    expect(historySidebar).not.toHaveClass("sidebar-open");
  });

  it("confirms deletion, disables controls, removes the row, and clears the active chat", async () => {
    let finishDelete: (() => void) | undefined;
    vi.mocked(deleteChatSession).mockImplementation(
      () => new Promise<void>((resolve) => { finishDelete = resolve; }),
    );
    renderGuide();

    await openHistory();
    const openButton = await screen.findByRole("button", { name: /^IRP 규칙/ });
    fireEvent.click(openButton);
    expect(await screen.findByText("저장된 질문")).toBeInTheDocument();
    await openHistory();

    const activeOpenButton = screen.getByRole("button", { name: /^IRP 규칙/ });
    const deleteButton = screen.getByRole("button", { name: "대화 삭제: IRP 규칙" });
    const composer = screen.getByLabelText("질문 입력");
    fireEvent.click(deleteButton);

    expect(window.confirm).toHaveBeenCalled();
    expect(deleteChatSession).toHaveBeenCalledWith(SESSION_ID, "access-token");
    expect(activeOpenButton).toBeDisabled();
    expect(deleteButton).toBeDisabled();

    finishDelete?.();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "대화 삭제: IRP 규칙" })).not.toBeInTheDocument();
      expect(screen.queryByText("저장된 질문")).not.toBeInTheDocument();
    });
    await waitFor(() => expect(composer).toHaveFocus());
  });

  it("does not retry server readiness after an authentication failure", async () => {
    const setTimeoutSpy = vi.spyOn(window, "setTimeout");
    vi.mocked(getScenarios).mockRejectedValue(new ApiError(401, "Unauthorized"));
    vi.mocked(getChatCards).mockResolvedValue({ cards: RECOMMENDED_CHAT_CARDS });
    renderGuide();

    expect(await screen.findByText("API 연결 필요")).toBeInTheDocument();
    expect(within(screen.getByLabelText("챗봇 추천 질문")).getAllByRole("button")).toHaveLength(3);
    expect(getScenarios).toHaveBeenCalledOnce();
    expect(setTimeoutSpy).not.toHaveBeenCalledWith(expect.any(Function), 3000);
    expect(setTimeoutSpy).not.toHaveBeenCalledWith(expect.any(Function), 6000);
    expect(setTimeoutSpy).not.toHaveBeenCalledWith(expect.any(Function), 12000);
  });

  it("shows a retry action when the recommendation catalog fails", async () => {
    vi.mocked(getChatCards)
      .mockRejectedValueOnce(new Error("catalog unavailable"))
      .mockResolvedValueOnce({ cards: RECOMMENDED_CHAT_CARDS });
    renderGuide();

    expect(await screen.findByText("추천 질문을 불러오지 못했어요.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(within(await screen.findByLabelText("챗봇 추천 질문")).getAllByRole("button")).toHaveLength(3);
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
    await openHistory();
    await screen.findByText("IRP 규칙");
    fireEvent.click(screen.getAllByRole("button", { name: "로그아웃" })[0]);
    await waitFor(() => expect(onSignOut).toHaveBeenCalledOnce());
    expect(deleteChatSession).not.toHaveBeenCalled();
  });

  it("deletes every previous session while preserving the active conversation", async () => {
    vi.mocked(getChatSessions).mockResolvedValue([CHAT_SESSION, PREVIOUS_SESSION]);
    renderGuide();

    await openStoredSession();
    expect(await screen.findByText("저장된 질문")).toBeInTheDocument();
    await openHistory();
    fireEvent.click(await screen.findByRole("button", {
      name: "현재 대화 제외 모두 삭제",
    }));

    await waitFor(() => {
      expect(deleteChatSession).toHaveBeenCalledTimes(1);
    });
    expect(deleteChatSession).toHaveBeenCalledWith(
      PREVIOUS_SESSION.session_id,
      "access-token",
    );
    expect(deleteChatSession).not.toHaveBeenCalledWith(SESSION_ID, "access-token");
    expect(deleteAllChatSessions).not.toHaveBeenCalled();
    expect(screen.getByText("저장된 질문")).toBeInTheDocument();
    const activeSessionButton = screen.getByRole("button", { name: /^IRP 규칙/ });
    expect(activeSessionButton.closest(".history-item")).toHaveClass("active");
    expect(screen.queryByRole("button", { name: "대화 삭제: 지난 대화" }))
      .not.toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent(
      "현재 대화를 제외한 지난 대화를 지웠어요.",
    );
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("현재 대화를 제외"));

    vi.mocked(getChatSessions).mockResolvedValue([CHAT_SESSION]);
    fireEvent.click(screen.getByRole("button", { name: "지난 대화 닫기" }));
    await openHistory();
    expect(screen.getByRole("button", { name: /^IRP 규칙/ }).closest(".history-item"))
      .toHaveClass("active");
    expect(screen.queryByRole("button", { name: "대화 삭제: 지난 대화" }))
      .not.toBeInTheDocument();
  });

  it("keeps a large hidden history out of the chat render tree and reveals it in pages", async () => {
    const sessions = Array.from({ length: 500 }, (_, index): ChatSessionSummary => ({
      session_id: `session-${index + 1}`,
      title: `대화 ${index + 1}`,
      created_at: "2026-07-19T00:00:00Z",
      updated_at: "2026-07-19T00:00:00Z",
    }));
    vi.mocked(getChatSessions).mockResolvedValue(sessions);
    renderGuide();

    expect(getChatSessions).not.toHaveBeenCalled();
    expect(document.querySelectorAll(".history-open")).toHaveLength(0);

    await openHistory();
    expect(document.querySelectorAll(".history-open")).toHaveLength(20);
    fireEvent.click(screen.getByRole("button", { name: "이전 대화 더 보기" }));
    expect(document.querySelectorAll(".history-open")).toHaveLength(40);
    fireEvent.click(screen.getByRole("button", { name: "이전 대화 더 보기" }));
    expect(document.querySelectorAll(".history-open")).toHaveLength(60);

    fireEvent.click(screen.getByRole("button", { name: "지난 대화 닫기" }));
    expect(document.querySelectorAll(".history-open")).toHaveLength(0);
  });

  it("renders a long active conversation in bounded message pages", async () => {
    vi.mocked(getStoredChatMessages).mockResolvedValue(
      Array.from({ length: 90 }, (_, index) => ({
        message_id: `message-${index + 1}`,
        question_message_id: null,
        role: "user" as const,
        content: `저장 메시지 ${index + 1}`,
        response: null,
        model_name: null,
        created_at: "2026-07-19T00:00:00Z",
        evidence: [],
      })),
    );
    renderGuide();

    await openStoredSession();
    expect(await screen.findByText("저장 메시지 90")).toBeInTheDocument();
    expect(screen.queryByText("저장 메시지 50")).not.toBeInTheDocument();
    expect(document.querySelectorAll(".message-row")).toHaveLength(40);

    fireEvent.click(screen.getByRole("button", { name: "이전 메시지 더 보기" }));
    expect(screen.getByText("저장 메시지 11")).toBeInTheDocument();
    expect(screen.queryByText("저장 메시지 10")).not.toBeInTheDocument();
    expect(document.querySelectorAll(".message-row")).toHaveLength(80);
  });

  it("falls back to owned per-session deletion while an older API is deployed", async () => {
    vi.mocked(deleteAllChatSessions).mockRejectedValue(
      new ApiError(405, "Method Not Allowed"),
    );
    renderGuide();

    await openHistory();
    fireEvent.click(await screen.findByRole("button", { name: "전체 삭제" }));

    await waitFor(() => {
      expect(deleteAllChatSessions).toHaveBeenCalledWith("access-token");
      expect(deleteChatSession).toHaveBeenCalledWith(SESSION_ID, "access-token");
    });
    expect(await screen.findByRole("status")).toHaveTextContent("지난 대화를 모두 지웠어요.");
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

    await openHistory();
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

    await openStoredSession();
    await screen.findByText("저장된 질문");
    const composer = screen.getByLabelText("질문 입력");
    fireEvent.change(composer, { target: { value: "첫 질문" } });
    fireEvent.submit(composer.closest("form")!);
    await screen.findAllByText("답변을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.");
    const retryButton = screen.getByRole("button", { name: /다시 시도/ });

    await openHistory();
    fireEvent.click(screen.getByRole("button", { name: "대화 삭제: IRP 규칙" }));

    await waitFor(() => expect(deleteChatSession).toHaveBeenCalledTimes(1));
    expect(composer).toBeDisabled();
    expect(screen.getByRole("button", { name: "질문 보내기" })).toBeDisabled();
    expect(retryButton).toBeDisabled();

    fireEvent.submit(composer.closest("form")!);
    fireEvent.click(retryButton);
    expect(sendAuthenticatedChatStream).toHaveBeenCalledTimes(1);
  });

  it("shows strategy visualizations while hiding duplicate numeric evidence cards", async () => {
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      response: {
        intent: "educational_portfolio",
        answer: "설문 결과에 맞는 투자전략을 정리했어요.",
        narration_mode: "deterministic",
        data_mode: "engine_multi_account_planning",
        numeric_evidence: [
          { label: "수령 개시까지 운용기간", value: "27", unit: "년", evidence_id: "engine:portfolio", basis: "엔진 계산" },
          { label: "equity_drawdown 스트레스 손실 추정치", value: "20", unit: "%", evidence_id: "engine:portfolio", basis: "엔진 시나리오" },
        ],
        news_items: [],
        suggested_follow_ups: [{
          follow_up_id: "risk_cap",
          label: "위험자산 한도 적용",
          message: "위험자산 한도 적용을 알려줘",
        }],
        sections: [{
          kind: "service_explanation",
          title: "위험중립형 투자전략",
          content: "목표 자산배분과 운용 원칙을 확인하세요.",
          evidence_ids: ["engine:portfolio"],
        }, {
          kind: "service_explanation",
          title: "DC형 · ETF 분야 살펴보기",
          content: "ETF 섹터를 살펴보세요.",
          evidence_ids: ["engine:portfolio"],
        }, {
          kind: "service_explanation",
          title: "IRP · ETF 분야 살펴보기",
          content: "ETF 섹터를 살펴보세요.",
          evidence_ids: ["engine:portfolio"],
        }, {
          kind: "service_explanation",
          title: "연금저축펀드 · ETF 분야 살펴보기",
          content: "ETF 섹터를 살펴보세요.",
          evidence_ids: ["engine:portfolio"],
        }],
        sources: [],
        warnings: [],
        visualizations: [
          {
            kind: "sleeve_allocation",
            title: "DC형 목표 자산배분",
            description: "규칙 엔진이 계산한 목표비중이에요.",
            data_boundary: "engine",
            evidence_ids: [],
            items: [{ label: "주식", value: "48", unit: "%", role: "segment" }],
            series: [],
          },
          {
            kind: "stress_scenarios",
            title: "DC형 스트레스 점검",
            description: "규칙 엔진이 계산한 손실 추정치예요.",
            data_boundary: "engine",
            evidence_ids: [],
            items: [{ label: "주식시장 급락", value: "27.5", unit: "%", role: "value" }],
            series: [],
          },
          {
            kind: "sleeve_allocation",
            title: "연금저축펀드 목표 자산배분",
            description: "규칙 엔진이 계산한 목표비중이에요.",
            data_boundary: "engine",
            evidence_ids: [],
            items: [{ label: "주식", value: "57.4", unit: "%", role: "segment" }],
            series: [],
          },
          {
            kind: "stress_scenarios",
            title: "연금저축펀드 스트레스 점검",
            description: "규칙 엔진이 계산한 손실 추정치예요.",
            data_boundary: "engine",
            evidence_ids: [],
            items: [{ label: "주식시장 급락", value: "30", unit: "%", role: "value" }],
            series: [],
          },
        ],
        limitations: [],
        conversation_context: null,
        educational_portfolio_evaluation: {
          evaluated_input: {
            account_type: "dc",
            age: 35,
            retirement_start_age: 60,
            risk_profile: "risk_neutral",
            loss_tolerance_percent: "20",
            current_holdings: [],
            new_contribution_krw: "0",
          },
          strategy_label: "코어·위성 전략",
          planning_horizon_years: 25,
          final_general_risk_target_percent: "48",
          loss_tolerance_binding: false,
          rebalancing: {
            cadence: {
              review_interval_months: 1,
              drift_threshold_percent_points: "3",
            },
          },
          planning_return: {
            conservative_planning_return_percent: "5.1",
            base_planning_return_percent: "5.5",
            sources: [],
          },
        },
      },
    } as unknown as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    renderGuide();

    const composer = screen.getByLabelText("질문 입력");
    fireEvent.change(composer, { target: { value: "내 성향에 맞는 포트폴리오를 보여줘" } });
    fireEvent.submit(composer.closest("form")!);

    expect(await screen.findByText("현재 투자성향 설문 결과(위험중립형)를 기준으로 한 예시 전략은 코어·위성 전략입니다.")).toBeInTheDocument();
    expect(await screen.findByText("위험중립형의 코어·위성 전략")).toBeInTheDocument();
    expect(screen.getByText("위험중립형 투자전략", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("연금 운용전략")).toBeInTheDocument();
    const orderedStrategyContent = [
      screen.getByText("코어·위성 전략"),
      screen.getByText("현재 설문 결과를 기준으로 연금자산을 아래처럼 나눠 볼 수 있어요."),
    ];
    for (let index = 1; index < orderedStrategyContent.length; index += 1) {
      expect(
        orderedStrategyContent[index - 1].compareDocumentPosition(
          orderedStrategyContent[index],
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
    for (const title of [
      "DC형 목표 자산배분",
      "DC형 스트레스 점검",
      "연금저축펀드 목표 자산배분",
      "연금저축펀드 스트레스 점검",
    ]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
    expect(screen.queryByLabelText("수치 근거")).not.toBeInTheDocument();
    expect(screen.queryByText("검증 답변")).not.toBeInTheDocument();
    expect(screen.queryByText("equity_drawdown 스트레스 손실 추정치")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("이어서 물어보기")).not.toBeInTheDocument();
    expect(screen.queryByText("DC형 · ETF 분야 살펴보기")).not.toBeInTheDocument();
    expect(screen.queryByText("IRP · ETF 분야 살펴보기")).not.toBeInTheDocument();
    expect(screen.queryByText("연금저축펀드 · ETF 분야 살펴보기")).not.toBeInTheDocument();
  });

  it("does not refresh hidden session history after a persisted answer", async () => {
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

    await openStoredSession();
    await screen.findByText("저장된 질문");
    const composer = screen.getByLabelText("질문 입력");
    fireEvent.change(composer, { target: { value: "새 질문" } });
    fireEvent.submit(composer.closest("form")!);

    expect(await screen.findByText("저장 답변")).toBeInTheDocument();
    expect(getChatSessions).toHaveBeenCalledOnce();
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
            regime_period: "2025-06-01",
            distance: "0.2500",
            etfs: [{
              isu_code: "069500",
              isu_name: "KODEX 200",
              history_source: "kis_adjusted_close_plus_kind_cash_distribution",
              source: {
                label: "한투 수정주가·KIND 현금분배 반영 원화 총수익지수",
                reference: "https://openapi.koreainvestment.com/",
                as_of: "2026-07-01",
              },
              history_start: "2025-07-01",
              history_end: "2026-07-01",
              horizons: [{
                horizon_months: 3,
                start_date: "2025-07-01",
                end_date: "2025-10-01",
                total_return_percent: "10.0000",
                maximum_drawdown_percent: "25.0000",
              }],
              gaps: [
                { horizon_months: 6, reason: "end_observation_unavailable" },
                { horizon_months: 12, reason: "end_observation_unavailable" },
              ],
            }, {
              isu_code: "snapshot:missing-etf",
              isu_name: "관측값 없는 ETF",
              history_source: "unavailable",
              source: null,
              history_start: null,
              history_end: null,
              horizons: [],
              gaps: [
                { horizon_months: 3, reason: "total_return_history_unavailable" },
                { horizon_months: 6, reason: "total_return_history_unavailable" },
                { horizon_months: 12, reason: "total_return_history_unavailable" },
              ],
            }],
          }, {
            regime_period: "2024-06-01",
            distance: "0.3000",
            etfs: [{
              isu_code: "069500",
              isu_name: "KODEX 200",
              history_source: "kis_adjusted_close_plus_kind_cash_distribution",
              source: {
                label: "한투 수정주가·KIND 현금분배 반영 원화 총수익지수",
                reference: "https://openapi.koreainvestment.com/",
                as_of: "2026-07-01",
              },
              history_start: "2024-07-01",
              history_end: "2026-07-01",
              horizons: [{
                horizon_months: 3,
                start_date: "2024-07-01",
                end_date: "2024-10-01",
                total_return_percent: "8.0000",
                maximum_drawdown_percent: "12.0000",
              }],
              gaps: [
                { horizon_months: 6, reason: "end_observation_unavailable" },
                { horizon_months: 12, reason: "end_observation_unavailable" },
              ],
            }],
          }, {
            regime_period: "2023-12-01",
            distance: "0.4000",
            etfs: [{
              isu_code: "snapshot:missing-regime-etf",
              isu_name: "전체 미관측 유사국면 ETF",
              history_source: "unavailable",
              source: null,
              history_start: null,
              history_end: null,
              horizons: [],
              gaps: [
                { horizon_months: 3, reason: "total_return_history_unavailable" },
                { horizon_months: 6, reason: "total_return_history_unavailable" },
                { horizon_months: 12, reason: "total_return_history_unavailable" },
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
    const outcomeDisclosure = within(outcomeCard).getByText("과거 실적은 필요할 때 확인").closest("details");
    expect(outcomeDisclosure).toHaveAttribute("open");
    expect(within(outcomeCard).getByText("2개 유사국면")).toBeInTheDocument();
    expect(within(outcomeCard).getByText("2025년 7월 시작 구간").closest("details")).toHaveAttribute("open");
    expect(within(outcomeCard).getByText("2024년 7월 시작 구간").closest("details")).toHaveAttribute("open");
    expect(within(outcomeCard).getAllByText("KODEX 200")).toHaveLength(2);
    expect(within(outcomeCard).getByText("10.0000%")).toBeInTheDocument();
    expect(within(outcomeCard).getByText("8.0000%")).toBeInTheDocument();
    expect(within(outcomeCard).getByText("최대낙폭 -25%")).toBeInTheDocument();
    expect(within(outcomeCard).queryByText("관측 부족")).not.toBeInTheDocument();
    expect(within(outcomeCard).queryByText("총수익 이력 없음")).not.toBeInTheDocument();
    expect(within(outcomeCard).queryByText("관측값 없는 ETF")).not.toBeInTheDocument();
    expect(within(outcomeCard).queryByText("2023년 12월 유사국면")).not.toBeInTheDocument();
    expect(within(outcomeCard).queryByText(/snapshot:/)).not.toBeInTheDocument();
    expect(within(outcomeCard).getAllByText(/KIND 현금분배/)).toHaveLength(2);
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
    expect(screen.queryByText(response.numeric_evidence[0].basis)).not.toBeInTheDocument();
    const firstCard = screen.getByText("카드 수치 1").closest(".number-card");
    expect(firstCard?.querySelector("small")).toBeNull();
    expect(within(firstCard as HTMLElement).getByText("1%")).toHaveStyle({
      fontSize: "clamp(16px, 4.5vw, 19px)",
      overflowWrap: "anywhere",
    });
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

  it("shows the concise single-account heading without rendering its validation evidence cards", async () => {
    const response: ChatResponse = {
      ...THEME_RESPONSE,
      intent: "account_rule",
      answer: "개인형 퇴직연금(IRP)의 핵심 특징을 정리했어요.",
      data_mode: "verified_pension_account_brief",
      sections: [{
        kind: "service_explanation",
        title: "개인형 퇴직연금(IRP) 특징",
        content: "이 계좌의 역할과 핵심 특징을 확인해 보세요.",
        evidence_ids: ["rule:pension_overview:law"],
        blocks: [{
          kind: "callout",
          title: "개인형 퇴직연금(IRP)",
          text: [
            "한눈에 보면: 세액공제 한도를 확대하고 퇴직금을 모아 관리하는 개인 퇴직연금",
            "핵심 특징: 원리금보장상품을 편입하고 여러 직장의 퇴직금을 모아 관리할 수 있습니다.",
          ].join("\n\n"),
          items: [],
          headers: [],
          rows: [],
        }],
      }],
      visualizations: [],
      numeric_evidence: [{
        label: "연금계좌 특징 수치 근거 1",
        value: "9000000",
        unit: "KRW",
        evidence_id: "rule:pension_overview:law",
        basis: "검증된 연금계좌 제도 근거",
      }],
      suggested_follow_ups: [
        {
          follow_up_id: "account_to_tax",
          label: "연금 세액공제 계산",
          message: "올해 연금저축에 600만원 넣으면 세액공제 얼마야?",
        },
        {
          follow_up_id: "account_to_edu",
          label: "맞춤형 포트폴리오",
          message: "내 상황에 맞는 연금저축전략을 알려줘.",
        },
      ],
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

    const cardTitle = await screen.findByText("개인형 퇴직연금(IRP)", {
      exact: true,
    });
    const section = cardTitle.closest("details");
    expect(section).toHaveAttribute("open");
    expect(within(section as HTMLElement).getByText("개인형 퇴직연금(IRP) 특징", {
      exact: true,
    })).toBeInTheDocument();
    expect(screen.queryByText(
      "개인형 퇴직연금(IRP) 특징 — 이 계좌의 역할과 핵심 특징을 확인해 보세요.",
      { exact: true },
    )).not.toBeInTheDocument();
    expect(within(section as HTMLElement).getByText(
      "이 계좌의 역할과 핵심 특징을 확인해 보세요.",
      { exact: true },
    )).toBeInTheDocument();
    expect(within(section as HTMLElement).getByText("한눈에 보면:")).toBeInTheDocument();
    expect(within(section as HTMLElement).getByText("핵심 특징:")).toBeInTheDocument();
    expect(screen.queryByText("연금계좌 특징 수치 근거 1")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("수치 근거")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "연금 세액공제 계산" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "맞춤형 포트폴리오" })).not.toBeInTheDocument();
  });

  it("opens pension tax-rule cards without duplicate numeric evidence cards", async () => {
    const cardTitles = [
      "기본 세액공제 대상 한도",
      "ISA 만기자금 이전 특례",
      "소득구간별 세액공제율",
      "정리하면",
    ];
    const response: ChatResponse = {
      ...THEME_RESPONSE,
      intent: "account_rule",
      answer: "매년 연금계좌에 납입한 금액의 일정 비율만큼 소득세를 줄여주는 제도예요.",
      data_mode: "verified_pension_tax_rule_brief",
      sections: [{
        kind: "service_explanation",
        title: "연금계좌 세액공제 혜택",
        content: "납입 한도와 ISA 만기 특례, 소득구간별 공제율을 확인해 보세요.",
        evidence_ids: ["rule:pension_overview:tax_credit"],
        blocks: cardTitles.map((title) => ({
          kind: "callout",
          title,
          text: `${title}에 대한 검증된 설명입니다.`,
          items: [],
          headers: [],
          rows: [],
        })),
      }],
      visualizations: [],
      numeric_evidence: [{
        label: "연금계좌 세액공제 규칙 수치 근거 1",
        value: "9000000",
        unit: "KRW",
        evidence_id: "rule:pension_overview:tax_credit",
        basis: "국세청·소득세법 연금계좌 세액공제 규칙",
      }],
      suggested_follow_ups: [
        {
          follow_up_id: "account_to_tax",
          label: "연금 세액공제 계산",
          message: "올해 연금저축에 600만원 넣으면 세액공제 얼마야?",
        },
        {
          follow_up_id: "account_to_edu",
          label: "맞춤형 포트폴리오",
          message: "내 상황에 맞는 연금저축전략을 알려줘.",
        },
        {
          follow_up_id: "account_to_diff",
          label: "계좌별 차이",
          message: "DC형, IRP, 연금저축은 뭐가 달라?",
        },
      ],
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

    const firstCard = await screen.findByText(cardTitles[0], { exact: true });
    expect(firstCard.closest("details")).toHaveAttribute("open");
    for (const title of cardTitles) {
      expect(screen.getByText(title, { exact: true })).toBeInTheDocument();
    }
    expect(
      screen.queryByText("연금계좌 세액공제 규칙 수치 근거 1"),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("수치 근거")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "계좌별 차이" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "연금 세액공제 계산" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "맞춤형 포트폴리오" })).not.toBeInTheDocument();
  });

  it("shows every authenticated pension-tax answer in the required field order", async () => {
    const primaryLabels = [
      "총급여액",
      "세액공제율",
      "올해 연금저축 납입액",
      "올해 IRP 납입액",
      "세액공제대상 납입액",
      "세액공제액",
    ];
    const response = {
      ...THEME_RESPONSE,
      intent: "pension_tax",
      answer: [
        "김연금님의 올해 연금세액공제 혜택을 정리했어요.",
        "이 문장은 새 구성에서 표시하지 않아요.",
      ].join("\n"),
      data_mode: "authenticated_mock_context_engine",
      pension_tax_result: { tax_credit: {} },
      visualizations: [{
        kind: "tax_summary",
        title: "세액공제 요약",
        description: "",
        data_boundary: "engine",
        evidence_ids: ["engine:pension_tax"],
        items: [
          { label: "세액공제 대상 납입액", value: "8760000", unit: "KRW", role: "value" },
          { label: "세액공제율", value: "13.2", unit: "%", role: "value" },
          { label: "세액공제액", value: "1156320", unit: "KRW", role: "value" },
        ],
        series: [],
      }],
      sections: [{
        kind: "service_explanation",
        title: "당해연도 세액공제 간이 계산",
        content: "답변에서 제거할 기존 저장 섹션",
        evidence_ids: ["engine:pension_tax"],
        blocks: [],
      }],
      numeric_evidence: [
        ...primaryLabels.map((label, index) => ({
          label,
          value: String(index + 1),
          unit: index === 1 ? "%" : "KRW",
          evidence_id: `evidence:${index + 1}`,
          basis: "로그인 사용자 DB 목데이터",
        })),
        {
          label: "확인된 소득구간 법정 세액공제액",
          value: "1051200",
          unit: "KRW",
          evidence_id: "evidence:legal-credit",
          basis: "규칙 엔진",
        },
        {
          label: "확인된 소득구간 법정 세액공제율",
          value: "12",
          unit: "%",
          evidence_id: "evidence:legal-rate",
          basis: "규칙 엔진",
        },
        {
          label: "숨겨진 추가 근거",
          value: "7",
          unit: "KRW",
          evidence_id: "evidence:7",
          basis: "규칙 엔진",
        },
      ],
      limitations: [
        "실제 환급액은 소득세 결정세액 등에 따라 달라질 수 있으므로 자세한 내용은 금융기관에 확인하거나 세무전문가와 상담해야 해요.",
      ],
      suggested_follow_ups: [
        {
          follow_up_id: "tax_withdrawal",
          label: "중도해지 세금",
          message: "연금저축을 중도에 해지하면 세금이 얼마나 나와?",
        },
        {
          follow_up_id: "tax_to_diff",
          label: "계좌별 차이",
          message: "DC형, IRP, 연금저축은 뭐가 달라?",
        },
        {
          follow_up_id: "tax_missed_benefit",
          label: "내가 놓친 혜택",
          message: "내가 놓치고 있는 세액공제혜택을 알려줘",
        },
      ],
    } as unknown as ChatResponse;
    vi.mocked(getChatCards).mockResolvedValue({ cards: [RECOMMENDED_CHAT_CARDS[1]] });
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: true,
      session_id: SESSION_ID,
      response,
    } as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /연금세액공제/ }));

    const lead = await screen.findByText(
      "김연금님의 올해 연금세액공제 혜택을 정리했어요.",
    );
    const summary = screen.getByRole("region", { name: "세액공제 요약" });
    const calculationLead = screen.getByText("세액공제액은 이렇게 계산했어요.");
    const grid = screen.getByLabelText("수치 근거");
    expect(lead.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(summary.compareDocumentPosition(calculationLead) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(calculationLead.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(calculationLead).toHaveStyle({ marginTop: "20px" });
    expect(grid).toHaveStyle({ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" });
    expect(
      Array.from(grid.querySelectorAll(".number-card > span")).map(
        (item) => item.textContent,
      ),
    ).toEqual([
      "총급여액",
      "세액공제율",
      "올해 연금저축 납입액",
      "올해 IRP 납입액",
      "세액공제대상 납입액",
      "세액공제액",
    ]);
    expect(screen.queryByText("숨겨진 추가 근거")).not.toBeInTheDocument();
    expect(screen.queryByText("확인된 소득구간 법정 세액공제액")).not.toBeInTheDocument();
    expect(screen.queryByText("당해연도 세액공제 간이 계산")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "숫자 근거 더보기" })).toBeInTheDocument();
    expect(screen.getByText(
      "세액공제율과 세액공제액은 지방소득세를 고려해서 계산했어요.",
    )).toBeInTheDocument();
    expect(screen.queryByText("이 문장은 새 구성에서 표시하지 않아요.")).not.toBeInTheDocument();
    expect(within(summary).getByText("8,760,000원")).toHaveStyle({
      fontSize: "clamp(13px, 3.4vw, 16px)",
      whiteSpace: "nowrap",
    });
    expect(within(grid).getByText("1원")).toHaveStyle({
      fontSize: "clamp(13px, 3.4vw, 16px)",
      whiteSpace: "nowrap",
    });
    expect(within(grid).getByText("2%")).toHaveStyle({
      fontSize: "clamp(13px, 3.4vw, 16px)",
      whiteSpace: "nowrap",
    });
    expect(screen.getByRole("button", { name: "계좌별 차이" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "내가 놓친 혜택" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "중도해지 세금" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "숫자 근거 더보기" }));
    expect(await screen.findByText("숨겨진 추가 근거")).toBeInTheDocument();
    expect(screen.getByText("지방세 제외 세액공제율")).toBeInTheDocument();
    expect(screen.queryByText("확인된 소득구간 법정 세액공제액")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "내가 놓친 혜택" }));
    await waitFor(() => {
      expect(vi.mocked(sendAuthenticatedChatStream).mock.calls.at(-1)?.[0]).toBe(
        "내가 놓치고 있는 세액공제혜택을 알려줘",
      );
    });
    expect(screen.queryByRole("button", { name: "내가 놓친 혜택" })).not.toBeInTheDocument();
  });

  it("shows the missed-benefit answer without the ordinary tax breakdown", async () => {
    const response = {
      ...THEME_RESPONSE,
      intent: "pension_tax",
      answer: [
        "정민재님은 올해 217,800원 만큼의 세금을 덜 돌려받고 있어요.",
        "",
        "연금저축계좌나 IRP 또는 DC형 계좌에 1,320,000원 만큼을 추가로 납입하세요.",
        "",
        "그러면 정민재님의 최대 세액공제혜택 1,485,000원을 온전히 받을 수 있어요.",
      ].join("\n"),
      data_mode: "missed_pension_tax_credit_engine",
      pension_tax_result: { tax_credit: {} },
      visualizations: [{
        kind: "tax_summary",
        title: "세액공제 요약",
        description: "",
        data_boundary: "engine",
        evidence_ids: ["engine:pension_tax"],
        items: [
          { label: "세액공제 대상 납입액", value: "7680000", unit: "KRW", role: "value" },
        ],
        series: [],
      }],
      numeric_evidence: [{
        label: "추가 납입 가능액",
        value: "1320000",
        unit: "KRW",
        evidence_id: "engine:pension_tax",
        basis: "규칙 엔진",
      }],
      sections: [],
      limitations: [
        "실제 환급액은 소득세 결정세액 등에 따라 달라질 수 있으므로 자세한 내용은 금융기관에 확인하거나 세무전문가와 상담해야 해요.",
      ],
      suggested_follow_ups: [{
        follow_up_id: "tax_to_diff",
        label: "계좌별 차이",
        message: "DC형, IRP, 연금저축은 뭐가 달라?",
      }],
    } as unknown as ChatResponse;
    vi.mocked(getChatCards).mockResolvedValue({ cards: [RECOMMENDED_CHAT_CARDS[1]] });
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: true,
      session_id: SESSION_ID,
      response,
    } as Awaited<ReturnType<typeof sendAuthenticatedChatStream>>);
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /연금세액공제/ }));

    const missedBenefitCopy = await screen.findByText(
      "정민재님은 올해 217,800원 만큼의 세금을 덜 돌려받고 있어요.",
      { exact: false },
    );
    expect(missedBenefitCopy.textContent).toBe(response.answer);
    expect(screen.queryByRole("region", { name: "세액공제 요약" })).not.toBeInTheDocument();
    expect(screen.queryByText("세액공제액은 이렇게 계산했어요.")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("수치 근거")).not.toBeInTheDocument();
    expect(screen.getByText(response.limitations[0])).toBeInTheDocument();
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

  it.each([
    ["glossary", "용어 설명", "deterministic"],
    ["investing_principle", "투자 원리", "claude_verified"],
    ["hesitation_support", "운용 고민", "deterministic"],
    ["getting_started", "시작 안내", "claude_verified"],
  ] as const)(
    "shows the %s response as the beginner-friendly %s badge",
    async (intent, label, narrationMode) => {
      const response: ChatResponse = {
        ...THEME_RESPONSE,
        intent,
        answer: `${label} 답변`,
        narration_mode: narrationMode,
      };
      vi.mocked(getChatCards).mockResolvedValue({ cards: [RECOMMENDED_CHAT_CARDS[0]] });
      vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
        persisted: false,
        session_id: null,
        response,
      });
      renderGuide();

      fireEvent.click(await screen.findByRole("button", { name: /오늘 증시 뉴스/ }));

      expect(await screen.findByText(label)).toHaveClass("intent-pill");
      expect(screen.queryByText("검증 답변")).not.toBeInTheDocument();
      expect(screen.queryByText("AI 서술")).not.toBeInTheDocument();
    },
  );

  it("shows news summary sources with a user-facing label", async () => {
    const response: ChatResponse = {
      ...THEME_RESPONSE,
      intent: "news",
      answer: "기사 요약을 확인했어요.",
      sources: [{
        evidence_id: "news-summary:test",
        label: "연금 시장 기사",
        locator: "https://example.test/news",
        data_boundary: "news_summary",
        publisher: "테스트 일보",
        as_of: "2026-07-26T00:00:00Z",
      }],
    };
    vi.mocked(getChatCards).mockResolvedValue({ cards: [RECOMMENDED_CHAT_CARDS[0]] });
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      persisted: false,
      session_id: null,
      response,
    });
    renderGuide();

    fireEvent.click(await screen.findByRole("button", { name: /오늘 증시 뉴스/ }));
    fireEvent.click(await screen.findByRole("button", { name: "출처 1개" }));

    expect(await screen.findByText("기사 요약 · 2026-07-26")).toBeInTheDocument();
  });

  it("drags ETF theme cards horizontally and keeps card submission", async () => {
    vi.mocked(sendAuthenticatedChatStream).mockResolvedValue({
      response: THEME_RESPONSE,
      persisted: false,
      session_id: null,
    });
    renderGuide();

    expect(await screen.findByRole("heading", {
      name: "연금계좌와 운용 방법을 물어보세요",
    })).toBeInTheDocument();
    const sectorCards = await screen.findByLabelText("ETF 섹터 카드 목록 (옆으로 넘겨 보기)");
    expect(ETF_THEME_CARDS).toHaveLength(21);
    expect(ETF_THEME_CARDS.map((card) => card.number)).toEqual(
      Array.from({ length: 21 }, (_, index) => index + 1),
    );
    expect(ETF_THEME_CARDS.map((card) => card.title)).not.toEqual(
      expect.arrayContaining(["AI·소프트웨어", "코리아밸류업", "ESG"]),
    );
    // 캐러셀: 21개 테마 카드가 모두 렌더되고 옆으로 스크롤(더보기/접기 없음)
    expect(within(sectorCards).getAllByRole("button", {
      name: /ETF 테마 설명 보기$/,
    })).toHaveLength(21);
    expect(within(sectorCards).getByRole("button", {
      name: "반도체 ETF 테마 설명 보기",
    })).toBeInTheDocument();
    expect(within(sectorCards).getByRole("button", {
      name: "자동차·모빌리티 ETF 테마 설명 보기",
    })).toBeInTheDocument();
    expect(within(sectorCards).getByRole("button", {
      name: "채권 ETF 테마 설명 보기",
    })).toBeInTheDocument();
    expect(within(sectorCards).queryByRole("button", {
      name: "나머지 ETF 테마 16개 더보기",
    })).not.toBeInTheDocument();

    Object.defineProperty(sectorCards, "scrollLeft", {
      configurable: true,
      value: 80,
      writable: true,
    });
    Object.assign(sectorCards, {
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn(),
      setPointerCapture: vi.fn(),
    });
    const semiconductorCard = within(sectorCards).getByRole("button", {
      name: "반도체 ETF 테마 설명 보기",
    });

    fireEvent.pointerDown(semiconductorCard, {
      button: 0,
      clientX: 240,
      pointerId: 1,
      pointerType: "mouse",
    });
    fireEvent.pointerMove(sectorCards, {
      clientX: 140,
      pointerId: 1,
      pointerType: "mouse",
    });
    expect(sectorCards).toHaveProperty("scrollLeft", 180);
    expect(sectorCards).toHaveClass("is-dragging");

    fireEvent.pointerUp(sectorCards, {
      clientX: 140,
      pointerId: 1,
      pointerType: "mouse",
    });
    expect(sectorCards).not.toHaveClass("is-dragging");

    fireEvent.click(semiconductorCard);
    await waitFor(() => {
      expect(vi.mocked(sendAuthenticatedChatStream).mock.calls.at(-1)?.[0]).toBe(
        "반도체 테마가 뭐야?",
      );
    });
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

    await openStoredSession();
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

    await openStoredSession();
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

    await openStoredSession();
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

    await openStoredSession();
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

    await openStoredSession();
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

  it("shows account-specific strategy guides without treating them as rebalancing results", async () => {
    const accountStrategyResponse = {
      ...STRUCTURED_PORTFOLIO_RESPONSE,
      sections: ["DC형", "IRP", "연금저축펀드"].map((accountLabel) => ({
        ...STRUCTURED_PORTFOLIO_RESPONSE.sections[0],
        title: `${accountLabel} · 위험중립형 투자전략`,
      })),
    };
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
        content: accountStrategyResponse.answer,
        response: accountStrategyResponse,
        model_name: null,
        created_at: "2026-07-20T00:00:01Z",
        evidence: [],
      },
    ]);
    renderGuide();

    await openStoredSession();
    await screen.findByText(accountStrategyResponse.answer);
    for (const accountLabel of ["DC형", "IRP", "연금저축펀드"]) {
      expect(screen.getByText(`${accountLabel} · 위험중립형 투자전략`)).toBeInTheDocument();
    }
    expect(screen.getAllByText("35년의 장기 운용기간을 고려한 전략이에요. 목표비중을 확인해 보세요.")).toHaveLength(3);
    expect(document.querySelector(".holdings-required-panel")).toBeNull();
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

  it("keeps the planner card out of the chat home", () => {
    const onOpenPlanner = vi.fn();
    renderGuide(undefined, onOpenPlanner);

    expect(screen.queryByRole("button", { name: "연금 수령 계획 시나리오 열기" })).not.toBeInTheDocument();
    expect(screen.queryByText("현재 보유 ETF 리밸런싱 가이드")).not.toBeInTheDocument();
    expect(onOpenPlanner).not.toHaveBeenCalled();
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

