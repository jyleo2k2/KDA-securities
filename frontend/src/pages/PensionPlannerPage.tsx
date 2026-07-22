import { useState } from "react";

import { calculatePension } from "../api/client";
import type {
  CompletedSurveyProfile,
  DemoUserFinancialContext,
  PensionCalculatorEvaluation,
} from "../api/types";

function won(value: string): string {
  return `${Number(value).toLocaleString("ko-KR")}원`;
}

const SCENARIO_LABELS = {
  low: "보수적 가정",
  base: "기준 가정",
  high: "낙관적 가정",
} as const;

export function PensionPlannerPage({
  profile,
  userContext,
  onBack,
  onOpenProfile,
}: {
  profile: CompletedSurveyProfile | null;
  userContext: DemoUserFinancialContext | null;
  onBack: () => void;
  onOpenProfile: () => void;
}) {
  const [currentBalance, setCurrentBalance] = useState(
    userContext?.total_pension_balance_krw ?? "0",
  );
  const [monthlyContribution, setMonthlyContribution] = useState("0");
  const [contributionEndAge, setContributionEndAge] = useState(
    String(profile?.retirement_start_age ?? 60),
  );
  const [payoutYears, setPayoutYears] = useState("20");
  const [scenario, setScenario] = useState<"low" | "base" | "high">("base");
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [result, setResult] = useState<PensionCalculatorEvaluation | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!profile) {
    return (
      <main style={{ maxWidth: 480, margin: "0 auto", padding: 16 }}>
        <button type="button" onClick={onBack}>가이드로 돌아가기</button>
        <h1>연금 수령 계획</h1>
        <p>계산에는 계좌 유형·나이·투자성향이 필요합니다. 먼저 투자성향 설문을 완료해 주세요.</p>
        <button type="button" onClick={onOpenProfile}>투자성향 설문 열기</button>
      </main>
    );
  }
  const plannerProfile = profile;

  async function submit(selectedStrategyId = strategyId): Promise<void> {
    if (loading) return;
    setError("");
    setLoading(true);
    try {
      setResult(await calculatePension({
        current_age: plannerProfile.current_age,
        contribution_end_age: Number(contributionEndAge),
        current_balance_krw: currentBalance,
        monthly_contribution_krw: monthlyContribution,
        account_type: plannerProfile.account_type,
        risk_profile: plannerProfile.risk_profile,
        strategy_id: selectedStrategyId,
        payout_years: Number(payoutYears),
        scenario,
      }));
    } catch {
      setError("수령 계획을 계산하지 못했습니다. 잔액·납입액과 나이를 확인해 주세요.");
    } finally {
      setLoading(false);
    }
  }

  const finalYear = result?.yearly.at(-1);
  return (
    <main style={{ maxWidth: 480, margin: "0 auto", padding: 16, display: "grid", gap: 18 }}>
      <header>
        <button type="button" onClick={onBack}>가이드로 돌아가기</button>
        <h1>연금 수령 계획</h1>
        <p>규칙 엔진의 교육용 가정 시나리오입니다. 미래 수익이나 수령액을 확정하거나 보장하지 않습니다.</p>
      </header>

      <section aria-label="연금 수령 계획 입력" style={{ display: "grid", gap: 12 }}>
        <p>설문 기준: {profile.current_age}세 · {profile.account_type} · {profile.risk_profile}</p>
        <label>현재 연금자산 잔액<input type="number" min="0" inputMode="numeric" value={currentBalance} onChange={(event) => setCurrentBalance(event.target.value)} /></label>
        <label>월 납입액<input type="number" min="0" inputMode="numeric" value={monthlyContribution} onChange={(event) => setMonthlyContribution(event.target.value)} /></label>
        <label>납입 종료 나이<select value={contributionEndAge} onChange={(event) => setContributionEndAge(event.target.value)}>{Array.from({ length: 16 }, (_, index) => 55 + index).map((age) => <option key={age} value={age}>{age}세</option>)}</select></label>
        <label>수령기간<select value={payoutYears} onChange={(event) => setPayoutYears(event.target.value)}>{[10, 15, 20, 25, 30, 40].map((years) => <option key={years} value={years}>{years}년</option>)}</select></label>
        <label>가정 시나리오<select value={scenario} onChange={(event) => setScenario(event.target.value as typeof scenario)}>{Object.entries(SCENARIO_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {error && <p role="alert">{error}</p>}
        <button type="button" onClick={() => void submit()} disabled={loading}>{loading ? "계산 중…" : "수령 계획 계산"}</button>
      </section>

      {result && <section aria-label="연금 수령 계획 결과" style={{ display: "grid", gap: 14 }}>
        <h2>가정 시나리오 결과</h2>
        <div className="portfolio-review-summary">
          <div><span>수령 시작 시점 계획 잔액</span><strong>{won(result.headline.total_krw)}</strong></div>
          <div><span>총 납입원금</span><strong>{won(result.headline.total_principal_krw)}</strong></div>
          <div><span>월 수령 계획금액(세전)</span><strong>{won(result.headline.monthly_payout_pretax_krw)}</strong></div>
          <div><span>월 수령 계획금액(1년차 세후)</span><strong>{won(result.headline.monthly_payout_after_tax_krw)}</strong></div>
        </div>
        {finalYear && <p>{finalYear.age}세 기준 적립 경로: 원금 {won(finalYear.cumulative_principal_krw)} · 수익금 {won(finalYear.cumulative_gain_krw)}</p>}
        <section aria-labelledby="strategy-recommendation-heading">
          <h3 id="strategy-recommendation-heading">성향 범위 안의 전략 카드</h3>
          <p>카드를 누르면 해당 전략의 교육용 가정으로 같은 입력을 다시 계산합니다.</p>
          <div className="planner-strategy-grid">
            {result.strategies.filter((strategy) => strategy.within_profile).map((strategy) => (
              <button
                aria-pressed={strategyId === strategy.strategy_id}
                disabled={loading}
                key={strategy.strategy_id}
                onClick={() => {
                  setStrategyId(strategy.strategy_id);
                  void submit(strategy.strategy_id);
                }}
                type="button"
              >
                <small>{strategy.presentation.risk_badge}</small>
                <strong>{strategy.presentation.display_name}</strong>
                <span>{strategy.presentation.summary}</span>
                <em>비용 차감 후 가정 {strategy.net_annual_return_percent}%</em>
              </button>
            ))}
          </div>
        </section>
        <p>수령 관련 세율 가정: {result.tax.effective_rate_percent}% · 연금수령 한도 및 이연퇴직소득 재원은 별도 확인이 필요합니다.</p>
        <div className="planning-source-chips" aria-label="계산 가정 출처"><a href={result.assumption.source.reference} target="_blank" rel="noreferrer">{result.assumption.source.label} · {result.assumption.source.as_of}</a></div>
        <p>{result.assumption.notice}</p>
        {result.warnings.map((warning) => <p key={warning}>{warning}</p>)}
      </section>}
    </main>
  );
}
