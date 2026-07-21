import { useMemo, useState, type FormEvent } from "react";

import type {
  AccountType,
  CompletedSurveyProfile,
  EducationalPortfolioEvaluation,
  EducationalPortfolioInput,
  PortfolioPlanningEvaluation,
  PortfolioRiskEvaluation,
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

const STRATEGY_LABELS: Record<string, string> = {
  capital_preservation_core: "자본보전 중심 전략",
  defensive_diversified_core: "방어적 분산 전략",
  balanced_core_satellite: "코어·위성 전략",
  growth_core_satellite: "성장 코어·위성 전략",
  barbell_growth_tactical: "바벨형 성장·전술 전략",
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

function PortfolioRiskReview({ risk }: { risk: PortfolioRiskEvaluation }) {
  const complete = risk.status === "complete";

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
      <p className="portfolio-risk-note">
        위 과거 지표는 제안 목표비중을 고정해 측정한 위험 참고치이며 수익률 예측이 아닙니다. 스트레스 값도 발생확률이나 미래 손실 예측이 아닌 교육용 정책 시나리오입니다.
      </p>
    </section>
  );
}

function PortfolioPlanningReview({
  planning,
}: {
  planning: PortfolioPlanningEvaluation;
}) {
  return (
    <section className="portfolio-planning-review" aria-labelledby="portfolio-planning-title">
      <header>
        <span>승인된 교육용 계획가정</span>
        <h4 id="portfolio-planning-title">장기 계획수익률 가정 근거</h4>
        <p>
          승인 장기 가정 · CMA {planning.cma_source_horizon_min_years}~{planning.cma_source_horizon_max_years}년 기준
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
      {error && <p className="holdings-form-error" role="alert">{error}</p>}
      <button className="holdings-analyze" type="submit" disabled={disabled}>
        {disabled ? "분석 중…" : "보유 ETF 분석하기"}
      </button>
    </form>
  );
}

export function EducationalPortfolioReview({
  evaluation,
}: {
  evaluation?: EducationalPortfolioEvaluation | null;
}) {
  if (!evaluation?.evaluated_input.current_holdings.length) return null;

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
      <PortfolioPlanningReview planning={evaluation.planning_return} />

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
