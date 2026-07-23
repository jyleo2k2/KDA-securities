// chatbot-mvp 브랜치의 챗 화면을 연금가이드 탭으로 이식한 것.
// 스타일은 src/index.css의 .app-shell 계열 클래스를 사용한다.
import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import {
  ApiError,
  apiErrorMessage,
  deleteChatSession,
  deleteAllChatSessions,
  getChatCards,
  getChatSessions,
  getScenarios,
  getStoredChatMessages,
} from "../api/client";
import { ChatVisualization } from "../components/ChatVisualization";
import { ChatIcon as Icon } from "../components/ChatIcon";
import {
  ChatEtfThemeCards,
  ChatQuestionRecommendations,
} from "../components/ChatRecommendations";
import { ChatSessionList } from "../components/ChatSessionList";
import { ChatComposer, ChatMessageList } from "../components/ChatConversation";
import { ChatTypingAnswer } from "../components/ChatTypingAnswer";
import {
  EducationalPortfolioReview,
  PortfolioHoldingsPanel,
} from "../components/PortfolioHoldingsPanel";
import type {
  AnswerBlock,
  CompletedSurveyProfile,
  ChatCard,
  ConversationContext,
  ChatResponse,
  ChatSessionSummary,
  DataBoundary,
  DemoUserFinancialContext,
  IncomeBasis,
  IrpDeferredIncomeStatus,
  IsaTransferEligibilityStatus,
  PensionTaxScenarioInput,
  ScenarioSummary,
  StoredChatMessage,
  WithdrawalReason,
} from "../api/types";
import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import { useChatStream, type ConversationMessage } from "../hooks/useChatStream";

const INTENT_LABELS: Record<ChatResponse["intent"], string> = {
  account_rule: "계좌 규칙",
  mock_portfolio: "목계좌 진단",
  provider_disclosure: "공식 공시",
  news: "증시 뉴스",
  pension_tax: "세액공제·중도해지",
  etf_theme: "ETF 테마",
  educational_portfolio: "연금 운용전략",
  macro_evidence: "거시지표 근거",
  out_of_scope: "지원 범위 안내",
};

const NUMBER_EVIDENCE_DEFAULT_LIMIT = 6;

const BOUNDARY_LABELS: Record<DataBoundary, string> = {
  verified_knowledge: "검증 지식",
  official_disclosure: "공식 공시",
  official_statistics: "공식 통계",
  news_metadata: "뉴스 메타데이터",
  mock: "계좌 데이터",
  engine: "규칙 엔진",
  user_input: "사용자 입력",
  unavailable: "미지원",
};

const DEFAULT_TYPING_INTERVAL_MS = 50;
const SERVER_READY_RETRY_DELAYS_MS = [3000, 6000, 12000] as const;

export const ETF_THEME_CARDS = [
  { number: 1, title: "반도체", message: "반도체 테마가 뭐야?" },
  { number: 2, title: "신재생·친환경", message: "신재생·친환경 테마가 뭐야?" },
  { number: 3, title: "바이오·헬스케어", message: "바이오·헬스케어 테마가 뭐야?" },
  { number: 4, title: "2차전지·배터리", message: "2차전지·배터리 테마가 뭐야?" },
  { number: 5, title: "건설·기계·인프라", message: "건설·기계·인프라 테마가 뭐야?" },
  { number: 6, title: "자동차·모빌리티", message: "자동차·모빌리티 테마가 뭐야?" },
  { number: 7, title: "그룹주", message: "그룹주 테마가 뭐야?" },
  { number: 8, title: "에너지·정유", message: "에너지·정유 테마가 뭐야?" },
  { number: 9, title: "미디어·엔터·게임", message: "미디어·엔터·게임 테마가 뭐야?" },
  { number: 10, title: "원자력·전력", message: "원자력·전력 테마가 뭐야?" },
  { number: 11, title: "리츠·부동산", message: "리츠·부동산 테마가 뭐야?" },
  { number: 12, title: "로봇", message: "로봇 테마가 뭐야?" },
  { number: 13, title: "은행·금융", message: "은행·금융 테마가 뭐야?" },
  { number: 14, title: "방산·우주", message: "방산·우주 테마가 뭐야?" },
  { number: 15, title: "소비재·음식료", message: "소비재·음식료 테마가 뭐야?" },
  { number: 16, title: "금·원자재", message: "금·원자재 테마가 뭐야?" },
  { number: 17, title: "철강·소재", message: "철강·소재 테마가 뭐야?" },
  { number: 18, title: "양자컴퓨팅", message: "양자컴퓨팅 테마가 뭐야?" },
  { number: 19, title: "메타버스", message: "메타버스 테마가 뭐야?" },
  { number: 20, title: "조선", message: "조선 테마가 뭐야?" },
  { number: 21, title: "채권", message: "채권 테마가 뭐야?" },
] as const;
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

export function filterChatCards(
  cards: ChatCard[],
  state: { hasScenario: boolean; hasSurvey: boolean; hasAuth: boolean },
): ChatCard[] {
  const visible = {
    requires_scenario: state.hasScenario,
    requires_survey: state.hasSurvey,
    requires_auth: state.hasAuth,
  };
  return [...cards]
    .filter((card) => card.conditions.every((condition) => visible[condition] === true))
    .sort((left, right) => left.priority - right.priority);
}

