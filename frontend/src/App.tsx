import { useEffect, useRef, useState, type JSX } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import {
  ApiError,
  apiErrorMessage,
  getDemoHeroes,
  getInvestmentProfile,
  getMyPensionContext,
} from "./api/client";
import type {
  DemoHeroPortfolio,
  DemoUserFinancialContext,
  InvestmentProfileResponse,
} from "./api/types";
import { useSupabaseAuth } from "./auth/useSupabaseAuth";
import { TabBar, type TabKey } from "./components/TabBar";
import { GuidePage } from "./pages/GuidePage";
import { HomePage } from "./pages/HomePage";
import { LoginFlowPage } from "./pages/LoginFlowPage";
import { MainHomeScreen } from "./pages/MainHomeScreen";
import {
  PensionPlannerPage,
  type PensionPlannerProfile,
} from "./pages/PensionPlannerPage";
import { ProfilePage } from "./pages/ProfilePage";
import { StrategyExploreScreen } from "./pages/StrategyExploreScreen";
import { StrategyDetailScreen } from "./pages/StrategyDetailScreen";
import { UserPickBenchmarkScreen } from "./pages/UserPickBenchmarkScreen";
import {
  clearPersistedUserState,
  persistSelectedScenario,
  selectedScenarioFromStorage,
} from "./pwa/cachePolicy";

const RISK_PROFILES = new Set(["stable", "stable_seeking", "risk_neutral", "active", "aggressive"]);

interface CurrentUserData {
  context: DemoUserFinancialContext | null;
  hero: DemoHeroPortfolio | null;
  heroes: DemoHeroPortfolio[];
  investmentProfile: InvestmentProfileResponse | null;
  loading: boolean;
  error: string | null;
}

function pensionContextErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.code === "string") return apiErrorMessage(error);
  if (error instanceof ApiError && error.status === 404) return "이 계정에는 연동된 연금 데이터가 없습니다.";
  if (error instanceof ApiError && error.status === 503) return "연금 데이터를 불러오는 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  return "연금 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

function plannerProfileFromContext(
  context: DemoUserFinancialContext | null,
  investmentProfile: InvestmentProfileResponse | null,
): PensionPlannerProfile | null {
  if (!context) return null;
  const savedAssessment = investmentProfile?.assessment;
  const riskProfile = savedAssessment && !savedAssessment.is_expired
    ? savedAssessment.risk_profile
    : context.risk_profile;
  if (!RISK_PROFILES.has(riskProfile)) return null;
  return {
    current_age: context.representative_age,
    risk_profile: riskProfile as PensionPlannerProfile["risk_profile"],
  };
}

export default function App(): JSX.Element {
  return <HashRouter><AppRoutes /></HashRouter>;
}

