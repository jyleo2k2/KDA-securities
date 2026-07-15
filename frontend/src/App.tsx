import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { getCapabilities, getScenarios, sendChat } from "./api";
import type {
  ChatCapabilities,
  ChatResponse,
  ConversationMessage,
  DataBoundary,
  ScenarioSummary,
} from "./types";

const SUGGESTED_PROMPTS = [
  "IRP와 연금저축의 위험자산 한도 차이를 알려줘",
  "DC형 방치 시나리오를 진단해줘",
  "내년 예상수익률을 알려줘",
  "연금 뉴스 알려줘",
];

const INTENT_LABELS: Record<ChatResponse["intent"], string> = {
  account_rule: "계좌 규칙",
  mock_portfolio: "목계좌 진단",
  provider_disclosure: "공식 공시",
  news: "연금 뉴스",
  out_of_scope: "지원 범위 안내",
};

const BOUNDARY_LABELS: Record<DataBoundary, string> = {
  verified_knowledge: "검증 지식",
  official_disclosure: "공식 공시",
  news_metadata: "뉴스 메타데이터",
  mock: "목데이터",
  engine: "규칙 엔진",
  unavailable: "미지원",
};

function Icon({ name, size = 20 }: { name: "spark" | "send" | "book" | "database" | "chevron" | "shield" | "refresh"; size?: number }) {
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

function SourceLink({ locator, children }: { locator: string; children: React.ReactNode }) {
  const isWeb = /^https?:\/\//.test(locator);
  if (!isWeb) return <span>{children}</span>;
  return <a href={locator} target="_blank" rel="noreferrer">{children}</a>;
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

      {response.sections.map((section, index) => (
        <details className={`answer-section section-${section.kind}`} key={`${section.title}-${index}`} open={section.kind === "limitation"}>
          <summary><span>{section.title}</span><small>내용 보기</small></summary>
          <p>{section.content}</p>
        </details>
      ))}

      {response.numeric_evidence.length > 0 && (
        <div className="number-grid" aria-label="수치 근거">
          {response.numeric_evidence.map((item, index) => (
            <div className="number-card" key={`${item.evidence_id}-${index}`}>
              <span>{item.label}</span>
              <strong>{item.value}{item.unit}</strong>
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

function App() {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState("");
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [capabilities, setCapabilities] = useState<ChatCapabilities | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [serverReady, setServerReady] = useState<boolean | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const latestMessageRef = useRef<HTMLDivElement>(null);

  const selectedScenarioData = useMemo(
    () => scenarios.find((scenario) => scenario.code === selectedScenario),
    [scenarios, selectedScenario],
  );

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
    if (messages.length > 0) {
      latestMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (isSending) {
      conversationEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isSending]);

  async function submitPrompt(prompt: string) {
    const normalized = prompt.trim();
    if (normalized.length < 2 || isSending) return;

    const userMessage: ConversationMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: normalized,
      createdAt: new Date(),
    };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsSending(true);

    try {
      const response = await sendChat(normalized, selectedScenario || undefined);
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: response.answer,
        response,
        createdAt: new Date(),
      }]);
      setServerReady(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : "서버 연결을 확인해 주세요.";
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: message,
        failedPrompt: normalized,
        createdAt: new Date(),
      }]);
      setServerReady(false);
    } finally {
      setIsSending(false);
      textareaRef.current?.focus();
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

        <button className="new-chat" type="button" onClick={() => { setMessages([]); setIsSidebarOpen(false); }}>
          <span>＋</span> 새 대화
        </button>

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
                <span><strong>{scenario.name}</strong><small>{scenario.investment_horizon_years}년 · {scenario.risk_profile}</small></span>
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="connection-status">
            <span className={`status-dot ${serverReady === false ? "offline" : ""}`} />
            <span>{serverReady === null ? "서버 확인 중" : serverReady ? "데모 API 연결됨" : "API 연결 필요"}</span>
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

export default App;
