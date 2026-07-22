import { useEffect, useRef, useState, type JSX } from "react";

import { ApiError, apiErrorMessage, getDemoHeroes, getMyPensionContext } from "./api/client";
import type { DemoHeroPortfolio, DemoUserFinancialContext } from "./api/types";
import { useSupabaseAuth } from "./auth/useSupabaseAuth";
import { TabBar, type TabKey } from "./components/TabBar";
import { BenchmarkPage } from "./pages/BenchmarkPage";
import { GuidePage } from "./pages/GuidePage";
import { HomePage } from "./pages/HomePage";
import { LoginFlowPage } from "./pages/LoginFlowPage";
import { MainHomeScreen } from "./pages/MainHomeScreen";
import { PensionPlannerPage } from "./pages/PensionPlannerPage";
import { ProfilePage } from "./pages/ProfilePage";
import { StrategyExploreScreen } from "./pages/StrategyExploreScreen";
import { UserPickBenchmarkScreen } from "./pages/UserPickBenchmarkScreen";

const CARD_PAGES: Partial<Record<TabKey, () => JSX.Element>> = { benchmark: BenchmarkPage };
const TAB_KEYS: readonly TabKey[] = ["home", "guide", "benchmark", "profile"];
const USER_STORAGE_KEYS = ["pension-copilot:survey-profile", "pension-copilot:mvp-profile-version", "pension-copilot:selected-scenario"] as const;
type AppRoute = TabKey | "login" | "main-home" | "planner" | "strategy-explore" | "user-pick-benchmark";

interface CurrentUserData {
  context: DemoUserFinancialContext | null;
  hero: DemoHeroPortfolio | null;
  loading: boolean;
  error: string | null;
}

function routeFromHash(): AppRoute {
  const candidate = window.location.hash.slice(1) as AppRoute;
  return candidate === "login" || candidate === "main-home" || candidate === "planner" || candidate === "strategy-explore" || candidate === "user-pick-benchmark" || TAB_KEYS.includes(candidate as TabKey) ? candidate : "login";
}

function clearUserStorage(): void {
  USER_STORAGE_KEYS.forEach((key) => window.localStorage.removeItem(key));
}

function pensionContextErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.code === "string") return apiErrorMessage(error);
  if (error instanceof ApiError && error.status === 404) return "이 계정에는 연동된 연금 데이터가 없습니다.";
  if (error instanceof ApiError && error.status === 503) return "연금 데이터를 불러오는 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  return "연금 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

