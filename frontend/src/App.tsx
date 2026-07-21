import { useEffect, useState, type JSX } from "react";

import { TabBar, type TabKey } from "./components/TabBar";
import { BenchmarkPage } from "./pages/BenchmarkPage";
import { GuidePage } from "./pages/GuidePage";
import { HomePage } from "./pages/HomePage";
import { LoginFlowPage } from "./pages/LoginFlowPage";
import { MainHomeScreen } from "./pages/MainHomeScreen";
import { ProfilePage } from "./pages/ProfilePage";
import type { CompletedSurveyProfile } from "./api/types";

// 상태관리·라우팅 라이브러리는 의도적으로 미도입(아키텍처.md §10 미확정 항목).
// 화면 담당자가 결정 후 교체한다.
const CARD_PAGES: Partial<Record<TabKey, () => JSX.Element>> = {
  benchmark: BenchmarkPage,
};

const TAB_KEYS: readonly TabKey[] = ["home", "guide", "benchmark", "profile"];
const SURVEY_PROFILE_VERSION = "completed-survey-v1";
type AppRoute = TabKey | "login" | "main-home";

function routeFromHash(): AppRoute {
  const candidate = window.location.hash.slice(1) as AppRoute;
  if (candidate === "login" || candidate === "main-home") return candidate;
  return TAB_KEYS.includes(candidate as TabKey) ? candidate : "login";
}

export default function App(): JSX.Element {
  const [activeRoute, setActiveRoute] = useState<AppRoute>(routeFromHash);
  const [surveyProfile, setSurveyProfile] = useState<CompletedSurveyProfile | null>(
    () => {
      const stored = window.localStorage.getItem("pension-copilot:survey-profile");
      const storedVersion = window.localStorage.getItem(
        "pension-copilot:mvp-profile-version",
      );
      if (stored && storedVersion === SURVEY_PROFILE_VERSION) {
        try {
          return JSON.parse(stored) as CompletedSurveyProfile;
        } catch {
          // Invalid local survey state is cleared below.
        }
      }
      window.localStorage.removeItem("pension-copilot:survey-profile");
      window.localStorage.removeItem("pension-copilot:mvp-profile-version");
      return null;
    },
  );
  const [selectedScenarioCode, setSelectedScenarioCode] = useState(
    () => window.localStorage.getItem("pension-copilot:selected-scenario") ?? "",
  );
  const activeTab: TabKey =
    activeRoute === "login" || activeRoute === "main-home" || !TAB_KEYS.includes(activeRoute as TabKey)
      ? "home"
      : (activeRoute as TabKey);
  const CardPage = CARD_PAGES[activeTab];

  useEffect(() => {
    const syncRouteFromHash = () => setActiveRoute(routeFromHash());
    window.addEventListener("hashchange", syncRouteFromHash);
    return () => window.removeEventListener("hashchange", syncRouteFromHash);
  }, []);

  function changeTab(tab: TabKey): void {
    setActiveRoute(tab);
    window.history.replaceState(null, "", `#${tab}`);
  }

  function goToMainHome(): void {
    setActiveRoute("main-home");
    window.history.replaceState(null, "", "#main-home");
  }

  function completeSurvey(profile: CompletedSurveyProfile): void {
    window.localStorage.setItem(
      "pension-copilot:survey-profile",
      JSON.stringify(profile),
    );
    window.localStorage.setItem(
      "pension-copilot:mvp-profile-version",
      SURVEY_PROFILE_VERSION,
    );
    setSurveyProfile(profile);
    changeTab("guide");
  }

  function analyzeHero(scenarioCode: string): void {
    window.localStorage.setItem("pension-copilot:selected-scenario", scenarioCode);
    setSelectedScenarioCode(scenarioCode);
    changeTab("guide");
  }

  return (
    <>
      {activeRoute === "login" ? (
        <LoginFlowPage onStart={goToMainHome} />
      ) : activeRoute === "main-home" ? (
        <MainHomeScreen onOpenChat={() => changeTab("guide")} />
      ) : activeTab === "guide" ? (
        // 챗 화면은 자체 레이아웃(app-shell)을 쓰므로 풀블리드로 렌더한다.
        <div className="guide-tab">
          <GuidePage
            initialScenarioCode={selectedScenarioCode}
            surveyProfile={surveyProfile}
          />
        </div>
      ) : (
        <div
          style={{
            maxWidth: 480,
            margin: "0 auto",
            minHeight: "100vh",
            paddingBottom: 72,
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <main style={{ padding: 16 }}>
            {activeTab === "home" ? (
              <HomePage onAnalyzeHero={analyzeHero} />
            ) : activeTab === "profile" ? (
              <ProfilePage profile={surveyProfile} onComplete={completeSurvey} />
            ) : CardPage ? <CardPage /> : null}
          </main>
        </div>
      )}
      {activeRoute !== "login" && activeRoute !== "main-home" && (
        <TabBar activeTab={activeTab} onChange={changeTab} />
      )}
    </>
  );
}
