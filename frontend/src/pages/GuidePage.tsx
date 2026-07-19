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
  deleteChatSession,
  getCapabilities,
  getChatSessions,
  getMyPensionContext,
  getScenarios,
  getStoredChatMessages,
  sendAuthenticatedChatStream,
  sendChatStream,
} from "../api/client";
import type {
  AnswerBlock,
  ChatCapabilities,
  CompletedSurveyProfile,
  ConversationContext,
  ChatResponse,
  ChatSessionSummary,
  ChatVisualization,
  DataBoundary,
  DemoUserFinancialContext,
  IncomeBasis,
  IrpDeferredIncomeStatus,
  PensionTaxScenarioInput,
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
  {
    category: "든든한 노후 설계",
    prompt: "내 나이에 맞는 연금 저축 전략을 알려줘.",
    icon: "sun" as const,
  },
  {
    category: "한눈에 보는 자산",
    prompt: "내 IRP·연금저축 수익률을 진단해 줄래?",
    icon: "chart" as const,
  },
  {
    category: "놓치기 쉬운 혜택",
    prompt: "올해 받을 수 있는 연금 세액공제가 궁금해.",
    icon: "star" as const,
  },
  {
    category: "ETF 테마 이해",
    prompt: "2번 반도체 ETF 테마를 쉽게 설명해 줘.",
    icon: "chart" as const,
  },
];

const INTENT_LABELS: Record<ChatResponse["intent"], string> = {
  account_rule: "계좌 규칙",
  mock_portfolio: "목계좌 진단",
  provider_disclosure: "공식 공시",
  news: "증시 뉴스",
  pension_tax: "세액공제·중도해지",
  etf_theme: "ETF 테마",
  educational_portfolio: "연금 운용전략",
  out_of_scope: "지원 범위 안내",
};

const BOUNDARY_LABELS: Record<DataBoundary, string> = {
  verified_knowledge: "검증 지식",
  official_disclosure: "공식 공시",
  news_metadata: "뉴스 메타데이터",
  news_summary: "뉴스 3줄 요약",
  mock: "목데이터",
  engine: "규칙 엔진",
  user_input: "사용자 입력",
  unavailable: "미지원",
};

const PENSION_TAX_PROMPT = /세액\s*공제|중도\s*해지|연금\s*외\s*수령|16\.5\s*%/;

function numericText(value: string | number, unit: string): string {
  if (unit.toUpperCase() === "KRW") {
    return `${Number(value).toLocaleString("ko-KR")}원`;
  }
  return `${value}${unit}`;
}

function displayText(value: string): string {
  return value.replace(/\*\*/g, "").replace(/\s+\/\s+/g, " ");
}

function newsDate(value?: string | null): string | null {
  return value ? new Date(value).toLocaleDateString("ko-KR") : null;
}

