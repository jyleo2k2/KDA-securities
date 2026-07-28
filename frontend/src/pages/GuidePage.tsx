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

import profileIcon from "../assets/chatbot/profile-icon.webp";
import yeongeumiProfile from "../assets/login/piggy-clean.png";
import {
  ApiError,
  apiErrorMessage,
  deleteChatSession,
  deleteAllChatSessions,
  getChatCards,
  getChatSessions,
  getScenarios,
  getStoredChatMessages,
  getRebalancingReminder,
  getRebalancingProfile,
  getMyPensionAccounts,
  updateRebalancingReminder,
  completeRebalancingReview,
  withoutDemoNameMarker,
} from "../api/client";
import { RebalancingReminderCard } from "../components/RebalancingReminderCard";
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
  AnswerSection,
  CompletedSurveyProfile,
  ChatCard,
  ChatVisualization as ChatVisualizationData,
  ConversationContext,
  ChatResponse,
  ChatSessionSummary,
  DataBoundary,
  DemoUserFinancialContext,
  EducationalPortfolioInput,
  IncomeBasis,
  IrpDeferredIncomeStatus,
  IsaTransferEligibilityStatus,
  NumericEvidence,
  PensionTaxScenarioInput,
  ScenarioSummary,
  StoredChatMessage,
  RebalancingReminderState,
  WithdrawalReason,
} from "../api/types";
import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import { useChatStream, type ConversationMessage } from "../hooks/useChatStream";
import { buildActualRebalancingReviewRequest } from "../rebalancingReviewRequest";

const INTENT_LABELS: Record<ChatResponse["intent"], string> = {
  account_rule: "계좌 규칙",
  mock_portfolio: "내 계좌 진단",
  provider_disclosure: "공식 공시",
  news: "증시 뉴스",
  pension_tax: "세액공제·중도해지",
  etf_theme: "ETF 테마",
  etf_distribution: "ETF 분배금",
  educational_portfolio: "연금 운용전략",
  macro_evidence: "거시지표 근거",
  glossary: "용어 설명",
  strategy_glossary: "투자 전략",
  investing_principle: "투자 원리",
  hesitation_support: "운용 고민",
  getting_started: "시작 안내",
  out_of_scope: "지원 범위 안내",
};

const NUMBER_EVIDENCE_DEFAULT_LIMIT = 6;
const PLANNING_RETURN_SECTION_SUFFIX = "장기 계산에 쓰는 수익률 가정";
const BASE_PLANNING_RETURN_LABEL = "기본으로 계산한 수익률 가정";
const CONSERVATIVE_PLANNING_RETURN_LABEL = "조심해서 계산한 수익률 가정";

const BOUNDARY_LABELS: Record<DataBoundary, string> = {
  verified_knowledge: "공식 안내 근거",
  official_disclosure: "공식 공시",
  official_statistics: "공식 통계",
  news_metadata: "기사 정보",
  news_summary: "기사 요약",
  mock: "계좌 정보",
  engine: "계산 근거",
  user_input: "입력한 정보",
  unavailable: "확인 필요",
};

const DEFAULT_TYPING_INTERVAL_MS = 50;
const CHAT_SESSION_PAGE_SIZE = 20;
const SERVER_READY_RETRY_DELAYS_MS = [3000, 6000, 12000] as const;
const PENSION_TAX_LOCAL_INCOME_TAX_NOTICE =
  "세액공제율과 세액공제액은 지방소득세를 고려해서 계산했어요.";

function visualizationItemsMatch(
  left: ChatVisualizationData,
  right: ChatVisualizationData,
): boolean {
  if (left.items.length !== right.items.length) return false;
  const ordered = (visualization: ChatVisualizationData) => [...visualization.items]
    .sort((a, b) => a.label.localeCompare(b.label, "ko"));

  return ordered(left).every((item, index) => {
    const other = ordered(right)[index];
    if (
      item.label !== other.label
      || item.unit !== other.unit
      || item.role !== other.role
    ) return false;
    const itemValue = Number(item.value);
    const otherValue = Number(other.value);
    return Number.isFinite(itemValue) && Number.isFinite(otherValue)
      ? Math.abs(itemValue - otherValue) < 0.0001
      : String(item.value) === String(other.value);
  });
}

export function collapseSharedStrategyAllocation(
  visualizations: ChatVisualizationData[],
): ChatVisualizationData[] {
  const allocations = visualizations.filter(
    (item) => item.kind === "sleeve_allocation",
  );
  if (
    allocations.length < 2
    || !allocations.every((item) => visualizationItemsMatch(allocations[0], item))
  ) return visualizations;

  return [
    {
      ...allocations[0],
      title: "보유 계좌 공통 목표 자산배분",
      description: "현재 조건에서는 보유한 연금계좌의 목표 비중이 같아요.",
      evidence_ids: Array.from(
        new Set(allocations.flatMap((item) => item.evidence_ids)),
      ),
    },
    ...visualizations.filter((item) => item.kind !== "sleeve_allocation"),
  ];
}

export function collapseSharedStrategyStressScenarios(
  visualizations: ChatVisualizationData[],
): ChatVisualizationData[] {
  const stressScenarios = visualizations.filter(
    (item) => item.kind === "stress_scenarios",
  );
  if (
    stressScenarios.length < 2
    || !stressScenarios.every((item) => (
      visualizationItemsMatch(stressScenarios[0], item)
    ))
  ) return visualizations;

  let insertedCommonScenario = false;
  return visualizations.flatMap((item) => {
    if (item.kind !== "stress_scenarios") return [item];
    if (insertedCommonScenario) return [];
    insertedCommonScenario = true;
    return [{
      ...stressScenarios[0],
      title: "보유 계좌 공통 스트레스 점검",
      description: "현재 조건에서는 보유한 연금계좌의 스트레스 손실 추정치가 같아요.",
      evidence_ids: Array.from(
        new Set(stressScenarios.flatMap((scenario) => scenario.evidence_ids)),
      ),
    }];
  });
}

