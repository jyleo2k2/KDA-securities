import { useState, type FormEvent, type JSX } from "react";

import piggyForm from "../assets/login/piggy-form.png";
import piggyIntro from "../assets/login/piggy-intro.png";
import piggySuccess from "../assets/login/piggy-success.png";
import { useSupabaseAuth } from "../auth/useSupabaseAuth";
import "./LoginFlowPage.css";

type LoginStep = "intro" | "form" | "success";

interface LoginFlowPageProps {
  onStart: () => void;
  onAuthenticated: () => void;
}

function StatusBar(): JSX.Element {
  return (
    <div className="login-status-bar" aria-hidden="true">
      <span>9:41</span>
      <span className="login-status-icons">● ● ● ▰</span>
    </div>
  );
}

export function LoginFlowPage({
  onStart,
  onAuthenticated,
}: LoginFlowPageProps): JSX.Element {
  const auth = useSupabaseAuth();
  const [step, setStep] = useState<LoginStep>("intro");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!loginId.trim() || !password || submitting) return;
    setSubmitting(true);
    setNotice(null);
    try {
      await auth.signIn(loginId, password);
      setPassword("");
      onAuthenticated();
      setStep("success");
    } catch {
      // The shared auth hook exposes a user-safe error message for this form.
    } finally {
      setSubmitting(false);
    }
  }

  function showSignupNotice(): void {
    setNotice("회원가입은 준비 중입니다.");
  }

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
              <button type="button" className="login-secondary" onClick={showSignupNotice}>회원가입</button>
              {notice && <p className="login-inline-notice" role="status">{notice}</p>}
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
            <form onSubmit={(event) => void handleSubmit(event)}>
              <label>
                <span>아이디</span>
                <input value={loginId} onChange={(event) => setLoginId(event.target.value)} placeholder="아이디를 입력하세요" autoComplete="username" />
              </label>
              <label>
                <span>비밀번호</span>
                <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호를 입력하세요" autoComplete="current-password" />
              </label>
              {auth.error && <p className="login-form-error" role="alert">{auth.error}</p>}
              {notice && <p className="login-inline-notice" role="status">{notice}</p>}
              <div className="login-links"><button type="button">아이디 찾기</button><i /> <button type="button">비밀번호 찾기</button><i /> <button type="button" onClick={showSignupNotice}>회원가입</button></div>
              <div className="login-submit-wrap"><button type="submit" className="login-primary" disabled={submitting}>{submitting ? "로그인 중..." : "로그인하기"}</button></div>
            </form>
          </div>
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
            <button type="button" className="login-primary" onClick={onStart}>시작하기</button>
          </div>
        )}
      </section>
    </main>
  );
}
