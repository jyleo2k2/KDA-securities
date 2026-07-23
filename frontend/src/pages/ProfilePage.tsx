import profileIcon from "../assets/main-home/profile-icon.webp";
import type { DemoUserFinancialContext, InvestmentProfileResponse, RiskProfile } from "../api/types";
import "./ProfilePage.css";

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
  const nickname = userContext?.nickname.replace(/\(가상\)/g, "") ?? "연금 사용자";

  return <section className="profile-page" aria-label="내 프로필">
    <header className="profile-page-header"><h1>내 페이지</h1><p>저장된 투자자정보와 연금 데이터 범위를 확인해요.</p></header>
    <section className="profile-user-row">
      <img src={profileIcon} alt="프로필" />
      <div><strong>{nickname}</strong><p>{userContext ? `${userContext.as_of_date} 기준 데모 프로필` : "연금계좌 정보 미연결"}</p></div>
    </section>
    <section className="profile-stat-grid" aria-label="프로필 데이터 요약">
      <div><span>데이터 구분</span><strong>{userContext ? "목데이터" : "미연결"}</strong></div>
      <div><span>정보 기준일</span><strong>{userContext?.as_of_date ?? "-"}</strong></div>
    </section>
    <section className="profile-investor-card">
      <div>
        <span>저장 투자성향</span>
        <strong>{assessment ? PROFILE_LABELS[assessment.risk_profile] : "진단 전"}</strong>
        {assessment ? <p>진단일 {assessment.assessed_on} · 유효기한 {assessment.valid_until}</p> : <p>저장된 투자성향이 없습니다.</p>}
        {assessment?.is_expired && <p className="profile-expired">투자성향 유효기간이 만료됐어요.</p>}
      </div>
      <button type="button" onClick={onResurvey}>진단 다시하기</button>
    </section>
    <p className="profile-boundary-note">표시 정보는 교육용 데모 목데이터이며 실제 금융사 계좌 연결·이전·자동매매가 발생하지 않아요.</p>
  </section>;
}