const ACCOUNT_SHARED_SECTION_TITLE_PATTERN = (
  /^(DC형|IRP|연금저축펀드) · (.+(?:전략|수익률 가정))$/
);

export function collapseSharedAccountSections(
  sections: AnswerSection[],
): AnswerSection[] {
  const sectionsBySharedTitle = new Map<string, AnswerSection[]>();
  sections.forEach((section) => {
    const titleMatch = section.title.match(ACCOUNT_SHARED_SECTION_TITLE_PATTERN);
    if (!titleMatch) return;
    const sharedTitle = titleMatch[2];
    sectionsBySharedTitle.set(
      sharedTitle,
      [...(sectionsBySharedTitle.get(sharedTitle) ?? []), section],
    );
  });

  const collapsibleSectionsByTitle = new Map<string, AnswerSection[]>();
  sectionsBySharedTitle.forEach((accountSections, sharedTitle) => {
    if (accountSections.length < 2) return;
    const first = accountSections[0];
    const allSectionsMatch = accountSections.every((section) => (
      section.kind === first.kind
      && section.content === first.content
      && JSON.stringify(section.blocks ?? []) === JSON.stringify(first.blocks ?? [])
    ));
    if (allSectionsMatch) {
      collapsibleSectionsByTitle.set(sharedTitle, accountSections);
    }
  });
  if (collapsibleSectionsByTitle.size === 0) return sections;

  const insertedSharedTitles = new Set<string>();
  return sections.flatMap((section) => {
    const titleMatch = section.title.match(ACCOUNT_SHARED_SECTION_TITLE_PATTERN);
    if (!titleMatch) return [section];
    const sharedTitle = titleMatch[2];
    const accountSections = collapsibleSectionsByTitle.get(sharedTitle);
    if (!accountSections) return [section];
    if (insertedSharedTitles.has(sharedTitle)) return [];
    insertedSharedTitles.add(sharedTitle);
    const first = accountSections[0];
    return [{
      ...first,
      title: `보유 계좌 공통 · ${sharedTitle}`,
      evidence_ids: Array.from(
        new Set(accountSections.flatMap((item) => item.evidence_ids)),
      ),
    }];
  });
}

function withoutStagflationStressScenario(
  visualizations: ChatVisualizationData[],
): ChatVisualizationData[] {
  return visualizations.flatMap((visualization) => {
    if (visualization.kind !== "stress_scenarios") return [visualization];
    const items = visualization.items.filter(
      (item) => item.label !== "스태그플레이션",
    );
    return items.length > 0 ? [{ ...visualization, items }] : [];
  });
}

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

function compactPlanningReturnBasis(basis: string): string {
  return basis
    .replace("과 ", "·")
    .replace("을 넣은 계산", " 반영");
}

function planningReturnEvidenceForSection(
  numericEvidence: NumericEvidence[],
  sectionTitle: string,
  evidenceLabel: string,
): NumericEvidence | undefined {
  const accountLabel = sectionTitle.match(/^(DC형|IRP|연금저축펀드) · /)?.[1];
  if (accountLabel) {
    return numericEvidence.find(
      (item) => item.label === `${accountLabel} · ${evidenceLabel}`,
    );
  }

  const matchingEvidence = numericEvidence.filter((item) => (
    item.label === evidenceLabel || item.label.endsWith(` · ${evidenceLabel}`)
  ));
  const first = matchingEvidence[0];
  if (!first) return undefined;
  return matchingEvidence.every((item) => (
    String(item.value) === String(first.value)
    && item.unit === first.unit
    && item.basis === first.basis
  ))
    ? first
    : undefined;
}

