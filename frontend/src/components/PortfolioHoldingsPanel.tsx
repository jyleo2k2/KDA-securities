import { useMemo, useState, type FormEvent } from "react";

import { calculatePortfolioCmaPension } from "../api/client";
import { conicGradient } from "../charts";
import type {
  AccountType,
  CompletedSurveyProfile,
  EducationalPortfolioEvaluation,
  EducationalPortfolioInput,
  PensionCalculatorPortfolioCmaEvaluation,
  PortfolioPlanningEvaluation,
  PortfolioRiskEvaluation,
  RiskProfile,
} from "../api/types";

const ACCOUNT_LABELS: Record<AccountType, string> = {
  dc: "DC형 퇴직연금",
  irp: "IRP",
  pension_savings: "연금저축펀드",
};

const SLEEVE_LABELS: Record<string, string> = {
  core_equity: "기본 주식",
  real_assets: "금·부동산",
  tactical: "작은 기회 투자",
  fixed_income: "채권",
  cash: "바로 쓸 돈",
};

const REBALANCE_STATUS_LABELS: Record<string, string> = {
  within_drift_band: "계획 안",
  underweight_after_contribution: "조금 더 채우기",
  overweight_review_only: "비율 줄이기 점검",
};

const STRESS_SCENARIO_LABELS: Record<string, string> = {
  equity_drawdown: "주식이 크게 떨어질 때",
  rate_inflation_shock: "금리와 물가가 함께 오를 때",
  stagflation: "물가는 오르는데 경기는 나쁠 때",
};

const STRESS_POLICY_STATUS_LABELS = {
  not_evaluated: "견딜 수 있는 손실과 아직 비교하지 않음",
  within_user_limit: "내가 견딜 수 있다고 고른 범위 안",
  review_required: "내가 고른 손실 범위를 다시 확인할 때",
} as const;

const STRATEGY_LABELS: Record<string, string> = {
  capital_preservation_core: "자본보전 중심 전략",
  defensive_diversified_core: "방어적 분산 전략",
  balanced_core_satellite: "코어·위성 전략",
  growth_core_satellite: "성장 코어·위성 전략",
  barbell_growth_tactical: "바벨형 성장·전술 전략",
};

const RISK_PROFILE_LABELS: Record<RiskProfile, string> = {
  stable: "안정형",
  stable_seeking: "안정추구형",
  risk_neutral: "위험중립형",
  active: "적극투자형",
  aggressive: "공격투자형",
};

const STRATEGY_GUIDES: Record<RiskProfile, {
  title: string;
  description: string;
  analogy: string;
}> = {
  stable: {
    title: "돈 지키기 전략 (자본보전 중심)",
    description: "연금 돈을 크게 잃지 않는 것을 먼저 생각해요. 채권과 현금을 많이, 주식은 조금만 담아요.",
    analogy: "비 오는 날 우산과 우비를 챙기는 것과 같아요. 빨리 가는 것보다 안전하게 가는 것이 더 중요해요.",
  },
  stable_seeking: {
    title: "안전하게 나누기 전략 (방어적 분산)",
    description: "채권과 현금을 중심에 두면서, 주식과 금·부동산 ETF도 조금 담아요.",
    analogy: "우산을 챙기되 날씨가 좋으면 조금 더 멀리 걸어가 보는 것과 같아요.",
  },
  risk_neutral: {
    title: "기본·작은 기회 전략 (코어·위성)",
    description: "여러 곳에 나눈 주식 ETF를 오래 가져갈 기본 투자로 두고, 특정 분야 ETF는 아주 조금만 더해요.",
    analogy: "큰 기본 식사에 작은 반찬을 더하는 것과 같아요. 기본 투자는 많이, 새로운 기회 투자는 조금만 담아요.",
  },
  active: {
    title: "성장 비중 늘리기 전략 (성장 코어·위성)",
    description: "주식 기본 투자를 더 크게 두되, 채권과 현금도 남겨 두는 계획이에요.",
    analogy: "기본 주식 투자를 크게 하고 작은 도전도 조금 늘리는 것과 같아요. 시장이 떨어질 때 손실도 더 클 수 있어요.",
  },
  aggressive: {
    title: "성장·안전 나누기 전략 (바벨형 성장·전술)",
    description: "주식과 작은 기회 투자를 많이 두면서도, 채권과 현금을 조금 남겨 한쪽에만 몰리지 않게 해요.",
    analogy: "바벨처럼 양쪽 끝에 무게를 나눠 다는 것과 같아요. 성장 쪽과 안전 쪽의 역할을 나눠 둬요.",
  },
};

const TARGET_ALLOCATION_COLORS = ["#4f8a70", "#84ad67", "#d8a45e", "#7183b1", "#bf7d70"];
const SECTOR_GUIDE_COLORS = ["#4f8a70", "#84ad67", "#d8a45e", "#7183b1", "#bf7d70", "#8b76ad", "#5f9c9c"];

type SectorGuideItem = {
  label: string;
  weight: number;
};