function Icon({
  name,
  size = 20,
}: {
  name: "spark" | "send" | "book" | "database" | "chevron" | "shield" | "refresh" | "sun" | "chart" | "star" | "trash";
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
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" /></>,
    chart: <><path d="M4 20V4M4 20h16" /><path d="m8 15 3-4 3 2 5-6" /></>,
    star: <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z" />,
    trash: <><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" width={size} height={size}>{paths[name]}</svg>;
}

function SourceLink({ locator, children }: { locator: string; children: ReactNode }) {
  const isWeb = /^https?:\/\//.test(locator);
  if (!isWeb) return <span>{children}</span>;
  return <a href={locator} target="_blank" rel="noreferrer">{children}</a>;
}

function VisualizationCard({ visualization }: { visualization: ChatVisualization }) {
  if (visualization.kind === "tax_summary") {
    return (
      <section className="allocation-chart tax-visualization" aria-label={visualization.title}>
        <h3>{visualization.title}</h3>
        <p className="visualization-description">{visualization.description}</p>
        <div className="tax-summary-grid">
          {visualization.items.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <strong>{numericText(item.value, item.unit)}</strong>
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (visualization.kind === "risk_cap") {
    const current = visualization.items.find((item) => item.role === "current");
    const limit = visualization.items.find((item) => item.role === "limit");
    const displayed = current ?? limit;
    const percent = Math.min(Number(displayed?.value ?? 0), 100);
    const summary = current && limit
      ? `${numericText(current.value, current.unit)} / 기준 ${numericText(limit.value, limit.unit)}`
      : `최대 ${numericText(limit?.value ?? 0, limit?.unit ?? "%")}`;

    return (
      <section className="allocation-chart" aria-label={visualization.title}>
        <h3>{visualization.title}</h3>
        <p className="visualization-description">{visualization.description}</p>
        <div className="allocation-row">
          <div><span>위험자산</span><strong>{summary}</strong></div>
          <div className="allocation-track" role="img" aria-label={`위험자산 ${summary}`}>
            <span style={{ width: `${percent}%` }} />
          </div>
        </div>
      </section>
    );
  }

  const colors = ["#4f8a70", "#84ad67", "#d8a45e", "#7183b1", "#bf7d70"];
  let start = 0;
  const gradientStops = visualization.items.map((item, index) => {
    const end = start + Number(item.value);
    const color = colors[index % colors.length];
    const stop = `${color} ${start}% ${end}%`;
    start = end;
    return stop;
  });

  return (
    <section className="allocation-chart" aria-label={visualization.title}>
      <h3>{visualization.title}</h3>
      <p className="visualization-description">{visualization.description}</p>
      <div className="allocation-pie-layout">
        <div
          aria-label={visualization.items.map((item) => `${item.label} ${item.value}%`).join(", ")}
          className="allocation-donut"
          role="img"
          style={{ background: `conic-gradient(${gradientStops.join(", ")})` }}
        >
          <span>전체<br /><strong>100%</strong></span>
        </div>
        <ul className="allocation-legend">
          {visualization.items.map((item, index) => (
            <li key={item.label}>
              <i style={{ backgroundColor: colors[index % colors.length] }} />
              <span>{item.label}</span>
              <strong>{item.value}%</strong>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function NewsCards({ response }: { response: ChatResponse }) {
  const items = response.news_items ?? [];
  const ordinals = ["첫 번째", "두 번째", "세 번째"];
  if (items.length === 0) return null;

  return (
    <section className="news-card-list" aria-label="뉴스 목록">
      {items.map((item, index) => (
        <a
          className="news-card"
          href={item.original_url}
          key={item.evidence_id}
          rel="noreferrer"
          target="_blank"
        >
          <div className="news-card-meta">
            <span>
              {item.summary_lines?.length === 3
                ? `${ordinals[index] ?? `${index + 1}번째`} 뉴스 · 3줄 요약`
                : "뉴스 메타데이터"}
            </span>
            {(item.publisher || newsDate(item.published_at)) && (
              <span>
                {item.publisher && `${displayText(item.publisher)} · `}
                {newsDate(item.published_at) && <time>{newsDate(item.published_at)}</time>}
              </span>
            )}
          </div>
          <strong>{displayText(item.title)}</strong>
          {item.summary_lines?.length === 3 ? (
            <ol className="news-card-summary">
              {item.summary_lines.map((line, lineIndex) => (
                <li key={`${item.evidence_id}-summary-${lineIndex}`}>
                  {displayText(line)}
                </li>
              ))}
            </ol>
          ) : (
            item.description && <p>{displayText(item.description)}</p>
          )}
          <small>원문 보기 <Icon name="chevron" size={13} /></small>
        </a>
      ))}
    </section>
  );
}

function AnswerBlocks({ blocks }: { blocks: AnswerBlock[] }) {
  return (
    <div className="answer-blocks">
      {blocks.map((block, index) => {
        const key = `${block.kind}-${index}`;
        if (block.kind === "callout") {
          return (
            <div className="answer-callout" key={key}>
              {block.title && <strong>{displayText(block.title)}</strong>}
              <p>{displayText(block.text ?? "")}</p>
            </div>
          );
        }
        if (block.kind === "paragraph") {
          return <p key={key}>{displayText(block.text ?? "")}</p>;
        }
        if (block.kind === "bullets") {
          return (
            <div key={key}>
              {block.title && <strong>{displayText(block.title)}</strong>}
              <ul className="answer-bullets">
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{displayText(item)}</li>
                ))}
              </ul>
            </div>
          );
        }
        if (block.kind === "formula") {
          return (
            <div className="answer-formula" key={key}>
              {block.title && <strong>{displayText(block.title)}</strong>}
              <pre>{displayText(block.text ?? "")}</pre>
            </div>
          );
        }
        return (
          <div className="answer-table-wrap" key={key}>
            {block.title && <strong className="answer-table-title">{displayText(block.title)}</strong>}
            <table>
              <thead>
                <tr>
                  {block.headers.map((header, headerIndex) => (
                    <th key={`${key}-header-${headerIndex}`}>{displayText(header)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr key={`${key}-row-${rowIndex}`}>
                    {row.map((cell, cellIndex) => (
                      <td key={`${key}-cell-${rowIndex}-${cellIndex}`}>{displayText(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
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
      {(response.data_mode !== "news_summary" || response.news_items.length === 0) && (
        <p className="message-copy">
          {response.salutation && <><strong>{response.salutation},</strong>{" "}</>}
          {displayText(response.answer)}
        </p>
      )}

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

      <NewsCards response={response} />

      {response.visualizations.map((visualization, index) => (
        <VisualizationCard
          visualization={visualization}
          key={`${visualization.kind}-${index}`}
        />
      ))}

      {/* narration_reasoning은 thinking 요약이라 대부분 영어로 나와 화면에 노출하지 않는다.
          응답 필드는 그대로 유지해 디버깅·로그에서 확인한다. */}

      {response.sections.map((section, index) => (
        <details className={`answer-section section-${section.kind}${section.blocks?.length ? " rich-answer-section" : ""}`} key={`${section.title}-${index}`} open={response.intent === "educational_portfolio" || response.data_mode === "verified_pension_account_overview" || response.data_mode === "verified_pension_account_deferred_topic" || section.kind === "limitation"}>
          <summary><span>{section.title}</span><small>내용 보기</small></summary>
          {section.blocks?.length ? (
            <>
              {section.content && <p>{displayText(section.content)}</p>}
              <AnswerBlocks blocks={section.blocks} />
            </>
          ) : (
            <p>{displayText(section.content)}</p>
          )}
        </details>
      ))}

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

export function GuidePage({
  surveyProfile,
}: {
  surveyProfile: CompletedSurveyProfile | null;
}) {
  const auth = useSupabaseAuth();
  const accessToken = auth.session?.access_token;
  const authenticatedUserId = auth.session?.user.id ?? null;
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState("");
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [userContext, setUserContext] =
    useState<DemoUserFinancialContext | null>(null);
  const [capabilities, setCapabilities] = useState<ChatCapabilities | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [sendingStage, setSendingStage] = useState("답변을 준비하고 있습니다.");
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [serverReady, setServerReady] = useState<boolean | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [conversationContext, setConversationContext] =
    useState<ConversationContext | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [deleteToast, setDeleteToast] = useState<string | null>(null);
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

  useEffect(() => {
    if (!deleteToast) return;
    const timer = window.setTimeout(() => setDeleteToast(null), 2500);
    return () => window.clearTimeout(timer);
  }, [deleteToast]);

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
    // 백엔드는 임베더 로딩 때문에 프론트보다 늦게 뜨고, --reload로 잠깐 끊기기도
    // 한다. 한 번 실패하고 포기하면 서버가 살아나도 "API 연결 필요"로 굳으므로
    // 연결될 때까지 다시 시도한다.
    let cancelled = false;
    let retryTimer: number | undefined;

    const check = () => {
      Promise.all([getScenarios(), getCapabilities()])
        .then(([scenarioData, capabilityData]) => {
          if (cancelled) return;
          setScenarios(scenarioData);
          setCapabilities(capabilityData);
          setServerReady(true);
        })
        .catch(() => {
          if (cancelled) return;
          setServerReady(false);
          retryTimer = window.setTimeout(check, 3000);
        });
    };

    check();
    return () => {
      cancelled = true;
      window.clearTimeout(retryTimer);
    };
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
      setDeletingSessionId(null);
    }
    if (userChanged) {
      conversationGenerationRef.current += 1;
      setMessages([]);
      setActiveSessionId(null);
      setConversationContext(null);
      setSelectedScenario("");
      setUserContext(null);
    }
    if (!accessToken) {
      setChatSessions([]);
      setUserContext(null);
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
    void getMyPensionContext(accessToken)
      .then((context) => {
        if (!active) return;
        setUserContext(context);
        setSelectedScenario(context.scenario_code);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setUserContext(null);
        setHistoryError(authenticatedErrorMessage(error));
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
      setUserContext(null);
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
      setSelectedScenario(userContext?.scenario_code ?? "");
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

  async function deleteStoredSession(session: ChatSessionSummary) {
    if (
      !accessToken
      || !authenticatedUserId
      || historyLoading
      || isSending
      || deletingSessionId
    ) return;
    const title = session.title?.trim() || "새 대화";
    if (!window.confirm(`‘${title}’ 대화를 삭제할까요?\n삭제한 대화는 복구할 수 없습니다.`)) {
      return;
    }

    const requestToken = accessToken;
    const requestUserId = authenticatedUserId;
    const authGeneration = authGenerationRef.current;
    setDeletingSessionId(session.session_id);
    setHistoryError(null);
    try {
      await deleteChatSession(session.session_id, requestToken);
      if (!isCurrentOperation(authGeneration, requestUserId, requestToken)) return;
      setChatSessions((current) => current.filter(
        (item) => item.session_id !== session.session_id,
      ));
      setDeleteToast("대화가 삭제되었습니다.");
      if (activeSessionId === session.session_id) {
        conversationGenerationRef.current += 1;
        setMessages([]);
        setActiveSessionId(null);
        setConversationContext(null);
        setIsSidebarOpen(false);
      }
    } catch (error) {
      if (!isCurrentOperation(authGeneration, requestUserId, requestToken)) return;
      setHistoryError(authenticatedErrorMessage(error));
    } finally {
      if (isCurrentOperation(authGeneration, requestUserId, requestToken)) {
        setDeletingSessionId((current) => (
          current === session.session_id ? null : current
        ));
      }
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
    setSendingStage("질문을 확인하고 있습니다.");
    setStreamingAnswer("");

    const appendAnswerDelta = (delta: string) => {
      if (isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) setStreamingAnswer((current) => current + delta);
    };

    const taxInput = !requestToken && PENSION_TAX_PROMPT.test(normalized)
      ? pensionTaxInput
      : undefined;

    try {
      const streamed = requestToken
        ? await sendAuthenticatedChatStream(
            normalized,
            requestToken,
            setSendingStage,
            appendAnswerDelta,
            undefined,
            activeSessionId || undefined,
            idempotencyKey,
            conversationContext,
            taxInput,
            surveyProfile,
          )
        : await sendChatStream(normalized, setSendingStage, appendAnswerDelta, {
            scenarioCode: selectedScenario || undefined,
            conversationContext,
            pensionTax: taxInput,
            surveyProfile,
          });
      const persisted = streamed.persisted ? streamed : null;
      const response = streamed.response;
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
        setStreamingAnswer("");
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
                ) : chatSessions.map((session) => {
                  const title = session.title || "새 대화";
                  const deleting = deletingSessionId === session.session_id;
                  const disabled = historyLoading || isSending || deletingSessionId !== null;
                  return (
                    <div
                      className={`history-item ${activeSessionId === session.session_id ? "active" : ""}`}
                      key={session.session_id}
                    >
                      <button
                        className="history-open"
                        type="button"
                        onClick={() => void loadStoredSession(session.session_id)}
                        disabled={disabled}
                      >
                        <strong>{title}</strong>
                        <small>{new Date(session.updated_at).toLocaleDateString("ko-KR", { month: "short", day: "numeric" })}</small>
                      </button>
                      <button
                        className="history-delete"
                        type="button"
                        aria-label={`대화 삭제: ${title}`}
                        title="대화 삭제"
                        onClick={() => void deleteStoredSession(session)}
                        disabled={disabled}
                      >
                        {deleting ? <span className="delete-progress">…</span> : <Icon name="trash" size={14} />}
                      </button>
                    </div>
                  );
                })}
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
          {userContext ? (
            <div className="user-context-card">
              <strong>{userContext.nickname}</strong>
              <span>{userContext.scenario_name} · 가상 목데이터</span>
              <small>
                총 연금자산 {Number(userContext.total_pension_balance_krw).toLocaleString("ko-KR")}원
                <br />기준일 {userContext.as_of_date}
              </small>
            </div>
          ) : (
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
          )}
        </div>

        {!userContext && <details className="tax-input-panel">
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
        </details>}

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
        <header className="topbar design-topbar">
          <button className="menu-button" type="button" aria-label="메뉴 열기" onClick={() => setIsSidebarOpen(true)}><span /><span /><span /></button>
          <button className="design-new-chat" type="button" onClick={startNewChat}><span>+</span> 새 대화</button>
          <div className="design-topbar-actions">
            <Icon name="database" size={25} />
            <span className="design-avatar">연</span>
          </div>
        </header>

        <div className="conversation" aria-live="polite">
          {messages.length === 0 ? (
            <div className="welcome design-welcome">
              <div className="design-brand">
                <span className="design-brand-mark">연</span>
                <strong>연금 <em>도우미</em></strong>
              </div>
              <h1>막막한 노후 준비, <em>연금 도우미</em>와<br />대화하며 풀어보세요.</h1>

              {(userContext || selectedScenarioData) && (
                <div className="selected-scenario-card">
                  <div><Icon name="database" size={19} /></div>
                  <span>
                    <strong>{userContext?.nickname ?? selectedScenarioData?.name}</strong>
                    <small>{userContext?.customer_context ?? selectedScenarioData?.description}</small>
                  </span>
                </div>
              )}

              <div className="prompt-grid design-prompt-grid">
                {SUGGESTED_PROMPTS.map(({ category, prompt, icon }) => (
                  <button type="button" key={prompt} onClick={() => void submitPrompt(prompt)}>
                    <span className="design-prompt-icon"><Icon name={icon} size={27} /></span>
                    <span className="design-prompt-copy"><small>{category}</small><strong>{prompt}</strong></span>
                  </button>
                ))}
              </div>

              {capabilities && <p className="capability-note">연금 도우미는 참고용 정보를 제공하며, 실제 투자·가입 결정은 본인의 판단과 전문가 상담을 거쳐 주세요.</p>}
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
                  {streamingAnswer ? (
                    <div className="message-bubble" aria-live="polite">
                      <AssistantMessage text={streamingAnswer} />
                    </div>
                  ) : (
                    <div className="message-bubble typing" aria-label={sendingStage}>
                      <span /><span /><span /><small>{sendingStage}</small>
                    </div>
                  )}
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
              placeholder="연금에 대해 무엇이든 물어보세요"
              rows={1}
              aria-label="질문 입력"
              disabled={isSending}
            />
            <button type="submit" disabled={input.trim().length < 2 || isSending} aria-label="질문 보내기"><Icon name="send" size={20} /></button>
          </form>
          <p>AI 답변은 투자 판단을 돕는 정보이며, 미래 수익을 보장하지 않습니다.</p>
        </div>
      </main>
      {deleteToast && (
        <div className="delete-toast" role="status" aria-live="polite">
          {deleteToast}
        </div>
      )}
    </div>
  );
}