function PlanningReturnAssumptionCards({
  numericEvidence,
  sectionTitle,
  fallback,
}: {
  numericEvidence: NumericEvidence[];
  sectionTitle: string;
  fallback: string;
}) {
  const cards = [
    {
      label: "기본 수익률",
      evidence: planningReturnEvidenceForSection(
        numericEvidence,
        sectionTitle,
        BASE_PLANNING_RETURN_LABEL,
      ),
    },
    {
      label: "보수적 수익률",
      evidence: planningReturnEvidenceForSection(
        numericEvidence,
        sectionTitle,
        CONSERVATIVE_PLANNING_RETURN_LABEL,
      ),
    },
  ];
  if (cards.some(({ evidence }) => !evidence)) {
    return <p>{displayText(fallback)}</p>;
  }

  return (
    <div className="return-assumption-summary" aria-label="장기 수익률 가정">
      <div className="return-assumption-grid">
        {cards.map(({ label, evidence }) => (
          <div className="return-assumption-card" key={label}>
            <span>{label}</span>
            <strong>{numericText(evidence!.value, evidence!.unit)}</strong>
            <small>{compactPlanningReturnBasis(evidence!.basis)}</small>
          </div>
        ))}
      </div>
      <p className="return-assumption-note">
        두 값 모두 장기 전망(CMA)과 ETF 비용을 반영하며, 보수적 수익률에는
        여유 폭을 더 적용해요. 미래 수익을 보장하는 값은 아니에요.
      </p>
    </div>
  );
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

const REPRESENTATIVE_COMPANY_LABELS = [
  "테마에서의 역할:",
  "쉽게 말하면:",
] as const;
const PENSION_ACCOUNT_LABELS = [
  "한눈에 보면:",
  "핵심 특징:",
] as const;
const THEME_PARAGRAPH_GAP = "10pt";

function CalloutCopy({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/).map((paragraph) => paragraph.trim()).filter(Boolean);
  const labels = [REPRESENTATIVE_COMPANY_LABELS, PENSION_ACCOUNT_LABELS].find(
    (candidate) => (
      paragraphs.length === candidate.length
      && paragraphs.every((paragraph, index) =>
        paragraph.startsWith(candidate[index]),
      )
    ),
  );

  if (paragraphs.length <= 1) {
    return <p>{displayText(text)}</p>;
  }

  return (
    <div className="answer-callout-copy">
      {paragraphs.map((paragraph, index) => {
        if (!labels) {
          return <p key={`${paragraph}-${index}`}>{displayText(paragraph)}</p>;
        }
        const label = labels[index];
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
  const visibleGroups = evaluation.groups
    .map((group) => ({
      ...group,
      etfs: group.etfs.filter((etf) => etf.horizons.length > 0),
    }))
    .filter((group) => group.etfs.length > 0);
  if (visibleGroups.length === 0) return null;

  return (
    <section className="macro-regime-card" aria-label="과거 유사국면 ETF 근거 카드">
      <header>
        <span>과거 실적 근거</span>
        <h3>유사국면 이후 ETF 총수익률·최대낙폭</h3>
        <p>국면 다음 달 첫 거래일부터 계산한 실제 관측값이며 미래 예측이나 자동 리밸런싱 신호가 아니에요.</p>
      </header>
      <details className="macro-regime-disclosure" open>
        <summary>
          <span><strong>과거 실적은 필요할 때 확인</strong><small>{visibleGroups.length}개 유사국면</small></span>
          <em>펼쳐보기</em>
        </summary>
        <div className="macro-regime-list">
          {visibleGroups.map((group) => {
            const outcomeStartDate = group.etfs
              .flatMap((etf) => etf.horizons)
              .map((horizon) => horizon.start_date)
              .sort()[0];
            return (
              <details key={group.regime_period} open>
              <summary>
                <strong>{regimeMonth(outcomeStartDate ?? group.regime_period)} 시작 구간</strong>
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
            );
          })}
        </div>
      </details>
    </section>
  );
}

function AssistantMessage({
  requestPrompt,
  response,
  text,
  onFollowUp,
  onOpenPlanner,
  onOpenStrategyPick,
  onAnalyzeHoldings,
  surveyProfile,
  disabled,
  usedFollowUpMessages,
}: {
  requestPrompt?: string;
  response?: ChatResponse;
  text: string;
  onFollowUp?: (message: string) => void;
  onOpenPlanner?: () => void;
  onOpenStrategyPick?: (prompt: string) => void;
  onAnalyzeHoldings?: (portfolio: EducationalPortfolioInput) => void;
  surveyProfile: CompletedSurveyProfile | null;
  userName: string | null;
  disabled: boolean;
  usedFollowUpMessages: ReadonlySet<string>;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [allNumericEvidenceOpen, setAllNumericEvidenceOpen] = useState(false);

  if (!response) return <p className="message-copy">{text}</p>;

  const isEducationalPortfolio = response.intent === "educational_portfolio";
  const educationalEvaluation = response.educational_portfolio_evaluation;
  const educationalProfileLabel = educationalEvaluation
    ? {
      stable: "안정형",
      stable_seeking: "안정추구형",
      risk_neutral: "위험중립형",
      active: "적극투자형",
      aggressive: "공격투자형",
    }[educationalEvaluation.evaluated_input.risk_profile]
    : undefined;
  const educationalFinalRiskTarget = Number(
    educationalEvaluation?.final_general_risk_target_percent,
  );
  const educationalRawRiskTarget = Number(
    educationalEvaluation?.raw_risk_target_percent,
  );
  const educationalLossToleranceAdjusted = (
    educationalEvaluation?.loss_tolerance_binding === true
    && Number.isFinite(educationalFinalRiskTarget)
    && Number.isFinite(educationalRawRiskTarget)
  );
  const isEducationalRebalancing = (
    isEducationalPortfolio
    && /리밸런싱|목표\s*비중.*(?:비교|이탈)|이탈폭/.test(requestPrompt ?? "")
  );
  const educationalResultLead = (
    isEducationalPortfolio
    && isEducationalRebalancing
    && educationalProfileLabel
    && educationalEvaluation?.strategy_label
  )
    ? `${educationalProfileLabel} 기준으로 한 ${educationalEvaluation.strategy_label}의 리밸런싱 결과입니다.`
    : undefined;
  const educationalStrategyLead = (
    isEducationalPortfolio
    && educationalProfileLabel
    && educationalEvaluation?.strategy_label
  )
    ? `현재 투자성향 설문 결과(${educationalProfileLabel})를 기준으로 한 예시 전략은 ${educationalEvaluation.strategy_label}입니다.`
    : undefined;
  const educationalLead = (
    educationalResultLead ?? educationalStrategyLead
  )
    ? educationalLossToleranceAdjusted
      ? (
        `${educationalResultLead ?? educationalStrategyLead} 선택한 손실감내율 `
        + `${Number(educationalEvaluation.evaluated_input.loss_tolerance_percent).toFixed(1)}%를 함께 반영했습니다. `
        + `손실감내율을 우선 적용해 성장자산 비중을 ${educationalRawRiskTarget.toFixed(1)}%에서 `
        + `${educationalFinalRiskTarget.toFixed(1)}%로 낮췄습니다.`
      )
      : educationalResultLead ?? educationalStrategyLead
    : undefined;
  const isPensionTaxCredit = (
    response.intent === "pension_tax"
    && response.pension_tax_result?.tax_credit != null
  );
  const isMissedTaxCredit = (
    response.data_mode === "missed_pension_tax_credit_engine"
  );
  const showPensionTaxBreakdown = isPensionTaxCredit && !isMissedTaxCredit;
  const isPensionTaxRelated = (
    isPensionTaxCredit
    || response.data_mode === "verified_pension_tax_rule_brief"
  );
  const isPensionAccountBrief = (
    response.data_mode === "verified_pension_account_brief"
  );
  const visibleFollowUps = (isEducationalPortfolio ? [] : response.suggested_follow_ups ?? []).filter(
    (followUp) => (
      !isPensionAccountBrief
      && (
        !isPensionTaxRelated
        || followUp.follow_up_id === "tax_to_diff"
        || followUp.follow_up_id === "tax_missed_benefit"
        || followUp.follow_up_id === "account_to_diff"
      )
      && !usedFollowUpMessages.has(followUp.message.trim())
    ),
  );
  const taxSummaryVisualization = showPensionTaxBreakdown
    ? response.visualizations.find((item) => (
      item.kind === "tax_summary" && item.title === "세액공제 요약"
    ))
    : undefined;
  const isEducationalStrategyGuide = (
    isEducationalPortfolio
    && !isEducationalRebalancing
  );
  const hiddenEducationalSummaryVisualizations = (
    isEducationalPortfolio
    && isEducationalRebalancing
  )
    ? response.visualizations.filter((item) => (
      item.kind === "sleeve_allocation" || item.kind === "stress_scenarios"
    ))
    : [];
  const educationalStrategySourceVisualizations = isEducationalStrategyGuide
    ? response.visualizations.filter((item) => (
      item.kind === "sleeve_allocation" || item.kind === "stress_scenarios"
    ))
    : [];
  const educationalStrategyVisualizations = isEducationalStrategyGuide
    ? collapseSharedStrategyStressScenarios(
      withoutStagflationStressScenario(
        collapseSharedStrategyAllocation(educationalStrategySourceVisualizations),
      ),
    )
    : [];
  const remainingVisualizations = (isMissedTaxCredit
    ? response.visualizations.filter((item) => item.kind !== "tax_summary")
    : taxSummaryVisualization
      ? response.visualizations.filter((item) => item !== taxSummaryVisualization)
      : response.visualizations
  ).filter((item) => (
    !hiddenEducationalSummaryVisualizations.includes(item)
    && !educationalStrategySourceVisualizations.includes(item)
  ));
  const visibleNumericEvidence = isMissedTaxCredit
    ? []
    : isPensionTaxCredit
    ? response.numeric_evidence.filter(
      (item) => !item.label.endsWith("법정 세액공제액"),
    )
    : response.numeric_evidence;
  const visibleSections = isEducationalStrategyGuide
    ? collapseSharedAccountSections(
      response.sections.filter(
        (section) => (
          section.title !== "적용한 MVP 설문 조건"
          && !section.title.endsWith("ETF 분야 살펴보기")
        ),
      ),
    )
    : isEducationalPortfolio
    ? []
    : isPensionTaxCredit
    ? response.sections.filter(
      (section) => section.title !== "당해연도 세액공제 간이 계산",
    )
    : response.sections;
  const visibleLimitations = isPensionTaxCredit
    ? Array.from(new Set([
      ...response.limitations,
      PENSION_TAX_LOCAL_INCOME_TAX_NOTICE,
    ]))
    : response.limitations;
  const legacyIncomeLabel = taxSummaryVisualization?.items.find(
    (item) => item.label === "총급여액" || item.label === "종합소득금액",
  )?.label;
  const numericEvidenceLabel = (label: string): string => {
    if (label === "소득금액" && legacyIncomeLabel) return legacyIncomeLabel;
    if (label === "확인된 소득구간 표시율") return "세액공제율";
    if (label === "연금저축 당해연도 납입액") return "올해 연금저축 납입액";
    if (label === "IRP 당해연도 납입액") return "올해 IRP 납입액";
    if (label === "합산 세액공제 대상 납입액") return "세액공제대상 납입액";
    if (label === "확인된 소득구간 지방세 포함 예상 절세효과") {
      return "세액공제액";
    }
    if (label.endsWith("법정 세액공제율")) {
      return "지방세 제외 세액공제율";
    }
    return label;
  };
  const shouldShowHoldingsPanel = (
    response.intent === "educational_portfolio"
    || response.data_mode === "etf_selection_required"
  );
  const shouldShowNumericEvidence = (
    response.intent !== "mock_portfolio"
    && response.intent !== "macro_evidence"
    && !isEducationalPortfolio
    && response.data_mode !== "theme_candidates"
    && response.data_mode !== "theme_component_holdings"
    && response.data_mode !== "verified_pension_account_brief"
    && response.data_mode !== "verified_pension_tax_rule_brief"
    && visibleNumericEvidence.length > 0
  );
  const hasHiddenNumericEvidence = (
    visibleNumericEvidence.length > NUMBER_EVIDENCE_DEFAULT_LIMIT
  );
  const displayedNumericEvidence = allNumericEvidenceOpen
    ? visibleNumericEvidence
    : visibleNumericEvidence.slice(0, NUMBER_EVIDENCE_DEFAULT_LIMIT);
  const numericEvidenceCards = shouldShowNumericEvidence ? (
    <>
      <div
        className="number-grid"
        aria-label="수치 근거"
        style={isPensionTaxCredit
          ? { gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }
          : undefined}
      >
        {displayedNumericEvidence.map((item, index) => (
          <div
            className="number-card"
            key={`${item.evidence_id}-${index}`}
            style={{ minWidth: 0, padding: 12 }}
          >
            <span style={{ fontSize: 10, lineHeight: 1.4 }}>
              {numericEvidenceLabel(item.label)}
            </span>
            <strong
              style={{
                fontSize: isPensionTaxCredit
                  ? "clamp(13px, 3.4vw, 16px)"
                  : "clamp(16px, 4.5vw, 19px)",
                lineHeight: 1.2,
                letterSpacing: isPensionTaxCredit ? "-0.02em" : undefined,
                margin: "5px 0 0",
                overflowWrap: isPensionTaxCredit ? "normal" : "anywhere",
                whiteSpace: isPensionTaxCredit ? "nowrap" : undefined,
              }}
            >
              {numericText(item.value, item.unit)}
            </strong>
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
              : isPensionTaxCredit
                ? "숫자 근거 더보기"
                : `숫자 근거 전체 ${visibleNumericEvidence.length}개 보기`}
          </span>
          <Icon name="chevron" size={16} />
        </button>
      )}
    </>
  ) : null;
  const followUpCards = visibleFollowUps.length > 0 ? (
    <div className="follow-up-cards" aria-label="이어서 물어보기">
      {visibleFollowUps.map((followUp) => (
        <button key={followUp.follow_up_id} onClick={() => followUp.follow_up_id === "open_pension_planner" ? onOpenPlanner?.() : onFollowUp?.(followUp.message)} type="button">
          {followUp.label}<Icon name="chevron" size={14} />
        </button>
      ))}
    </div>
  ) : null;
  const strategyPickCta = isEducationalPortfolio ? (
    <div className="follow-up-cards" aria-label="연금KDA 전략 더보기">
      <button type="button" onClick={() => onOpenStrategyPick?.("ㅇㅇ")} disabled={disabled}>
        연금KDA의 전략 더 보여드릴까요?<Icon name="chevron" size={14} />
      </button>
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
      </div>
      {response.intent !== "macro_evidence" && (response.data_mode !== "news_summary" || response.news_items.length === 0) && (
        <p className="message-copy">
          {response.salutation && <><strong>{response.salutation},</strong>{" "}</>}
          {displayText(
            showPensionTaxBreakdown
              ? response.answer.split(/\r?\n/, 1)[0]
              : educationalLead ?? response.answer,
          )}
        </p>
      )}

      {showPensionTaxBreakdown && taxSummaryVisualization && (
        <ChatVisualization
          visualization={taxSummaryVisualization}
          sources={response.sources}
        />
      )}
      {showPensionTaxBreakdown && (
        <p className="message-copy" style={{ marginTop: 20 }}>
          세액공제액은 이렇게 계산했어요.
        </p>
      )}
      {showPensionTaxBreakdown && numericEvidenceCards}

      <MacroEvidenceCards response={response} />
      <MacroRegimeOutcomeCards response={response} />

      {!showPensionTaxBreakdown && numericEvidenceCards}

      <EducationalPortfolioReview
        evaluation={response.educational_portfolio_evaluation}
        showStrategyGuide={isEducationalStrategyGuide}
        visualizations={educationalStrategyVisualizations}
        sources={response.sources}
      />

      {shouldShowHoldingsPanel && onAnalyzeHoldings && (
        <PortfolioHoldingsPanel
          surveyProfile={surveyProfile}
          disabled={disabled}
          onAnalyze={onAnalyzeHoldings}
        />
      )}

      <NewsCards response={response} />

      {remainingVisualizations.map((visualization, index) => (
        <ChatVisualization
          visualization={visualization}
          sources={response.sources}
          key={`${visualization.kind}-${index}`}
        />
      ))}

      {response.intent !== "etf_theme" && followUpCards}

      {/* narration_reasoning은 thinking 요약이라 대부분 영어로 나와 화면에 노출하지 않는다.
          응답 필드는 그대로 유지해 디버깅·로그에서 확인한다. */}

      {response.data_mode !== "news_summary" && visibleSections.map((section, index) => (
        <Fragment key={`${section.title}-${index}`}>
          <details className={`answer-section section-${section.kind}${section.blocks?.length ? " rich-answer-section" : ""}${section.title.endsWith(PLANNING_RETURN_SECTION_SUFFIX) ? " return-assumption-section" : ""}`} open={isEducationalStrategyGuide || response.data_mode === "verified_pension_account_overview" || response.data_mode === "verified_pension_account_deferred_topic" || response.data_mode === "verified_pension_account_brief" || response.data_mode === "verified_pension_tax_rule_brief" || response.data_mode === "theme_candidates" || response.data_mode === "theme_component_holdings" || section.kind === "limitation"}>
            <summary>
              <span>{section.title}</span>
              <small>내용 보기</small>
            </summary>
            {section.title.endsWith(PLANNING_RETURN_SECTION_SUFFIX) ? (
              <PlanningReturnAssumptionCards
                numericEvidence={response.numeric_evidence}
                sectionTitle={section.title}
                fallback={section.content}
              />
            ) : section.blocks?.length ? (
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

      {strategyPickCta}

      {visibleLimitations.length > 0 && (
        <details className="limitation-box">
          <summary>
            <span><Icon name="shield" size={18} /> 확인할 점 {visibleLimitations.length}가지 보기</span>
            <Icon name="chevron" size={16} />
          </summary>
          <div>
            {visibleLimitations.map((item, index) => <p key={index}>{item}</p>)}
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
    return "대화를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.";
  }
  return "답변을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.";
}

export function GuidePage({
  auth,
  initialHistoryOpen = false,
  initialScenarioCode,
  onBack,
  onOpenPlanner,
  onOpenProfile,
  onOpenStrategyPick,
  onPortfolioDiagnosisConsumed,
  onSignOut,
  portfolioDiagnosisRequestId,
  surveyProfile,
  userContext,
  typingIntervalMs = DEFAULT_TYPING_INTERVAL_MS,
}: {
  auth: SupabaseAuthState;
  initialHistoryOpen?: boolean;
  initialScenarioCode?: string;
  onBack?: () => void;
  onOpenPlanner?: () => void;
  onOpenProfile?: () => void;
  onOpenStrategyPick?: (prompt: string) => void;
  onPortfolioDiagnosisConsumed?: () => void;
  onSignOut: () => Promise<void>;
  portfolioDiagnosisRequestId?: string;
  surveyProfile: CompletedSurveyProfile | null;
  userContext: DemoUserFinancialContext | null;
  typingIntervalMs?: number;
}) {
  const accessToken = auth.session?.access_token;
  const authenticatedUserId = auth.session?.user.id ?? null;
  const [input, setInput] = useState("");
  const [rebalancingReminder, setRebalancingReminder] = useState<RebalancingReminderState | null>(null);
  const [reminderBusy, setReminderBusy] = useState(false);
  const [reminderLoading, setReminderLoading] = useState(true);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [chatCards, setChatCards] = useState<ChatCard[]>([]);
  const [chatCardsLoading, setChatCardsLoading] = useState(true);
  const [chatCardsRequestVersion, setChatCardsRequestVersion] = useState(0);
  const [selectedScenario, setSelectedScenario] = useState(initialScenarioCode ?? "");
  const [isSidebarOpen, setIsSidebarOpen] = useState(initialHistoryOpen);
  const [serverReady, setServerReady] = useState<boolean | null>(null);
  const [chatSessions, setChatSessions] = useState<ChatSessionSummary[]>([]);
  const [visibleSessionCount, setVisibleSessionCount] = useState(CHAT_SESSION_PAGE_SIZE);
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
  const conversationRef = useRef<HTMLDivElement>(null);
  const latestMessageRef = useRef<HTMLDivElement>(null);
  const previousAuthRef = useRef<{
    userId: string | null;
    accessToken: string | null;
  }>({ userId: null, accessToken: null });
  const currentAuthRef = useRef<{
    userId: string | null;
    accessToken: string | null;
  }>({ userId: authenticatedUserId, accessToken: accessToken ?? null });
  const consumedPortfolioDiagnosisRequestRef = useRef<string | null>(null);
  const authGenerationRef = useRef(0);
  const conversationGenerationRef = useRef(0);
  const sessionListGenerationRef = useRef(0);

  const authStatusLabel = auth.loading
    ? "로그인 확인 중"
    : auth.session
      ? "로그인됨"
      : "로그인 필요";

  currentAuthRef.current = {
    userId: authenticatedUserId,
    accessToken: accessToken ?? null,
  };

  useEffect(() => {
    if (!accessToken) { setRebalancingReminder(null); setReminderLoading(false); return; }
    setReminderLoading(true);
    void getRebalancingReminder(accessToken)
      .then(setRebalancingReminder)
      .catch(() => setRebalancingReminder(null))
      .finally(() => setReminderLoading(false));
  }, [accessToken]);

  async function enableReminder() { if (!accessToken) return; setReminderBusy(true); try { setRebalancingReminder(await updateRebalancingReminder(true, accessToken)); } finally { setReminderBusy(false); } }
  async function completeReminder() { if (!accessToken) return; setReminderBusy(true); try { setRebalancingReminder(await completeRebalancingReview(accessToken)); } finally { setReminderBusy(false); } }

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
    stopStream,
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
      if (isSidebarOpen) void refreshChatSessions(token, userId);
    },
    onServerReady: setServerReady,
    onStart: () => setHistoryLoading(false),
    getAuthGeneration: () => authGenerationRef.current,
  });

  useEffect(() => {
    if (
      !accessToken
      || !portfolioDiagnosisRequestId
      || consumedPortfolioDiagnosisRequestRef.current === portfolioDiagnosisRequestId
      || chatCardsLoading
      || isSending
      || messages.length > 0
    ) return;

    const portfolioCard = visibleChatCards.find(
      (card) => card.card_id === "edu_portfolio",
    );
    if (!portfolioCard) return;

    consumedPortfolioDiagnosisRequestRef.current = portfolioDiagnosisRequestId;
    onPortfolioDiagnosisConsumed?.();
    void submitPrompt(portfolioCard.message);
  }, [
    accessToken,
    chatCardsLoading,
    isSending,
    messages.length,
    onPortfolioDiagnosisConsumed,
    portfolioDiagnosisRequestId,
    submitPrompt,
    visibleChatCards,
  ]);

  const usedFollowUpMessages = useMemo(
    () => new Set(
      messages
        .filter((message) => message.role === "user")
        .map((message) => message.text.trim()),
    ),
    [messages],
  );

  function appendRebalancingReviewNotice(message: string) {
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        text: message,
        createdAt: new Date(),
      },
    ]);
  }

  async function requestActualRebalancingReview() {
    if (!accessToken) {
      appendRebalancingReviewNotice("저장된 투자성향과 로그인된 계좌가 있어야 실제 보유 비중을 점검할 수 있어요.");
      return;
    }

    setReminderBusy(true);
    try {
      const [profile, portfolio] = await Promise.all([
        surveyProfile ? Promise.resolve(surveyProfile) : getRebalancingProfile(accessToken),
        getMyPensionAccounts(accessToken),
      ]);
      const review = buildActualRebalancingReviewRequest(profile, portfolio);
      if (review.status !== "ready") {
        appendRebalancingReviewNotice(
          review.status === "account_not_found"
            ? "저장한 투자성향의 계좌와 연결된 보유내역을 찾지 못했어요. 계좌 연동 상태를 확인한 뒤 다시 요청해 주세요."
            : "점검할 보유자산 금액이 아직 없어요. 계좌 보유내역을 확인한 뒤 다시 요청해 주세요.",
        );
        return;
      }
      await submitPrompt(
        "리밸런싱 점검해줘",
        review.input,
      );
    } catch {
      appendRebalancingReviewNotice("계좌 보유내역을 불러오지 못해 실제 비중 점검을 시작하지 못했어요. 잠시 후 다시 요청해 주세요.");
    } finally {
      setReminderBusy(false);
    }
  }

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
      setChatSessions([]);
      setVisibleSessionCount(CHAT_SESSION_PAGE_SIZE);
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
            ? "로그인하면 지난 대화를 이어서 볼 수 있어요."
            : null,
      );
      setHistoryLoading(false);
      return;
    }
    if (!isSidebarOpen) {
      setHistoryLoading(false);
      return;
    }

    let active = true;
    setHistoryLoading(true);
    setHistoryError(null);
    void getChatSessions(accessToken)
      .then((sessions) => {
        if (active) {
          setChatSessions(sessions);
          setVisibleSessionCount(CHAT_SESSION_PAGE_SIZE);
        }
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
  }, [accessToken, authenticatedUserId, auth.configured, auth.loading, isSidebarOpen]);

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
      setVisibleSessionCount(CHAT_SESSION_PAGE_SIZE);
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
          requestPrompt: message.question_message_id
            ? stored.find((candidate) => candidate.message_id === message.question_message_id)?.content
            : undefined,
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
    const sessionsToDelete = chatSessions.filter(
      (session) => session.session_id !== activeSessionId,
    );
    if (
      !accessToken
      || !authenticatedUserId
      || historyLoading
      || isSending
      || deletingSessionId
      || deletingAllSessions
      || sessionsToDelete.length === 0
    ) return;
    const confirmationMessage = activeSessionId
      ? "현재 대화를 제외한 지난 대화를 모두 지울까요?\n삭제 후에는 되돌릴 수 없어요."
      : "지난 대화를 모두 지울까요?\n삭제 후에는 되돌릴 수 없어요.";
    if (!window.confirm(confirmationMessage)) {
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
      if (activeSessionId) {
        await Promise.all(
          sessionsToDelete.map((session) => deleteChatSession(
            session.session_id,
            requestToken,
          )),
        );
      } else {
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
            sessionsToDelete.map((session) => deleteChatSession(
              session.session_id,
              requestToken,
            )),
          );
        }
      }
      if (!isCurrentOperation(authGeneration, requestUserId, requestToken)) return;
      setChatSessions((current) => current.filter(
        (session) => session.session_id === activeSessionId,
      ));
      setVisibleSessionCount(CHAT_SESSION_PAGE_SIZE);
      setDeleteStatus(
        activeSessionId
          ? "현재 대화를 제외한 지난 대화를 지웠어요."
          : "지난 대화를 모두 지웠어요.",
      );
      window.setTimeout(() => textareaRef.current?.focus(), 0);
    } catch (error) {
      if (!isCurrentOperation(authGeneration, requestUserId, requestToken)) return;
      setHistoryError(authenticatedErrorMessage(error));
      void refreshChatSessions(requestToken, requestUserId);
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

  const welcomeName = userContext?.nickname
    ?? (
      typeof auth.session?.user?.user_metadata?.name === "string"
        ? withoutDemoNameMarker(auth.session.user.user_metadata.name)
        : "고객"
    );

  return (
    <div className="app-shell">
      <aside className={`sidebar ${isSidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand design-drawer-heading">
          <strong>지난 대화</strong>
          <button type="button" aria-label="지난 대화 닫기" onClick={() => setIsSidebarOpen(false)}>×</button>
        </div>

        <button className="new-chat" type="button" onClick={startNewChat}>
          <span>＋</span> 새 대화 시작
        </button>

        <div className="auth-panel">
          {auth.loading ? (
            <p className="auth-note">로그인 상태 확인 중...</p>
          ) : auth.session ? (
            <>
              <div className="auth-user">
                <span><strong>내 대화</strong><small>{auth.session.user.email ?? "인증 사용자"}</small></span>
                <button type="button" onClick={() => void handleLogout()} disabled={authSubmitting}>로그아웃</button>
              </div>
              {isSidebarOpen && (
                <ChatSessionList
                  activeSessionId={activeSessionId}
                  chatSessions={chatSessions.slice(0, visibleSessionCount)}
                  deletableSessionCount={chatSessions.filter(
                    (session) => session.session_id !== activeSessionId,
                  ).length}
                  deleteStatus={deleteStatus}
                  deletingAllSessions={deletingAllSessions}
                  deletingSessionId={deletingSessionId}
                  hasMoreSessions={visibleSessionCount < chatSessions.length}
                  historyLoading={historyLoading}
                  isSending={isSending}
                  onDelete={(session) => void deleteStoredSession(session)}
                  onDeleteAll={() => void deleteAllStoredSessions()}
                  onLoadMore={() => setVisibleSessionCount((current) => (
                    current + CHAT_SESSION_PAGE_SIZE
                  ))}
                  onLoad={(sessionId) => void loadStoredSession(sessionId)}
                />
              )}
            </>
          ) : auth.configured ? (
            <>
              <button className="login-toggle" type="button" onClick={() => setLoginPanelOpen((open) => !open)}>
                로그인하고 대화 이어가기
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
            <p className="auth-note">로그인 설정을 완료하면 지난 대화를 이어서 볼 수 있어요.</p>
          )}
          {(historyError || auth.error) && <p className="auth-error">{historyError || auth.error}</p>}
        </div>

        <div className="sidebar-section">
          <p className="sidebar-label">내 연금계좌</p>
          {userContext ? (
            <div className="user-context-card">
              <strong>{userContext.nickname}</strong>
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
          <button className="menu-button design-back-button" type="button" aria-label="뒤로 가기" onClick={onBack ?? (() => setIsSidebarOpen(true))}>
            <svg aria-hidden="true" width="12" height="20" viewBox="0 0 12 20" fill="none"><path d="M9.5 1L1.5 10L9.5 19" /></svg>
          </button>
          <div className="chat-screen-title">
            <strong>연금 가이드</strong>
            <span><i aria-hidden="true" /> 연그미와 대화 중</span>
          </div>
          <div className="design-topbar-actions">
          <button
            className="design-history-button"
            type="button"
            onClick={() => setIsSidebarOpen(true)}
            aria-label="지난 대화 열기"
            title="지난 대화"
          >
            <Icon name="book" size={19} />
          </button>
            {auth.session && <button type="button" className="design-logout" onClick={() => void handleLogout()} disabled={authSubmitting}>로그아웃</button>}
            <button
              className={`design-avatar ${auth.session ? "authenticated" : "anonymous"}`}
              type="button"
              aria-label={`${authStatusLabel} · 프로필 화면 열기`}
              title={authStatusLabel}
              onClick={onOpenProfile}
            >
              <img src={profileIcon} alt="프로필" />
            </button>
          </div>
        </header>

        <div className="conversation" ref={conversationRef}>
          {messages.length === 0 ? (
            <div className="welcome design-welcome">
              <section className="chat-welcome-hero" aria-labelledby="chat-welcome-title">
                <span className="design-brand-avatar" aria-hidden="true">
                  <img src={yeongeumiProfile} alt="" />
                </span>
                <div className="chat-welcome-copy">
                  <span className="chat-welcome-eyebrow"><i aria-hidden="true" /> AI 연금 도우미 연그미</span>
                  <h1 id="chat-welcome-title">{welcomeName}님,<br />어떤 연금 고민이 있으세요?</h1>
                  <p>계좌별 규칙부터 절세, ETF 정보까지 근거와 함께 쉽게 설명해 드려요.</p>
                </div>
              </section>
              <div className="chat-welcome-scope" aria-label="연금 가이드 지원 영역">
                <span><Icon name="book" size={14} /> 계좌별 규칙</span>
                <span><Icon name="shield" size={14} /> 절세 점검</span>
                <span><Icon name="chart" size={14} /> ETF 정보</span>
              </div>

              {/* 리밸런싱 카드는 API 응답이 늦으므로 로딩 중 같은 골격의 스켈레톤으로 자리를 잡아 아래 추천 질문이 밀리지 않게 한다. */}
              <div className="welcome-intro-cards">
                {reminderLoading ? (
                  <div className="rebalancing-reminder-card is-skeleton" aria-hidden="true">
                    <strong><span className="skeleton-line" style={{ width: "58%" }} /></strong>
                    <p><span className="skeleton-line" /><span className="skeleton-line" style={{ width: "82%" }} /></p>
                    <div><span className="skeleton-line skeleton-button" /></div>
                    <small><span className="skeleton-line" style={{ width: "44%" }} /></small>
                  </div>
                ) : rebalancingReminder && (
                  <RebalancingReminderCard reminder={rebalancingReminder} busy={reminderBusy || isSending} onEnable={() => void enableReminder()} onComplete={() => void completeReminder()} onAsk={() => void requestActualRebalancingReview()} />
                )}
              </div>

              <ChatQuestionRecommendations
                cards={visibleChatCards.filter((card) => card.intent !== "etf_theme")}
                isLoading={chatCardsLoading}
                onSubmit={(message) => void submitPrompt(message)}
                onRetry={() => setChatCardsRequestVersion((version) => version + 1)}
              />

              <ChatEtfThemeCards
                onSubmit={(message) => void submitPrompt(message)}
                themeCards={ETF_THEME_CARDS}
              />

              <p className="capability-note">연금 도우미는 참고용 정보를 제공하며, 실제 투자·가입 결정은 본인의 판단과 전문가 상담을 거쳐 주세요.</p>
            </div>
          ) : (
            <ChatMessageList
              conversationEndRef={conversationEndRef}
              conversationKey={activeSessionId}
              deletingSessionId={deletingSessionId}
              isSending={isSending}
              latestMessageRef={latestMessageRef}
              messages={messages}
              onRetry={(message) => void submitPrompt(message.failedPrompt!, message.failedEducationalPortfolio)}
              renderMessage={(message) => (
                <AssistantMessage
                  requestPrompt={message.requestPrompt}
                  onFollowUp={(prompt) => void submitPrompt(prompt)}
                  onOpenPlanner={onOpenPlanner}
                  onOpenStrategyPick={onOpenStrategyPick}
                  onAnalyzeHoldings={(portfolio) => void submitPrompt(
                    "현재 보유 ETF의 중복도와 계좌 한도, 리밸런싱 가이드를 보여줘",
                    portfolio,
                  )}
                  response={message.response}
                  surveyProfile={surveyProfile}
                  userName={
                    userContext?.nickname
                    ?? (
                      typeof auth.session?.user?.user_metadata?.name === "string"
                        ? withoutDemoNameMarker(auth.session.user.user_metadata.name)
                        : null
                    )
                  }
                  disabled={isSending || deletingSessionId !== null}
                  text={message.text}
                  usedFollowUpMessages={usedFollowUpMessages}
                />
              )}
              renderStreamingAnswer={() => streamingAnswer ? (
                <div className="message-bubble">
                  <ChatTypingAnswer
                    animate={!streamingAnswerIsNarration}
                    intervalMs={typingIntervalMs}
                    onProgress={() => {
                      const el = conversationRef.current;
                      // 사용자가 위로 올려 읽는 중이면 따라가지 않는다. 바닥 근처일 때만, smooth 관성 없이 즉시 붙인다.
                      if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 120) {
                        el.scrollTop = el.scrollHeight;
                      }
                    }}
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
          onStop={stopStream}
          onSubmit={handleSubmit}
          textareaRef={textareaRef}
        />
      </main>
    </div>
  );
}
