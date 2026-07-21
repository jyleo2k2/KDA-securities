import { useState, type FormEvent, type JSX } from "react";

import piggyForm from "../assets/login/piggy-form.png";
import piggyIntro from "../assets/login/piggy-intro.png";
import piggySuccess from "../assets/login/piggy-success.png";
import { getAccountLinkOptions } from "../api/client";
import type { AccountLinkOptionsResponse } from "../api/types";
import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import "./LoginFlowPage.css";

type LoginStep = "intro" | "form" | "success" | "consent";
interface LoginFlowPageProps { auth: SupabaseAuthState; onStart: () => void; onAuthenticated: () => void; }
function StatusBar(): JSX.Element { return <div className="login-status-bar" aria-hidden="true"><span>9:41</span><span className="login-status-icons">● ● ● ▰</span></div>; }

export function LoginFlowPage({ auth, onStart, onAuthenticated }: LoginFlowPageProps): JSX.Element {
  const [step, setStep] = useState<LoginStep>("intro");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [linkOptions, setLinkOptions] = useState<AccountLinkOptionsResponse | null>(null);
  const [linkOptionsLoading, setLinkOptionsLoading] = useState(false);
  const [linkOptionsError, setLinkOptionsError] = useState<string | null>(null);
  const [requiredConsent, setRequiredConsent] = useState(false);
  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!auth.configured) { setNotice("로그인 환경이 설정되지 않았습니다."); return; }
    if (!loginId.trim() || !password || submitting) return;
    setSubmitting(true); setNotice(null);
    try { await auth.signIn(loginId, password); setPassword(""); onAuthenticated(); setStep("success"); } catch { /* shared hook exposes a safe error */ } finally { setSubmitting(false); }
  }
  function showSignupNotice(): void { setNotice("회원가입은 준비 중입니다."); }
  async function loadLinkOptions(): Promise<void> {
    setLinkOptionsLoading(true); setLinkOptionsError(null);
    try { setLinkOptions(await getAccountLinkOptions()); }
    catch { setLinkOptionsError("연결 가능한 계좌 정보를 불러오지 못했습니다."); }
    finally { setLinkOptionsLoading(false); }
  }
  function openConsent(): void {
    setRequiredConsent(false); setStep("consent");
    if (linkOptions === null && !linkOptionsLoading) void loadLinkOptions();
  }
  const diagnosableOptionCount = linkOptions?.options.filter((option) => option.diagnosable).length ?? 0;
  return <main className="login-flow-stage"><section className="login-flow-phone" aria-label="연금 도우미 로그인"><StatusBar />
    {step === "intro" && <div className="login-intro"><div className="login-intro-copy"><p className="login-kicker">연금 도우미</p><h1>차곡차곡 모아<br />든든한 <em>미래</em>로</h1><p>연금 준비가 쉬워지는 나만의 가이드</p><div className="login-page-dots"><b /><i /><i /></div></div><div className="login-intro-visual"><span className="login-bill login-bill-one">₩</span><span className="login-bill login-bill-two">₩</span><img src={piggyIntro} alt="저금통" /></div><div className="login-intro-actions"><button type="button" className="login-primary" onClick={() => setStep("form")}>로그인</button><button type="button" className="login-secondary" onClick={showSignupNotice}>회원가입</button>{notice && <p className="login-inline-notice" role="status">{notice}</p>}<p>서비스 시작은 이용약관 및 개인정보 처리방침 동의로 간주됩니다.</p></div></div>}
    {step === "form" && <div className="login-form-page"><button type="button" className="login-back" onClick={() => setStep("intro")} aria-label="이전 화면">←</button><h1>로그인</h1><div className="login-form-brand"><img src={piggyForm} alt="저금통" /></div><h2>안녕하세요.<br /><em>연금</em> 도우미입니다.</h2><p>맞춤 서비스를 이용하기 위해 로그인해 주세요.</p><form onSubmit={(event) => void handleSubmit(event)}><label><span>아이디</span><input value={loginId} onChange={(event) => setLoginId(event.target.value)} placeholder="아이디를 입력하세요" autoComplete="username" disabled={submitting} /></label><label><span>비밀번호</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호를 입력하세요" autoComplete="current-password" disabled={submitting} /></label>{auth.error && <p className="login-form-error" role="alert">{auth.error}</p>}{notice && <p className="login-inline-notice" role="status">{notice}</p>}<div className="login-links"><button type="button">아이디 찾기</button><i /> <button type="button">비밀번호 찾기</button><i /> <button type="button" onClick={showSignupNotice}>회원가입</button></div><div className="login-submit-wrap"><button type="submit" className="login-primary" disabled={submitting}>{submitting ? "로그인 중..." : "로그인하기"}</button></div></form></div>}
    {step === "success" && <div className="login-success-page"><header><h1><em>로그인 성공!</em><br />이제 차곡차곡 모아볼까요?</h1><p>오늘부터 연금의 든든한 길을 함께 찾아볼게요.</p></header><div className="login-success-visual"><span className="login-bill login-bill-one">₩</span><span className="login-bill login-bill-two">₩</span><span className="login-sparkle">✦</span><img src={piggySuccess} alt="저금통" /></div><button type="button" className="login-primary" onClick={openConsent}>시작하기</button></div>}
    {step === "consent" && <div className="login-consent-page">
      <button type="button" className="login-back" onClick={() => setStep("success")} aria-label="로그인 성공 화면으로 돌아가기">←</button>
      <h1>연금계좌 연동</h1>
      <div className="login-consent-content">
        {linkOptionsLoading && <p className="login-consent-status" role="status">연결 가능한 계좌를 확인하고 있습니다.</p>}
        {linkOptionsError && <div className="login-consent-error" role="alert"><p>{linkOptionsError}</p><button type="button" onClick={() => void loadLinkOptions()}>다시 시도</button></div>}
        {linkOptions && <>
          <div className="login-consent-chips" aria-label="계좌 연동 특징"><span>데모</span><span>조회</span><b>{diagnosableOptionCount}종 계좌</b></div>
          <section className="login-consent-hero"><span>통합해서 확인하는 계좌</span><h2>{diagnosableOptionCount}개 <em>연금계좌</em></h2><p>한 번에 불러와 통합 자산으로 확인해요.</p><small>현재 MVP는 목데이터이며 실제 계좌 연결이 아닙니다.</small></section>
          <section className="login-consent-card login-consent-accounts"><h2>연결할 수 있는 계좌</h2>{linkOptions.options.map((option) => <div className="login-consent-account" key={option.code}><p><strong>{option.display_name}</strong><b>{option.category_label}</b></p>{option.description && <small>{option.description}</small>}</div>)}</section>
          <section className="login-consent-safe"><h2>안심하고 확인하세요</h2><p>{linkOptions.notice}</p></section>
          <section className="login-consent-card login-consent-check-card"><h2>연결 전 확인</h2><dl><dt>불러오는 정보</dt><dd>금융회사와 계좌 종류<br />잔액 · 평가금액 · 보유 상품 · 정보 기준일</dd><dt>이용 목적</dt><dd>연금자산 통합조회와 운용 현황 분석</dd></dl><button type="button" className="login-consent-item" aria-pressed={requiredConsent} onClick={() => setRequiredConsent((checked) => !checked)}><span className="login-consent-box" aria-hidden="true">{requiredConsent && "✓"}</span><span>필수 정보 이용 내용을 확인했습니다.</span></button></section>
        </>}
      </div>
      <div className="login-consent-cta"><button type="button" className="login-primary" disabled={linkOptions === null || !requiredConsent} onClick={onStart}><span>연동</span> 내 연금계좌 보기</button></div>
    </div>}
  </section></main>;
}
