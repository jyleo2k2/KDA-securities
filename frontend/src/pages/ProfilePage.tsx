import type { DemoUserFinancialContext } from "../api/types";
import profileIcon from "../assets/main-home/profile-icon.png";
import "./ProfilePage.css";

interface ProfilePageProps {
  onBack: () => void;
  onOpenChatHistory: () => void;
  onResurvey: () => void;
  userContext: DemoUserFinancialContext | null;
}

export function ProfilePage({ onBack, onOpenChatHistory, onResurvey, userContext }: ProfilePageProps) {
  const nickname = userContext?.nickname ?? "김연금";

  return <main className="profile-stage">
    <section className="profile-phone" aria-label="내 프로필">
      <div className="profile-statusbar"><span>9:41</span><span aria-hidden="true">● ● ▰</span></div>
      <header className="profile-header"><button type="button" onClick={onBack} aria-label="홈 화면으로 돌아가기">‹</button><h1>내 페이지</h1></header>
      <div className="profile-body">
        <section className="profile-user-row">
          <img src={profileIcon} alt="프로필" />
          <div><strong>{nickname}</strong><p>yeongeum@example.com</p></div>
          <button type="button" className="profile-outline-button">개인정보 변경</button>
        </section>
        <section className="profile-stat-grid">
          <div><span>서비스 이용</span><strong>14<small>개월째</small></strong></div>
          <div><span>종사 업종</span><strong>제조업 · 반도체</strong></div>
        </section>
        <section className="profile-investor-card">
          <div><span>투자자 성향</span><strong>적극투자형</strong><p>일반금융소비자 투자성향 진단 기준</p></div>
          <button type="button" onClick={onResurvey}><span>진단 다시하기</span><small>하루 3회 가능</small></button>
        </section>
        <section className="profile-menu-list">
          {['앱 설정', '인증 / 보안', 'ID / 비밀번호 관리'].map((item) => <button type="button" key={item}><span>{item}</span><b>›</b></button>)}
          <button type="button" onClick={onOpenChatHistory}><span>채팅 기록</span><b>›</b></button>
        </section>
      </div>
    </section>
  </main>;
}
