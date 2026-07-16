import { useEffect, useState, type JSX } from "react";

import { TabBar, type TabKey } from "./components/TabBar";
import { BenchmarkPage } from "./pages/BenchmarkPage";
import { GuidePage } from "./pages/GuidePage";
import { HomePage } from "./pages/HomePage";
import { ProfilePage } from "./pages/ProfilePage";
import type { CompletedSurveyProfile } from "./api/types";

// 상태관리·라우팅 라이브러리는 의도적으로 미도입(아키텍처.md §10 미확정 항목).
// 화면 담당자가 결정 후 교체한다.
const CARD_PAGES: Partial<Record<TabKey, () => JSX.Element>> = {
  home: HomePage,
  benchmark: BenchmarkPage,
};

const TAB_KEYS: readonly TabKey[] = ["home", "guide", "benchmark", "profile"];
const MVP_DEMO_PROFILE_VERSION = "irp-pension-savings-neutral-30-55-v1";
const MVP_DEMO_SURVEY_PROFILE: CompletedSurveyProfile = {
  account_type: "irp",
  account_types: ["irp", "pension_savings"],
  current_age: 30,
  retirement_start_age: 55,
  risk_profile: "risk_neutral",
  loss_tolerance_percent: 10,
};

function tabFromHash(): TabKey {
  const candidate = window.location.hash.slice(1) as TabKey;
  return TAB_KEYS.includes(candidate) ? candidate : "home";
}

export default function App(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>(tabFromHash);
  const [surveyProfile, setSurveyProfile] = useState<CompletedSurveyProfile | null>(
    () => {
      const stored = window.localStorage.getItem("pension-copilot:survey-profile");
      const storedVersion = window.localStorage.getItem(
        "pension-copilot:mvp-profile-version",
      );
      if (stored && storedVersion === MVP_DEMO_PROFILE_VERSION) {
        try {
          return JSON.parse(stored) as CompletedSurveyProfile;
        } catch {
          // Use the fixed MVP profile below when stored demo data is malformed.
        }
      }
      window.localStorage.setItem(
        "pension-copilot:survey-profile",
        JSON.stringify(MVP_DEMO_SURVEY_PROFILE),
      );
      window.localStorage.setItem(
        "pension-copilot:mvp-profile-version",
        MVP_DEMO_PROFILE_VERSION,
      );
      return MVP_DEMO_SURVEY_PROFILE;
    },
  );
  const CardPage = CARD_PAGES[activeTab];

  useEffect(() => {
    const syncTabFromHash = () => setActiveTab(tabFromHash());
    window.addEventListener("hashchange", syncTabFromHash);
    return () => window.removeEventListener("hashchange", syncTabFromHash);
  }, []);

  function changeTab(tab: TabKey): void {
    setActiveTab(tab);
    window.history.replaceState(null, "", `#${tab}`);
  }

  function completeSurvey(profile: CompletedSurveyProfile): void {
    window.localStorage.setItem(
      "pension-copilot:survey-profile",
      JSON.stringify(profile),
    );
    setSurveyProfile(profile);
    changeTab("guide");
  }

  return (
    <>
      {activeTab === "guide" ? (
        // 챗 화면은 자체 레이아웃(app-shell)을 쓰므로 풀블리드로 렌더한다.
        <div className="guide-tab">
          <GuidePage surveyProfile={surveyProfile} />
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
            {activeTab === "profile" ? (
              <ProfilePage profile={surveyProfile} onComplete={completeSurvey} />
            ) : CardPage ? <CardPage /> : null}
          </main>
        </div>
      )}
      <TabBar activeTab={activeTab} onChange={changeTab} />
    </>
  );
}
