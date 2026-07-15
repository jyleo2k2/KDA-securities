import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type JSX,
} from "react";

import {
  getChatMessages,
  listChatSessions,
  sendAuthenticatedChat,
  sendDemoChat,
} from "../api/chat";
import { ApiError } from "../api/client";
import type {
  ChatSession,
  EvidenceAnswer,
  PortfolioInput,
} from "../api/types";
import { useSupabaseAuth } from "../auth/useSupabaseAuth";

type ChatMode = "demo" | "account";
type RequestState = "idle" | "sending" | "stopped" | "db_error" | "error";

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  answer?: EvidenceAnswer;
}

interface Scenario {
  id: string;
  label: string;
  description: string;
  portfolio: PortfolioInput;
}

const SCENARIOS: Scenario[] = [
  {
    id: "irp_balanced",
    label: "IRP 균형형",
    description: "일반 위험자산 60% · 원리금보장 40%",
    portfolio: {
      account_type: "irp",
      holdings: [
        { holding_id: "irp-risk", amount_krw: "60000000", risk_treatment: "general_risky" },
        { holding_id: "irp-safe", amount_krw: "40000000", risk_treatment: "capital_preservation" },
      ],
    },
  },
  {
    id: "dc_limit",
    label: "DC 한도 근접형",
    description: "일반 위험자산 70% · 원리금보장 30%",
    portfolio: {
      account_type: "dc",
      holdings: [
        { holding_id: "dc-risk", amount_krw: "70000000", risk_treatment: "general_risky" },
        { holding_id: "dc-safe", amount_krw: "30000000", risk_treatment: "capital_preservation" },
      ],
    },
  },
  {
    id: "pension_growth",
    label: "연금저축 성장형",
    description: "일반 위험자산 85% · 현금성 15%",
    portfolio: {
      account_type: "pension_savings",
      holdings: [
        { holding_id: "ps-risk", amount_krw: "85000000", risk_treatment: "general_risky" },
        { holding_id: "ps-cash", amount_krw: "15000000", risk_treatment: "capital_preservation" },
      ],
    },
  },
];

const SCENARIO_KEY = "pension-copilot:mock-scenario";

function savedScenarioId(): string {
  return localStorage.getItem(SCENARIO_KEY) ?? SCENARIOS[0].id;
}

function dataBoundaryLabel(boundary: string): string {
  if (boundary.includes("mock")) return "목데이터";
  if (boundary.includes("real_data")) return "실데이터";
  if (boundary === "verified_knowledge") return "검증 지식";
  if (boundary === "blocked_before_retrieval") return "조회 전 차단";
  return "데이터 경계 확인";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium" }).format(
    new Date(value),
  );
}

