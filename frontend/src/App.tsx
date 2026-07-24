import { useEffect, useRef, useState, type JSX } from "react";
import {
  HashRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";

import {
  aggregatePensionAccounts,
  ApiError,
  apiErrorMessage,
  getInvestmentProfile,
  getMyPensionAccounts,
  getMyPensionContext,
} from "./api/client";
import type {
  AggregationEvaluation,
  DemoUserFinancialContext,
  InvestmentProfileResponse,
  UserPensionPortfolio,
} from "./api/types";
import { useSupabaseAuth } from "./auth/useSupabaseAuth";
import { StatusBar } from "./components/StatusBar";
import { GuidePage } from "./pages/GuidePage";
import { LoginFlowPage } from "./pages/LoginFlowPage";
import { MainHomeScreen } from "./pages/MainHomeScreen";
import {
  PensionPlannerPage,
  type PensionPlannerProfile,
} from "./pages/PensionPlannerPage";
import { ProfileHtmlPage } from "./pages/ProfileHtmlPage";
import { SlangiTouchPage } from "./pages/SlangiTouchPage";
import { StrategyDetailScreen } from "./pages/StrategyDetailScreen";
import { StrategyExploreScreen } from "./pages/StrategyExploreScreen";
import { UserPickBenchmarkScreen } from "./pages/UserPickBenchmarkScreen";
import { toAggregationInput } from "./ownerPensionPortfolio";
import {
  clearPersistedUserState,
  selectedScenarioFromStorage,
} from "./pwa/cachePolicy";

interface CurrentUserData {
  portfolio: UserPensionPortfolio | null;
  aggregation: AggregationEvaluation | null;
  investmentProfile: InvestmentProfileResponse | null;
  loading: boolean;
  error: string | null;
}

const EMPTY_USER_DATA: CurrentUserData = {
  portfolio: null,
  aggregation: null,
  investmentProfile: null,
  loading: false,
  error: null,
};

function pensionAccountErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.code === "string") {
    return apiErrorMessage(error);
  }
  if (error instanceof ApiError && error.status === 404) {
    return "이 계정에는 연동된 연금 데이터가 없습니다.";
  }
  return "연금 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

function plannerProfileFromSession(
  representativeAge: unknown,
  investmentProfile: InvestmentProfileResponse | null,
): PensionPlannerProfile | null {
  const age = Number(representativeAge);
  const assessment = investmentProfile?.assessment;
  if (
    !Number.isInteger(age)
    || age < 20
    || age > 69
    || !assessment
    || assessment.is_expired
  ) return null;
  return { current_age: age, risk_profile: assessment.risk_profile };
}

export default function App(): JSX.Element {
  return <HashRouter><AppRoutes /></HashRouter>;
}

function DesktopPreviewStatus(): JSX.Element | null {
  const { pathname } = useLocation();
  if (["/", "/login", "/main-home", "/planner", "/profile-html", "/slangi", "/strategy-explore", "/strategy-detail", "/user-pick-benchmark"].includes(pathname)) return null;

  return <StatusBar className="desktop-preview-status" />;
}

