import type { DemoUserFinancialContext, InvestmentProfileResponse, RiskProfile } from "../api/types";

interface ProfilePageProps {
  investmentProfile: InvestmentProfileResponse | null;
  onResurvey: () => void;
  userContext: DemoUserFinancialContext | null;
}

const PROFILE_LABELS: Record<RiskProfile, string> = {
  stable: "안정형",
  stable_seeking: "안정추구형",
  risk_neutral: "위험중립형",
  active: "적극투자형",
  aggressive: "공격투자형",
};

export function ProfilePage({ investmentProfile, onResurvey, userContext }: ProfilePageProps) {
  const assessment = investmentProfile?.assessment;
  return <section>
    <h1 style={{ fontSize: 20 }}>투자자정보</h1>
    <p>투자성향은 로그인 후 작성하는 투자자정보 확인서를 기준으로 관리합니다.</p>
    {assessment ? <div>
      <strong>{PROFILE_LABELS[assessment.risk_profile]}</strong>
      <p>최근 진단일 {new Date(assessment.assessed_at).toLocaleDateString("ko-KR")} · 유효기한 {assessment.valid_until}</p>
      {assessment.is_expired && <p>투자성향 유효기간이 만료되어 재설문이 필요합니다.</p>}
    </div> : <p>저장된 투자성향이 없습니다.</p>}
    {userContext && <p style={{ color: "#52645a", fontSize: 13 }}>{userContext.nickname.replace(/\(가상\)/g, "")}님의 연금계좌 정보를 바탕으로 ETF 교육용 안내를 제공합니다.</p>}
    <button type="button" onClick={onResurvey}>재설문하기</button>
  </section>;
}
