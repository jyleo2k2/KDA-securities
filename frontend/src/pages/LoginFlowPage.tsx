import { useEffect, useState, type FormEvent, type JSX } from "react";

import bangIcon from "../assets/login/bang.png";
import piggyClean from "../assets/login/piggy-clean.png";
import piggyForm from "../assets/login/piggy-form.webp";
import piggyIntro from "../assets/login/piggy-intro.webp";
import piggySuccess from "../assets/login/piggy-success.png";
import { getAccountLinkOptions, saveInvestmentProfile } from "../api/client";
import type { AccountLinkOptionsResponse, InvestmentProfileAssessment, InvestmentProfileResponse, InvestmentProfileSubmission } from "../api/types";
import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import { InvestorInfoForm } from "./InvestorInfoForm";
import { InvestorResultScreen } from "./InvestorResultScreen";
import "./LoginFlowPage.css";

type LoginStep = "intro" | "form" | "consent" | "success" | "linking" | "risk-assessment" | "investor-info" | "investor-result";

interface LoginFlowPageProps {
  auth: SupabaseAuthState;
  displayName?: string;
  onAuthenticated: () => void;
  onProfileSaved: (profile: InvestmentProfileResponse) => void;
  onStart: () => void;
  resurvey?: boolean;
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

export function LoginFlowPage({ auth, displayName, onAuthenticated, onProfileSaved, onStart, resurvey = false }: LoginFlowPageProps): JSX.Element {
  const [step, setStep] = useState<LoginStep>(resurvey ? "risk-assessment" : "intro");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [consents, setConsents] = useState<Record<string, boolean>>({});
  const [linkOptions, setLinkOptions] = useState<AccountLinkOptionsResponse | null>(null);
  const [linkOptionsLoading, setLinkOptionsLoading] = useState(false);
  const [linkOptionsError, setLinkOptionsError] = useState<string | null>(null);
  const [assessment, setAssessment] = useState<InvestmentProfileAssessment | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!auth.configured) { setNotice("로그인 환경이 설정되지 않았습니다."); return; }
    if (!loginId.trim() || !password || submitting) return;
    setSubmitting(true); setNotice(null);
    try { await auth.signIn(loginId, password); setPassword(""); onAuthenticated(); setStep("success"); }
    catch { /* shared hook exposes a safe error message */ }
    finally { setSubmitting(false); }
  }

  async function loadLinkOptions(): Promise<void> {
    setLinkOptionsLoading(true); setLinkOptionsError(null);
    try { setLinkOptions(await getAccountLinkOptions()); }
    catch { setLinkOptionsError("연결 가능한 계좌 정보를 불러오지 못했습니다."); }
    finally { setLinkOptionsLoading(false); }
  }

  async function saveInvestorInformation(submission: InvestmentProfileSubmission): Promise<void> {
    const accessToken = auth.session?.access_token;
    if (!accessToken) throw new Error("authenticated session is missing");
    const response = await saveInvestmentProfile(submission, accessToken);
    if (response.assessment === null) throw new Error("saved assessment is missing");
    onProfileSaved(response);
    setAssessment(response.assessment);
    setStep("investor-result");
  }

  function openConsent(): void {
    setConsents({}); setStep("consent");
    if (linkOptions === null && !linkOptionsLoading) void loadLinkOptions();
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
                <input value={loginId} onChange={(event) => setLoginId(event.target.value)} placeholder="아이디를 입력하세요" autoComplete="username" disabled={submitting} />
              </label>
              <label>
                <span>비밀번호</span>
                <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호를 입력하세요" autoComplete="current-password" disabled={submitting} />
              </label>
              {auth.error && <p className="login-form-error" role="alert">{auth.error}</p>}{notice && <p className="login-inline-notice" role="status">{notice}</p>}
              <div className="login-links"><button type="button">아이디 찾기</button><i /> <button type="button">비밀번호 찾기</button><i /> <button type="button">회원가입</button></div>
              <div className="login-submit-wrap"><button type="submit" className="login-primary" disabled={submitting}>{submitting ? "로그인 중..." : "로그인하기"}</button></div>
            </form>
          </div>
        )}

        {step === "consent" && (
          <div className="login-consent-page">
            <div className="login-consent-header">
              <button type="button" className="login-back" onClick={() => setStep("success")} aria-label="로그인 성공 화면으로 돌아가기">←</button>
              <h1>연금계좌 연동</h1>
            </div>
            <div className="login-consent-content">
              <section className="login-consent-hero">
                <span>연결 가능한 계좌</span>
                <h2>연금계좌 <em>{linkOptions?.options.filter((option) => option.diagnosable).length ?? 0}종</em>을<br />나눠서 불러와요</h2>
                <p>계좌 종류별로 각각 확인할 수 있어요</p>
                <div className="login-consent-hero-accounts">
                  {linkOptions?.options.filter((option) => option.diagnosable).map((option) => (
                    <div key={option.code} className="login-consent-hero-account">
                      <b>{option.code === "pension_savings" ? "연금" : option.code.toUpperCase()}</b>
                      <span><strong>{option.code === "dc" ? "직접 운용하는 퇴직연금" : option.code === "irp" ? "스스로 적립하는 개인 연금계좌" : "세액공제 받는 개인 연금저축"}</strong><small>{option.category_label}</small></span>
                    </div>
                  ))}
                </div>
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
                {linkOptionsLoading && <p>계좌 정보를 확인하고 있습니다.</p>}
                {linkOptionsError && <div role="alert"><p>{linkOptionsError}</p><button type="button" onClick={() => void loadLinkOptions()}>다시 시도</button></div>}
                {linkOptions?.options.filter((option) => option.diagnosable).map((option) => <p key={option.code}><strong>{option.display_name}</strong><b>{option.category_label}</b></p>)}
              </section>
              <section className="login-consent-safe"><h2>안심하고 연결하세요</h2><p>마이데이터를 통해 내 연금계좌를 안전하게 연동해서 가져와요.</p></section>
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
                disabled={!requiredConsentsMet || linkOptions === null}
                onClick={() => setStep("linking")}
              >
                <span>연동</span> 내 연금계좌 보기
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
              <button type="button" className="login-risk-skip" onClick={onStart}>나중에 할게요</button>
              <p>진단 결과는 <a href="#">투자자 정보</a> 등록에만 사용돼요</p>
            </div>
          </div>
        )}

        {step === "investor-info" && (
          <InvestorInfoForm onBack={() => setStep("risk-assessment")} onSubmit={saveInvestorInformation} />
        )}

        {step === "investor-result" && (
          <InvestorResultScreen assessment={assessment} displayName={displayName} onBack={() => setStep("investor-info")} onStart={onStart} />
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
            <button type="button" className="login-primary" onClick={openConsent}>시작하기</button>
          </div>
        )}
      </section>
    </main>
  );
}