function AppRoutes(): JSX.Element {
  const auth = useSupabaseAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [loginSuccessPending, setLoginSuccessPending] = useState(false);
  const [resurveyPending, setResurveyPending] = useState(false);
  const [selectedScenarioCode, setSelectedScenarioCode] = useState(
    selectedScenarioFromStorage,
  );
  const [guideContext, setGuideContext] = useState<DemoUserFinancialContext | null>(
    null,
  );
  const [currentUserData, setCurrentUserData] = useState(EMPTY_USER_DATA);
  const previousAuthRef = useRef<{
    userId: string | null;
    token: string | null;
  } | null>(null);
  const userLoadGenerationRef = useRef(0);
  const guideLoadGenerationRef = useRef(0);
  const mainHomeScrollTopRef = useRef(0);
  const sessionExpiresAt = auth.session?.expires_at;
  const hasExpiredSession = sessionExpiresAt !== undefined
    && sessionExpiresAt <= Math.floor(Date.now() / 1000);
  const accessToken = hasExpiredSession
    ? null
    : auth.session?.access_token ?? null;
  const authenticatedUserId = accessToken
    ? auth.session?.user.id ?? null
    : null;

  useEffect(() => {
    if (auth.session === null) setLoginSuccessPending(false);
  }, [auth.session]);

  useEffect(() => {
    if (!loginSuccessPending || resurveyPending || currentUserData.loading) return;
    const assessment = currentUserData.investmentProfile?.assessment;
    if (assessment && !assessment.is_expired) { setLoginSuccessPending(false); navigate("/main-home"); }
  }, [loginSuccessPending, resurveyPending, currentUserData.loading, currentUserData.investmentProfile, navigate]);
  useEffect(() => {
    if (auth.loading) return;
    const previous = previousAuthRef.current;
    const userChanged = previous?.userId !== authenticatedUserId;
    if (!userChanged && previous?.token === accessToken) return;
    previousAuthRef.current = {
      userId: authenticatedUserId,
      token: accessToken,
    };
    const generation = ++userLoadGenerationRef.current;
    if (userChanged) {
      clearPersistedUserState();
      mainHomeScrollTopRef.current = 0;
      setSelectedScenarioCode("");
      setGuideContext(null);
    }
    if (!accessToken) {
      setCurrentUserData(EMPTY_USER_DATA);
      return;
    }
    setCurrentUserData({ ...EMPTY_USER_DATA, loading: true });
    void Promise.all([
      getMyPensionAccounts(accessToken),
      getInvestmentProfile(accessToken),
    ])
      .then(async ([portfolio, investmentProfile]) => {
        const aggregation = portfolio.accounts.length > 0
          ? await aggregatePensionAccounts(toAggregationInput(portfolio))
          : null;
        if (userLoadGenerationRef.current !== generation) return;
        setCurrentUserData({
          portfolio,
          aggregation,
          investmentProfile,
          loading: false,
          error: portfolio.accounts.length > 0
            ? null
            : "이 계정에는 연동된 연금 데이터가 없습니다.",
        });
      })
      .catch((error: unknown) => {
        if (userLoadGenerationRef.current !== generation) return;
        setCurrentUserData({
          ...EMPTY_USER_DATA,
          error: pensionAccountErrorMessage(error),
        });
      });
  }, [accessToken, auth.loading, authenticatedUserId]);

  useEffect(() => {
    const generation = ++guideLoadGenerationRef.current;
    if (!accessToken || location.pathname !== "/guide") {
      setGuideContext(null);
      return;
    }
    void getMyPensionContext(accessToken)
      .then((context) => {
        if (guideLoadGenerationRef.current !== generation) return;
        setGuideContext(context);
        setSelectedScenarioCode(context.scenario_code);
      })
      .catch(() => {
        if (guideLoadGenerationRef.current === generation) setGuideContext(null);
      });
  }, [accessToken, location.pathname]);

  function goToMainHome(): void {
    setLoginSuccessPending(false);
    setResurveyPending(false);
    navigate("/main-home");
  }
  function handleProfileSaved(
    investmentProfile: InvestmentProfileResponse,
  ): void {
    setCurrentUserData((previous) => ({ ...previous, investmentProfile }));
  }
  async function handleSignOut(): Promise<void> {
    userLoadGenerationRef.current += 1;
    guideLoadGenerationRef.current += 1;
    clearPersistedUserState();
    setSelectedScenarioCode("");
    setGuideContext(null);
    setCurrentUserData(EMPTY_USER_DATA);
    mainHomeScrollTopRef.current = 0;
    setLoginSuccessPending(false);
    setResurveyPending(false);
    navigate("/login");
    await auth.signOut();
  }

  if (auth.loading) {
    return <main className="app-auth-loading" aria-label="로그인 상태 확인 중" />;
  }
  const metadata = auth.session?.user.user_metadata;
  const metadataName = metadata?.nickname ?? metadata?.name;
  const email = auth.session?.user.email ?? "";
  const displayName = typeof metadataName === "string" && metadataName.trim()
    ? metadataName.replace(/\(가상\)/g, "").trim()
    : email.replace("@kda-demo.invalid", "") || "인증 사용자";
  if (
    auth.configured
    && (!accessToken || loginSuccessPending || resurveyPending)
  ) {
    return (
      <LoginFlowPage
        auth={auth}
        displayName={displayName}
        onAuthenticated={() => setLoginSuccessPending(true)}
        onProfileSaved={handleProfileSaved}
        onStart={goToMainHome}
        resurvey={resurveyPending}
      />
    );
  }
  const plannerProfile = plannerProfileFromSession(
    metadata?.representative_age,
    currentUserData.investmentProfile,
  );

  return (
    <>
      <DesktopPreviewStatus />
      <Routes>
      <Route path="/" element={<Navigate replace to="/main-home" />} />
      <Route path="/login" element={<Navigate replace to="/main-home" />} />
      <Route
        path="/guide"
        element={(
          <div className="guide-tab">
            <GuidePage
              auth={auth}
              initialScenarioCode={selectedScenarioCode}
              onBack={goToMainHome}
              onOpenPlanner={() => navigate("/planner")}
              onSignOut={handleSignOut}
              surveyProfile={null}
              userContext={guideContext}
            />
          </div>
        )}
      />
      <Route
        path="/main-home"
        element={(
          <MainHomeScreen
            aggregation={currentUserData.aggregation}
            displayName={displayName}
            error={currentUserData.error}
            investmentProfile={currentUserData.investmentProfile}
            initialScrollTop={mainHomeScrollTopRef.current}
            loading={currentUserData.loading}
            onOpenChat={() => navigate("/guide")}
            onOpenPlanner={() => navigate("/planner")}
            onOpenProfile={() => navigate("/profile-html")}
            onOpenSlangi={() => navigate("/slangi")}
            onScrollPositionChange={(scrollTop) => {
              mainHomeScrollTopRef.current = scrollTop;
            }}
            onOpenStrategyExplore={() => navigate("/strategy-explore")}
            onOpenUserPick={() => navigate("/user-pick-benchmark")}
            portfolio={currentUserData.portfolio}
          />
        )}
      />
      <Route
        path="/planner"
        element={(
          <PensionPlannerPage
            aggregation={currentUserData.aggregation}
            onBack={goToMainHome}
            portfolio={currentUserData.portfolio}
            profile={plannerProfile}
          />
        )}
      />
      <Route
        path="/profile-html"
        element={(
          <ProfileHtmlPage
            displayName={displayName}
            email={email}
            investmentProfile={currentUserData.investmentProfile}
            onBack={goToMainHome}
            portfolio={currentUserData.portfolio}
          />
        )}
      />
      <Route path="/slangi" element={<SlangiTouchPage />} />
      <Route
        path="/strategy-explore"
        element={<StrategyExploreScreen onBack={goToMainHome} />}
      />
      <Route
        path="/strategy-detail"
        element={(
          <StrategyDetailScreen
            onBack={() => navigate("/strategy-explore")}
          />
        )}
      />
      <Route
        path="/user-pick-benchmark"
        element={<UserPickBenchmarkScreen onBack={goToMainHome} />}
      />
        <Route path="*" element={<Navigate replace to="/main-home" />} />
      </Routes>
    </>
  );
}
