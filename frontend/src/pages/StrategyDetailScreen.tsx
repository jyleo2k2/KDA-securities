import { useEffect, useState, type CSSProperties, type JSX } from "react";

import { getStrategyPlanningReturns } from "../api/client";
import type {
  AggregationEvaluation,
  AssetClass,
  StrategyPlanningReturnComponent,
  StrategyPlanningReturnEvaluation,
  UserPensionPortfolio,
} from "../api/types";
import { StatusBar } from "../components/StatusBar";
import {
  STRATEGIES,
  STRATEGY_INTRO_SUMMARIES,
  type StrategyExploreItem,
} from "./strategyExplore/strategies";
import "./StrategyDetailScreen.css";

interface StrategyDetailScreenProps {
  aggregation?: AggregationEvaluation | null;
  onBack: () => void;
  onPartnerBrokerClick?: () => void;
  pensionDataLoading?: boolean;
  portfolio?: UserPensionPortfolio | null;
}

const THEME_ALLOCATION_BY_AGE = [
  { age: "20대", percent: 10 },
  { age: "30대", percent: 8 },
  { age: "40대", percent: 4 },
  { age: "50~54세", percent: 2 },
] as const;

const THEME_CATEGORIES = ["AI", "반도체", "바이오", "인프라"] as const;

const STRATEGY_FIT_MESSAGES: Record<string, string> = {
  "market-beta": "특정 종목을 고르기보다 시장 전체에 오래 분산 투자하고 싶은 분께 잘 맞는 운용 방식이에요.",
  factor: "시장 전체 투자에 기업의 재무·가치·추세 기준을 더해 코어 자산을 보완하고 싶은 분께 잘 맞아요.",
  theme: "가격 변동을 감수하더라도 성장 산업을 연금의 제한된 보조 비중으로 활용하고 싶은 분께 적합해요.",
  topdown: "금리·물가·경기 흐름을 보며 국가·산업·자산군 비중을 조절하고 싶은 분께 잘 맞아요.",
  bottomup: "경제 전망보다 기업의 경쟁력과 재무·성장성을 꼼꼼히 살펴 투자하고 싶은 분께 잘 맞아요.",
  barbell: "성장 기회는 유지하면서 단기채·현금성 자산으로 가격 변동을 완충하고 싶은 분께 잘 맞아요.",
  volatility: "상승 수익의 일부를 놓칠 수 있어도 연금자산의 큰 등락을 줄이는 데 우선순위를 두는 분께 잘 맞아요.",
  longshort: "복잡한 운용 구조와 비용을 확인하고 시장 방향 노출을 낮춘 보조 전략을 찾는 분께 적합해요.",
  eventdriven: "기업 이벤트의 성사·무산 위험을 이해하고 제한된 비중으로 기회를 살펴보려는 분께 적합해요.",
  trend: "추세가 바뀔 때의 손실과 비용을 감수하고 여러 자산의 흐름을 규칙으로 활용하려는 분께 적합해요.",
};

