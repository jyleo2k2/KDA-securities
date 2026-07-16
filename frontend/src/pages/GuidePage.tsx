// chatbot-mvp 브랜치의 챗 화면을 연금가이드 탭으로 이식한 것.
// 스타일은 src/index.css의 .app-shell 계열 클래스를 사용한다.
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import {
  ApiError,
  getCapabilities,
  getChatSessions,
  getScenarios,
  getStoredChatMessages,
  sendAuthenticatedChat,
  sendChat,
} from "../api/client";
import type {
  ChatCapabilities,
  ConversationContext,
  ChatResponse,
  ChatSessionSummary,
  DataBoundary,
  IncomeBasis,
  IrpDeferredIncomeStatus,
  PensionTaxScenarioInput,
  ScenarioEvaluation,
  ScenarioSummary,
  StoredChatMessage,
  WithdrawalReason,
} from "../api/types";
import { useSupabaseAuth } from "../auth/useSupabaseAuth";

interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
  failedPrompt?: string;
  createdAt: Date;
}

const SUGGESTED_PROMPTS = [
  "IRP와 연금저축의 위험자산 한도 차이를 알려줘",
  "DC형 방치 시나리오를 진단해줘",
  "내년 예상수익률을 알려줘",
  "연금 뉴스 알려줘",
  "연금저축과 IRP 세액공제 혜택과 중도해지 세금을 알려줘",
];

const INTENT_LABELS: Record<ChatResponse["intent"], string> = {
  account_rule: "계좌 규칙",
  mock_portfolio: "목계좌 진단",
  provider_disclosure: "공식 공시",
  news: "연금 뉴스",
  pension_tax: "세액공제·중도해지",
  out_of_scope: "지원 범위 안내",
};

const BOUNDARY_LABELS: Record<DataBoundary, string> = {
  verified_knowledge: "검증 지식",
  official_disclosure: "공식 공시",
  news_metadata: "뉴스 메타데이터",
  mock: "목데이터",
  engine: "규칙 엔진",
  user_input: "사용자 입력",
  unavailable: "미지원",
};

const PENSION_TAX_PROMPT = /세액\s*공제|중도\s*해지|연금\s*외\s*수령|16\.5\s*%/;

const ASSET_CLASS_LABELS: Record<string, string> = {
  deposit: "원리금보장형 자산",
  cash: "현금성 자산",
  bond: "채권형 자산",
  global_equity: "글로벌 주식형 자산",
  eligible_tdf: "적격 TDF",
};

function numericText(value: string | number, unit: string): string {
  if (unit.toUpperCase() === "KRW") {
    return `${Number(value).toLocaleString("ko-KR")}원`;
  }
  return `${value}${unit}`;
}

