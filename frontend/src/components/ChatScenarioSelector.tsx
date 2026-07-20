import type { ReactNode } from "react";

import type { DemoUserFinancialContext, ScenarioSummary } from "../api/types";

export function ChatScenarioSelector({
  scenarios,
  selectedScenario,
  userContext,
  onSelect,
  renderIcon,
}: {
  scenarios: ScenarioSummary[];
  selectedScenario: string;
  userContext: DemoUserFinancialContext | null;
  onSelect: (code: string) => void;
  renderIcon: (name: "book" | "database") => ReactNode;
}) {
  return (
    <div className="sidebar-section">
      <p className="sidebar-label">목계좌 시나리오</p>
      {userContext ? (
        <div className="user-context-card">
          <strong>{userContext.nickname}</strong>
          <span>{userContext.scenario_name} · 가상 목데이터</span>
          <small>총 연금자산 {Number(userContext.total_pension_balance_krw).toLocaleString("ko-KR")}원<br />기준일 {userContext.as_of_date}</small>
        </div>
      ) : (
        <div className="scenario-list">
          <button className={!selectedScenario ? "active" : ""} type="button" onClick={() => onSelect("")}>
            <span className="scenario-icon">{renderIcon("book")}</span><span><strong>선택 안 함</strong><small>일반 제도 질문</small></span>
          </button>
          {scenarios.map((scenario) => (
            <button className={selectedScenario === scenario.code ? "active" : ""} type="button" key={scenario.code} onClick={() => onSelect(scenario.code)}>
              <span className="scenario-icon">{renderIcon("database")}</span><span><strong>{scenario.name}</strong><small>{scenario.age_band} · {scenario.investment_horizon_years}년 · {scenario.risk_profile}</small></span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