// Display-only examples using the approved ETF theme catalog. They are not ETF
// selection weights and do not change the rules-engine portfolio result.
const SECTOR_GUIDES: Record<RiskProfile, readonly SectorGuideItem[]> = {
  stable: [
    { label: "채권", weight: 48 },
    { label: "소비재·음식료", weight: 16 },
    { label: "바이오·헬스케어", weight: 15 },
    { label: "은행·금융", weight: 11 },
    { label: "리츠·부동산", weight: 10 },
  ],
  stable_seeking: [
    { label: "채권", weight: 35 },
    { label: "소비재·음식료", weight: 14 },
    { label: "바이오·헬스케어", weight: 14 },
    { label: "은행·금융", weight: 12 },
    { label: "리츠·부동산", weight: 10 },
    { label: "신재생·친환경", weight: 15 },
  ],
  risk_neutral: [
    { label: "채권", weight: 25 },
    { label: "반도체", weight: 17 },
    { label: "바이오·헬스케어", weight: 14 },
    { label: "소비재·음식료", weight: 12 },
    { label: "은행·금융", weight: 12 },
    { label: "원자력·전력", weight: 10 },
    { label: "리츠·부동산", weight: 10 },
  ],
  active: [
    { label: "채권", weight: 15 },
    { label: "반도체", weight: 22 },
    { label: "2차전지·배터리", weight: 16 },
    { label: "원자력·전력", weight: 14 },
    { label: "로봇", weight: 13 },
    { label: "바이오·헬스케어", weight: 10 },
    { label: "방산·우주", weight: 10 },
  ],
  aggressive: [
    { label: "채권", weight: 5 },
    { label: "반도체", weight: 25 },
    { label: "2차전지·배터리", weight: 18 },
    { label: "로봇", weight: 17 },
    { label: "방산·우주", weight: 15 },
    { label: "원자력·전력", weight: 10 },
    { label: "양자컴퓨팅", weight: 10 },
  ],
};

interface HoldingDraft {
  id: string;
  isuCode: string;
  amountKrw: string;
}

function newHolding(): HoldingDraft {
  return { id: crypto.randomUUID(), isuCode: "", amountKrw: "" };
}

function wholeWon(value: string): string | null {
  const normalized = value.replaceAll(",", "").trim();
  return /^\d+$/.test(normalized) ? normalized : null;
}

function won(value: string): string {
  const integer = value.split(".")[0] || "0";
  try {
    return `${BigInt(integer).toLocaleString("ko-KR")}원`;
  } catch {
    return `${value}원`;
  }
}