function Icon({
  name,
  size = 20,
}: {
  name: "spark" | "send" | "book" | "database" | "chevron" | "shield" | "refresh";
  size?: number;
}) {
  const paths = {
    spark: <path d="M12 2l1.7 4.6L18 8.3l-4.3 1.7L12 14.5 10.3 10 6 8.3l4.3-1.7L12 2Zm6 10 .9 2.2L21 15l-2.1.8L18 18l-.9-2.2L15 15l2.1-.8L18 12ZM6 14l1.2 3.1L10 18.2l-2.8 1.1L6 22l-1.2-2.7L2 18.2l2.8-1.1L6 14Z" />,
    send: <path d="m21 3-7.6 18-4.2-7.1L2 9.7 21 3Zm0 0L9.2 13.9" />,
    book: <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 19.5A2.5 2.5 0 0 0 6.5 22H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14Z" />,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm-3-10 2 2 4-4" />,
    refresh: <path d="M20 11a8.1 8.1 0 1 0 2 5M20 4v7h-7" />,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" width={size} height={size}>{paths[name]}</svg>;
}

function SourceLink({ locator, children }: { locator: string; children: ReactNode }) {
  const isWeb = /^https?:\/\//.test(locator);
  if (!isWeb) return <span>{children}</span>;
  return <a href={locator} target="_blank" rel="noreferrer">{children}</a>;
}

function AssetAllocationChart({ evaluation }: { evaluation: ScenarioEvaluation }) {
  return (
    <section className="allocation-chart" aria-label="전체 자산 구성 그래프">
      <h3>전체 자산 구성</h3>
      {evaluation.asset_allocations.map((item) => {
        const percent = Number(item.allocation_percent);
        return (
          <div className="allocation-row" key={item.asset_class_code}>
            <div>
              <span>{ASSET_CLASS_LABELS[item.asset_class_code] ?? "기타 자산"}</span>
              <strong>{percent}%</strong>
            </div>
            <div className="allocation-track" role="img" aria-label={`${ASSET_CLASS_LABELS[item.asset_class_code] ?? "기타 자산"} ${percent}%`}>
              <span style={{ width: `${percent}%` }} />
            </div>
          </div>
        );
      })}
    </section>
  );
}

function AssistantMessage({ response, text }: { response?: ChatResponse; text: string }) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  if (!response) return <p className="message-copy">{text}</p>;

  return (
    <div className="answer-content">
      <div className="answer-meta">
        <span className={`intent-pill intent-${response.intent}`}>{INTENT_LABELS[response.intent]}</span>
        <span>{response.narration_mode === "deterministic" ? "검증 답변" : "AI 서술"}</span>
      </div>
      <p className="message-copy">{response.answer}</p>

      {response.scenario_evaluation && (
        <AssetAllocationChart evaluation={response.scenario_evaluation} />
      )}

      {response.narration_reasoning && (
        <details className="answer-section section-service_explanation">
          <summary><span>AI가 검토한 과정</span><small>내용 보기</small></summary>
          <p>{response.narration_reasoning}</p>
        </details>
      )}

      {response.sections.map((section, index) => (
        <details className={`answer-section section-${section.kind}`} key={`${section.title}-${index}`} open={section.kind === "limitation"}>
          <summary><span>{section.title}</span><small>내용 보기</small></summary>
          <p>{section.content}</p>
        </details>
      ))}

      {response.intent !== "mock_portfolio" && response.numeric_evidence.length > 0 && (
        <div className="number-grid" aria-label="수치 근거">
          {response.numeric_evidence.map((item, index) => (
            <div className="number-card" key={`${item.evidence_id}-${index}`}>
              <span>{item.label}</span>
              <strong>{numericText(item.value, item.unit)}</strong>
              <small>{item.basis}</small>
            </div>
          ))}
        </div>
      )}

      {response.limitations.length > 0 && (
        <div className="limitation-box">
          <Icon name="shield" size={18} />
          <div>
            <strong>확인할 점</strong>
            {response.limitations.map((item, index) => <p key={index}>{item}</p>)}
          </div>
        </div>
      )}

      {response.sources.length > 0 && (
        <div className="evidence-wrap">
          <button className="evidence-toggle" type="button" onClick={() => setDetailsOpen((value) => !value)} aria-expanded={detailsOpen}>
            <span><Icon name="book" size={17} /> 출처 {response.sources.length}개</span>
            <Icon name="chevron" size={16} />
          </button>
          {detailsOpen && (
            <div className="source-list">
              {response.sources.map((source) => (
                <SourceLink locator={source.locator} key={source.evidence_id}>
                  <span className="source-item">
                    <span className={`boundary-dot boundary-${source.data_boundary}`} />
                    <span className="source-text">
                      <strong>{source.label}</strong>
                      <small>{BOUNDARY_LABELS[source.data_boundary]}{source.as_of ? ` · ${source.as_of.slice(0, 10)}` : ""}</small>
                    </span>
                    <Icon name="chevron" size={15} />
                  </span>
                </SourceLink>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function authenticatedErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "로그인이 만료되었습니다. 다시 로그인해 주세요.";
  }
  if (error instanceof ApiError && error.status === 503) {
    return "대화 저장소에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  }
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
}

export function GuidePage() {
  const auth = useSupabaseAuth();
  const accessToken = auth.session?.access_token;
  const authenticatedUserId = auth.session?.user.id ?? null;
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState("");
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [capabilities, setCapabilities] = useState<ChatCapabilities | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [serverReady, setServerReady] = useState<boolean | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [conversationContext, setConversationContext] =
    useState<ConversationContext | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [loginPanelOpen, setLoginPanelOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pensionSavingsBalance, setPensionSavingsBalance] = useState("");
  const [irpBalance, setIrpBalance] = useState("");
  const [pensionSavingsContribution, setPensionSavingsContribution] = useState("0");
  const [irpContribution, setIrpContribution] = useState("0");
  const [incomeBasis, setIncomeBasis] = useState<IncomeBasis>("unknown");
  const [incomeAmount, setIncomeAmount] = useState("");
  const [withdrawalReason, setWithdrawalReason] = useState<WithdrawalReason>("general");
  const [irpDeferredStatus, setIrpDeferredStatus] = useState<IrpDeferredIncomeStatus>("unknown");
  const [irpDeferredAmount, setIrpDeferredAmount] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const latestMessageRef = useRef<HTMLDivElement>(null);
  const previousAuthRef = useRef<{
    userId: string | null;
    accessToken: string | null;
  }>({ userId: null, accessToken: null });
  const currentAuthRef = useRef<{
    userId: string | null;
    accessToken: string | null;
  }>({ userId: authenticatedUserId, accessToken: accessToken ?? null });
  const authGenerationRef = useRef(0);
  const conversationGenerationRef = useRef(0);
  const sendingRef = useRef(false);

  currentAuthRef.current = {
    userId: authenticatedUserId,
    accessToken: accessToken ?? null,
  };

  function isCurrentOperation(
    authGeneration: number,
    userId: string | null,
    token: string | null,
    conversationGeneration?: number,
  ) {
    const currentAuth = currentAuthRef.current;
    return (
      authGenerationRef.current === authGeneration
      && currentAuth.userId === userId
      && currentAuth.accessToken === token
      && (
        conversationGeneration === undefined
        || conversationGenerationRef.current === conversationGeneration
      )
    );
  }

  const selectedScenarioData = useMemo(
    () => scenarios.find((scenario) => scenario.code === selectedScenario),
    [scenarios, selectedScenario],
  );

  const pensionTaxInput = useMemo<PensionTaxScenarioInput | undefined>(() => {
    if (!pensionSavingsBalance.trim() || !irpBalance.trim()) return undefined;
    if (incomeBasis !== "unknown" && !incomeAmount.trim()) return undefined;
    if (irpDeferredStatus === "known" && !irpDeferredAmount.trim()) return undefined;
    return {
      tax_year: 2026,
      income_basis: incomeBasis,
      ...(incomeBasis !== "unknown" ? { income_amount_krw: incomeAmount } : {}),
      pension_savings: {
        balance_krw: pensionSavingsBalance,
        current_year_contribution_krw: pensionSavingsContribution || "0",
      },
      irp: {
        balance_krw: irpBalance,
        current_year_contribution_krw: irpContribution || "0",
      },
      withdrawal_reason: withdrawalReason,
      irp_deferred_income_status: irpDeferredStatus,
      ...(irpDeferredStatus === "known"
        ? { irp_deferred_retirement_income_krw: irpDeferredAmount }
        : {}),
    };
  }, [
    incomeAmount,
    incomeBasis,
    irpBalance,
    irpContribution,
    irpDeferredAmount,
    irpDeferredStatus,
    pensionSavingsBalance,
    pensionSavingsContribution,
    withdrawalReason,
  ]);

  useEffect(() => {
    Promise.all([getScenarios(), getCapabilities()])
      .then(([scenarioData, capabilityData]) => {
        setScenarios(scenarioData);
        setCapabilities(capabilityData);
        setServerReady(true);
      })
      .catch(() => setServerReady(false));
  }, []);

  useEffect(() => {
    const previousAuth = previousAuthRef.current;
    const userChanged = previousAuth.userId !== authenticatedUserId;
    const authChanged = (
      userChanged || previousAuth.accessToken !== (accessToken ?? null)
    );
    previousAuthRef.current = {
      userId: authenticatedUserId,
      accessToken: accessToken ?? null,
    };
    if (authChanged) {
      authGenerationRef.current += 1;
      sendingRef.current = false;
      setIsSending(false);
      setHistoryLoading(false);
    }
    if (userChanged) {
      conversationGenerationRef.current += 1;
      setMessages([]);
      setActiveSessionId(null);
      setConversationContext(null);
      setSelectedScenario("");
    }
    if (!accessToken) {
      setChatSessions([]);
      setHistoryError(null);
      setHistoryLoading(false);
      return;
    }

    let active = true;
    setHistoryLoading(true);
    setHistoryError(null);
    void getChatSessions(accessToken)
      .then((sessions) => {
        if (active) setChatSessions(sessions);
      })
      .catch((error: unknown) => {
        if (active) setHistoryError(authenticatedErrorMessage(error));
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [accessToken, authenticatedUserId]);

  useEffect(() => {
    if (messages.length > 0) {
      latestMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (isSending) {
      conversationEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isSending]);

  async function refreshChatSessions(token: string, userId: string) {
    const authGeneration = authGenerationRef.current;
    try {
      const sessions = await getChatSessions(token);
      if (!isCurrentOperation(authGeneration, userId, token)) return;
      setChatSessions(sessions);
      setHistoryError(null);
    } catch (error) {
      if (!isCurrentOperation(authGeneration, userId, token)) return;
      setHistoryError(authenticatedErrorMessage(error));
    }
  }

  function startNewChat() {
    conversationGenerationRef.current += 1;
    sendingRef.current = false;
    setMessages([]);
    setActiveSessionId(null);
    setConversationContext(null);
    setHistoryError(null);
    setHistoryLoading(false);
    setIsSending(false);
    setIsSidebarOpen(false);
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password || authSubmitting) return;
    setAuthSubmitting(true);
    setHistoryError(null);
    try {
      await auth.signIn(email, password);
      setPassword("");
      setLoginPanelOpen(false);
    } catch (error) {
      setHistoryError(authenticatedErrorMessage(error));
    } finally {
      setAuthSubmitting(false);
    }
  }

  async function handleLogout() {
    if (authSubmitting) return;
    authGenerationRef.current += 1;
    conversationGenerationRef.current += 1;
    sendingRef.current = false;
    setAuthSubmitting(true);
      setMessages([]);
      setChatSessions([]);
      setActiveSessionId(null);
      setConversationContext(null);
    setHistoryError(null);
    setHistoryLoading(false);
    setIsSending(false);
    try {
      await auth.signOut();
    } catch (error) {
      setHistoryError(authenticatedErrorMessage(error));
    } finally {
      setAuthSubmitting(false);
    }
  }

  async function loadStoredSession(sessionId: string) {
    if (!accessToken || !authenticatedUserId || historyLoading) return;
    const requestToken = accessToken;
    const requestUserId = authenticatedUserId;
    const authGeneration = authGenerationRef.current;
    const conversationGeneration = ++conversationGenerationRef.current;
    sendingRef.current = false;
    setIsSending(false);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const stored = await getStoredChatMessages(sessionId, requestToken);
      if (!isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) return;
      const restored = stored
        .filter(
          (message): message is StoredChatMessage & {
            role: "user" | "assistant";
          } => message.role === "user" || message.role === "assistant",
        )
        .map<ConversationMessage>((message) => ({
          id: message.message_id,
          role: message.role,
          text: message.content,
          response: message.response ?? undefined,
          createdAt: new Date(message.created_at),
        }));
      setMessages(restored);
      setActiveSessionId(sessionId);
      const lastContext = [...restored]
        .reverse()
        .find((message) => message.response?.conversation_context)
        ?.response?.conversation_context;
      setConversationContext(lastContext ?? null);
      setSelectedScenario("");
      setIsSidebarOpen(false);
    } catch (error) {
      if (!isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) return;
      setHistoryError(authenticatedErrorMessage(error));
    } finally {
      if (isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) setHistoryLoading(false);
    }
  }

  async function submitPrompt(prompt: string) {
    const normalized = prompt.trim();
    if (normalized.length < 2 || sendingRef.current) return;

    const requestToken = accessToken ?? null;
    const requestUserId = authenticatedUserId;
    const authGeneration = authGenerationRef.current;
    const conversationGeneration = ++conversationGenerationRef.current;
    sendingRef.current = true;
    setHistoryLoading(false);

    const userMessage: ConversationMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: normalized,
      createdAt: new Date(),
    };
    const idempotencyKey = crypto.randomUUID();
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsSending(true);

    const taxInput = PENSION_TAX_PROMPT.test(normalized)
      ? pensionTaxInput
      : undefined;

    try {
      const persisted = requestToken
        ? await sendAuthenticatedChat(
            normalized,
            requestToken,
            selectedScenario || undefined,
            activeSessionId || undefined,
            idempotencyKey,
            conversationContext,
            taxInput,
          )
        : null;
      const response = persisted
        ? persisted.response
        : await sendChat(normalized, {
            scenarioCode: selectedScenario || undefined,
            conversationContext,
            pensionTax: taxInput,
          });
      if (!isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) return;
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: response.answer,
        response,
        createdAt: new Date(),
      }]);
      setConversationContext(
        response.conversation_context ?? conversationContext,
      );
      if (persisted?.persisted && persisted.session_id) {
        setActiveSessionId(persisted.session_id);
        void refreshChatSessions(requestToken!, requestUserId!);
      }
      setServerReady(true);
    } catch (error) {
      if (!isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) return;
      const message = requestToken
        ? authenticatedErrorMessage(error)
        : error instanceof Error
          ? error.message
          : "서버 연결을 확인해 주세요.";
      if (requestToken) setHistoryError(message);
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: message,
        failedPrompt: normalized,
        createdAt: new Date(),
      }]);
      setServerReady(
        error instanceof ApiError && error.status !== 503,
      );
    } finally {
      if (isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) {
        sendingRef.current = false;
        setIsSending(false);
        textareaRef.current?.focus();
      }
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    void submitPrompt(input);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submitPrompt(input);
    }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${isSidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Icon name="spark" size={22} /></div>
          <div><strong>연금 코파일럿</strong><span>Pension guide</span></div>
        </div>

        <button className="new-chat" type="button" onClick={startNewChat}>
          <span>＋</span> 새 대화
        </button>

        <div className="auth-panel">
          {auth.loading ? (
            <p className="auth-note">로그인 상태 확인 중...</p>
          ) : auth.session ? (
            <>
              <div className="auth-user">
                <span><strong>대화 저장 중</strong><small>{auth.session.user.email ?? "인증 사용자"}</small></span>
                <button type="button" onClick={() => void handleLogout()} disabled={authSubmitting}>로그아웃</button>
              </div>
              <p className="sidebar-label history-label">저장된 대화</p>
              <div className="history-list">
                {historyLoading && chatSessions.length === 0 ? (
                  <p className="auth-note">대화 이력을 불러오는 중...</p>
                ) : chatSessions.length === 0 ? (
                  <p className="auth-note">아직 저장된 대화가 없습니다.</p>
                ) : chatSessions.map((session) => (
                  <button
                    className={activeSessionId === session.session_id ? "active" : ""}
                    type="button"
                    key={session.session_id}
                    onClick={() => void loadStoredSession(session.session_id)}
                    disabled={historyLoading}
                  >
                    <strong>{session.title || "새 대화"}</strong>
                    <small>{new Date(session.updated_at).toLocaleDateString("ko-KR", { month: "short", day: "numeric" })}</small>
                  </button>
                ))}
              </div>
            </>
          ) : auth.configured ? (
            <>
              <button className="login-toggle" type="button" onClick={() => setLoginPanelOpen((open) => !open)}>
                로그인하고 대화 저장
              </button>
              {loginPanelOpen && (
                <form className="login-form" onSubmit={handleLogin}>
                  <label>
                    <span>이메일</span>
                    <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
                  </label>
                  <label>
                    <span>비밀번호</span>
                    <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
                  </label>
                  <button type="submit" disabled={authSubmitting || !email.trim() || !password}>
                    {authSubmitting ? "로그인 중..." : "로그인"}
                  </button>
                </form>
              )}
            </>
          ) : (
            <p className="auth-note">Supabase 공개 키를 설정하면 로그인과 대화 저장을 사용할 수 있습니다.</p>
          )}
          {(historyError || auth.error) && <p className="auth-error">{historyError || auth.error}</p>}
        </div>

        <div className="sidebar-section">
          <p className="sidebar-label">목계좌 시나리오</p>
          <div className="scenario-list">
            <button className={!selectedScenario ? "active" : ""} type="button" onClick={() => setSelectedScenario("")}>
              <span className="scenario-icon"><Icon name="book" size={17} /></span>
              <span><strong>선택 안 함</strong><small>일반 제도 질문</small></span>
            </button>
            {scenarios.map((scenario) => (
              <button className={selectedScenario === scenario.code ? "active" : ""} type="button" key={scenario.code} onClick={() => { setSelectedScenario(scenario.code); setIsSidebarOpen(false); }}>
                <span className="scenario-icon"><Icon name="database" size={17} /></span>
                <span><strong>{scenario.name}</strong><small>{scenario.age_band} · {scenario.investment_horizon_years}년 · {scenario.risk_profile}</small></span>
              </button>
            ))}
          </div>
        </div>

        <details className="tax-input-panel">
          <summary>세액공제·중도해지 선택 입력</summary>
          <div className="tax-input-fields">
            <label>
              <span>연금저축 잔액</span>
              <input type="number" min="0" inputMode="numeric" value={pensionSavingsBalance} onChange={(event) => setPensionSavingsBalance(event.target.value)} placeholder="예: 30000000" />
            </label>
            <label>
              <span>IRP 잔액</span>
              <input type="number" min="0" inputMode="numeric" value={irpBalance} onChange={(event) => setIrpBalance(event.target.value)} placeholder="예: 50000000" />
            </label>
            <label>
              <span>올해 연금저축 납입액</span>
              <input type="number" min="0" inputMode="numeric" value={pensionSavingsContribution} onChange={(event) => setPensionSavingsContribution(event.target.value)} />
            </label>
            <label>
              <span>올해 IRP 납입액</span>
              <input type="number" min="0" inputMode="numeric" value={irpContribution} onChange={(event) => setIrpContribution(event.target.value)} />
            </label>
            <label>
              <span>세액공제 소득 기준</span>
              <select value={incomeBasis} onChange={(event) => setIncomeBasis(event.target.value as IncomeBasis)}>
                <option value="unknown">모름</option>
                <option value="gross_salary">근로소득 총급여</option>
                <option value="comprehensive_income">종합소득금액</option>
              </select>
            </label>
            {incomeBasis !== "unknown" && (
              <label>
                <span>소득 기준 금액</span>
                <input type="number" min="0" inputMode="numeric" value={incomeAmount} onChange={(event) => setIncomeAmount(event.target.value)} />
              </label>
            )}
            <label>
              <span>인출 사유</span>
              <select value={withdrawalReason} onChange={(event) => setWithdrawalReason(event.target.value as WithdrawalReason)}>
                <option value="general">일반 중도해지</option>
                <option value="unavoidable">의료 등 부득이한 사유</option>
                <option value="unknown">모름</option>
              </select>
            </label>
            <label>
              <span>IRP 퇴직금 이전분</span>
              <select value={irpDeferredStatus} onChange={(event) => setIrpDeferredStatus(event.target.value as IrpDeferredIncomeStatus)}>
                <option value="unknown">모름</option>
                <option value="none">없음</option>
                <option value="known">금액을 알고 있음</option>
              </select>
            </label>
            {irpDeferredStatus === "known" && (
              <label>
                <span>IRP 퇴직금 이전분 금액</span>
                <input type="number" min="0" inputMode="numeric" value={irpDeferredAmount} onChange={(event) => setIrpDeferredAmount(event.target.value)} />
              </label>
            )}
            <p className={pensionTaxInput ? "tax-input-ready" : "auth-note"}>
              {pensionTaxInput
                ? "입력값이 준비됐습니다. 질문에 금액을 함께 적으면 최신 질문의 값이 우선됩니다."
                : "금액과 사유를 질문에 직접 적어도 자동 인식합니다. 필요할 때만 이 패널을 사용하고 계좌번호·인증정보는 입력하지 마세요."}
            </p>
          </div>
        </details>

        <div className="sidebar-footer">
          <div className="connection-status">
            <span className={`status-dot ${serverReady === false ? "offline" : ""}`} />
            <span>{serverReady === null ? "서버 확인 중" : serverReady ? (auth.session ? "저장 API 연결됨" : "데모 API 연결됨") : "API 연결 필요"}</span>
          </div>
          <p>실제 주문을 실행하지 않는<br />자문·정보 제공형 데모입니다.</p>
        </div>
      </aside>

      {isSidebarOpen && <button className="sidebar-backdrop" type="button" aria-label="메뉴 닫기" onClick={() => setIsSidebarOpen(false)} />}

      <main className="chat-main">
        <header className="topbar">
          <button className="menu-button" type="button" aria-label="메뉴 열기" onClick={() => setIsSidebarOpen(true)}><span /><span /><span /></button>
          <div className="topbar-title">
            <strong>연금가이드</strong>
            <span>{selectedScenarioData ? `${selectedScenarioData.name} · 목데이터` : "검증된 근거로 답변해요"}</span>
          </div>
          <div className="trust-label"><Icon name="shield" size={16} /> 근거 검증</div>
        </header>

        <div className="conversation" aria-live="polite">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-icon"><Icon name="spark" size={30} /></div>
              <p className="eyebrow">PENSION COPILOT</p>
              <h1>연금계좌, 무엇이든<br />쉽게 물어보세요.</h1>
              <p className="welcome-copy">DC형·IRP·연금저축의 차이부터 목계좌 진단까지,<br className="desktop-break" /> 규칙 엔진과 확인된 출처를 바탕으로 설명해 드려요.</p>

              {selectedScenarioData && (
                <div className="selected-scenario-card">
                  <div><Icon name="database" size={19} /></div>
                  <span><strong>{selectedScenarioData.name}</strong><small>{selectedScenarioData.description}</small></span>
                </div>
              )}

              <div className="prompt-grid">
                {SUGGESTED_PROMPTS.map((prompt, index) => (
                  <button type="button" key={prompt} onClick={() => void submitPrompt(prompt)}>
                    <span className={`prompt-number prompt-${index + 1}`}>0{index + 1}</span>
                    <span>{prompt}</span>
                    <Icon name="chevron" size={17} />
                  </button>
                ))}
              </div>

              {capabilities && <p className="capability-note">현재 {capabilities.supported.length}가지 질문 유형 지원 · 실데이터 기능은 연결 상태에 따라 달라집니다.</p>}
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message) => (
                <div
                  className={`message-row ${message.role}`}
                  key={message.id}
                  ref={message.id === messages[messages.length - 1]?.id ? latestMessageRef : undefined}
                >
                  {message.role === "assistant" && <div className="assistant-avatar"><Icon name="spark" size={16} /></div>}
                  <div className="message-group">
                    <div className="message-bubble">
                      <AssistantMessage response={message.response} text={message.text} />
                    </div>
                    {message.failedPrompt && (
                      <button className="retry-button" type="button" onClick={() => void submitPrompt(message.failedPrompt!)} disabled={isSending}>
                        <Icon name="refresh" size={15} /> 다시 시도
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {isSending && (
                <div className="message-row assistant">
                  <div className="assistant-avatar"><Icon name="spark" size={16} /></div>
                  <div className="message-bubble typing" aria-label="답변 작성 중"><span /><span /><span /></div>
                </div>
              )}
              <div ref={conversationEndRef} />
            </div>
          )}
        </div>

        <div className="composer-wrap">
          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(event) => setInput(event.target.value.slice(0, 1000))}
              onKeyDown={handleKeyDown}
              placeholder="연금계좌에 대해 질문해 보세요"
              rows={1}
              aria-label="질문 입력"
              disabled={isSending}
            />
            <button type="submit" disabled={input.trim().length < 2 || isSending} aria-label="질문 보내기"><Icon name="send" size={20} /></button>
          </form>
          <p>AI 답변은 투자 판단을 돕는 정보이며, 미래 수익을 보장하지 않습니다.</p>
        </div>
      </main>
    </div>
  );
}
