import { useState, type FormEvent } from "react";

import { evaluateProfileSurvey } from "../api/client";
import type {
  AccountType,
  CompletedSurveyProfile,
  DemoUserFinancialContext,
  RiskProfile,
  SurveyAnswer,
} from "../api/types";

const QUESTIONS = [
  ["investment_horizon", "투자 예정 기간"],
  ["investment_experience", "투자 경험"],
  ["financial_knowledge", "금융상품 지식 수준"],
  ["risky_asset_share", "현재 위험자산 비중"],
  ["loss_tolerance", "감내 가능한 손실 수준"],
  ["income_stability", "소득 안정성"],
] as const;

const PROFILE_LABELS: Record<RiskProfile, string> = {
  stable: "안정형",
  stable_seeking: "안정추구형",
  risk_neutral: "위험중립형",
  active: "적극투자형",
  aggressive: "공격투자형",
};

interface ProfilePageProps {
  profile: CompletedSurveyProfile | null;
  onComplete: (profile: CompletedSurveyProfile) => void;
  userContext: DemoUserFinancialContext | null;
}

export function ProfilePage({ profile, onComplete, userContext }: ProfilePageProps) {
  const [accountType, setAccountType] = useState<AccountType>(
    profile?.account_type ?? "irp",
  );
  const [currentAge, setCurrentAge] = useState(profile?.current_age ?? 35);
  const [retirementAge, setRetirementAge] = useState(
    profile?.retirement_start_age ?? 60,
  );
  const [scores, setScores] = useState<Record<string, number>>(
    Object.fromEntries(QUESTIONS.map(([code]) => [code, 3])),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const answers: SurveyAnswer[] = QUESTIONS.map(([questionCode]) => ({
        question_code: questionCode,
        selected_score: scores[questionCode],
      }));
      const evaluation = await evaluateProfileSurvey({ answers });
      onComplete({
        account_type: accountType,
        current_age: currentAge,
        retirement_start_age: retirementAge,
        risk_profile: evaluation.risk_profile,
        loss_tolerance_percent: evaluation.loss_tolerance_percent,
      });
    } catch {
      setError("설문 결과를 계산하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h1 style={{ fontSize: 20 }}>투자성향 설문</h1>
      {userContext && (
        <section style={{ marginBottom: 20, padding: 14, borderRadius: 12, background: "#f4f7ee" }}>
          <span className="mock-chip">대표 시나리오 목데이터</span>
          <h2 style={{ margin: "8px 0 4px", fontSize: 17 }}>{userContext.nickname}</h2>
          <p style={{ margin: 0, color: "#52645a", fontSize: 13 }}>
            {userContext.representative_age}세 · {userContext.customer_context}
          </p>
        </section>
      )}
      {profile && (
        <p style={{ color: "#1a6148", fontWeight: 700 }}>
          현재 결과: {PROFILE_LABELS[profile.risk_profile]}
        </p>
      )}
      <form onSubmit={submit} style={{ display: "grid", gap: 16 }}>
        <label>
          <span style={{ display: "block", marginBottom: 6 }}>연금계좌</span>
          <select
            value={accountType}
            onChange={(event) => setAccountType(event.target.value as AccountType)}
          >
            <option value="dc">DC형</option>
            <option value="irp">IRP</option>
            <option value="pension_savings">연금저축펀드</option>
          </select>
        </label>
        <label>
          <span style={{ display: "block", marginBottom: 6 }}>현재 나이</span>
          <input
            type="number"
            min={20}
            max={54}
            value={currentAge}
            onChange={(event) => setCurrentAge(Number(event.target.value))}
            required
          />
        </label>
        <label>
          <span style={{ display: "block", marginBottom: 6 }}>
            연금 수령 개시 나이
          </span>
          <input
            type="number"
            min={55}
            max={60}
            value={retirementAge}
            onChange={(event) => setRetirementAge(Number(event.target.value))}
            required
          />
        </label>
        {QUESTIONS.map(([code, topic]) => (
          <label key={code}>
            <span style={{ display: "block", marginBottom: 6 }}>{topic}</span>
            <select
              value={scores[code]}
              onChange={(event) => setScores((current) => ({
                ...current,
                [code]: Number(event.target.value),
              }))}
            >
              {[1, 2, 3, 4, 5].map((score) => (
                <option value={score} key={score}>{score}점</option>
              ))}
            </select>
          </label>
        ))}
        {error && <p style={{ color: "#b42318", margin: 0 }}>{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "계산 중" : "설문 완료"}
        </button>
      </form>
    </section>
  );
}
