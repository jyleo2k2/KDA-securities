import { useEffect, useState, type FormEvent, type JSX } from "react";

import bangIcon from "../assets/login/bang.png";
import piggyClean from "../assets/login/piggy-clean.png";
import piggyForm from "../assets/login/piggy-form.png";
import piggyIntro from "../assets/login/piggy-intro.png";
import piggySuccess from "../assets/login/piggy-success.png";
import { InvestorInfoForm } from "./InvestorInfoForm";
import { InvestorResultScreen } from "./InvestorResultScreen";
import "./LoginFlowPage.css";

type LoginStep = "intro" | "form" | "consent" | "success" | "linking" | "risk-assessment" | "investor-info" | "investor-result";

interface LoginFlowPageProps {
  onStart: () => void;
}

const REQUIRED_CONSENT_ID = "account-link";
const LINKING_DURATION_MS = 1500;

function StatusBar(): JSX.Element {
  return (
    <div className="login-status-bar" aria-hidden="true">
      <span>9:41</span>
      <span className="login-status-icons">● ● ● ▰</span>
    </div>
  );
}

export function LoginFlowPage({ onStart }: LoginFlowPageProps): JSX.Element {
  const [step, setStep] = useState<LoginStep>("intro");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [consents, setConsents] = useState<Record<string, boolean>>({});

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setStep("success");
  }

  function toggleConsent(id: string): void {
    setConsents((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  const requiredConsentsMet = Boolean(consents[REQUIRED_CONSENT_ID]);

  // 연금계좌 연동 중 화면을 잠시 보여준 뒤 성향진단 화면으로 자동 전환한다.
  useEffect(() => {
    if (step !== "linking") return;
    const timer = window.setTimeout(() => setStep("risk-assessment"), LINKING_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [step]);

  return (
    <main className="login-flow-stage">
      <section className="login-flow-phone" aria-label="연금 도우미 로그인">
        <StatusBar />

        {step === "intro" && (
          <div className="login-intro">
            <div className="login-intro-copy">
              <p className="login-kicker">연금 도우미</p>
              <h1>차곡차곡 모아<br />든든한 <em>미래</em>로</h1>
              <p>연금 준비가 쉬워지는 나만의 가이드</p>
              <div className="login-page-dots"><b /><i /><i /></div>
            </div>
            <div className="login-intro-visual">
              <span className="login-bill login-bill-one">₩</span>
              <span className="login-bill login-bill-two">₩</span>
              <img src={piggyIntro} alt="저금통" />
            </div>
            <div className="login-intro-actions">
              <button type="button" className="login-primary" onClick={() => setStep("form")}>로그인</button>
              <button type="button" className="login-secondary">회원가입</button>
              <p>서비스 시작은 이용약관 및 개인정보 처리방침 동의로 간주됩니다.</p>
            </div>
          </div>
        )}

        {step === "form" && (
          <div className="login-form-page">
            <button type="button" className="login-back" onClick={() => setStep("intro")} aria-label="이전 화면">←</button>
            <h1>로그인</h1>
            <div className="login-form-brand"><img src={piggyForm} alt="저금통" /></div>
            <h2>안녕하세요.<br /><em>연금</em> 도우미입니다.</h2>
            <p>맞춤 서비스를 이용하기 위해 로그인해 주세요.</p>
            <form onSubmit={handleSubmit}>
              <label>
                <span>아이디</span>
                <input value={loginId} onChange={(event) => setLoginId(event.target.value)} placeholder="아이디를 입력하세요" autoComplete="username" />
              </label>
              <label>
                <span>비밀번호</span>
                <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호를 입력하세요" autoComplete="current-password" />
              </label>
              <div className="login-links"><button type="button">아이디 찾기</button><i /> <button type="button">비밀번호 찾기</button><i /> <button type="button">회원가입</button></div>
              <div className="login-submit-wrap"><button type="submit" className="login-primary">로그인하기</button></div>
            </form>
          </div>
        )}

        {step === "consent" && (
          <div className="login-consent-page">
            <button type="button" className="login-back" onClick={() => setStep("success")} aria-label="이전 화면">←</button>
            <h1>연금계좌 연동</h1>
            <div className="login-consent-content">
              <div className="login-consent-chips" aria-label="계좌 연동 특징">
                <span>데모</span><span>조회</span><b>3종 계좌</b>
              </div>
              <section className="login-consent-hero">
                <span>연결 가능한 계좌</span>
                <h2>DC&nbsp; IRP<br /><em>연금저축</em></h2>
                <p>한 번에 불러와 통합 자산으로 확인</p>
                <small>현재 MVP는 목데이터 · 실제 계좌 연결 아님</small>
              </section>
              <section className="login-consent-card">
                <strong>불러오면 확인하는 내용</strong>
                <h2>3개 연금계좌 통합</h2>
                <div className="login-consent-progress"><i /></div>
                <b className="login-consent-highlight">전체 자산과 비중을 한눈에</b>
                <p>적립금 · 보유상품 · 현금성 · 위험자산 비중을 확인해요.</p>
              </section>
              <section className="login-consent-card login-consent-accounts">
                <h2>연결할 수 있는 계좌</h2>
                <p><strong>DC형 퇴직연금</strong><b>직접 운용 계좌</b></p>
                <p><strong>IRP · 연금저축</strong><b>개인 연금계좌</b></p>
                <small>DB형은 가입 여부만 확인하고 운용 진단에서는 제외해요.</small>
              </section>
              <section className="login-consent-safe">
                <h2>안심하고 연결하세요</h2>
                <p>계좌 불러오기는 조회와 분석을 위한 연결이에요.<br />계좌가 이전되거나 상품이 자동으로 매매되지 않아요.<br />연결은 언제든 해제할 수 있어요.</p>
              </section>
              <section className="login-consent-card login-consent-check-card">
                <h2>연결 전 확인</h2>
                <dl><dt>불러오는 정보</dt><dd>금융회사와 계좌 종류<br />잔액 · 평가금액 · 보유 상품 · 정보 기준일</dd><dt>이용 목적</dt><dd>연금자산 통합조회와 운용 현황 분석</dd></dl>
                <button
                  type="button"
                  className="login-consent-item"
                  aria-pressed={requiredConsentsMet}
                  onClick={() => toggleConsent(REQUIRED_CONSENT_ID)}
                >
                  <span className="login-consent-box" aria-hidden="true">{requiredConsentsMet && "✓"}</span>
                  <span>필수 정보 이용 내용을 확인했습니다.</span>
                </button>
              </section>
            </div>
            <div className="login-consent-cta">
              <button
                type="button"
                className="login-primary"
                disabled={!requiredConsentsMet}
                onClick={() => setStep("linking")}
              >
                <span>연동</span> 내 연금계좌 찾기
              </button>
            </div>
          </div>
        )}

        {step === "linking" && (
          <div className="login-linking-page">
            <div className="login-linking-copy">
              <h1>연금 계좌에 <em>연동</em>하고 있어요</h1>
              <p>조금만 기다려주세요</p>
            </div>
            <div className="login-linking-visual">
              <img src={piggyClean} alt="저금통" />
            </div>
            <div className="login-linking-status">
              <span className="login-linking-spinner" aria-hidden="true" />
              <span>안전하게 연결하는 중…</span>
            </div>
          </div>
        )}

        {step === "risk-assessment" && (
          <div className="login-risk-page">
            <div className="login-risk-copy">
              <h1><em>투자자 정보</em>가<br />필요해요!</h1>
              <p>설문지에 응답하여 성향을 진단해보세요!</p>
            </div>
            <div className="login-risk-visual">
              <div className="login-risk-piggy-wrap">
                <img className="login-risk-bang" src={bangIcon} alt="!" />
                <img className="login-risk-piggy" src={piggyClean} alt="저금통" />
              </div>
            </div>
            <div className="login-risk-actions">
              <button type="button" className="login-primary" onClick={() => setStep("investor-info")}>투자 성향 진단받기</button>
              <button type="button" className="login-risk-skip" onClick={() => setStep("consent")}>나중에 할게요</button>
              <p>진단 결과는 <a href="#">투자자 정보</a> 등록에만 사용돼요</p>
            </div>
          </div>
        )}

        {step === "investor-info" && (
          <InvestorInfoForm onBack={() => setStep("risk-assessment")} onSubmit={() => setStep("investor-result")} />
        )}

        {step === "investor-result" && (
          <InvestorResultScreen onBack={() => setStep("investor-info")} onStart={onStart} />
        )}

        {step === "success" && (
          <div className="login-success-page">
            <header>
              <h1><em>로그인 성공!</em><br />이제 차곡차곡 모아볼까요?</h1>
              <p>오늘부터 연금의 든든한 길을 함께 찾아볼게요.</p>
            </header>
            <div className="login-success-visual">
              <span className="login-bill login-bill-one">₩</span>
              <span className="login-bill login-bill-two">₩</span>
              <span className="login-sparkle">✦</span>
              <img src={piggySuccess} alt="저금통" />
            </div>
            <button type="button" className="login-primary" onClick={() => setStep("consent")}>시작하기</button>
          </div>
        )}
      </section>
    </main>
  );
}