function percent(value: string): string {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(1)}%` : `${value}%`;
}

function optionalPercent(value: string | null): string {
  return value === null ? "산출 불가" : percent(value);
}

function dateText(value: string | null): string {
  return value === null ? "확인 불가" : value.slice(0, 10);
}

function sleeveLabel(value: string): string {
  return SLEEVE_LABELS[value] ?? "기타 자산군";
}

function strategyLabel(value: string): string {
  if (!value) return "연금 자산배분 전략";
  return STRATEGY_LABELS[value] ?? (
    /^[a-z]+(?:_[a-z]+)+$/.test(value) ? "연금 자산배분 전략" : value
  );
}

function PortfolioSectorGuide({ riskProfile }: { riskProfile: RiskProfile }) {
  const items = SECTOR_GUIDES[riskProfile];
  const guideLabel = RISK_PROFILE_LABELS[riskProfile];
  const gradientStops = conicGradient(
    items.map((item) => item.weight),
    SECTOR_GUIDE_COLORS,
  );

  return (
    <section className="portfolio-sector-guide" aria-labelledby="portfolio-sector-guide-title">
      <header>
        <span>여러 분야로 나눠 보기</span>
        <h4 id="portfolio-sector-guide-title">{guideLabel} ETF 분야 예시</h4>
        <p>투자성향에 따라 살펴볼 분야의 비율 예시예요. 실제 계산 결과나 계좌 한도는 바꾸지 않아요.</p>
      </header>
      <div className="portfolio-sector-guide-layout">
        <div
          aria-label={items.map((item) => `${item.label} ${item.weight}%`).join(", ")}
          className="portfolio-sector-donut"
          role="img"
          style={{ background: `conic-gradient(${gradientStops})` }}
        >
          <span>전체<br /><strong>100%</strong></span>
        </div>
        <ul className="portfolio-sector-legend">
          {items.map((item, index) => (
            <li key={item.label}>
              <i style={{ backgroundColor: SECTOR_GUIDE_COLORS[index % SECTOR_GUIDE_COLORS.length] }} />
              <span>{item.label}</span>
              <strong>{item.weight.toFixed(1)}%</strong>
            </li>
          ))}
        </ul>
      </div>
      <p className="portfolio-sector-guide-note">여기서는 ETF가 다루는 분야만 보여드려요. “사세요”라는 추천이나 미래 수익 예측은 아니에요.</p>
    </section>
  );
}

function TargetAllocationGuide({
  evaluation,
}: {
  evaluation: EducationalPortfolioEvaluation;
}) {
  const items = evaluation.target_sleeves
    .map((item) => ({
      label: sleeveLabel(item.sleeve),
      weight: Number(item.target_percent),
    }))
    .filter((item) => Number.isFinite(item.weight) && item.weight > 0);
  const gradientStops = conicGradient(
    items.map((item) => item.weight),
    TARGET_ALLOCATION_COLORS,
  );

  return (
    <section className="portfolio-target-allocation" aria-labelledby="portfolio-target-allocation-title">
      <header>
        <span>계산으로 정한 비율</span>
        <h4 id="portfolio-target-allocation-title">연금 돈 나누기</h4>
        <p>연금 돈을 어디에 얼마나 나눠 둘지 정한 비율이에요.</p>
      </header>
      <div className="portfolio-target-allocation-layout">
        <div
          aria-label={items.map((item) => `${item.label} ${item.weight.toFixed(1)}%`).join(", ")}
          className="portfolio-target-donut"
          role="img"
          style={{ background: `conic-gradient(${gradientStops})` }}
        >
          <span>전체<br /><strong>100%</strong></span>
        </div>
        <ul className="portfolio-target-legend">
          {items.map((item, index) => (
            <li key={item.label}>
              <i style={{ backgroundColor: TARGET_ALLOCATION_COLORS[index % TARGET_ALLOCATION_COLORS.length] }} />
              <span>{item.label}</span>
              <strong>{item.weight.toFixed(1)}%</strong>
            </li>
          ))}
        </ul>
      </div>
      <p className="portfolio-target-allocation-note">
        큰 비율을 먼저 정한 뒤, ETF 분야 살펴보기에서 각 분야의 위험을 확인할 수 있어요.
      </p>
    </section>
  );
}

function RebalancingCadenceGuide({
  evaluation,
}: {
  evaluation: EducationalPortfolioEvaluation;
}) {
  const cadence = evaluation.rebalancing.cadence;
  return (
    <section className="portfolio-rebalance-cadence" aria-labelledby="portfolio-rebalance-cadence-title">
      <header>
        <span>비율 다시 맞춰 보기</span>
        <h4 id="portfolio-rebalance-cadence-title">{cadence.review_interval_months}개월마다 비율 점검</h4>
        <p>{cadence.rationale}</p>
      </header>
      <div className="portfolio-review-summary">
        <div><span>얼마마다 볼까</span><strong>{cadence.review_interval_months}개월</strong></div>
        <div><span>비율 차이 기준</span><strong>±{percent(cadence.drift_threshold_percent_points)}</strong></div>
      </div>
      <p className="portfolio-target-allocation-note">리밸런싱은 달라진 비율을 처음 계획에 가깝게 맞추는 점검이에요. 새로 넣는 돈은 부족한 쪽에 먼저 넣어요.</p>
    </section>
  );
}

function EducationalStrategyGuide({
  evaluation,
}: {
  evaluation: EducationalPortfolioEvaluation;
}) {
  const profile = evaluation.evaluated_input.risk_profile;
  const guide = STRATEGY_GUIDES[profile];
  const planning = evaluation.planning_return;

  return (
    <section className="portfolio-strategy-guide" aria-labelledby="portfolio-strategy-guide-title">
      <header>
        <span>투자성향 기반 연금투자전략</span>
        <h3 id="portfolio-strategy-guide-title">{RISK_PROFILE_LABELS[profile]}의 {guide.title}</h3>
        <p>
          {ACCOUNT_LABELS[evaluation.evaluated_input.account_type]} · 연금을 받기 시작할 때까지 {evaluation.planning_horizon_years}년
        </p>
      </header>

      <article className="portfolio-strategy-explanation">
        <strong>{guide.title}</strong>
        <p>{guide.description}</p>
        <p><b>쉽게 말하면:</b> {guide.analogy}</p>
      </article>

      <p className="portfolio-strategy-transition">
        이 성향이라면 연금 돈을 아래처럼 나눠 볼 수 있어요.
      </p>
      <TargetAllocationGuide evaluation={evaluation} />
      <RebalancingCadenceGuide evaluation={evaluation} />

      <section className="portfolio-strategy-planning" aria-labelledby="portfolio-strategy-planning-title">
        <header>
          <span>장기 계산에 쓰는 숫자</span>
          <h4 id="portfolio-strategy-planning-title">두 가지 수익률 가정</h4>
        </header>
        <div className="portfolio-planning-metrics">
          <div>
            <span>조심해서 계산한 경우</span>
            <strong>{optionalPercent(planning.conservative_planning_return_percent)}</strong>
            <small>장기 전망·비용·여유 폭 반영</small>
          </div>
          <div>
            <span>기본으로 계산한 경우</span>
            <strong>{optionalPercent(planning.base_planning_return_percent)}</strong>
            <small>장기 전망·ETF 비용 반영</small>
          </div>
        </div>
        <div className="planning-source-chips" aria-label="장기 수익률 가정 출처">
          {planning.sources.map((source) => (
            /^https?:\/\//.test(source.reference) ? (
              <a href={source.reference} target="_blank" rel="noreferrer" key={`${source.label}-${source.reference}`}>
                {source.label} · {dateText(source.as_of)}
              </a>
            ) : (
              <span key={`${source.label}-${source.reference}`}>{source.label} · {dateText(source.as_of)}</span>
            )
          ))}
        </div>
        <p className="portfolio-planning-note">
          *CMA는 여러 자산의 10년 이상 장기 전망을 정리한 계산용 가정이에요. ETF 비용도 넣어 계산하지만, 미래 수익을 맞히거나 약속하는 숫자는 아니에요.
        </p>
      </section>

      <section className="portfolio-theme-next-step" aria-labelledby="portfolio-theme-next-step-title">
        <strong id="portfolio-theme-next-step-title">어떤 ETF 분야를 살펴볼까?</strong>
        <p>
          이 서비스는 “이 ETF를 사세요”라고 정해 주지 않아요. ETF 분야 살펴보기에서 각 분야가 어떤 위험이 있는지 확인해 보세요.
        </p>
      </section>
    </section>
  );
}

function PortfolioRiskReview({ risk }: { risk: PortfolioRiskEvaluation }) {
  const complete = risk.status === "complete";
  const hasStressPolicy = (
    risk.stress_loss_limit_percent !== null
    && risk.stress_loss_limit_percent !== undefined
    && risk.worst_stress_loss_percent !== undefined
  );
  const reviewRequired = risk.stress_loss_policy_status === "review_required";

  return (
    <section className="portfolio-risk-review" aria-labelledby="portfolio-risk-title">
      <header>
        <span>지나간 자료로 본 모습</span>
        <h4 id="portfolio-risk-title">얼마나 흔들릴 수 있는지 보기</h4>
        <p>
          {dateText(risk.observation_start)}~{dateText(risk.observation_end)} · 공통 일간 관측 {risk.observation_count.toLocaleString("ko-KR")}개
        </p>
      </header>

      {complete ? (
        <div className="portfolio-risk-metrics">
          <div><span>1년 동안의 흔들림 크기</span><strong>{optionalPercent(risk.annualized_volatility_percent)}</strong></div>
          <div><span>떨어질 때의 흔들림</span><strong>{optionalPercent(risk.annualized_downside_deviation_percent)}</strong></div>
          <div><span>과거 가장 크게 떨어진 폭</span><strong>{optionalPercent(risk.maximum_drawdown_percent)}</strong></div>
          <div><span>나쁜 날 하루 손실 기준</span><strong>{optionalPercent(risk.historical_95pct_one_day_loss_percent)}</strong></div>
        </div>
      ) : (
        <p className="portfolio-risk-unavailable">
          후보 ETF의 공통 일간 수익률이 60개 미만이라 과거 위험지표를 산출하지 않았습니다.
        </p>
      )}

      <div className="stress-scenario-grid" aria-label="정책 스트레스 시나리오">
        {risk.stress_scenarios.map((scenario) => (
          <div key={scenario.scenario_code}>
            <span title={scenario.scenario_code}>{STRESS_SCENARIO_LABELS[scenario.scenario_code] ?? "기타 시장 충격"}</span>
            <strong>{percent(scenario.estimated_loss_percent)}</strong>
            <small>정책 충격 가정</small>
          </div>
        ))}
      </div>
      {hasStressPolicy && (
        <section
          className={`portfolio-risk-policy ${reviewRequired ? "review-required" : "within-limit"}`}
          aria-label="견딜 수 있는 손실 범위 점검"
        >
          <strong>{STRESS_POLICY_STATUS_LABELS[risk.stress_loss_policy_status]}</strong>
          <p>
            내가 고른 손실 범위 {percent(risk.stress_loss_limit_percent!)} · 가장 큰 충격 가정 {percent(risk.worst_stress_loss_percent)}
          </p>
          {reviewRequired && <small>연금 돈을 나눈 비율과 새 납입 계획을 다시 확인해 주세요. 자동으로 팔지는 않아요.</small>}
        </section>
      )}
      <div className="planning-source-chips" aria-label="위험·스트레스 출처">
        {risk.sources.map((source) => (
          /^https?:\/\//.test(source.reference) ? (
            <a href={source.reference} target="_blank" rel="noreferrer" key={`${source.label}-${source.reference}`}>
              {source.label} · {dateText(source.as_of)}
            </a>
          ) : (
            <span key={`${source.label}-${source.reference}`}>{source.label} · {dateText(source.as_of)}</span>
          )
        ))}
      </div>
      <p className="portfolio-risk-note">
        위 숫자는 지나간 자료로 본 참고값이에요. 앞으로의 수익이나 손실을 맞히는 숫자는 아니에요.
      </p>
    </section>
  );
}

function PortfolioPlanningReview({
  planning,
  titleId,
  title,
  description,
}: {
  planning: PortfolioPlanningEvaluation;
  titleId: string;
  title: string;
  description: string;
}) {
  return (
    <section className="portfolio-planning-review" aria-labelledby={titleId}>
      <header>
        <span>장기 계산에 쓰는 숫자</span>
        <h4 id={titleId}>{title}</h4>
        <p>
          {description} · 장기 전망(CMA) {planning.cma_source_horizon_min_years}~{planning.cma_source_horizon_max_years}년 기준
          {planning.annual_review_required ? " · 매년 재검토" : ""}
        </p>
      </header>

      <div className="portfolio-planning-metrics">
        <div><span>기본으로 계산한 경우</span><strong>{optionalPercent(planning.base_planning_return_percent)}</strong><small>장기 전망·비용 반영</small></div>
        <div><span>조심해서 계산한 경우</span><strong>{optionalPercent(planning.conservative_planning_return_percent)}</strong><small>여유 폭을 더 뺌</small></div>
        <div><span>ETF 비용 빼기 전</span><strong>{optionalPercent(planning.gross_planning_return_percent)}</strong><small>불확실성 반영</small></div>
        <div><span>ETF 비용 뺀 뒤</span><strong>{optionalPercent(planning.net_planning_return_percent)}</strong><small>1년 비용까지 뺌</small></div>
      </div>

      <div className="portfolio-planning-table-wrap">
        <table className="portfolio-planning-table">
          <thead>
            <tr>
              <th>ETF</th>
              <th>목표 비율</th>
              <th>장기 전망</th>
              <th>여유 폭</th>
              <th>연간 비용</th>
            </tr>
          </thead>
          <tbody>
            {planning.components.map((component) => (
              <tr key={component.isu_code}>
                <th>{component.isu_name}<small>{component.isu_code}{component.proxy_used ? " · 비슷한 자산의 장기 전망 사용" : ""}</small></th>
                <td>{percent(component.target_percent)}</td>
                <td>{percent(component.cma_percent)}</td>
                <td>-{percent(component.uncertainty_discount_percent)}</td>
                <td>-{percent(component.annual_cost_drag_percent)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="planning-source-chips" aria-label="장기 수익률 가정 출처">
        {planning.sources.map((source) => (
          /^https?:\/\//.test(source.reference) ? (
            <a href={source.reference} target="_blank" rel="noreferrer" key={`${source.label}-${source.reference}`}>
              {source.label} · {dateText(source.as_of)}
            </a>
          ) : (
            <span key={`${source.label}-${source.reference}`}>{source.label} · {dateText(source.as_of)}</span>
          )
        ))}
      </div>
      <p className="portfolio-planning-note">
        계산에 쓴 ETF 비중 {percent(planning.coverage_weight_percent)} · {planning.historical_performance_used ? "과거 수익률 사용" : "과거 수익률 미사용"} · {planning.is_forecast ? "예측값" : "미래 수익을 맞히는 값이 아닙니다"}.
      </p>
    </section>
  );
}

function PensionPlanReview({
  evaluation,
}: {
  evaluation: PensionCalculatorPortfolioCmaEvaluation;
}) {
  const { calculator, planning_return: planning } = evaluation;
  return (
    <section className="portfolio-planning-review" aria-labelledby="portfolio-pension-plan-title">
      <header>
        <span>현재 보유 ETF 기준</span>
        <h4 id="portfolio-pension-plan-title">장기 수령 계획 예시</h4>
        <p>현재 평가금액 비중과 CMA·검증 비용을 반영한 계획가정입니다.</p>
      </header>
      <div className="portfolio-review-summary">
        <div><span>수령 시작 시점 계획 잔액</span><strong>{won(calculator.headline.total_krw)}</strong></div>
        <div><span>월 수령 계획금액(세전)</span><strong>{won(calculator.headline.monthly_payout_pretax_krw)}</strong></div>
        <div><span>월 수령 계획금액(1년차 세후)</span><strong>{won(calculator.headline.monthly_payout_after_tax_krw)}</strong></div>
        <div><span>비용 차감 후 계획가정</span><strong>{optionalPercent(planning.net_planning_return_percent)}</strong></div>
      </div>
      <div className="planning-source-chips" aria-label="수령 계획 출처">
        {[calculator.assumption.source, ...planning.sources].map((source) => (
          /^https?:\/\//.test(source.reference) ? (
            <a href={source.reference} target="_blank" rel="noreferrer" key={`${source.label}-${source.reference}`}>
              {source.label} · {dateText(source.as_of)}
            </a>
          ) : (
            <span key={`${source.label}-${source.reference}`}>{source.label} · {dateText(source.as_of)}</span>
          )
        ))}
      </div>
      <p className="portfolio-planning-note">{calculator.assumption.notice}</p>
    </section>
  );
}

export function PortfolioHoldingsPanel({
  surveyProfile,
  disabled,
  onAnalyze,
}: {
  surveyProfile: CompletedSurveyProfile | null;
  disabled: boolean;
  onAnalyze: (input: EducationalPortfolioInput) => void;
}) {
  const availableAccounts = useMemo(() => {
    if (!surveyProfile) return [];
    const accounts = surveyProfile.account_types?.length
      ? surveyProfile.account_types
      : [surveyProfile.account_type];
    return Array.from(new Set(accounts));
  }, [surveyProfile]);
  const [selectedAccount, setSelectedAccount] = useState<AccountType | "">("");
  const [holdings, setHoldings] = useState<HoldingDraft[]>([newHolding()]);
  const [newContribution, setNewContribution] = useState("0");
  const [monthlyContribution, setMonthlyContribution] = useState("0");
  const [payoutYears, setPayoutYears] = useState("20");
  const [pensionPlan, setPensionPlan] = useState<PensionCalculatorPortfolioCmaEvaluation | null>(null);
  const [pensionPlanError, setPensionPlanError] = useState("");
  const [pensionPlanLoading, setPensionPlanLoading] = useState(false);
  const [error, setError] = useState("");

  const accountType = availableAccounts.includes(selectedAccount as AccountType)
    ? selectedAccount as AccountType
    : availableAccounts[0];

  if (!surveyProfile) {
    return (
      <div className="holdings-required-panel">
        <strong>먼저 투자 프로필을 완성해 주세요.</strong>
        <p>연령, 연금 수령 시작 나이, 계좌 유형과 투자성향을 엔진 입력으로 사용합니다.</p>
        <a href="#profile">프로필 입력하러 가기</a>
      </div>
    );
  }

  const updateHolding = (
    id: string,
    field: "isuCode" | "amountKrw",
    value: string,
  ) => {
    setHoldings((current) => current.map((holding) => (
      holding.id === id ? { ...holding, [field]: value } : holding
    )));
    setError("");
  };

  const validatedHoldings = () => {
    const normalized = holdings.map((holding) => ({
      isu_code: holding.isuCode.trim(),
      amount_krw: wholeWon(holding.amountKrw),
    }));
    if (normalized.some((holding) => !/^\d{6}$/.test(holding.isu_code))) {
      setError("ETF 종목코드는 6자리 숫자로 입력해 주세요.");
      return null;
    }
    if (normalized.some((holding) => holding.amount_krw === null || BigInt(holding.amount_krw) <= 0n)) {
      setError("각 ETF의 평가금액은 1원 이상 정수로 입력해 주세요.");
      return null;
    }
    if (new Set(normalized.map((holding) => holding.isu_code)).size !== normalized.length) {
      setError("같은 ETF는 평가금액을 합친 뒤 한 줄로 입력해 주세요.");
      return null;
    }
    return normalized.map((holding) => ({
      isu_code: holding.isu_code,
      amount_krw: holding.amount_krw!,
    }));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = holdings.map((holding) => ({
      isu_code: holding.isuCode.trim(),
      amount_krw: wholeWon(holding.amountKrw),
    }));
    if (normalized.some((holding) => !/^\d{6}$/.test(holding.isu_code))) {
      setError("ETF 종목코드는 6자리 숫자로 입력해 주세요.");
      return;
    }
    if (normalized.some((holding) => holding.amount_krw === null || BigInt(holding.amount_krw) <= 0n)) {
      setError("각 ETF의 평가금액을 1원 이상 정수로 입력해 주세요.");
      return;
    }
    if (new Set(normalized.map((holding) => holding.isu_code)).size !== normalized.length) {
      setError("같은 ETF는 평가금액을 합쳐 한 줄로 입력해 주세요.");
      return;
    }
    const contribution = wholeWon(newContribution);
    if (contribution === null) {
      setError("추가 납입 예정금액은 0원 이상 정수로 입력해 주세요.");
      return;
    }
    onAnalyze({
      account_type: accountType,
      age: surveyProfile.current_age,
      retirement_start_age: surveyProfile.retirement_start_age,
      risk_profile: surveyProfile.risk_profile,
      loss_tolerance_percent: surveyProfile.loss_tolerance_percent,
      max_etfs: 7,
      current_holdings: normalized.map((holding) => ({
        isu_code: holding.isu_code,
        amount_krw: holding.amount_krw!,
      })),
      new_contribution_krw: contribution,
    });
  };

  const calculatePensionPlan = async () => {
    const normalized = validatedHoldings();
    if (normalized === null) return;
    const monthly = wholeWon(monthlyContribution);
    if (monthly === null) {
      setPensionPlanError("월 납입액은 0원 이상의 정수로 입력해 주세요.");
      return;
    }
    const currentBalance = normalized
      .reduce((total, holding) => total + BigInt(holding.amount_krw), 0n)
      .toString();
    setPensionPlanError("");
    setPensionPlanLoading(true);
    try {
      const result = await calculatePortfolioCmaPension({
        calculator: {
          current_age: surveyProfile.current_age,
          contribution_end_age: surveyProfile.retirement_start_age,
          current_balance_krw: currentBalance,
          monthly_contribution_krw: monthly,
          account_type: accountType,
          risk_profile: surveyProfile.risk_profile,
          payout_years: Number(payoutYears),
          scenario: "base",
        },
        current_holdings: normalized,
      });
      setPensionPlan(result);
    } catch {
      setPensionPlan(null);
      setPensionPlanError("현재 보유 ETF의 비용·적격성 데이터를 확인하지 못해 수령 계획을 계산하지 못했습니다. 종목코드와 데이터 기준일을 확인해 주세요.");
    } finally {
      setPensionPlanLoading(false);
    }
  };

  return (
    <form className="holdings-input-form" onSubmit={submit}>
      <div className="holdings-form-field">
        <label htmlFor="holdings-account">분석할 연금계좌</label>
        <select
          id="holdings-account"
          value={accountType}
          onChange={(event) => setSelectedAccount(event.target.value as AccountType)}
          disabled={disabled}
        >
          {availableAccounts.map((account) => (
            <option key={account} value={account}>{ACCOUNT_LABELS[account]}</option>
          ))}
        </select>
      </div>

      <fieldset>
        <legend>현재 보유 ETF</legend>
        <p className="holdings-field-help">종목코드와 현재 평가금액만 입력하세요. 계좌번호나 인증정보는 받지 않습니다.</p>
        {holdings.map((holding, index) => (
          <div className="holding-row" key={holding.id}>
            <label>
              <span>{index + 1}. ETF 종목코드</span>
              <input
                aria-label={`${index + 1}번째 ETF 종목코드`}
                inputMode="numeric"
                maxLength={6}
                placeholder="예: 069500"
                value={holding.isuCode}
                onChange={(event) => updateHolding(
                  holding.id,
                  "isuCode",
                  event.target.value.replace(/\D/g, ""),
                )}
                disabled={disabled}
              />
            </label>
            <label>
              <span>평가금액(원)</span>
              <input
                aria-label={`${index + 1}번째 ETF 평가금액`}
                inputMode="numeric"
                placeholder="예: 10000000"
                value={holding.amountKrw}
                onChange={(event) => updateHolding(
                  holding.id,
                  "amountKrw",
                  event.target.value.replace(/\D/g, ""),
                )}
                disabled={disabled}
              />
            </label>
            {holdings.length > 1 && (
              <button
                className="holding-remove"
                type="button"
                aria-label={`${index + 1}번째 ETF 삭제`}
                onClick={() => setHoldings((current) => current.filter((item) => item.id !== holding.id))}
                disabled={disabled}
              >
                삭제
              </button>
            )}
          </div>
        ))}
        {holdings.length < 10 && (
          <button
            className="holding-add"
            type="button"
            onClick={() => setHoldings((current) => [...current, newHolding()])}
            disabled={disabled}
          >
            + ETF 추가
          </button>
        )}
      </fieldset>

      <div className="holdings-form-field">
        <label htmlFor="new-contribution">이번 추가 납입 예정금액(원)</label>
        <input
          id="new-contribution"
          inputMode="numeric"
          value={newContribution}
          onChange={(event) => {
            setNewContribution(event.target.value.replace(/\D/g, ""));
            setError("");
          }}
          disabled={disabled}
        />
        <small>새 납입금으로 비중 차이를 먼저 줄이는 예시를 계산합니다.</small>
      </div>
      <fieldset>
        <legend>장기 수령 계획 입력</legend>
        <p className="holdings-field-help">월 납입액과 수령기간만 입력하면, 위 ETF 평가금액 합계와 현재 비중을 사용합니다.</p>
        <div className="holding-row">
          <label>
            <span>월 납입액(원)</span>
            <input
              aria-label="월 납입액"
              inputMode="numeric"
              value={monthlyContribution}
              onChange={(event) => {
                setMonthlyContribution(event.target.value.replace(/\D/g, ""));
                setPensionPlanError("");
              }}
              disabled={disabled || pensionPlanLoading}
            />
          </label>
          <label>
            <span>수령기간</span>
            <select
              aria-label="수령기간"
              value={payoutYears}
              onChange={(event) => setPayoutYears(event.target.value)}
              disabled={disabled || pensionPlanLoading}
            >
              {[10, 15, 20, 25, 30, 40].map((years) => (
                <option key={years} value={years}>{years}년</option>
              ))}
            </select>
          </label>
        </div>
      </fieldset>
      {error && <p className="holdings-form-error" role="alert">{error}</p>}
      {pensionPlanError && <p className="holdings-form-error" role="alert">{pensionPlanError}</p>}
      <button className="holdings-analyze" type="submit" disabled={disabled}>
        {disabled ? "분석 중…" : "보유 ETF 분석하기"}
      </button>
      <button className="holdings-analyze" type="button" onClick={() => void calculatePensionPlan()} disabled={disabled || pensionPlanLoading}>
        {pensionPlanLoading ? "수령 계획 계산 중…" : "보유 ETF 기준 수령 계획 계산"}
      </button>
      {pensionPlan && <PensionPlanReview evaluation={pensionPlan} />}
    </form>
  );
}

export function EducationalPortfolioReview({
  evaluation,
}: {
  evaluation?: EducationalPortfolioEvaluation | null;
}) {
  if (!evaluation) return null;
  if (!evaluation.evaluated_input.current_holdings.length) {
    return <EducationalStrategyGuide evaluation={evaluation} />;
  }

  const rebalancing = evaluation.rebalancing;
  const highestCorrelation = evaluation.candidates.reduce<number | null>((highest, candidate) => {
    if (candidate.max_correlation_with_selected === null || candidate.max_correlation_with_selected === undefined) {
      return highest;
    }
    const current = Number(candidate.max_correlation_with_selected);
    if (!Number.isFinite(current)) return highest;
    return highest === null ? current : Math.max(highest, current);
  }, null);
  const reviewSleeveCount = rebalancing.sleeves.filter(
    (sleeve) => sleeve.status !== "within_drift_band",
  ).length;
  const reviewHeadline = reviewSleeveCount > 0
    ? `${reviewSleeveCount}개 자산군의 비중을 확인해 보세요`
    : "현재 자산 비중은 점검 범위 안에 있어요";
  const reviewGuidance = reviewSleeveCount > 0
    ? "먼저 비중이 벗어난 자산군을 확인하고, 새 납입금으로 차이를 줄이는 순서로 보면 돼요."
    : "지금 구성을 유지하면서 정기 점검 시점에 다시 확인하면 돼요.";

  return (
    <section className="portfolio-review" aria-labelledby="portfolio-review-title">
      <header>
        <span>계산으로 비교한 결과</span>
        <h3 id="portfolio-review-title">보유 ETF 비율 점검</h3>
        <p title={evaluation.strategy_label}>{ACCOUNT_LABELS[evaluation.evaluated_input.account_type]} · {strategyLabel(evaluation.strategy_label)}</p>
      </header>

      <div className="portfolio-review-lead">
        <span>먼저 볼 내용</span>
        <strong>{reviewHeadline}</strong>
        <p>{reviewGuidance}</p>
      </div>

      <div className="portfolio-review-summary">
        <div><span>현재 평가금액</span><strong>{won(rebalancing.current_total_krw)}</strong></div>
        <div>
          <span>계좌에서 허용하는 최대 비율</span>
          <strong>{evaluation.account_risk_cap_percent == null ? "법정 총량한도 없음" : percent(evaluation.account_risk_cap_percent)}</strong>
        </div>
        <div><span>가격이 크게 움직일 수 있는 자산</span><strong>{percent(evaluation.final_general_risk_target_percent)}</strong></div>
      </div>

      <details className="portfolio-review-details">
        <summary>
          <span><small>1단계</small><strong>자산 구성과 조정 기준</strong></span>
          <em>펼쳐보기</em>
        </summary>
        <div className="portfolio-review-details-body">
          <PortfolioSectorGuide riskProfile={evaluation.evaluated_input.risk_profile} />
          <RebalancingCadenceGuide evaluation={evaluation} />

          <div className="overlap-check">
            <strong>한곳에 너무 몰렸는지 보기</strong>
            <p>지금 가진 ETF 비율을 목표와 비교했어요. 비슷한 역할의 ETF가 한곳에 몰렸는지는 아래 비율 차이에서 볼 수 있어요.</p>
            {highestCorrelation !== null && (
              <p>새 후보 ETF끼리 과거에 같이 오르내린 정도는 최대 {highestCorrelation.toFixed(1)}%예요. 같은 회사가 몇 개 겹쳤는지를 뜻하는 숫자는 아니에요.</p>
            )}
            <small>ETF별 실제 구성종목 중복률은 구성종목 원천 데이터가 완전한 상품에 한해서만 계산할 수 있어 현재 결과에서 임의 추정하지 않습니다.</small>
          </div>

          <div className="portfolio-review-table-wrap">
            <table className="portfolio-review-table">
              <thead>
                <tr>
                  <th>자산군</th>
                  <th>현재</th>
                  <th>목표</th>
                  <th>이탈폭</th>
                  <th>납입 후</th>
                  <th>추가 납입 예시</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {rebalancing.sleeves.map((sleeve) => (
                  <tr key={sleeve.sleeve}>
                    <th title={sleeve.sleeve}>{sleeveLabel(sleeve.sleeve)}</th>
                    <td>{percent(sleeve.current_percent)}</td>
                    <td>{percent(sleeve.target_percent)}</td>
                    <td>{Number(sleeve.drift_before_percent_points) > 0 ? "+" : ""}{percent(sleeve.drift_before_percent_points)}p</td>
                    <td>{percent(sleeve.projected_percent_after_contribution)}</td>
                    <td>{won(sleeve.contribution_example_krw)}</td>
                    <td><span className={`rebalance-status status-${sleeve.status}`} title={sleeve.status}>{REBALANCE_STATUS_LABELS[sleeve.status] ?? "추가 점검 필요"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </details>

      <details className="portfolio-review-details">
        <summary>
          <span><small>2단계</small><strong>위험과 수익률 계산 근거</strong></span>
          <em>펼쳐보기</em>
        </summary>
        <div className="portfolio-review-details-body">
          <PortfolioRiskReview risk={evaluation.portfolio_risk} />
          {evaluation.current_holdings_planning_return ? (
            <PortfolioPlanningReview
              planning={evaluation.current_holdings_planning_return}
              titleId="current-holdings-planning-title"
              title="현재 보유 ETF 장기 계산용 숫자"
              description="지금 가진 ETF 비율을 넣어 계산"
            />
          ) : evaluation.warnings.some((warning) => warning.startsWith("current_holdings_planning_return_unavailable:")) ? (
            <p className="portfolio-review-warning">
              현재 보유 ETF 중 확인할 자료가 부족한 항목이 있어 장기 계산용 숫자를 보여드리지 못했어요. 종목코드와 자료 기준일을 확인해 주세요.
            </p>
          ) : null}
          <PortfolioPlanningReview
            planning={evaluation.planning_return}
            titleId="target-portfolio-planning-title"
            title="목표 포트폴리오 장기 계산용 숫자"
            description="목표로 정한 ETF 비율을 넣어 계산"
          />
        </div>
      </details>

      {Number(rebalancing.unclassified_holding_amount_krw) > 0 && (
        <p className="portfolio-review-warning">
          분류하지 못한 보유자산 {won(rebalancing.unclassified_holding_amount_krw)}은 비중 계산에 별도로 남겼습니다. 상품 분류와 자료 기준일을 확인해 주세요.
        </p>
      )}
      {evaluation.account_cap_binding && (
        <p className="portfolio-review-warning">투자성향보다 계좌 규칙이 먼저 적용되어, 가격이 크게 움직일 수 있는 자산 비율을 낮췄어요.</p>
      )}
      <p className="portfolio-review-disclaimer">
        이 서비스가 자동으로 팔지는 않아요. 새로 넣는 돈으로 부족한 쪽을 먼저 채워 보는 안내예요.
      </p>
    </section>
  );
}
