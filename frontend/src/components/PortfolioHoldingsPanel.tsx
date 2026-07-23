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
  core_equity: "분산 주식",
  real_assets: "금·리츠",
  tactical: "전술 자산",
  fixed_income: "채권",
  cash: "현금성",
};

const REBALANCE_STATUS_LABELS: Record<string, string> = {
  within_drift_band: "허용 범위",
  underweight_after_contribution: "비중 부족",
  overweight_review_only: "비중 초과 점검",
};

const STRESS_SCENARIO_LABELS: Record<string, string> = {
  equity_drawdown: "주식시장 급락",
  rate_inflation_shock: "금리·물가 충격",
  stagflation: "스태그플레이션",
};

const STRESS_POLICY_STATUS_LABELS = {
  not_evaluated: "손실감내도 미비교",
  within_user_limit: "손실감내도 기준 이내",
  review_required: "손실감내도 재점검 필요",
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
    title: "자본보전 중심 전략",
    description: "높은 수익을 추구하기보다 연금자산의 큰 손실을 줄이고 안정적으로 유지하는 데 목적이 있습니다.",
    analogy: "학교 가는 길에 비가 올까 봐 우산, 우비, 여벌 옷까지 챙기는 사람과 비슷해요. 많이 빨리 가는 것보다 비를 맞지 않고 안전하게 가는 것이 더 중요합니다.",
  },
  stable_seeking: {
    title: "방어적 분산 전략",
    description: "방어자산을 중심에 두되 장기 성장과 물가상승에 대응하기 위해 주식과 실물자산을 조금 더 적극적으로 편입합니다.",
    analogy: "안정형이 우산과 우비를 모두 챙기는 사람이라면, 안정추구형은 우산을 챙기되 날씨가 좋으면 조금 더 멀리 걸어가 보는 사람에 가깝습니다.",
  },
  risk_neutral: {
    title: "코어·위성 전략",
    description: "광범위한 주식 ETF를 장기 성장의 코어로 두고 특정 테마 ETF는 5% 이내의 위성자산으로 제한하는 구조입니다.",
    analogy: "큰 기본 식사에 작은 반찬을 더하는 전략입니다. 코어는 주식시장의 기본 뼈대이고, 위성은 조금만 담는 특별 반찬입니다.",
  },
  active: {
    title: "성장 코어·위성 전략",
    description: "장기 성장자산의 비중을 확대하면서도 채권과 현금을 완전히 없애지 않는 구조입니다.",
    analogy: "기본 주식 투자를 크게 하고 작은 도전도 조금 늘리는 전략입니다. 위험중립형보다 성장 가능성을 더 중요하게 생각하는 대신, 시장이 떨어질 때 손실도 더 클 수 있습니다.",
  },
  aggressive: {
    title: "바벨형 성장·전술 전략",
    description: "주식과 전술자산의 성장축을 크게 두면서 반대편에 최소한의 채권과 현금 방어축을 별도로 유지합니다.",
    analogy: "바벨은 양쪽 끝에 무게가 달린 긴 막대예요. 중간 성격의 자산을 많이 두기보다 성장 쪽과 안전 쪽의 역할을 분명히 나눠 두는 방식입니다.",
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
        <span>교육용 섹터 분산 예시</span>
        <h4 id="portfolio-sector-guide-title">{guideLabel} 섹터 가이드</h4>
        <p>투자성향에 따라 살펴볼 테마의 비중 예시입니다. 실제 엔진 목표비중·후보 ETF·계좌 한도는 바꾸지 않습니다.</p>
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
      <p className="portfolio-sector-guide-note">테마는 챗봇에서 설명하는 승인된 ETF 테마 카탈로그 중에서만 표시하며, 매수·수익률 예측 안내가 아닙니다.</p>
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
        <span>규칙 엔진 목표비중</span>
        <h4 id="portfolio-target-allocation-title">목표 자산배분</h4>
        <p>이 전략에 따른 자산군별 목표비중입니다.</p>
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
        전체적인 자산배분의 틀은 이렇게 가져가고, 각 자산 분류를 어떤 테마 ETF로 채울지는 ETF 섹터 알아보기에서 탐색할 수 있습니다.
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
        <span>규칙 엔진 리밸런싱 정책</span>
        <h4 id="portfolio-rebalance-cadence-title">{cadence.review_interval_months}개월마다 비중 점검</h4>
        <p>{cadence.rationale}</p>
      </header>
      <div className="portfolio-review-summary">
        <div><span>정기 점검 주기</span><strong>{cadence.review_interval_months}개월</strong></div>
        <div><span>목표비중 이탈 기준</span><strong>±{percent(cadence.drift_threshold_percent_points)}</strong></div>
      </div>
      <p className="portfolio-target-allocation-note">목표비중은 연령·수령 시점·투자성향·계좌 한도로 다시 계산할 때만 바뀌며, 정기 점검만으로 임의 변경하지 않습니다. 이탈 시에는 새 납입금으로 부족한 자산군을 먼저 보완해요.</p>
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
          {ACCOUNT_LABELS[evaluation.evaluated_input.account_type]} · 연금 수령 개시까지 {evaluation.planning_horizon_years}년
        </p>
      </header>

      <article className="portfolio-strategy-explanation">
        <strong>{guide.title}</strong>
        <p>{guide.description}</p>
        <p><b>쉽게 말하면:</b> {guide.analogy}</p>
      </article>

      <p className="portfolio-strategy-transition">
        이 전략에 따르면 {RISK_PROFILE_LABELS[profile]} 연금투자전략은 아래와 같습니다.
      </p>
      <TargetAllocationGuide evaluation={evaluation} />
      <RebalancingCadenceGuide evaluation={evaluation} />

      <section className="portfolio-strategy-planning" aria-labelledby="portfolio-strategy-planning-title">
        <header>
          <span>장기 계획가정</span>
          <h4 id="portfolio-strategy-planning-title">보수·기준 계획수익률</h4>
        </header>
        <div className="portfolio-planning-metrics">
          <div>
            <span>보수 계획수익률</span>
            <strong>{optionalPercent(planning.conservative_planning_return_percent)}</strong>
            <small>CMA·비용·불확실성 할인</small>
          </div>
          <div>
            <span>기준 계획수익률</span>
            <strong>{optionalPercent(planning.base_planning_return_percent)}</strong>
            <small>CMA·ETF 운용비용 반영</small>
          </div>
        </div>
        <div className="planning-source-chips" aria-label="장기 계획수익률 출처">
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
          *이는 J.P. Morgan의 LTCMA 장기 자본시장 가정과 ETF 운용비용을 반영해 산출한 교육용 계획가정이며, 미래 수익률 예측이나 보장값이 아닙니다.
        </p>
      </section>

      <section className="portfolio-theme-next-step" aria-labelledby="portfolio-theme-next-step-title">
        <strong id="portfolio-theme-next-step-title">그러면 어떤 종목을 살까?</strong>
        <p>
          구체 종목의 매수 추천은 하지 않습니다. ETF 섹터 알아보기에서 각 자산 분류를 채울 ETF 테마의 구조와 위험을 확인해 보세요.
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
        <span>과거 관측 기반</span>
        <h4 id="portfolio-risk-title">목표 포트폴리오 위험·스트레스</h4>
        <p>
          {dateText(risk.observation_start)}~{dateText(risk.observation_end)} · 공통 일간 관측 {risk.observation_count.toLocaleString("ko-KR")}개
        </p>
      </header>

      {complete ? (
        <div className="portfolio-risk-metrics">
          <div><span>연환산 변동성</span><strong>{optionalPercent(risk.annualized_volatility_percent)}</strong></div>
          <div><span>연환산 하방편차</span><strong>{optionalPercent(risk.annualized_downside_deviation_percent)}</strong></div>
          <div><span>과거 최대낙폭</span><strong>{optionalPercent(risk.maximum_drawdown_percent)}</strong></div>
          <div><span>과거 95% 1일 손실</span><strong>{optionalPercent(risk.historical_95pct_one_day_loss_percent)}</strong></div>
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
          aria-label="손실감내도 정책 점검"
        >
          <strong>{STRESS_POLICY_STATUS_LABELS[risk.stress_loss_policy_status]}</strong>
          <p>
            사용자 손실감내도 {percent(risk.stress_loss_limit_percent!)} · 최악 정책 스트레스 손실 {percent(risk.worst_stress_loss_percent)}
          </p>
          {reviewRequired && <small>목표비중과 추가 납입 계획을 다시 확인해 주세요. 자동 매도 지시는 만들지 않습니다.</small>}
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
        위 과거 지표는 제안 목표비중을 고정해 측정한 위험 참고치이며 수익률 예측이 아닙니다. 스트레스 값도 발생확률이나 미래 손실 예측이 아닌 교육용 정책 시나리오입니다.
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
        <span>승인된 교육용 계획가정</span>
        <h4 id={titleId}>{title}</h4>
        <p>
          {description} · CMA {planning.cma_source_horizon_min_years}~{planning.cma_source_horizon_max_years}년 기준
          {planning.annual_review_required ? " · 매년 재검토" : ""}
        </p>
      </header>

      <div className="portfolio-planning-metrics">
        <div><span>기준 계획가정</span><strong>{optionalPercent(planning.base_planning_return_percent)}</strong><small>CMA·비용 반영</small></div>
        <div><span>보수 계획가정</span><strong>{optionalPercent(planning.conservative_planning_return_percent)}</strong><small>불확실성 추가 할인</small></div>
        <div><span>비용 차감 전</span><strong>{optionalPercent(planning.gross_planning_return_percent)}</strong><small>불확실성 반영</small></div>
        <div><span>비용 차감 후</span><strong>{optionalPercent(planning.net_planning_return_percent)}</strong><small>연간 비용까지 차감</small></div>
      </div>

      <div className="portfolio-planning-table-wrap">
        <table className="portfolio-planning-table">
          <thead>
            <tr>
              <th>ETF</th>
              <th>목표비중</th>
              <th>CMA</th>
              <th>불확실성</th>
              <th>연간 비용</th>
            </tr>
          </thead>
          <tbody>
            {planning.components.map((component) => (
              <tr key={component.isu_code}>
                <th>{component.isu_name}<small>{component.isu_code}{component.proxy_used ? " · 대체 CMA" : ""}</small></th>
                <td>{percent(component.target_percent)}</td>
                <td>{percent(component.cma_percent)}</td>
                <td>-{percent(component.uncertainty_discount_percent)}</td>
                <td>-{percent(component.annual_cost_drag_percent)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="planning-source-chips" aria-label="장기 계획가정 출처">
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
        엔진 산출 커버리지 {percent(planning.coverage_weight_percent)} · {planning.historical_performance_used ? "과거 수익률 사용" : "과거 수익률 미사용"} · {planning.is_forecast ? "예측값" : "미래 수익률 예측이 아닙니다"}. 위험·스트레스는 위 카드에서 별도로 확인하세요.
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
        <p>현재 평가금액 비중과 CMA·검증 비용을 반영한 교육용 계획가정입니다.</p>
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
        <small>새 납입금으로 비중 차이를 먼저 줄이는 교육용 예시를 계산합니다.</small>
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

  return (
    <section className="portfolio-review" aria-labelledby="portfolio-review-title">
      <header>
        <span>규칙 엔진 결과</span>
        <h3 id="portfolio-review-title">보유 ETF 리밸런싱 점검</h3>
        <p title={evaluation.strategy_label}>{ACCOUNT_LABELS[evaluation.evaluated_input.account_type]} · {strategyLabel(evaluation.strategy_label)}</p>
      </header>

      <div className="portfolio-review-summary">
        <div><span>현재 평가금액</span><strong>{won(rebalancing.current_total_krw)}</strong></div>
        <div><span>일반 위험자산 목표</span><strong>{percent(evaluation.final_general_risk_target_percent)}</strong></div>
        <div>
          <span>계좌 위험자산 한도</span>
          <strong>{evaluation.account_risk_cap_percent == null ? "법정 총량한도 없음" : percent(evaluation.account_risk_cap_percent)}</strong>
        </div>
        <div><span>리밸런싱 기준</span><strong>±{percent(rebalancing.drift_threshold_percent_points)}</strong></div>
      </div>

      <PortfolioSectorGuide riskProfile={evaluation.evaluated_input.risk_profile} />
      <RebalancingCadenceGuide evaluation={evaluation} />

      <div className="overlap-check">
        <strong>중복도·편중 점검</strong>
        <p>현재 보유 비중을 자산군별로 묶어 엔진 목표와 비교했습니다. 같은 역할의 ETF가 몰린 구간은 아래 비중 차이에서 확인할 수 있습니다.</p>
        {highestCorrelation !== null && (
          <p>신규 후보들 사이의 최대 과거 가격 동행성은 {highestCorrelation.toFixed(1)}%입니다. 이는 구성종목 중복률이 아니라 가격 수익률 상관관계입니다.</p>
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
                <td>{percent(sleeve.projected_percent_after_contribution)}</td>
                <td>{won(sleeve.contribution_example_krw)}</td>
                <td><span className={`rebalance-status status-${sleeve.status}`} title={sleeve.status}>{REBALANCE_STATUS_LABELS[sleeve.status] ?? "추가 점검 필요"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <PortfolioRiskReview risk={evaluation.portfolio_risk} />
      {evaluation.current_holdings_planning_return ? (
        <PortfolioPlanningReview
          planning={evaluation.current_holdings_planning_return}
          titleId="current-holdings-planning-title"
          title="현재 보유 ETF CMA·비용 계획가정"
          description="현재 평가금액 비중으로 가중한 보유 ETF 기준"
        />
      ) : evaluation.warnings.some((warning) => warning.startsWith("current_holdings_planning_return_unavailable:")) ? (
        <p className="portfolio-review-warning">
          현재 보유 ETF 중 검증된 비용 또는 계좌별 적격성 데이터가 없는 항목이 있어 CMA·비용 계획가정을 표시하지 못했습니다. 종목코드와 데이터 기준일을 확인해 주세요.
        </p>
      ) : null}
      <PortfolioPlanningReview
        planning={evaluation.planning_return}
        titleId="target-portfolio-planning-title"
        title="제안 포트폴리오 CMA·비용 계획가정"
        description="목표 비중으로 가중한 제안 포트폴리오 기준"
      />

      {Number(rebalancing.unclassified_holding_amount_krw) > 0 && (
        <p className="portfolio-review-warning">
          분류하지 못한 보유 ETF {won(rebalancing.unclassified_holding_amount_krw)}은 비중 계산에 별도로 남겼습니다. 종목코드와 유니버스 기준일을 확인해 주세요.
        </p>
      )}
      {evaluation.account_cap_binding && (
        <p className="portfolio-review-warning">투자성향 목표보다 계좌 위험자산 한도가 먼저 적용되었습니다.</p>
      )}
      <p className="portfolio-review-disclaimer">
        매도 주문을 만들지 않으며, 추가 납입금으로 목표 비중과의 차이를 먼저 줄이는 교육용 가이드입니다.
      </p>
    </section>
  );
}