function AnswerCard({ answer }: { answer: EvidenceAnswer }): JSX.Element {
  if (answer.status === "no_evidence") {
    return (
      <div style={noticeStyle("#fff7e6", "#8a5300")}>
        <strong>{answer.narrative.facts}</strong>
        <div style={{ marginTop: 6 }}>{answer.narrative.limitations}</div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
        <span style={chipStyle("#e9f1ff", "#174ea6")}>
          {dataBoundaryLabel(answer.data_boundary)}
        </span>
        {answer.as_of_date && (
          <span style={chipStyle("#eef8ef", "#256c2e")}>
            기준일 {formatDate(answer.as_of_date)}
          </span>
        )}
        {answer.collected_at && (
          <span style={chipStyle("#f3f0ff", "#5d3fa3")}>
            수집 {formatDate(answer.collected_at)}
          </span>
        )}
      </div>

      <AnswerSection label="사실" text={answer.narrative.facts} />
      <AnswerSection label="외부 의견" text={answer.narrative.external_opinion} />
      <AnswerSection label="서비스 해석" text={answer.narrative.service_interpretation} />
      <AnswerSection label="한계" text={answer.narrative.limitations} />

      {answer.numeric_evidence.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <strong style={{ fontSize: 13 }}>수치 근거</strong>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 7 }}>
            {answer.numeric_evidence.map((item) => (
              <span key={item.metric} style={chipStyle("#f5f6f8", "#263238")}>
                {item.label} {item.value}{item.unit}
              </span>
            ))}
          </div>
        </div>
      )}

      {answer.sources.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <strong style={{ fontSize: 13 }}>출처</strong>
          <ul style={{ margin: "7px 0 0", paddingLeft: 18 }}>
            {answer.sources.map((source, index) => (
              <li key={`${source.url}-${index}`} style={{ marginBottom: 5 }}>
                {source.url.startsWith("http") ? (
                  <a href={source.url} target="_blank" rel="noreferrer" style={{ color: "#174ea6" }}>
                    {source.title}
                  </a>
                ) : (
                  <span>{source.title}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AnswerSection({ label, text }: { label: string; text: string }): JSX.Element {
  return (
    <div style={{ marginTop: 10 }}>
      <strong style={{ display: "block", fontSize: 13, marginBottom: 3 }}>{label}</strong>
      <div style={{ lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{text}</div>
    </div>
  );
}

function LoginPanel({
  loading,
  error,
  onSignIn,
}: {
  loading: boolean;
  error: string | null;
  onSignIn: (email: string, password: string) => Promise<boolean>;
}): JSX.Element {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    await onSignIn(email, password);
  }

  return (
    <form onSubmit={(event) => void submit(event)} style={panelStyle}>
      <strong>Supabase 로그인</strong>
      <p style={{ color: "#667085", fontSize: 13, lineHeight: 1.5 }}>
        로그인 후 질문과 답변 근거가 내 대화에 저장됩니다.
      </p>
      <input
        type="email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        placeholder="이메일"
        autoComplete="email"
        required
        style={inputStyle}
      />
      <input
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        placeholder="비밀번호"
        autoComplete="current-password"
        required
        style={{ ...inputStyle, marginTop: 8 }}
      />
      {error && <div style={{ color: "#b42318", fontSize: 13, marginTop: 8 }}>{error}</div>}
      <button type="submit" disabled={loading} style={{ ...primaryButtonStyle, marginTop: 12, width: "100%" }}>
        {loading ? "확인 중…" : "로그인"}
      </button>
    </form>
  );
}

export function GuidePage(): JSX.Element {
  const auth = useSupabaseAuth();
  const [mode, setMode] = useState<ChatMode>(auth.configured ? "account" : "demo");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [scenarioId, setScenarioId] = useState(savedScenarioId);
  const abortRef = useRef<AbortController | null>(null);
  const listEndRef = useRef<HTMLDivElement | null>(null);

  const scenario = useMemo(
    () => SCENARIOS.find((item) => item.id === scenarioId) ?? SCENARIOS[0],
    [scenarioId],
  );
  const accessToken = auth.session?.access_token;
  const activeSessionKey = auth.session
    ? `pension-copilot:active-session:${auth.session.user.id}`
    : null;

  useEffect(() => {
    localStorage.setItem(SCENARIO_KEY, scenarioId);
  }, [scenarioId]);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, requestState]);

  useEffect(() => {
    if (mode !== "account" || !accessToken || !activeSessionKey) {
      setSessions([]);
      return;
    }
    let active = true;
    void listChatSessions(accessToken)
      .then((items) => {
        if (!active) return;
        setSessions(items);
        const saved = localStorage.getItem(activeSessionKey);
        if (saved && items.some((item) => item.session_id === saved)) {
          void openSession(saved, accessToken, activeSessionKey);
        }
      })
      .catch((error: unknown) => {
        if (!active) return;
        handleRequestError(error);
      });
    return () => {
      active = false;
    };
    // 세션 복구는 사용자 또는 대화 모드가 바뀔 때 한 번만 수행한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, accessToken, activeSessionKey]);

  function handleRequestError(error: unknown): void {
    if (error instanceof DOMException && error.name === "AbortError") {
      setRequestState("stopped");
      setErrorMessage("답변 생성을 중단했습니다. 같은 질문을 다시 시도할 수 있습니다.");
      return;
    }
    if (error instanceof ApiError && error.status === 503) {
      setRequestState("db_error");
      setErrorMessage("데이터베이스 또는 답변 저장소에 연결하지 못했습니다.");
      return;
    }
    setRequestState("error");
    setErrorMessage(error instanceof Error ? error.message : "요청을 처리하지 못했습니다.");
  }

  async function refreshSessions(token: string): Promise<void> {
    const items = await listChatSessions(token);
    setSessions(items);
  }

  async function openSession(id: string, token = accessToken, storageKey = activeSessionKey): Promise<void> {
    if (!token) return;
    setRequestState("idle");
    setErrorMessage(null);
    try {
      const stored = await getChatMessages(id, token);
      setMessages(
        stored.map((message) => ({
          id: message.message_id,
          role: message.role,
          content: message.role === "user" ? message.content : "",
          answer: message.answer ?? undefined,
        })),
      );
      setSessionId(id);
      if (storageKey) localStorage.setItem(storageKey, id);
    } catch (error) {
      handleRequestError(error);
    }
  }

  function newChat(): void {
    abortRef.current?.abort();
    setMessages([]);
    setSessionId(null);
    setQuestion("");
    setLastQuestion(null);
    setRequestState("idle");
    setErrorMessage(null);
    if (activeSessionKey) localStorage.removeItem(activeSessionKey);
  }

  async function send(text: string): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || requestState === "sending") return;
    if (mode === "account" && !accessToken) {
      setRequestState("error");
      setErrorMessage("로그인 후 저장형 대화를 사용할 수 있습니다.");
      return;
    }

    const userMessage: DisplayMessage = {
      id: `local-${crypto.randomUUID()}`,
      role: "user",
      content: trimmed,
    };
    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setLastQuestion(trimmed);
    setErrorMessage(null);
    setRequestState("sending");
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      if (mode === "demo") {
        const response = await sendDemoChat(
          { question: trimmed, portfolio: scenario.portfolio },
          controller.signal,
        );
        setMessages((current) => [
          ...current,
          { id: `demo-${crypto.randomUUID()}`, role: "assistant", content: "", answer: response.answer },
        ]);
      } else {
        const response = await sendAuthenticatedChat(
          { question: trimmed, session_id: sessionId, portfolio: scenario.portfolio },
          accessToken!,
          controller.signal,
        );
        setSessionId(response.session_id);
        if (activeSessionKey) localStorage.setItem(activeSessionKey, response.session_id);
        setMessages((current) => [
          ...current,
          { id: response.assistant_message_id, role: "assistant", content: "", answer: response.answer },
        ]);
        await refreshSessions(accessToken!);
      }
      setRequestState("idle");
    } catch (error) {
      handleRequestError(error);
    } finally {
      abortRef.current = null;
    }
  }

  function submit(event: FormEvent): void {
    event.preventDefault();
    void send(question);
  }

  function retry(): void {
    if (!lastQuestion) return;
    setMessages((current) => {
      const last = current.at(-1);
      return last?.role === "user" && last.content === lastQuestion ? current.slice(0, -1) : current;
    });
    void send(lastQuestion);
  }

  const accountUnavailable = mode === "account" && !auth.configured;
  const needsLogin = mode === "account" && auth.configured && !auth.session;

  return (
    <section>
      <header style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
          <div>
            <h1 style={{ fontSize: 22, margin: 0 }}>연금 코파일럿</h1>
            <div style={{ fontSize: 12, color: "#667085", marginTop: 4 }}>근거와 데이터 경계를 함께 보여주는 대화</div>
          </div>
          {auth.session && mode === "account" && (
            <button type="button" onClick={() => void auth.signOut()} style={textButtonStyle}>로그아웃</button>
          )}
        </div>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 12 }}>
        <ModeButton active={mode === "demo"} onClick={() => { setMode("demo"); newChat(); }}>발표용 데모</ModeButton>
        <ModeButton active={mode === "account"} onClick={() => { setMode("account"); newChat(); }}>로그인 대화</ModeButton>
      </div>

      {accountUnavailable && (
        <div style={noticeStyle("#fff7e6", "#8a5300")}>
          Supabase 공개 환경변수가 아직 없습니다. 데모 대화는 계속 사용할 수 있습니다.
        </div>
      )}
      {needsLogin && <LoginPanel loading={auth.loading} error={auth.error} onSignIn={auth.signIn} />}

      {!accountUnavailable && !needsLogin && (
        <>
          <div style={{ ...panelStyle, marginBottom: 10 }}>
            <label htmlFor="scenario" style={{ display: "block", fontWeight: 700, fontSize: 13, marginBottom: 6 }}>
              목시나리오
            </label>
            <select id="scenario" value={scenarioId} onChange={(event) => setScenarioId(event.target.value)} style={inputStyle}>
              {SCENARIOS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
            <div style={{ color: "#667085", fontSize: 12, marginTop: 5 }}>{scenario.description} · 브라우저에 선택 상태 저장</div>
          </div>

          {mode === "account" && (
            <div style={{ ...panelStyle, marginBottom: 10 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <strong style={{ fontSize: 13 }}>이전 대화</strong>
                <button type="button" onClick={newChat} style={textButtonStyle}>＋ 새 대화</button>
              </div>
              {sessions.length === 0 ? (
                <div style={{ color: "#667085", fontSize: 12, marginTop: 8 }}>저장된 대화가 없습니다.</div>
              ) : (
                <div style={{ display: "flex", gap: 6, overflowX: "auto", marginTop: 8, paddingBottom: 2 }}>
                  {sessions.map((item) => (
                    <button
                      key={item.session_id}
                      type="button"
                      onClick={() => void openSession(item.session_id)}
                      style={sessionButtonStyle(item.session_id === sessionId)}
                    >
                      {item.title || "제목 없는 대화"}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div style={{ minHeight: 270, padding: "4px 0 14px" }} aria-live="polite">
            {messages.length === 0 && (
              <div style={{ textAlign: "center", color: "#667085", padding: "40px 20px", lineHeight: 1.6 }}>
                계좌 규칙, 과거 공시, 뉴스 또는 선택한 목계좌 진단을 질문해 보세요.
              </div>
            )}
            {messages.map((message) => (
              <div key={message.id} style={message.role === "user" ? userBubbleStyle : assistantBubbleStyle}>
                {message.role === "user" ? message.content : message.answer ? <AnswerCard answer={message.answer} /> : "저장된 답변 형식을 읽을 수 없습니다."}
              </div>
            ))}
            {requestState === "sending" && <div style={assistantBubbleStyle}>근거를 조회하고 있습니다…</div>}
            <div ref={listEndRef} />
          </div>

          {requestState === "db_error" && (
            <div style={noticeStyle("#fff0f0", "#b42318")}>
              <strong>DB 연결 실패</strong><div style={{ marginTop: 4 }}>{errorMessage}</div>
            </div>
          )}
          {(requestState === "error" || requestState === "stopped") && (
            <div style={noticeStyle("#fff7e6", "#8a5300")}>{errorMessage}</div>
          )}
          {["db_error", "error", "stopped"].includes(requestState) && lastQuestion && (
            <button type="button" onClick={retry} style={{ ...textButtonStyle, margin: "8px 0" }}>↻ 마지막 질문 재시도</button>
          )}

          <form onSubmit={submit} style={{ position: "sticky", bottom: 64, background: "#ffffff", padding: "10px 0 2px" }}>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder="예: IRP 일반 위험자산 한도를 알려줘"
              maxLength={4000}
              rows={3}
              disabled={requestState === "sending"}
              style={{ ...inputStyle, resize: "vertical", lineHeight: 1.45 }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 7 }}>
              <span style={{ fontSize: 11, color: "#667085" }}>민감정보·주문·미래 수익 예측은 처리하지 않습니다.</span>
              {requestState === "sending" ? (
                <button type="button" onClick={() => abortRef.current?.abort()} style={stopButtonStyle}>■ 중단</button>
              ) : (
                <button type="submit" disabled={!question.trim()} style={primaryButtonStyle}>질문 보내기</button>
              )}
            </div>
          </form>
        </>
      )}
    </section>
  );
}

function ModeButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: string }): JSX.Element {
  return <button type="button" onClick={onClick} style={{ ...modeButtonStyle, ...(active ? { background: "#174ea6", color: "white", border: "1px solid #174ea6" } : {}) }}>{children}</button>;
}

const panelStyle = { border: "1px solid #e4e7ec", borderRadius: 12, padding: 12, background: "#ffffff" } as const;
const inputStyle = { boxSizing: "border-box", width: "100%", border: "1px solid #cfd4dc", borderRadius: 9, padding: "10px 11px", font: "inherit", background: "#ffffff" } as const;
const primaryButtonStyle = { border: 0, borderRadius: 9, padding: "9px 13px", background: "#174ea6", color: "#ffffff", fontWeight: 700, cursor: "pointer" } as const;
const stopButtonStyle = { ...primaryButtonStyle, background: "#b42318" } as const;
const textButtonStyle = { border: 0, background: "transparent", color: "#174ea6", fontWeight: 700, cursor: "pointer", padding: 4 } as const;
const modeButtonStyle = { border: "1px solid #cfd4dc", borderRadius: 9, padding: 9, background: "#ffffff", color: "#344054", fontWeight: 700, cursor: "pointer" } as const;
const userBubbleStyle = { maxWidth: "86%", margin: "10px 0 10px auto", padding: "11px 13px", background: "#174ea6", color: "#ffffff", borderRadius: "14px 14px 3px 14px", lineHeight: 1.5, overflowWrap: "anywhere" } as const;
const assistantBubbleStyle = { margin: "10px 24px 10px 0", padding: "13px", background: "#f5f7fa", color: "#1d2939", borderRadius: "14px 14px 14px 3px", lineHeight: 1.5, overflowWrap: "anywhere" } as const;

function chipStyle(background: string, color: string) {
  return { display: "inline-block", borderRadius: 999, padding: "4px 8px", background, color, fontSize: 11, fontWeight: 700 } as const;
}

function noticeStyle(background: string, color: string) {
  return { padding: 11, borderRadius: 10, background, color, fontSize: 13, lineHeight: 1.45 } as const;
}

function sessionButtonStyle(active: boolean) {
  return { flex: "0 0 auto", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", border: `1px solid ${active ? "#174ea6" : "#d0d5dd"}`, borderRadius: 999, padding: "6px 10px", background: active ? "#e9f1ff" : "#ffffff", color: active ? "#174ea6" : "#344054", cursor: "pointer" } as const;
}
