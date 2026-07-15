import { useEffect, useState } from "react";

import { apiGet } from "../api/client";
import type { HealthResponse } from "../api/types";

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

export function HomePage() {
  const [status, setStatus] = useState<BackendStatus>("loading");

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
      <p style={{ color: "#555555", lineHeight: 1.6 }}>
        DC형·IRP·연금저축 통합 원그래프, 일일 점검, 주간 매크로 가이드가 이
        화면에 들어온다. 데이터는 <code>/engine/aggregation</code>·
        <code>/engine/diagnostics</code> 결과를 사용한다.
      </p>
    </section>
  );
}
