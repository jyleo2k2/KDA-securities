import { useEffect, useState } from "react";

import { apiGet, getMockScenarioEvaluation, getScenarios } from "../api/client";
import type { HealthResponse, ScenarioEvaluation, ScenarioSummary } from "../api/types";

type BackendStatus = "loading" | "ok" | "unreachable";

const BADGE_COLOR: Record<BackendStatus, string> = {
  loading: "#999999",
  ok: "#1a7f37",
  unreachable: "#c0392b",
};

const BADGE_LABEL: Record<BackendStatus, string> = {
  loading: "백엔드 확인 중…",
  ok: "백엔드 연결됨",
  unreachable: "백엔드 연결 안 됨",
};

function formatKrw(value: string): string {
  const amount = Math.round(Number(value));
  return `${amount.toLocaleString("ko-KR")}원`;
}

export function HomePage() {
  const [status, setStatus] = useState<BackendStatus>("loading");
  const [scenario, setScenario] = useState<ScenarioSummary | null>(null);
  const [evaluation, setEvaluation] = useState<ScenarioEvaluation | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<HealthResponse>("/health")
      .then((health) => {
        if (!cancelled) {
          setStatus(health.status === "ok" ? "ok" : "unreachable");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("unreachable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getScenarios()
      .then((scenarios) => {
        const first = scenarios[0];
        if (!first || cancelled) return;
        setScenario(first);
        return getMockScenarioEvaluation(first.code);
      })
      .then((result) => {
        if (!cancelled && result) setEvaluation(result);
      })
      .catch(() => {
        if (!cancelled) {
          setScenarioError("목시나리오 데이터를 불러오지 못했습니다.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section>
      <h1 style={{ fontSize: 20 }}>내 연금 포트폴리오</h1>
      <p
        style={{
          display: "inline-block",
          padding: "4px 10px",
          borderRadius: 12,
          fontSize: 13,
          color: "#ffffff",
          background: BADGE_COLOR[status],
        }}
      >
        {BADGE_LABEL[status]}
      </p>

      {scenarioError && (
        <p style={{ color: "#c0392b", fontSize: 13 }}>{scenarioError}</p>
      )}

      {scenario && evaluation && (
        <div
          style={{
            marginTop: 12,
            padding: 12,
            border: "1px solid #e5e5e5",
            borderRadius: 8,
          }}
        >
          <p
            style={{
              display: "inline-block",
              padding: "2px 8px",
              borderRadius: 8,
              fontSize: 11,
              color: "#8a5a00",
              background: "#fff3cd",
              marginBottom: 6,
            }}
          >
            목데이터(MOCK) 시연 — {evaluation.source.label} · 기준일{" "}
            {evaluation.source.as_of}
          </p>
          <h2 style={{ fontSize: 16, margin: "4px 0" }}>{scenario.name}</h2>
          <p style={{ color: "#666666", fontSize: 12, margin: "2px 0" }}>
            대표 연령대 {scenario.age_band}
          </p>
          <p style={{ color: "#555555", fontSize: 13, lineHeight: 1.5 }}>
            {scenario.description}
          </p>
          <p style={{ fontSize: 14, fontWeight: 600 }}>
            총자산 {formatKrw(evaluation.total_amount_krw)}
          </p>

          <p style={{ fontSize: 13, fontWeight: 600, marginTop: 10 }}>
            계좌별 위험자산 한도 판정
          </p>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            {evaluation.account_evaluations.map((account) => (
              <li key={account.evaluated_input.account_type}>
                {account.evaluated_input.account_type.toUpperCase()}: 일반
                위험자산 {account.general_risky_ratio_percent}%
                {account.limit_percent !== null && (
                  <> (한도 {account.limit_percent}%
                    {account.within_limit ? " · 이내" : " · 초과"})</>
                )}
              </li>
            ))}
          </ul>

          <p style={{ fontSize: 13, fontWeight: 600, marginTop: 10 }}>
            통합 자산군 비중
          </p>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            {evaluation.asset_allocations.map((item) => (
              <li key={item.asset_class_code}>
                {item.asset_class_code}: {item.allocation_percent}%
              </li>
            ))}
          </ul>
        </div>
      )}

      <p style={{ color: "#555555", lineHeight: 1.6, marginTop: 12 }}>
        위 카드는 <code>/chat/demo/scenarios</code>·
        <code>/engine/mock-scenario/{"{code}"}</code>가 반환하는 목시나리오
        엔진 결과다. 실계좌 연동 전까지 홈 화면의 통합 원그래프·진단은 이
        데이터로 대체한다.
      </p>
    </section>
  );
}
