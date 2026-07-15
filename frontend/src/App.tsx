import { useEffect, useState, type JSX } from "react";

import { TabBar, type TabKey } from "./components/TabBar";
import { BenchmarkPage } from "./pages/BenchmarkPage";
import { GuidePage } from "./pages/GuidePage";
import { HomePage } from "./pages/HomePage";
import { ProfilePage } from "./pages/ProfilePage";

// 상태관리·라우팅 라이브러리는 의도적으로 미도입(아키텍처.md §10 미확정 항목).
// 화면 담당자가 결정 후 교체한다.
const CARD_PAGES: Partial<Record<TabKey, () => JSX.Element>> = {
  home: HomePage,
  benchmark: BenchmarkPage,
  profile: ProfilePage,
};

const TAB_KEYS: readonly TabKey[] = ["home", "guide", "benchmark", "profile"];

function tabFromHash(): TabKey {
  const candidate = window.location.hash.slice(1) as TabKey;
  return TAB_KEYS.includes(candidate) ? candidate : "home";
}

export default function App(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>(tabFromHash);
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

  return (
    <>
      {activeTab === "guide" ? (
        // 챗 화면은 자체 레이아웃(app-shell)을 쓰므로 풀블리드로 렌더한다.
        <div className="guide-tab">
          <GuidePage />
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
          <main style={{ padding: 16 }}>{CardPage ? <CardPage /> : null}</main>
        </div>
      )}
      <TabBar activeTab={activeTab} onChange={changeTab} />
    </>
  );
}
