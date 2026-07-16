import { useEffect, useState } from "react";

import { getBenchmarkSummary } from "../api/client";
import type {
  BenchmarkAccountTypeStat,
  BenchmarkDistribution,
  BenchmarkSummary,
} from "../api/types";

const ageLabels: Record<string, string> = {
  "20s": "20대",
  "30s": "30대",
  "40s": "40대",
  "50_plus": "50대 이상",
};

const riskLabels: Record<string, string> = {
  STABLE_SEEKING: "안정추구형",
  STABLE: "안정형",
  RISK_NEUTRAL: "위험중립형",
  ACTIVE: "적극투자형",
};

const accountLabels: Record<string, string> = {
  DC: "DC형 퇴직연금",
  IRP: "IRP",
  PENSION_SAVINGS_FUND: "연금저축펀드",
};

function formatWon(value: string): string {
  return `${Math.round(Number(value)).toLocaleString("ko-KR")}원`;
}

function Distribution({
  items,
  labels,
}: {
  items: BenchmarkDistribution[];
  labels: Record<string, string>;
}) {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  return (
    <div style={{ display: "grid", gap: 14 }}>
      {items.map((item) => {
        const percent = total === 0 ? 0 : (item.count / total) * 100;
        return (
          <div key={item.code}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span>{labels[item.code] ?? item.code}</span>
              <span style={{ color: "#586174", fontWeight: 700 }}>
                {item.count.toLocaleString("ko-KR")}명 · {percent.toFixed(1)}%
              </span>
            </div>
            <div style={{ height: 10, borderRadius: 999, background: "#e8edf5", overflow: "hidden" }}>
              <div style={{ width: `${percent}%`, height: "100%", borderRadius: 999, background: "#3877e8" }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function AccountStat({ stat }: { stat: BenchmarkAccountTypeStat }) {
  return (
    <article style={{ border: "1px solid #dce5f3", borderRadius: 16, padding: 18, background: "#fff" }}>
      <h3 style={{ margin: 0, fontSize: 16 }}>{accountLabels[stat.account_type] ?? stat.account_type}</h3>
      <p style={{ color: "#596579", margin: "8px 0 16px" }}>{stat.account_count.toLocaleString("ko-KR")}개 계좌 기준</p>
      <dl style={{ margin: 0, display: "grid", gap: 10 }}>
        <div><dt style={{ color: "#69758a", fontSize: 13 }}>평균 잔액</dt><dd style={{ margin: "3px 0 0", fontWeight: 800 }}>{formatWon(stat.mean_balance_krw)}</dd></div>
        <div><dt style={{ color: "#69758a", fontSize: 13 }}>평균 월 납입액</dt><dd style={{ margin: "3px 0 0", fontWeight: 800 }}>{formatWon(stat.mean_monthly_contribution_krw)}</dd></div>
        <div><dt style={{ color: "#69758a", fontSize: 13 }}>평균 위험자산 비중</dt><dd style={{ margin: "3px 0 0", fontWeight: 800 }}>{Number(stat.mean_risky_asset_ratio_percent).toFixed(1)}%</dd></div>
      </dl>
    </article>
  );
}

export function BenchmarkPage() {
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getBenchmarkSummary().then(setSummary).catch(() => {
      setError("벤치마크 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.");
    });
  }, []);

  return (
    <section style={{ maxWidth: 960, margin: "0 auto", padding: "24px 16px 48px" }}>
      <p style={{ color: "#2d6bd3", fontWeight: 800, margin: 0 }}>익명 연금 벤치마크</p>
      <h1 style={{ fontSize: 28, margin: "8px 0" }}>내 상황을 이해하기 위한 전체 흐름</h1>
      <p style={{ color: "#586174", lineHeight: 1.6, marginTop: 0 }}>
        다른 사람의 계좌를 따라 하는 공간이 아닙니다. 1만 명의 통계 모델 목데이터를 바탕으로,
        내 연금계좌를 바라볼 때 참고할 수 있는 전체 분포를 보여드립니다.
      </p>

      {error && <p role="alert" style={{ color: "#b42318" }}>{error}</p>}
      {!summary && !error && <p>벤치마크를 불러오는 중입니다…</p>}
      {summary && <>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12, margin: "24px 0" }}>
          {[
            ["고객 표본", `${summary.user_count.toLocaleString("ko-KR")}명`],
            ["연금계좌", `${summary.account_count.toLocaleString("ko-KR")}개`],
            ["보유 항목", `${summary.holding_count.toLocaleString("ko-KR")}건`],
          ].map(([label, value]) => <article key={label} style={{ background: "#eef5ff", borderRadius: 16, padding: 18 }}><p style={{ margin: 0, color: "#596579" }}>{label}</p><strong style={{ display: "block", fontSize: 22, marginTop: 6 }}>{value}</strong></article>)}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 20 }}>
          <article style={{ border: "1px solid #dce5f3", borderRadius: 18, padding: 20 }}><h2 style={{ fontSize: 18, marginTop: 0 }}>연령대 구성</h2><Distribution items={summary.age_groups} labels={ageLabels} /></article>
          <article style={{ border: "1px solid #dce5f3", borderRadius: 18, padding: 20 }}><h2 style={{ fontSize: 18, marginTop: 0 }}>투자성향 구성</h2><Distribution items={summary.risk_profiles} labels={riskLabels} /></article>
        </div>

        <h2 style={{ fontSize: 20, margin: "32px 0 14px" }}>계좌 유형별 평균</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 14 }}>
          {summary.account_type_stats.map((stat) => <AccountStat key={stat.account_type} stat={stat} />)}
        </div>
        <p style={{ marginTop: 24, padding: 16, borderRadius: 12, background: "#f6f7f9", color: "#4d596c", lineHeight: 1.6 }}>
          <strong>{summary.source_label}</strong><br />{summary.notice}
        </p>
      </>}
    </section>
  );
}