function AppRoutes(): JSX.Element {
  const auth = useSupabaseAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [loginSuccessPending, setLoginSuccessPending] = useState(false);
  const [resurveyPending, setResurveyPending] = useState(false);
  const [selectedScenarioCode, setSelectedScenarioCode] = useState(selectedScenarioFromStorage);
  const [currentUserData, setCurrentUserData] = useState<CurrentUserData>({ context: null, hero: null, heroes: [], investmentProfile: null, loading: false, error: null });
  const previousAuthRef = useRef<{ userId: string | null; token: string | null } | null>(null);
  const userLoadGenerationRef = useRef(0);
  const sessionExpiresAt = auth.session?.expires_at;
  const hasExpiredSession = sessionExpiresAt !== undefined && sessionExpiresAt <= Math.floor(Date.now() / 1000);
  const accessToken = hasExpiredSession ? null : auth.session?.access_token ?? null;
  const authenticatedUserId = accessToken ? auth.session?.user.id ?? null : null;

  useEffect(() => { if (auth.session === null) setLoginSuccessPending(false); }, [auth.session]);
  useEffect(() => {
    if (auth.loading) return;
    const previous = previousAuthRef.current;
    const userChanged = previous?.userId !== authenticatedUserId;
    if (!userChanged && previous?.token === accessToken) return;
    previousAuthRef.current = { userId: authenticatedUserId, token: accessToken };
    const generation = ++userLoadGenerationRef.current;
    if (userChanged) { clearPersistedUserState(); setSelectedScenarioCode(""); }
    if (!accessToken) { setCurrentUserData({ context: null, hero: null, heroes: [], investmentProfile: null, loading: false, error: null }); return; }
    setCurrentUserData({ context: null, hero: null, heroes: [], investmentProfile: null, loading: true, error: null });
    void Promise.all([
      getMyPensionContext(accessToken),
      getDemoHeroes(accessToken),
      getInvestmentProfile(accessToken),
    ])
      .then(([context, heroes, investmentProfile]) => {
        if (userLoadGenerationRef.current !== generation) return;
        const hero = heroes.find((item) => item.scenario_code === context.scenario_code) ?? null;
        setCurrentUserData({ context, hero, heroes, investmentProfile, loading: false, error: hero ? null : "내 연금 상세 시나리오를 찾지 못했습니다. 기본 정보만 표시합니다." });
        setSelectedScenarioCode(context.scenario_code);
      })
      .catch((error: unknown) => {
        if (userLoadGenerationRef.current === generation) setCurrentUserData({ context: null, hero: null, heroes: [], investmentProfile: null, loading: false, error: pensionContextErrorMessage(error) });
      });
  }, [accessToken, auth.loading, authenticatedUserId]);

  function changeTab(tab: TabKey): void { navigate(`/${tab}`); }
  function goToMainHome(): void { setLoginSuccessPending(false); setResurveyPending(false); navigate("/main-home"); }
  function goToPlanner(): void { navigate("/planner"); }
  function goToProfileHtml(): void { navigate("/profile-html"); }
  function goToStrategyExplore(): void { navigate("/strategy-explore"); }
  function goToUserPickBenchmark(): void { navigate("/user-pick-benchmark"); }
  function beginResurvey(): void { setResurveyPending(true); }
  function analyzeHero(scenarioCode: string): void { persistSelectedScenario(scenarioCode); setSelectedScenarioCode(scenarioCode); changeTab("guide"); }
  function handleProfileSaved(investmentProfile: InvestmentProfileResponse): void {
    setCurrentUserData((previous) => ({ ...previous, investmentProfile }));
  }
  async function handleSignOut(): Promise<void> { userLoadGenerationRef.current += 1; clearPersistedUserState(); setSelectedScenarioCode(""); setCurrentUserData({ context: null, hero: null, heroes: [], investmentProfile: null, loading: false, error: null }); setLoginSuccessPending(false); setResurveyPending(false); navigate("/login"); await auth.signOut(); }

  if (auth.loading) return <main className="app-auth-loading" aria-label="로그인 상태 확인 중" />;
  const metadataName = auth.session?.user.user_metadata?.name;
  const loginDisplayName = typeof metadataName === "string" && metadataName.trim() ? metadataName.trim() : currentUserData.context?.nickname ?? auth.session?.user.email?.split("@")[0] ?? "고객";
  if (auth.configured && (!accessToken || loginSuccessPending || resurveyPending)) return <LoginFlowPage auth={auth} displayName={loginDisplayName} onAuthenticated={() => setLoginSuccessPending(true)} onProfileSaved={handleProfileSaved} onStart={goToMainHome} resurvey={resurveyPending} />;
  const activeTab: TabKey = location.pathname === "/guide" ? "guide" : location.pathname === "/profile" ? "profile" : "home";
  const displayName = currentUserData.context?.nickname ?? auth.session?.user.email?.replace("@kda-demo.invalid", "") ?? "인증 사용자";
  const plannerProfile = plannerProfileFromContext(currentUserData.context, currentUserData.investmentProfile);

  const mainHome = <MainHomeScreen error={currentUserData.error} hero={currentUserData.hero} investmentProfile={currentUserData.investmentProfile} loading={currentUserData.loading} onOpenChat={() => changeTab("guide")} onOpenPlanner={goToPlanner} onOpenProfile={goToProfileHtml} onOpenStrategyExplore={goToStrategyExplore} onOpenUserPick={goToUserPickBenchmark} onResurvey={beginResurvey} userContext={currentUserData.context} />;
  const content = activeTab === "guide" ? (
    <div className="guide-tab">
      <GuidePage auth={auth} initialScenarioCode={selectedScenarioCode} onBack={goToMainHome} onOpenPlanner={goToPlanner} onSignOut={handleSignOut} surveyProfile={null} userContext={currentUserData.context} />
    </div>
  ) : (
    <div style={{ maxWidth: 480, margin: "0 auto", minHeight: "100vh", paddingBottom: 72, fontFamily: "system-ui, sans-serif" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "16px 16px 0" }}>
        <span style={{ fontSize: 13, fontWeight: 700 }}>{displayName}</span>
        <button type="button" onClick={() => void handleSignOut()}>로그아웃</button>
      </header>
      <main style={{ padding: 16 }}>
        {activeTab === "home" ? <HomePage error={currentUserData.error} hero={currentUserData.hero} investmentProfile={currentUserData.investmentProfile} loading={currentUserData.loading} onAnalyzeHero={analyzeHero} userContext={currentUserData.context} /> : activeTab === "profile" ? <ProfilePage investmentProfile={currentUserData.investmentProfile} onResurvey={beginResurvey} userContext={currentUserData.context} /> : null}
      </main>
    </div>
  );
  const tabPage = <>{content}{activeTab !== "guide" && <TabBar activeTab={activeTab} onChange={changeTab} />}</>;
  return <Routes>
    <Route path="/" element={<Navigate replace to="/home" />} />
    <Route path="/home" element={tabPage} />
    <Route path="/guide" element={tabPage} />
    <Route path="/profile" element={tabPage} />
    <Route path="/main-home" element={mainHome} />
    <Route path="/planner" element={<PensionPlannerPage profile={plannerProfile} userContext={currentUserData.context} onBack={goToMainHome} onOpenProfile={beginResurvey} />} />
    <Route path="/profile-html" element={<iframe title="내 프로필" src={`${import.meta.env.BASE_URL}profile-html/`} style={{ width: "100%", height: "100vh", border: 0, display: "block" }} />} />
    <Route path="/strategy-explore" element={<StrategyExploreScreen onBack={goToMainHome} />} />
    <Route path="/strategy-detail" element={<StrategyDetailScreen onBack={goToStrategyExplore} />} />
    <Route path="/user-pick-benchmark" element={<UserPickBenchmarkScreen heroes={currentUserData.heroes} onBack={goToMainHome} />} />
    <Route path="*" element={<Navigate replace to="/home" />} />
  </Routes>;
}