const STRATEGY_TRADEOFFS: Record<string, { benefit: string; risk: string }> = {
  "market-beta": {
    benefit: "시장 전체에 넓게 분산하고 운용 기준을 단순하게 유지할 수 있어요.",
    risk: "시장 하락을 그대로 겪을 수 있고, 시장 평균을 크게 웃도는 성과를 목표로 하지는 않아요.",
  },
  factor: {
    benefit: "기업 특성을 정해진 기준으로 선별해 종목 선택 과정을 일관되게 유지할 수 있어요.",
    risk: "선택한 팩터의 부진이 오래 이어질 수 있고, 최근 성과를 좇으면 손실 위험이 커질 수 있어요.",
  },
  theme: {
    benefit: "산업 구조 변화가 기대되는 분야의 성장 기회를 보조 비중으로 활용할 수 있어요.",
    risk: "소수 산업·종목에 집중될 수 있고, 높은 기대가 이미 가격에 반영됐을 수 있어요.",
  },
  topdown: {
    benefit: "금리·물가·경기 변화에 맞춰 자산군의 역할을 능동적으로 조절할 수 있어요.",
    risk: "거시 전망이 빗나가면 비중 조정이 오히려 손실을 키울 수 있어요.",
  },
  bottomup: {
    benefit: "기업의 경쟁력과 재무상태를 바탕으로 투자 대상을 선별할 수 있어요.",
    risk: "기업 분석이 틀릴 수 있고 액티브 상품의 비용과 종목 집중도를 확인해야 해요.",
  },
  barbell: {
    benefit: "성장자산과 안정화 자산의 역할을 분리해 변동에 대응하기 쉬워요.",
    risk: "비중을 주기적으로 맞추지 않으면 의도한 위험 완충 효과가 약해질 수 있어요.",
  },
  volatility: {
    benefit: "시장 변동이 커질 때 위험자산 비중을 낮춰 큰 등락을 줄이는 데 도움을 줄 수 있어요.",
    risk: "손실을 없애는 전략은 아니며, 빠른 상승장에서는 수익 일부를 놓칠 수 있어요.",
  },
  longshort: {
    benefit: "시장 상승·하락 방향에 대한 노출을 낮추는 보조 역할을 기대할 수 있어요.",
    risk: "운용 구조가 복잡하고 비용이 높을 수 있으며, 연금계좌 편입 가능 상품이 제한될 수 있어요.",
  },
  eventdriven: {
    benefit: "시장 전체 흐름과 다른 기업 이벤트의 가격 변화를 활용할 수 있어요.",
    risk: "거래 무산·일정 변경·규제 변수로 예상과 다른 손실이 발생할 수 있어요.",
  },
  trend: {
    benefit: "주식·채권 등 여러 자산의 방향성을 같은 규칙으로 살펴볼 수 있어요.",
    risk: "추세가 자주 바뀌는 구간에서는 연속 손실과 매매 비용이 커질 수 있어요.",
  },
};

const STRATEGY_ENGINE_IDS: Record<string, string> = {
  "market-beta": "market_beta",
  factor: "factor",
  theme: "thematic",
  topdown: "top_down",
  bottomup: "bottom_up",
  barbell: "barbell",
  volatility: "volatility_managed",
  longshort: "market_neutral",
  eventdriven: "event_driven",
  trend: "trend_global_macro",
};

const STRESS_SCENARIO_LABELS: Record<string, string> = {
  equity_drawdown: "주식 급락",
  rate_inflation_shock: "금리·물가 충격",
  stagflation: "경기 둔화·고물가",
};

const ASSET_CLASS_PRESENTATION: Record<string, { label: string; color: string }> = {
  global_equity: { label: "국내 상장 해외주식형 ETF·공모펀드", color: "#3d92d0" },
  global_60_40: { label: "국내 상장 글로벌 혼합형 ETF·공모펀드", color: "#607d8b" },
  us_10y_treasury: { label: "국내 상장 해외채권형 ETF·공모펀드", color: "#7586b0" },
  cash: { label: "현금성 자산", color: "#d9a24d" },
  us_large_cap_equity: { label: "국내 상장 해외주식형 ETF·공모펀드", color: "#3d92d0" },
  us_investment_grade_credit: { label: "국내 상장 해외채권형 ETF·공모펀드", color: "#6f7fa8" },
};

const PENSION_ASSET_PRESENTATION: Record<AssetClass, { label: string; color: string }> = {
  cash: { label: "현금성", color: "#d9a24d" },
  deposit: { label: "원리금보장", color: "#a8b6bc" },
  bond: { label: "채권형 ETF·펀드", color: "#7586b0" },
  domestic_equity: { label: "국내주식형 ETF·펀드", color: "#1ea766" },
  global_equity: { label: "해외주식형 ETF·펀드", color: "#3d92d0" },
  alternative: { label: "대체자산형 ETF·펀드", color: "#a075b7" },
  eligible_tdf: { label: "적격 TDF", color: "#f28c4b" },
  default_option: { label: "디폴트옵션", color: "#667a74" },
};

interface AllocationDisplayItem {
  color: string;
  key: string;
  label: string;
  percent: string;
}

function selectedStrategy(): StrategyExploreItem {
  const hash = typeof window !== "undefined" ? window.location.hash : "";
  const query = hash.includes("?") ? hash.slice(hash.indexOf("?") + 1) : "";
  const id = new URLSearchParams(query).get("strategy");
  return STRATEGIES.find((item) => item.id === id) ?? STRATEGIES[0];
}

