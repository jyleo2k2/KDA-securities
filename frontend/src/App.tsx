import { useState, type JSX } from "react";

import { TabBar, type TabKey } from "./components/TabBar";
import { BenchmarkPage } from "./pages/BenchmarkPage";
import { GuidePage } from "./pages/GuidePage";
import { HomePage } from "./pages/HomePage";
import { ProfilePage } from "./pages/ProfilePage";

// 상태관리·라우팅 라이브러리는 의도적으로 미도입(아키텍처.md §10 미확정 항목).
// 화면 담당자가 결정 후 교체한다.
const PAGES: Record<TabKey, () => JSX.Element> = {
  home: HomePage,
  guide: GuidePage,
  benchmark: BenchmarkPage,
  profile: ProfilePage,
};

export default function App(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>("home");
  const ActivePage = PAGES[activeTab];

  return (
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
        <ActivePage />
      </main>
      <TabBar activeTab={activeTab} onChange={setActiveTab} />
    </div>
  );
}