export default function App(): JSX.Element {
  const auth = useSupabaseAuth();
  const [activeRoute, setActiveRoute] = useState<AppRoute>(routeFromHash);
  const [loginSuccessPending, setLoginSuccessPending] = useState(false);
  const [resurveyPending, setResurveyPending] = useState(false);
  const [selectedScenarioCode, setSelectedScenarioCode] = useState(() => window.localStorage.getItem("pension-copilot:selected-scenario") ?? "");
  const [currentUserData, setCurrentUserData] = useState<CurrentUserData>({ context: null, hero: null, loading: false, error: null });
  const previousAuthRef = useRef<{ userId: string | null; token: string | null } | null>(null);
  const userLoadGenerationRef = useRef(0);
  const sessionExpiresAt = auth.session?.expires_at;
  const hasExpiredSession = sessionExpiresAt !== undefined && sessionExpiresAt <= Math.floor(Date.now() / 1000);
  const accessToken = hasExpiredSession ? null : auth.session?.access_token ?? null;
  const authenticatedUserId = accessToken ? auth.session?.user.id ?? null : null;

  useEffect(() => {
    const sync = () => setActiveRoute(routeFromHash());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  useEffect(() => { if (auth.session === null) setLoginSuccessPending(false); }, [auth.session]);
  useEffect(() => {
    if (auth.loading) return;
    const previous = previousAuthRef.current;
    const userChanged = previous?.userId !== authenticatedUserId;
    if (!userChanged && previous?.token === accessToken) return;
    previousAuthRef.current = { userId: authenticatedUserId, token: accessToken };
    const generation = ++userLoadGenerationRef.current;
    if (userChanged) { clearUserStorage(); setSelectedScenarioCode(""); }
    if (!accessToken) { setCurrentUserData({ context: null, hero: null, loading: false, error: null }); return; }
    setCurrentUserData({ context: null, hero: null, loading: true, error: null });
    void Promise.all([getMyPensionContext(accessToken), getDemoHeroes(accessToken)])
      .then(([context, heroes]) => {
        if (userLoadGenerationRef.current !== generation) return;
        const hero = heroes.find((item) => item.scenario_code === context.scenario_code) ?? null;
        setCurrentUserData({ context, hero, loading: false, error: hero ? null : "내 연금 상세 시나리오를 찾지 못했습니다. 기본 정보만 표시합니다." });
        setSelectedScenarioCode(context.scenario_code);
      })
      .catch((error: unknown) => {
        if (userLoadGenerationRef.current === generation) setCurrentUserData({ context: null, hero: null, loading: false, error: pensionContextErrorMessage(error) });
      });
  }, [accessToken, auth.loading, authenticatedUserId]);

  function changeTab(tab: TabKey): void { setActiveRoute(tab); window.history.replaceState(null, "", `#${tab}`); }
  function goToMainHome(): void { setLoginSuccessPending(false); setResurveyPending(false); setActiveRoute("main-home"); window.history.replaceState(null, "", "#main-home"); }
  function goToPlanner(): void { setActiveRoute("planner"); window.history.replaceState(null, "", "#planner"); }
  function goToStrategyExplore(): void { setActiveRoute("strategy-explore"); window.history.replaceState(null, "", "#strategy-explore"); }
  function goToUserPickBenchmark(): void { setActiveRoute("user-pick-benchmark"); window.history.replaceState(null, "", "#user-pick-benchmark"); }
  function beginResurvey(): void { setResurveyPending(true); }
  function analyzeHero(scenarioCode: string): void { window.localStorage.setItem("pension-copilot:selected-scenario", scenarioCode); setSelectedScenarioCode(scenarioCode); changeTab("guide"); }
  async function handleSignOut(): Promise<void> { userLoadGenerationRef.current += 1; clearUserStorage(); setSelectedScenarioCode(""); setCurrentUserData({ context: null, hero: null, loading: false, error: null }); setLoginSuccessPending(false); setResurveyPending(false); setActiveRoute("login"); window.history.replaceState(null, "", "#login"); await auth.signOut(); }

  if (auth.loading) return <main className="app-auth-loading" aria-label="로그인 상태 확인 중" />;
  if (auth.configured && (!accessToken || loginSuccessPending || resurveyPending)) return <LoginFlowPage auth={auth} onAuthenticated={() => setLoginSuccessPending(true)} onStart={goToMainHome} resurvey={resurveyPending} />;
  const resolvedRoute = !auth.configured && activeRoute === "login" ? "home" : activeRoute;
  const activeTab: TabKey = resolvedRoute === "login" || resolvedRoute === "main-home" || resolvedRoute === "planner" || resolvedRoute === "strategy-explore" || resolvedRoute === "user-pick-benchmark" ? "home" : resolvedRoute;
  const CardPage = CARD_PAGES[activeTab];
  const displayName = currentUserData.context?.nickname ?? auth.session?.user.email?.replace("@kda-demo.invalid", "") ?? "인증 사용자";

  if (resolvedRoute === "strategy-explore") return <StrategyExploreScreen onBack={goToMainHome} />;
  if (resolvedRoute === "user-pick-benchmark") return <UserPickBenchmarkScreen onBack={goToMainHome} />;
  if (resolvedRoute === "main-home") return <MainHomeScreen error={currentUserData.error} hero={currentUserData.hero} loading={currentUserData.loading} onOpenChat={() => changeTab("guide")} onOpenStrategyExplore={goToStrategyExplore} onOpenUserPick={goToUserPickBenchmark} onResurvey={beginResurvey} userContext={currentUserData.context} />;
  if (resolvedRoute === "planner") return <PensionPlannerPage profile={null} userContext={currentUserData.context} onBack={() => changeTab("guide")} onOpenProfile={beginResurvey} />;
  return <><>{activeTab === "guide" ? <div className="guide-tab"><GuidePage auth={auth} initialScenarioCode={selectedScenarioCode} onBack={goToMainHome} onOpenPlanner={goToPlanner} onSignOut={handleSignOut} surveyProfile={null} userContext={currentUserData.context} /></div> : <div style={{ maxWidth: 480, margin: "0 auto", minHeight: "100vh", paddingBottom: 72, fontFamily: "system-ui, sans-serif" }}><header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "16px 16px 0" }}><span style={{ fontSize: 13, fontWeight: 700 }}>{displayName}</span><button type="button" onClick={() => void handleSignOut()}>로그아웃</button></header><main style={{ padding: 16 }}>{activeTab === "home" ? <HomePage error={currentUserData.error} hero={currentUserData.hero} loading={currentUserData.loading} onAnalyzeHero={analyzeHero} userContext={currentUserData.context} /> : activeTab === "profile" ? <ProfilePage onResurvey={beginResurvey} userContext={currentUserData.context} /> : CardPage ? <CardPage /> : null}</main></div>}</>{activeTab !== "guide" && <TabBar activeTab={activeTab} onChange={changeTab} /></>;
}