function strategyCheckMessage(strategy: StrategyExploreItem): string {
  if (strategy.directness === "계좌별 매수 가능 상품 확인") {
    return "연금계좌에서 매수할 수 있는 상품인지, 상품 설명서의 운용 구조와 비용을 먼저 확인해요.";
  }

  return "전체 연금자산에서 맡을 역할을 정하고, 계좌별 규칙과 상품 비용을 함께 확인해요.";
}

function highlightStrategyTerms(
  text: string,
  strategy: StrategyExploreItem,
  extraTerms: string[] = [],
): Array<string | JSX.Element> {
  const terms = [...new Set([
    ...extraTerms,
    ...strategy.keywords,
    ...strategy.easyWords.map((item) => item.word),
  ])]
    .filter((term) => term.length > 1 && text.includes(term))
    .sort((left, right) => right.length - left.length);

  if (terms.length === 0) return [text];

  const escapedTerms = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const termPattern = new RegExp(`(${escapedTerms.join("|")})`, "g");

  return text.split(termPattern).map((part, index) => (
    terms.includes(part)
      ? <mark className="sd-highlight" key={`${part}-${index}`}>{part}</mark>
      : part
  ));
}

function assetClassPresentation(component: StrategyPlanningReturnComponent): {
  label: string;
  color: string;
} {
  return ASSET_CLASS_PRESENTATION[component.cma_bucket] ?? {
    label: component.cma_bucket,
    color: "#7d8a83",
  };
}

function formatPercent(value: string): string {
  const percent = Number(value);
  return Number.isInteger(percent) ? `${percent}%` : `${percent.toFixed(1)}%`;
}

function formatSourceDate(value: string): string {
  return value.replaceAll("-", ".");
}

function formatKrw(value: string): string {
  return `${Math.round(Number(value)).toLocaleString("ko-KR")}원`;
}

function latestPortfolioDate(portfolio?: UserPensionPortfolio | null): string | null {
  const dates = portfolio?.accounts.map((account) => account.as_of_date).filter(Boolean) ?? [];
  return dates.length > 0 ? [...dates].sort().at(-1) ?? null : null;
}

function currentPensionAllocation(
  aggregation?: AggregationEvaluation | null,
): AllocationDisplayItem[] {
  return aggregation?.asset_class_totals
    .map((item) => ({
      color: PENSION_ASSET_PRESENTATION[item.asset_class].color,
      key: item.asset_class,
      label: PENSION_ASSET_PRESENTATION[item.asset_class].label,
      percent: item.weight_percent,
    }))
    .sort((left, right) => Number(right.percent) - Number(left.percent)) ?? [];
}

function strategyAllocation(
  planningReturn: StrategyPlanningReturnEvaluation | null,
): AllocationDisplayItem[] {
  return planningReturn?.components.map((component) => ({
    ...assetClassPresentation(component),
    key: component.cma_bucket,
    percent: component.target_percent,
  })) ?? [];
}

function AllocationBreakdown({
  ariaLabel,
  items,
}: {
  ariaLabel: string;
  items: AllocationDisplayItem[];
}): JSX.Element {
  return (
    <>
      <div
        className="sd-composition-bar"
        aria-label={`${ariaLabel}: ${items
          .map((item) => `${item.label} ${formatPercent(item.percent)}`)
          .join(", ")}`}
      >
        {items.map((item) => (
          <span
            key={item.key}
            style={{
              width: `${Number(item.percent)}%`,
              backgroundColor: item.color,
            }}
          />
        ))}
      </div>

      <ul className="sd-composition-legend">
        {items.map((item) => (
          <li key={item.key}>
            <i aria-hidden="true" style={{ backgroundColor: item.color }} />
            <span>{item.label}</span>
            <strong>{formatPercent(item.percent)}</strong>
          </li>
        ))}
      </ul>
    </>
  );
}

