import type { DemoUserFinancialContext } from "../api/types";

interface ProfilePageProps {
  onResurvey: () => void;
  userContext: DemoUserFinancialContext | null;
}

export function ProfilePage({ onResurvey, userContext }: ProfilePageProps) {
  return <section>
    <h1 style={{ fontSize: 20 }}>투자자정보</h1>
    <p>투자성향은 로그인 후 작성하는 투자자정보 확인서를 기준으로 관리합니다.</p>
    {userContext && <p style={{ color: "#52645a", fontSize: 13 }}>{userContext.nickname}님의 연금계좌 목데이터 범위에서 ETF 교육용 안내를 제공합니다.</p>}
    <button type="button" onClick={onResurvey}>재설문하기</button>
  </section>;
}