function SourceLink({ locator, children }: { locator: string; children: ReactNode }) {
  const isWeb = /^https?:\/\//.test(locator);
  if (!isWeb) return <span>{children}</span>;
  return <a href={locator} target="_blank" rel="noreferrer">{children}</a>;
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
                : item.evidence_id.startsWith("live-news:")
                  ? "실시간 헤드라인 · 3줄 요약 전"
                  : "뉴스 메타데이터"}
            </span>
            {newsDate(item.published_at) && <time>{newsDate(item.published_at)}</time>}
          </div>
          <strong>{displayText(item.title)}</strong>
          {item.summary_lines?.length === 3 ? (
            <ol className="news-card-summary">
              {item.summary_lines.map((line, lineIndex) => (
                <li key={`${item.evidence_id}-summary-${lineIndex}`}>
                  <span className="news-card-summary-number">{lineIndex + 1}.</span>
                  <span className="news-card-summary-text">{displayText(line)}</span>
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
              <CalloutCopy text={block.text ?? ""} />
            </div>
          );
        }
        if (block.kind === "paragraph") {
          return <p key={key}>{displayText(block.text ?? "")}</p>;
        }
        if (block.kind === "bullets") {
          return (
            <div className="answer-bullet-block" key={key}>
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

function sectionPreview(content: string): string {
  const normalized = displayText(content).replace(/\s+/g, " ").trim();
  const sentence = normalized.match(/^.*?[.!?](?:\s|$)/);
  return (sentence?.[0] ?? normalized).trim();
}

const REPRESENTATIVE_COMPANY_LABELS = [
  "테마에서의 역할:",
  "쉽게 말하면:",
] as const;
const THEME_PARAGRAPH_GAP = "10pt";

function CalloutCopy({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/).map((paragraph) => paragraph.trim()).filter(Boolean);
  const isRepresentativeCompany =
    paragraphs.length === REPRESENTATIVE_COMPANY_LABELS.length &&
    paragraphs.every((paragraph, index) =>
      paragraph.startsWith(REPRESENTATIVE_COMPANY_LABELS[index]),
    );

  if (paragraphs.length <= 1) {
    return <p>{displayText(text)}</p>;
  }

  return (
    <div className="answer-callout-copy">
      {paragraphs.map((paragraph, index) => {
        if (!isRepresentativeCompany) {
          return <p key={`${paragraph}-${index}`}>{displayText(paragraph)}</p>;
        }
        const label = REPRESENTATIVE_COMPANY_LABELS[index];
        const body = paragraph.slice(label.length).trim();
        return (
          <p key={label}>
            <strong>{label}</strong> {displayText(body)}
          </p>
        );
      })}
    </div>
  );
}

function macroPublisherCode(publisher: string): string {
  if (publisher.includes("한국은행")) return "BOK";
  if (publisher.includes("KOSIS")) return "KOSIS";
  if (publisher.includes("St. Louis")) return "FRED";
  return "공식 통계";
}

function MacroEvidenceCards({ response }: { response: ChatResponse }) {
  if (response.intent !== "macro_evidence") return null;

  const groups = new Map<string, {
    publisher: string;
    metrics: Array<{
      label: string;
      value: string | number;
      unit: string;
      observedAt?: string | null;
      locator: string;
    }>;
  }>();
  response.sources.forEach((source) => {
    const numeric = response.numeric_evidence.find(
      (item) => item.evidence_id === source.evidence_id,
    );
    if (!numeric) return;
    const publisher = source.publisher ?? source.label;
    const group = groups.get(publisher) ?? { publisher, metrics: [] };
    group.metrics.push({
      label: numeric.label,
      value: numeric.value,
      unit: numeric.unit,
      observedAt: source.as_of,
      locator: source.locator,
    });
    groups.set(publisher, group);
  });

  return (
    <section className="macro-evidence-card" aria-label="거시환경 근거 카드">
      <header>
        <span>거시환경 근거</span>
        <h3>BOK · KOSIS · FRED 공식 관측</h3>
        <p>현재 환경을 설명하는 관측값이며 계획수익률·목표비중·리밸런싱 신호에 자동 반영하지 않아요.</p>
      </header>
      <div className="macro-provider-list">
        {Array.from(groups.values()).map((group) => (
          <article className="macro-provider-card" key={group.publisher}>
            <div className="macro-provider-heading">
              <strong>{macroPublisherCode(group.publisher)}</strong>
              <span>{group.publisher}</span>
            </div>
            <div className="macro-metric-grid">
              {group.metrics.map((metric) => (
                <SourceLink locator={metric.locator} key={`${group.publisher}-${metric.label}`}>
                  <span className="macro-metric-item">
                    <small>{metric.label}</small>
                    <strong>{numericText(metric.value, metric.unit)}</strong>
                    <span>공식 출처{metric.observedAt ? ` · ${metric.observedAt.slice(0, 10)}` : ""} <Icon name="chevron" size={12} /></span>
                  </span>
                </SourceLink>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

const REGIME_GAP_LABELS: Record<string, string> = {
  total_return_history_unavailable: "총수익 이력 없음",
  verified_total_return_basis_unavailable: "총수익 기준 미확인",
  source_chip_unavailable: "출처 확인 필요",
  start_observation_unavailable: "시작 관측 부족",
  end_observation_unavailable: "종료 관측 부족",
  outcome_window_incomplete: "관측 구간 부족",
};

const SCENARIO_RISK_PROFILE_LABELS: Record<string, string> = {
  stable: "안정형",
  stable_seeking: "안정추구형",
  risk_neutral: "위험중립형",
  active: "적극투자형",
  aggressive: "공격투자형",
};

function regimeMonth(value: string): string {
  const [year, month] = value.split("-");
  return `${year}년 ${Number(month)}월`;
}

function drawdownText(value: string | number): string {
  const parsed = Math.abs(Number(value));
  return parsed === 0 ? "0%" : `-${numericText(parsed, "%")}`;
}

function MacroRegimeOutcomeCards({ response }: { response: ChatResponse }) {
  const evaluation = response.macro_regime_etf_outcomes;
  if (!evaluation) return null;

  return (
    <section className="macro-regime-card" aria-label="과거 유사국면 ETF 근거 카드">
      <header>
        <span>과거 실적 근거</span>
        <h3>유사국면 이후 ETF 총수익률·최대낙폭</h3>
        <p>국면 다음 달 첫 거래일부터 계산한 실제 관측값이며 미래 예측이나 자동 리밸런싱 신호가 아니에요.</p>
      </header>
      <div className="macro-regime-list">
        {evaluation.groups.map((group, groupIndex) => (
          <details key={group.regime_period} open={groupIndex === 0}>
            <summary>
              <strong>{regimeMonth(group.regime_period)} 유사국면</strong>
              <span>유사도 거리 {Number(group.distance).toFixed(4)}</span>
            </summary>
            <div className="macro-regime-etfs">
              {group.etfs.map((etf) => (
                <article key={`${group.regime_period}-${etf.isu_code}`}>
                  <div className="macro-regime-etf-heading">
                    <strong>{etf.isu_name}</strong>
                    <span>{etf.isu_code}</span>
                  </div>
                  <div className="macro-regime-horizons">
                    {etf.horizons.map((horizon) => (
                      <div key={horizon.horizon_months}>
                        <span>{horizon.horizon_months}개월</span>
                        <strong className={Number(horizon.total_return_percent) >= 0 ? "positive" : "negative"}>
                          {numericText(horizon.total_return_percent, "%")}
                        </strong>
                        <small>최대낙폭 {drawdownText(horizon.maximum_drawdown_percent)}</small>
                        <em>{horizon.start_date} ~ {horizon.end_date}</em>
                      </div>
                    ))}
                    {etf.gaps.map((gap) => (
                      <div className="unavailable" key={`gap-${gap.horizon_months}`}>
                        <span>{gap.horizon_months}개월</span>
                        <strong>관측 부족</strong>
                        <small title={gap.reason}>{REGIME_GAP_LABELS[gap.reason] ?? "기타 관측 제한"}</small>
                      </div>
                    ))}
                  </div>
                  {etf.source && (
                    <SourceLink locator={etf.source.reference}>
                      <span className="macro-regime-source-chip">
                        {etf.source.label} · {etf.source.as_of}
                      </span>
                    </SourceLink>
                  )}
                </article>
              ))}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

function AssistantMessage({
  response,
  text,
  onFollowUp,
  onOpenPlanner,
  usedFollowUpMessages,
}: {
  response?: ChatResponse;
  text: string;
  onFollowUp?: (message: string) => void;
  onOpenPlanner?: () => void;
  usedFollowUpMessages: ReadonlySet<string>;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [allNumericEvidenceOpen, setAllNumericEvidenceOpen] = useState(false);

  if (!response) return <p className="message-copy">{text}</p>;

  const visibleFollowUps = (response.suggested_follow_ups ?? []).filter(
    (followUp) => !usedFollowUpMessages.has(followUp.message.trim()),
  );
  const isEducationalPortfolio = response.intent === "educational_portfolio";
  const shouldShowNumericEvidence = (
    response.intent !== "mock_portfolio"
    && response.intent !== "macro_evidence"
    && !isEducationalPortfolio
    && response.data_mode !== "theme_candidates"
    && response.data_mode !== "theme_component_holdings"
    && response.numeric_evidence.length > 0
  );
  const hasHiddenNumericEvidence = (
    response.numeric_evidence.length > NUMBER_EVIDENCE_DEFAULT_LIMIT
  );
  const displayedNumericEvidence = allNumericEvidenceOpen
    ? response.numeric_evidence
    : response.numeric_evidence.slice(0, NUMBER_EVIDENCE_DEFAULT_LIMIT);
  const followUpCards = visibleFollowUps.length > 0 ? (
    <div className="follow-up-cards" aria-label="이어서 물어보기">
      {visibleFollowUps.map((followUp) => (
        <button key={followUp.follow_up_id} onClick={() => followUp.follow_up_id === "open_pension_planner" ? onOpenPlanner?.() : onFollowUp?.(followUp.message)} type="button">
          {followUp.label}<Icon name="chevron" size={14} />
        </button>
      ))}
    </div>
  ) : null;

  return (
    <div
      className={`answer-content${response.intent === "etf_theme" ? " theme-answer-content" : ""}${response.data_mode === "theme_component_holdings" ? " holdings-answer-content" : ""}`}
      style={response.intent === "etf_theme"
        ? { "--theme-paragraph-gap": THEME_PARAGRAPH_GAP } as CSSProperties
        : undefined}
    >
      <div className="answer-meta">
        <span className={`intent-pill intent-${response.intent}`}>{INTENT_LABELS[response.intent]}</span>
        {!isEducationalPortfolio && (
          <span>{response.narration_mode === "deterministic" ? "검증 답변" : "AI 서술"}</span>
        )}
      </div>
      {response.intent !== "macro_evidence" && (response.data_mode !== "news_summary" || response.news_items.length === 0) && (
        <p className="message-copy">
          {response.salutation && <><strong>{response.salutation},</strong>{" "}</>}
          {displayText(response.answer)}
        </p>
      )}

      <MacroEvidenceCards response={response} />
      <MacroRegimeOutcomeCards response={response} />

      {shouldShowNumericEvidence && (
        <>
          <div className="number-grid" aria-label="수치 근거">
            {displayedNumericEvidence.map((item, index) => (
              <div className="number-card" key={`${item.evidence_id}-${index}`}>
                <span>{item.label}</span>
                <strong>{numericText(item.value, item.unit)}</strong>
                <small>{item.basis}</small>
              </div>
            ))}
          </div>
          {hasHiddenNumericEvidence && (
            <button
              className="evidence-toggle number-evidence-toggle"
              type="button"
              onClick={() => setAllNumericEvidenceOpen((value) => !value)}
              aria-expanded={allNumericEvidenceOpen}
            >
              <span>
                {allNumericEvidenceOpen
                  ? "숫자 근거 접기"
                  : `숫자 근거 전체 ${response.numeric_evidence.length}개 보기`}
              </span>
              <Icon name="chevron" size={16} />
            </button>
          )}
        </>
      )}

      <EducationalPortfolioReview evaluation={response.educational_portfolio_evaluation} />

      <NewsCards response={response} />

      {response.visualizations.map((visualization, index) => (
        <ChatVisualization
          visualization={visualization}
          key={`${visualization.kind}-${index}`}
        />
      ))}

      {response.intent !== "etf_theme" && followUpCards}

      {/* narration_reasoning은 thinking 요약이라 대부분 영어로 나와 화면에 노출하지 않는다.
          응답 필드는 그대로 유지해 디버깅·로그에서 확인한다. */}

      {response.data_mode !== "news_summary" && response.sections.map((section, index) => (
        <Fragment key={`${section.title}-${index}`}>
          <details className={`answer-section section-${section.kind}${section.blocks?.length ? " rich-answer-section" : ""}`} open={response.data_mode === "verified_pension_account_overview" || response.data_mode === "verified_pension_account_deferred_topic" || response.data_mode === "theme_candidates" || response.data_mode === "theme_component_holdings" || section.kind === "limitation"}>
            <summary>
              <span>{section.title}{sectionPreview(section.content) && ` — ${sectionPreview(section.content)}`}</span>
              <small>내용 보기</small>
            </summary>
            {section.blocks?.length ? (
              <>
                {section.content && <p>{displayText(section.content)}</p>}
                <AnswerBlocks blocks={section.blocks} />
              </>
            ) : (
              <p>{displayText(section.content)}</p>
            )}
          </details>
          {response.intent === "etf_theme" && index === 0 && followUpCards}
        </Fragment>
      ))}

      {response.limitations.length > 0 && (
        <details className="limitation-box">
          <summary>
            <span><Icon name="shield" size={18} /> 확인할 점 {response.limitations.length}가지 보기</span>
            <Icon name="chevron" size={16} />
          </summary>
          <div>
            {response.limitations.map((item, index) => <p key={index}>{item}</p>)}
          </div>
        </details>
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
  if (error instanceof ApiError && typeof error.code === "string") return apiErrorMessage(error);
  if (error instanceof ApiError && error.status === 401) {
    return "로그인이 만료되었습니다. 다시 로그인해 주세요.";
  }
  if (error instanceof ApiError && error.status === 503) {
    return "대화 저장소에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  }
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

export function GuidePage({
  auth,
  initialScenarioCode,
  onBack,
  onOpenPlanner,
  onSignOut,
  surveyProfile,
  userContext,
  typingIntervalMs = DEFAULT_TYPING_INTERVAL_MS,
}: {
  auth: SupabaseAuthState;
  initialScenarioCode?: string;
  onBack?: () => void;
  onOpenPlanner?: () => void;
  onSignOut: () => Promise<void>;
  surveyProfile: CompletedSurveyProfile | null;
  userContext: DemoUserFinancialContext | null;
  typingIntervalMs?: number;
}) {
  const accessToken = auth.session?.access_token;
  const authenticatedUserId = auth.session?.user.id ?? null;
  const [input, setInput] = useState("");
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [chatCards, setChatCards] = useState<ChatCard[]>([]);
  const [chatCardsLoading, setChatCardsLoading] = useState(true);
  const [chatCardsRequestVersion, setChatCardsRequestVersion] = useState(0);
  const [allEtfThemesVisible, setAllEtfThemesVisible] = useState(false);
  const [selectedScenario, setSelectedScenario] = useState(initialScenarioCode ?? "");
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [serverReady, setServerReady] = useState<boolean | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [conversationContext, setConversationContext] =
    useState<ConversationContext | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [deletingAllSessions, setDeletingAllSessions] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState<string | null>(null);
  const [loginPanelOpen, setLoginPanelOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pensionSavingsBalance, setPensionSavingsBalance] = useState("");
  const [irpBalance, setIrpBalance] = useState("");
  const [pensionSavingsContribution, setPensionSavingsContribution] = useState("0");
  const [irpContribution, setIrpContribution] = useState("0");
  const [dcEmployeeContribution, setDcEmployeeContribution] = useState("0");
  const [dcEmployerContribution, setDcEmployerContribution] = useState("0");
  const [irpDeferredContribution, setIrpDeferredContribution] = useState("0");
  const [pensionAccountTransfer, setPensionAccountTransfer] = useState("0");
  const [isaMaturityTransfer, setIsaMaturityTransfer] = useState("0");
  const [isaEligibility, setIsaEligibility] =
    useState<IsaTransferEligibilityStatus>("none");
  const [isaPriorLimitUsed, setIsaPriorLimitUsed] = useState("0");
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
  const sessionListGenerationRef = useRef(0);

  const authStatusLabel = auth.loading
    ? "로그인 확인 중"
    : auth.session
      ? "로그인됨"
      : "로그인 필요";
  const authAvatarText = auth.loading
    ? "…"
    : auth.session
      ? (userContext?.nickname?.trim().charAt(0)
        || auth.session.user.email?.trim().charAt(0).toUpperCase()
        || "연")
      : "연금";

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

  const visibleChatCards = useMemo(() => filterChatCards(chatCards, {
    hasScenario: Boolean(selectedScenario || userContext?.scenario_code),
    hasSurvey: surveyProfile !== null,
    hasAuth: auth.session !== null,
  }), [auth.session, chatCards, selectedScenario, surveyProfile, userContext?.scenario_code]);

  const pensionTaxInput = useMemo<PensionTaxScenarioInput | undefined>(() => {
    if (!pensionSavingsBalance.trim() || !irpBalance.trim()) return undefined;
    if (incomeBasis !== "unknown" && !incomeAmount.trim()) return undefined;
    if (irpDeferredStatus === "known" && !irpDeferredAmount.trim()) return undefined;
    if (Number(isaMaturityTransfer || "0") > 0 && isaEligibility === "none") {
      return undefined;
    }
    if (Number(isaPriorLimitUsed || "0") > 0 && isaEligibility !== "eligible") {
      return undefined;
    }
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
      dc_employee_additional_contribution_krw: dcEmployeeContribution || "0",
      dc_employer_contribution_krw: dcEmployerContribution || "0",
      irp_deferred_retirement_income_contribution_krw:
        irpDeferredContribution || "0",
      pension_account_transfer_contribution_krw: pensionAccountTransfer || "0",
      isa_maturity_transfer_krw: isaMaturityTransfer || "0",
      isa_transfer_eligibility_status: isaEligibility,
      isa_additional_limit_used_prior_tax_year_krw: isaPriorLimitUsed || "0",
      withdrawal_reason: withdrawalReason,
      irp_deferred_income_status: irpDeferredStatus,
      ...(irpDeferredStatus === "known"
        ? { irp_deferred_retirement_income_krw: irpDeferredAmount }
        : {}),
    };
  }, [
    dcEmployeeContribution,
    dcEmployerContribution,
    incomeAmount,
    incomeBasis,
    irpBalance,
    irpContribution,
    irpDeferredContribution,
    irpDeferredAmount,
    irpDeferredStatus,
    isaEligibility,
    isaMaturityTransfer,
    isaPriorLimitUsed,
    pensionAccountTransfer,
    pensionSavingsBalance,
    pensionSavingsContribution,
    withdrawalReason,
  ]);

  const {
    isSending,
    messages,
    resetStream,
    sendingStage,
    setMessages,
    streamingAnswer,
    streamingAnswerIsNarration,
    submitPrompt,
  } = useChatStream({
    accessToken,
    authenticatedUserId,
    activeSessionId,
    conversationContext,
    conversationGenerationRef,
    deletingSessionId,
    selectedScenario,
    surveyProfile,
    isCurrentOperation,
    onAuthenticatedError: setHistoryError,
    onConversationContext: setConversationContext,
    onComplete: () => textareaRef.current?.focus(),
    onInputClear: () => setInput(""),
    onPersistedSession: (sessionId, token, userId) => {
      setActiveSessionId(sessionId);
      void refreshChatSessions(token, userId);
    },
    onServerReady: setServerReady,
    onStart: () => setHistoryLoading(false),
    getAuthGeneration: () => authGenerationRef.current,
  });

  const usedFollowUpMessages = useMemo(
    () => new Set(
      messages
        .filter((message) => message.role === "user")
        .map((message) => message.text.trim()),
    ),
    [messages],
  );

  useEffect(() => {
    // 백엔드는 임베더 로딩 때문에 프론트보다 늦게 뜨고, --reload로 잠깐 끊기기도
    // 한다. 한 번 실패하고 포기하면 서버가 살아나도 "API 연결 필요"로 굳으므로
    // 연결될 때까지 다시 시도한다.
    let cancelled = false;
    let retryTimer: number | undefined;
    let retryCount = 0;

    const check = () => {
      setChatCardsLoading(true);
      Promise.allSettled([
        accessToken ? getScenarios(accessToken) : Promise.resolve([]),
        getChatCards(),
      ])
        .then(([scenarioResult, cardsResult]) => {
          if (cancelled) return;
          if (scenarioResult.status === "fulfilled") {
            setScenarios(scenarioResult.value);
          }
          if (cardsResult.status === "fulfilled") {
            setChatCards(cardsResult.value.cards);
          }
          setChatCardsLoading(false);

          const errors = [scenarioResult, cardsResult]
            .filter((result): result is PromiseRejectedResult => result.status === "rejected")
            .map((result) => result.reason);
          if (errors.length === 0) {
            setServerReady(true);
            return;
          }

          setServerReady(false);
          const retryable = errors.some((error: unknown) => !(error instanceof ApiError)
            || error.status === undefined
            || error.status >= 500);
          const delay = SERVER_READY_RETRY_DELAYS_MS[retryCount];
          if (retryable && delay !== undefined) {
            retryCount += 1;
            retryTimer = window.setTimeout(check, delay);
          }
        });
    };

    check();
    return () => {
      cancelled = true;
      window.clearTimeout(retryTimer);
    };
  }, [accessToken, chatCardsRequestVersion]);

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
      sessionListGenerationRef.current += 1;
      resetStream();
      setHistoryLoading(false);
      setDeletingSessionId(null);
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
      setHistoryError(
        auth.loading
          ? null
          : auth.configured
            ? "로그인 세션이 없습니다. 로그인하면 저장된 대화를 다시 불러옵니다."
            : null,
      );
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
  }, [accessToken, authenticatedUserId, auth.configured, auth.loading]);

  useEffect(() => {
    if (userContext) setSelectedScenario(userContext.scenario_code);
  }, [userContext?.scenario_code]);

  useEffect(() => {
    if (messages.length > 0) {
      latestMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (isSending) {
      conversationEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isSending]);

  async function refreshChatSessions(token: string, userId: string) {
    const authGeneration = authGenerationRef.current;
    const sessionListGeneration = sessionListGenerationRef.current;
    try {
      const sessions = await getChatSessions(token);
      if (
        !isCurrentOperation(authGeneration, userId, token)
        || sessionListGenerationRef.current !== sessionListGeneration
      ) return;
      setChatSessions(sessions);
      setHistoryError(null);
    } catch (error) {
      if (
        !isCurrentOperation(authGeneration, userId, token)
        || sessionListGenerationRef.current !== sessionListGeneration
      ) return;
      setHistoryError(authenticatedErrorMessage(error));
    }
  }

  function startNewChat() {
    conversationGenerationRef.current += 1;
    resetStream();
    setMessages([]);
    setActiveSessionId(null);
    setConversationContext(null);
    setHistoryError(null);
    setHistoryLoading(false);
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
    resetStream();
    setAuthSubmitting(true);
      setMessages([]);
      setChatSessions([]);
      setActiveSessionId(null);
      setConversationContext(null);
    setHistoryError(null);
    setHistoryLoading(false);
    try {
      // 로그아웃은 화면 상태만 비운다. 저장된 대화는 명시적 삭제 버튼으로만 제거한다.
      await onSignOut();
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
    resetStream();
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
    const conversationGeneration = conversationGenerationRef.current;
    const deletedIndex = chatSessions.findIndex(
      (item) => item.session_id === session.session_id,
    );
    const focusSessionId = (
      chatSessions[deletedIndex + 1] ?? chatSessions[deletedIndex - 1]
    )?.session_id;
    sessionListGenerationRef.current += 1;
    setDeletingSessionId(session.session_id);
    setDeleteStatus(null);
    setHistoryError(null);
    try {
      await deleteChatSession(session.session_id, requestToken);
      if (!isCurrentOperation(authGeneration, requestUserId, requestToken)) return;
      setChatSessions((current) => current.filter(
        (item) => item.session_id !== session.session_id,
      ));
      sessionListGenerationRef.current += 1;
      setDeleteStatus("대화가 삭제되었습니다.");
      if (
        activeSessionId === session.session_id
        && conversationGenerationRef.current === conversationGeneration
      ) {
        conversationGenerationRef.current += 1;
        setMessages([]);
        setActiveSessionId(null);
        setConversationContext(null);
        setIsSidebarOpen(false);
      }
      const focusGeneration = conversationGenerationRef.current;
      window.setTimeout(() => {
        if (
          !isCurrentOperation(
            authGeneration,
            requestUserId,
            requestToken,
            focusGeneration,
          )
        ) return;
        const nextHistoryButton = Array.from(
          document.querySelectorAll<HTMLButtonElement>(".history-open"),
        ).find((button) => button.dataset.sessionId === focusSessionId);
        (nextHistoryButton ?? textareaRef.current)?.focus();
      }, 0);
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

  async function deleteAllStoredSessions() {
    if (
      !accessToken
      || !authenticatedUserId
      || historyLoading
      || isSending
      || deletingSessionId
      || deletingAllSessions
      || chatSessions.length === 0
    ) return;
    if (!window.confirm("저장된 모든 대화를 삭제할까요?\n삭제한 대화는 복구할 수 없습니다.")) {
      return;
    }

    const requestToken = accessToken;
    const requestUserId = authenticatedUserId;
    const authGeneration = authGenerationRef.current;
    sessionListGenerationRef.current += 1;
    setDeletingAllSessions(true);
    setDeleteStatus(null);
    setHistoryError(null);
    try {
      try {
        await deleteAllChatSessions(requestToken);
      } catch (error) {
        // During a rolling API update an older server may not have the
        // collection DELETE route yet. The established per-session route
        // still enforces the same owner boundary, so use it only for that
        // compatibility case.
        if (
          !(error instanceof ApiError)
          || (error.status !== 404 && error.status !== 405)
        ) {
          throw error;
        }
        await Promise.all(
          chatSessions.map((session) => deleteChatSession(
            session.session_id,
            requestToken,
          )),
        );
      }
      if (!isCurrentOperation(authGeneration, requestUserId, requestToken)) return;
      conversationGenerationRef.current += 1;
      setChatSessions([]);
      setMessages([]);
      setActiveSessionId(null);
      setConversationContext(null);
      setDeleteStatus("저장된 모든 대화를 삭제했습니다.");
      window.setTimeout(() => textareaRef.current?.focus(), 0);
    } catch (error) {
      if (!isCurrentOperation(authGeneration, requestUserId, requestToken)) return;
      setHistoryError(authenticatedErrorMessage(error));
    } finally {
      if (isCurrentOperation(authGeneration, requestUserId, requestToken)) {
        setDeletingAllSessions(false);
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
              <ChatSessionList
                activeSessionId={activeSessionId}
                chatSessions={chatSessions}
                deleteStatus={deleteStatus}
                deletingAllSessions={deletingAllSessions}
                deletingSessionId={deletingSessionId}
                historyLoading={historyLoading}
                isSending={isSending}
                onDelete={(session) => void deleteStoredSession(session)}
                onDeleteAll={() => void deleteAllStoredSessions()}
                onLoad={(sessionId) => void loadStoredSession(sessionId)}
              />
            </>
          ) : auth.configured ? (
            <>
              <button className="login-toggle" type="button" onClick={() => setLoginPanelOpen((open) => !open)}>
                로그인하고 대화 저장
              </button>
              {loginPanelOpen && (
                <form className="login-form" onSubmit={handleLogin}>
                  <label>
                    <span>로그인 ID</span>
                    <input type="text" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" placeholder="예: seoyeon34" required />
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
          <p className="sidebar-label">내 연금계좌</p>
          {userContext ? (
            <div className="user-context-card">
              <strong>{userContext.nickname.replace(/\(가상\)/g, "")}</strong>
              <span>{userContext.scenario_name}</span>
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
                <span><strong>{scenario.name}</strong><small title={scenario.risk_profile}>{scenario.age_band} · {scenario.investment_horizon_years}년 · {SCENARIO_RISK_PROFILE_LABELS[scenario.risk_profile] ?? "기타 투자성향"}</small></span>
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
              <span>올해 IRP 본인 추가납입액</span>
              <input type="number" min="0" inputMode="numeric" value={irpContribution} onChange={(event) => setIrpContribution(event.target.value)} />
            </label>
            <label>
              <span>올해 DC 근로자 본인 추가납입액</span>
              <input type="number" min="0" inputMode="numeric" value={dcEmployeeContribution} onChange={(event) => setDcEmployeeContribution(event.target.value)} />
            </label>
            <label>
              <span>올해 DC 회사 부담금(공제 제외)</span>
              <input type="number" min="0" inputMode="numeric" value={dcEmployerContribution} onChange={(event) => setDcEmployerContribution(event.target.value)} />
            </label>
            <label>
              <span>올해 IRP 퇴직급여 이전액(공제 제외)</span>
              <input type="number" min="0" inputMode="numeric" value={irpDeferredContribution} onChange={(event) => setIrpDeferredContribution(event.target.value)} />
            </label>
            <label>
              <span>연금계좌 간 이전액(공제 제외)</span>
              <input type="number" min="0" inputMode="numeric" value={pensionAccountTransfer} onChange={(event) => setPensionAccountTransfer(event.target.value)} />
            </label>
            <label>
              <span>ISA 만기자금 연금계좌 전환액</span>
              <input type="number" min="0" inputMode="numeric" value={isaMaturityTransfer} onChange={(event) => setIsaMaturityTransfer(event.target.value)} />
            </label>
            <label>
              <span>ISA 전환 적격 여부</span>
              <select value={isaEligibility} onChange={(event) => setIsaEligibility(event.target.value as IsaTransferEligibilityStatus)}>
                <option value="none">전환액 없음</option>
                <option value="eligible">법정 요건 확인됨</option>
                <option value="unknown">확인 필요</option>
              </select>
            </label>
            {isaEligibility === "eligible" && (
              <label>
                <span>전년도에 사용한 ISA 추가 한도</span>
                <input type="number" min="0" max="3000000" inputMode="numeric" value={isaPriorLimitUsed} onChange={(event) => setIsaPriorLimitUsed(event.target.value)} />
              </label>
            )}
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
            <span>{serverReady === null ? "서버 확인 중" : serverReady ? "저장 API 연결됨" : "API 연결 필요"}</span>
          </div>
          <p>실제 주문을 실행하지 않는<br />자문·정보 제공형 서비스입니다.</p>
        </div>
      </aside>

      {isSidebarOpen && <button className="sidebar-backdrop" type="button" aria-label="메뉴 닫기" onClick={() => setIsSidebarOpen(false)} />}

      <main className="chat-main">
        <header className="topbar design-topbar">
          <button className="menu-button design-menu-button" type="button" aria-label={onBack ? "뒤로 가기" : "메뉴 열기"} onClick={onBack ?? (() => setIsSidebarOpen(true))}>
            <span aria-hidden="true"><i /><i /><i /></span>
          </button>
          <button
            className="design-history-button"
            type="button"
            onClick={startNewChat}
            aria-label="새 대화 시작"
          >
            <span aria-hidden="true">＋</span> 새 대화
          </button>
          <div className="design-topbar-actions">
            <Icon name="database" size={25} />
            <span className={`design-auth-state ${auth.session ? "authenticated" : "anonymous"}`}>
              {authStatusLabel}
            </span>
            {auth.session && <button type="button" className="design-logout" onClick={() => void handleLogout()} disabled={authSubmitting}>로그아웃</button>}
            <button
              className={`design-avatar ${auth.session ? "authenticated" : "anonymous"}`}
              type="button"
              aria-label={`${authStatusLabel} · 계정 메뉴 열기`}
              title={authStatusLabel}
              onClick={() => setIsSidebarOpen(true)}
            >
              {authAvatarText}
            </button>
          </div>
        </header>

        <div className="conversation" aria-live="polite">
          {messages.length === 0 ? (
            <div className="welcome design-welcome">
              <div className="design-brand">
                <span className="design-brand-mark">연금</span>
                <strong>연금 <em>도우미</em></strong>
              </div>
              <div className="design-intro-row">
                <span className="design-intro-avatar" aria-hidden="true">연금</span>
                <p>막막한 노후 준비, <em>연금 도우미</em>와 대화하며 풀어보세요.</p>
              </div>

              {(userContext || selectedScenarioData) && (
                <div className="selected-scenario-card">
                  <div><Icon name="database" size={19} /></div>
                  <span>
                    <strong>{userContext?.nickname ?? selectedScenarioData?.name}</strong>
                    <small>{userContext?.customer_context ?? selectedScenarioData?.description}</small>
                  </span>
                </div>
              )}

              <ChatQuestionRecommendations
                cards={visibleChatCards.filter((card) => card.intent !== "etf_theme")}
                isLoading={chatCardsLoading}
                onSubmit={(message) => void submitPrompt(message)}
                onRetry={() => setChatCardsRequestVersion((version) => version + 1)}
              />

              {onOpenPlanner && (
                <section className="chat-home-card-section" aria-labelledby="planner-heading">
                  <header className="chat-home-section-heading">
                    <p>연금 수령 계획</p>
                    <h2 id="planner-heading">가정 시나리오로 수령 계획 점검</h2>
                    <span>
                      {surveyProfile
                        ? "현재 잔액과 월 납입액을 바탕으로 규칙 엔진의 가정별 적립금과 월 수령액을 비교합니다."
                        : "투자 성향을 먼저 확인한 뒤, 규칙 엔진의 가정 시나리오로 수령 계획을 점검합니다."}
                    </span>
                  </header>
                  <div className="prompt-carousel">
                    <button
                      aria-label="연금 수령 계획 시나리오 열기"
                      onClick={onOpenPlanner}
                      type="button"
                    >
                      <span className="design-prompt-copy">
                        <small>규칙 엔진 가정</small>
                        <strong>연금 수령 계획</strong>
                        <em>계획 시나리오 열기</em>
                      </span>
                    </button>
                  </div>
                </section>
              )}

              <section className="chat-home-card-section holdings-section" aria-labelledby="holdings-heading">
                <header className="chat-home-section-heading">
                  <p>내 ETF 점검</p>
                  <h2 id="holdings-heading">현재 보유 ETF 리밸런싱 가이드</h2>
                  <span>평가금액을 입력하면 계좌 한도와 자산군 편중을 규칙 엔진으로 점검합니다.</span>
                </header>
                <PortfolioHoldingsPanel
                  surveyProfile={surveyProfile}
                  disabled={isSending || deletingSessionId !== null}
                  onAnalyze={(portfolio) => void submitPrompt(
                    "현재 보유 ETF의 중복도와 계좌 한도, 리밸런싱 가이드를 보여줘",
                    portfolio,
                  )}
                />
              </section>

              <ChatEtfThemeCards
                allVisible={allEtfThemesVisible}
                onSubmit={(message) => void submitPrompt(message)}
                onToggle={() => setAllEtfThemesVisible((visible) => !visible)}
                themeCards={ETF_THEME_CARDS}
              />

              <p className="capability-note">연금 도우미는 참고용 정보를 제공하며, 실제 투자·가입 결정은 본인의 판단과 전문가 상담을 거쳐 주세요.</p>
            </div>
          ) : (
            <ChatMessageList
              conversationEndRef={conversationEndRef}
              deletingSessionId={deletingSessionId}
              isSending={isSending}
              latestMessageRef={latestMessageRef}
              messages={messages}
              onRetry={(message) => void submitPrompt(message.failedPrompt!, message.failedEducationalPortfolio)}
              renderMessage={(message) => (
                <AssistantMessage
                  onFollowUp={(prompt) => void submitPrompt(prompt)}
                  onOpenPlanner={onOpenPlanner}
                  response={message.response}
                  text={message.text}
                  usedFollowUpMessages={usedFollowUpMessages}
                />
              )}
              renderStreamingAnswer={() => streamingAnswer ? (
                <div className="message-bubble" aria-live="polite">
                  <ChatTypingAnswer
                    animate={!streamingAnswerIsNarration}
                    intervalMs={typingIntervalMs}
                    onProgress={() => conversationEndRef.current?.scrollIntoView({
                      behavior: "smooth",
                      block: "end",
                    })}
                    text={streamingAnswer}
                  />
                </div>
              ) : null}
              sendingStage={sendingStage}
            />
          )}
        </div>

        <ChatComposer
          deletingSessionId={deletingSessionId}
          input={input}
          isSending={isSending}
          onChange={setInput}
          onKeyDown={handleKeyDown}
          onSubmit={handleSubmit}
          textareaRef={textareaRef}
        />
      </main>
    </div>
  );
}