export function StrategyDetailScreen({
  aggregation,
  onBack,
  onPartnerBrokerClick,
  pensionDataLoading = false,
  portfolio,
}: StrategyDetailScreenProps): JSX.Element {
  const strategy = selectedStrategy();
  const isThemeStrategy = strategy.id === "theme";
  const [planningReturn, setPlanningReturn] =
    useState<StrategyPlanningReturnEvaluation | null>(null);
  const [compositionStatus, setCompositionStatus] =
    useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let isActive = true;
    const engineStrategyId = STRATEGY_ENGINE_IDS[strategy.id];

    setPlanningReturn(null);
    setCompositionStatus("loading");

    void getStrategyPlanningReturns()
      .then((evaluations) => {
        if (!isActive) return;
        const selectedEvaluation = evaluations.find(
          (evaluation) => evaluation.strategy_id === engineStrategyId,
        );

        if (!selectedEvaluation) {
          setCompositionStatus("error");
          return;
        }

        setPlanningReturn(selectedEvaluation);
        setCompositionStatus("ready");
      })
      .catch(() => {
        if (isActive) setCompositionStatus("error");
      });

    return () => {
      isActive = false;
    };
  }, [strategy.id]);

  const compositionSource = planningReturn?.sources.find(
    (source) => source.label === "홈 전략 카드 대표구성 정책",
  );
  const stressRisk = planningReturn?.stress_risk;
  const pensionAllocation = currentPensionAllocation(aggregation);
  const representativeAllocation = strategyAllocation(planningReturn);
  const pensionAsOfDate = latestPortfolioDate(portfolio);
  const introSummary = STRATEGY_INTRO_SUMMARIES[strategy.id] ?? {
    desc: strategy.desc,
    keywords: strategy.keywords,
  };
  const fitMessage = STRATEGY_FIT_MESSAGES[strategy.id];
  const tradeoffs = STRATEGY_TRADEOFFS[strategy.id];

  const comparisonContent = (
    <>
      <section
        className="sd-strategy-allocation"
        aria-labelledby="strategy-allocation-title"
      >
        <div className="sd-strategy-allocation-heading">
          <div>
            <span>현재와 전략을 한눈에</span>
            <h2 id="strategy-allocation-title">내 연금과 자산군 비교</h2>
          </div>
          <strong>연금 KDA 기준</strong>
        </div>

        <section className="sd-comparison-panel is-current" aria-labelledby="current-pension-title">
          <div className="sd-comparison-panel-heading">
            <h3 id="current-pension-title">내 연금 현재 구성</h3>
            {aggregation && <strong>{formatKrw(aggregation.total_amount_krw)}</strong>}
          </div>

          {pensionDataLoading && (
            <p className="sd-composition-state">연결된 연금 구성을 확인하고 있어요.</p>
          )}

          {!pensionDataLoading && pensionAllocation.length === 0 && (
            <p className="sd-composition-state">
              연금계좌를 연결하면 현재 구성과 전략 구성을 함께 비교할 수 있어요.
            </p>
          )}

          {!pensionDataLoading && pensionAllocation.length > 0 && (
            <>
              <AllocationBreakdown
                ariaLabel="내 연금 현재 자산군 구성"
                items={pensionAllocation}
              />
              <span className="sd-source-chip">
                기준: 연결된 연금계좌 합산
                {pensionAsOfDate ? ` · ${formatSourceDate(pensionAsOfDate)}` : ""}
              </span>
            </>
          )}
        </section>

        <div className="sd-comparison-guide" aria-hidden="true">
          <span>↓</span>
          아래 전략의 대표 구성과 비교해보세요
        </div>

        <section className="sd-comparison-panel" aria-labelledby="representative-strategy-title">
          <div className="sd-comparison-panel-heading">
            <h3 id="representative-strategy-title">{strategy.name} 편입 상품군</h3>
            <strong>국내 연금계좌 기준</strong>
          </div>

          {compositionStatus === "loading" && (
            <p className="sd-composition-state">자산군 구성을 확인하고 있어요.</p>
          )}

          {compositionStatus === "error" && (
            <p className="sd-composition-state is-error">
              자산군 구성을 불러오지 못했어요. 잠시 후 다시 확인해주세요.
            </p>
          )}

          {compositionStatus === "ready" && representativeAllocation.length > 0 && (
            <>
              <AllocationBreakdown
                ariaLabel={`${strategy.name} 연금계좌 편입 상품군 구성`}
                items={representativeAllocation}
              />
              {compositionSource && (
                <span className="sd-source-chip">
                  기준: {compositionSource.label} · {formatSourceDate(compositionSource.as_of)}
                </span>
              )}
            </>
          )}
        </section>

      </section>

      {isThemeStrategy && (
        <section className="sd-theme-allocation" aria-labelledby="theme-allocation-title">
          <div className="sd-theme-allocation-heading">
            <div>
              <span>함께 참고해요</span>
              <h2 id="theme-allocation-title">연령대별 테마 활용 비중 예시</h2>
            </div>
            <strong>공격투자형 운용안</strong>
          </div>

          <ul className="sd-theme-age-bars">
            {THEME_ALLOCATION_BY_AGE.map((item) => (
              <li key={item.age}>
                <span>{item.age}</span>
                <i aria-hidden="true">
                  <b style={{ width: `${item.percent * 10}%` }} />
                </i>
                <strong>{item.percent}%</strong>
              </li>
            ))}
          </ul>

          <div className="sd-theme-categories">
            <span>주요 테마</span>
            <ul>
              {THEME_CATEGORIES.map((category) => (
                <li key={category}>{category}</li>
              ))}
            </ul>
          </div>

          <p>
            연령이 높아질수록 테마 비중을 줄이는 예시예요.
            AI·반도체·바이오·인프라의 세부 비중은 선택한 상품 구성에 따라 달라져요.
          </p>
          <span className="sd-source-chip">기준: 연금 KDA 공격형 전략 운용안 · 2026.07</span>
        </section>
      )}
    </>
  );

  return (
    <main
      className="app-phone-stage sd-stage"
      style={{ "--sd-accent": strategy.accent } as CSSProperties}
    >
      <section className="app-phone-frame sd-phone" aria-label={`${strategy.name} 상세`}>
        <StatusBar />

        <header className="sd-header">
          <button
            type="button"
            className="sd-back"
            data-strategy-detail-back
            onClick={onBack}
            aria-label="뒤로 가기"
          >
            ‹
          </button>
          <span className="sd-brand">연금 <em>KDA</em></span>
        </header>

        <div className="sd-scroll">
          <section className="sd-hero" aria-labelledby="strategy-detail-title">
            <div className="sd-hero-main">
              <div className="sd-hero-avatar">
                <img src={strategy.img} alt="" />
              </div>
              <div className="sd-hero-text">
                <span className="sd-badge">제휴 투자전략</span>
                <h1 className="sd-title" id="strategy-detail-title">{strategy.name}</h1>
                <p className="sd-desc">
                  {highlightStrategyTerms(introSummary.desc, strategy, introSummary.keywords)}
                </p>
              </div>
            </div>
          </section>

          <div className="sd-flow-heading">
            <span>읽는 순서</span>
            <strong>위에서 아래로 하나씩 살펴보세요</strong>
          </div>

          <ol className="sd-timeline" aria-label="전략 이해 순서">
            <li className="sd-timeline-item">
              <span className="sd-step-number" aria-hidden="true">1</span>
              <section className="sd-step-card">
                <div className="sd-step-meta">
                  <span className="sd-step-kicker">먼저</span>
                  <span className="sd-step-keyword">1단계 · 운용 방식</span>
                </div>
                <h2>이 전략은 이렇게 운용해요</h2>
                <p>{highlightStrategyTerms(strategy.howItWorks, strategy)}</p>
              </section>
            </li>

            <li className="sd-timeline-item">
              <span className="sd-step-number" aria-hidden="true">2</span>
              <section className="sd-step-card">
                <div className="sd-step-meta">
                  <span className="sd-step-kicker">나에게 맞을까?</span>
                  <span className="sd-step-keyword">2단계 · 이런 분께 좋아요</span>
                </div>
                <h2>이런 운용 방식을 원한다면 살펴보세요</h2>
                <p>{highlightStrategyTerms(fitMessage, strategy)}</p>
                {isThemeStrategy && (
                  <span className="sd-profile-chip">적합 투자성향 · 공격투자형</span>
                )}
              </section>
            </li>

            <li className="sd-timeline-item">
              <span className="sd-step-number" aria-hidden="true">3</span>
              <section className="sd-step-card sd-comparison-step-card">
                <div className="sd-step-meta">
                  <span className="sd-step-kicker">내 연금과 비교</span>
                  <span className="sd-step-keyword">3단계 · 자산군 비교</span>
                </div>
                {comparisonContent}
              </section>
            </li>

            <li className="sd-timeline-item">
              <span className="sd-step-number" aria-hidden="true">4</span>
              <section className="sd-step-card sd-check-card">
                <div className="sd-step-meta">
                  <span className="sd-step-kicker">마지막으로</span>
                  <span className="sd-step-keyword">4단계 · 장단점과 위험</span>
                </div>
                <h2>장점과 위험을 함께 확인해요</h2>
                <dl className="sd-tradeoffs">
                  <div className="is-benefit">
                    <dt>장점</dt>
                    <dd>{tradeoffs.benefit}</dd>
                  </div>
                  <div className="is-risk">
                    <dt>유의할 위험</dt>
                    <dd>{tradeoffs.risk}</dd>
                  </div>
                </dl>
                <section className="sd-stress-risk" aria-labelledby="strategy-stress-title">
                  <div className="sd-stress-risk-heading">
                    <div>
                      <span>대표 구성 위험 점검</span>
                      <h3 id="strategy-stress-title">정책 스트레스 시나리오</h3>
                    </div>
                    {stressRisk && (
                      <strong>
                        {formatPercent(stressRisk.worst_estimated_loss_percent)}
                        <small>
                          가장 큰 손실 · {STRESS_SCENARIO_LABELS[stressRisk.worst_scenario_code]
                            ?? stressRisk.worst_scenario_code}
                        </small>
                      </strong>
                    )}
                  </div>

                  {compositionStatus === "loading" && (
                    <p className="sd-stress-state">손실 추정치를 확인하고 있어요.</p>
                  )}

                  {compositionStatus === "error" && (
                    <p className="sd-stress-state is-error">
                      손실 추정치를 불러오지 못했어요. 잠시 후 다시 확인해주세요.
                    </p>
                  )}

                  {stressRisk && (
                    <>
                      <p className="sd-stress-explanation">
                        정해진 시장충격을 {strategy.name}의 대표 구성에 적용한 참고값이에요.
                        발생 확률이나 미래 최대손실, 손실 한도를 뜻하지 않으며 실제 손실은
                        더 커질 수 있어요.
                      </p>
                      <details className="sd-stress-details">
                        <summary>시나리오별 손실 추정치 보기</summary>
                        <ul>
                          {stressRisk.scenarios.map((scenario) => (
                            <li key={scenario.scenario_code}>
                              <span>
                                {STRESS_SCENARIO_LABELS[scenario.scenario_code]
                                  ?? scenario.scenario_code}
                              </span>
                              <strong>{formatPercent(scenario.estimated_loss_percent)}</strong>
                            </li>
                          ))}
                        </ul>
                      </details>
                      <span className="sd-source-chip">
                        기준: {stressRisk.source.label} · {formatSourceDate(stressRisk.source.as_of)}
                      </span>
                    </>
                  )}
                </section>
                <h3 className="sd-check-title">결정 전에 확인할 3가지</h3>
                <ul className="sd-check-list">
                  <li>
                    <strong>{strategy.directness}</strong>
                    {strategyCheckMessage(strategy)}
                  </li>
                  <li>최근 성과만 보고 판단하지 말고, 전략의 역할과 위험을 함께 살펴봐요.</li>
                  <li>상품 선택과 실제 주문은 제휴 증권사에서 직접 확인하고 결정해요.</li>
                </ul>
              </section>
            </li>
          </ol>

          <section className="sd-partner-panel">
            <button
              type="button"
              className="sd-partner-cta"
              aria-label="제휴 증권사로 이동"
              onClick={onPartnerBrokerClick}
            >
              제휴 증권사에서 상품 확인하기
              <span aria-hidden="true">→</span>
            </button>
          </section>

          <section className="sd-note">
            <p>
              이 화면은 전략을 이해하기 위한 정보입니다. 미래 수익률을 예측하거나
              특정 상품을 추천하지 않으며, 투자 결과에 따라 원금 손실이 발생할 수 있습니다.
            </p>
          </section>
        </div>
      </section>
    </main>
  );
}
