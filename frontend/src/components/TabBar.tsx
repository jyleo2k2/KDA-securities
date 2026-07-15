import type { JSX } from "react";

export type TabKey = "home" | "guide" | "benchmark" | "profile";

const TAB_LABELS: Record<TabKey, string> = {
  home: "홈",
  guide: "연금가이드",
  benchmark: "벤치마크",
  profile: "프로필",
};

interface TabBarProps {
  activeTab: TabKey;
  onChange: (tab: TabKey) => void;
}

export function TabBar({ activeTab, onChange }: TabBarProps): JSX.Element {
  return (
    <nav
      style={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        display: "flex",
        maxWidth: 480,
        margin: "0 auto",
        borderTop: "1px solid #e0e0e0",
        background: "#ffffff",
      }}
    >
      {(Object.keys(TAB_LABELS) as TabKey[]).map((tab) => (
        <button
          key={tab}
          type="button"
          onClick={() => onChange(tab)}
          style={{
            flex: 1,
            padding: "12px 0",
            border: "none",
            background: "none",
            fontSize: 14,
            fontWeight: activeTab === tab ? 700 : 400,
            color: activeTab === tab ? "#1a4fd8" : "#555555",
            cursor: "pointer",
          }}
        >
          {TAB_LABELS[tab]}
        </button>
      ))}
    </nav>
  );
}
