import { useEffect, useMemo, useState } from "react";

import { getDemoHeroes } from "../api/client";
import type {
  AssetClass,
  DemoHeroPortfolio,
} from "../api/types";
import { conicGradient } from "../charts";


const ASSET_LABELS: Record<AssetClass, string> = {
  cash: "현금성",
  deposit: "원리금보장",
  bond: "채권",
  domestic_equity: "국내주식",
  global_equity: "글로벌주식",
  alternative: "대체자산",
  eligible_tdf: "적격 TDF",
  default_option: "디폴트옵션",
};

const RISK_LABELS: Record<string, string> = {
  conservative: "안정형",
  balanced: "균형형",
  growth: "성장형",
};

const ACCOUNT_LABELS: Record<string, string> = {
  dc: "DC",
  irp: "IRP",
  pension_savings: "연금저축",
};

const ALLOCATION_COLORS = ["#007848", "#8ead52", "#d7a44d", "#6887aa", "#d37c67"];

function formatKrw(value: string): string {
  return `${Math.round(Number(value)).toLocaleString("ko-KR")}원`;
}

interface HomePageProps {
  onAnalyzeHero: (scenarioCode: string) => void;
  onSignOut: () => void;
}

export function HomePage({ onAnalyzeHero, onSignOut }: HomePageProps) {
  const [heroes, setHeroes] = useState<DemoHeroPortfolio[]>([]);
  const [selectedCode, setSelectedCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getDemoHeroes()
      .then((items) => {
        if (cancelled) return;
        setHeroes(items);
        setSelectedCode((current) => current || items[0]?.scenario_code || "");
      })
      .catch(() => {
        if (!cancelled) setError("가상 고객 포트폴리오를 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(
    () => heroes.find((hero) => hero.scenario_code === selectedCode) ?? null,
    [heroes, selectedCode],
  );

  return (
    <section className="home-dashboard">
      <header className="home-hero-heading">
        <div className="home-heading-topline">
          <span>연금계좌 운용 가이드</span>
          {/* 임시 위치 — 추후 프로필/헤더로 이동 */}
          <button className="home-temp-sign-out" onClick={onSignOut} type="button">로그아웃</button>
        </div>
        <h1>누구의 포트폴리오를<br />살펴볼까요?</h1>
        <p>발표용 가상 고객 6명의 실제 ETF 연결 보유내역을 확인할 수 있습니다.</p>
      </header>

      {error && <p className="home-error">{error}</p>}
      {!error && heroes.length === 0 && <p className="home-loading">고객 포트폴리오를 불러오는 중입니다…</p>}

      <div className="hero-picker" aria-label="가상 고객 선택">
        {heroes.map((hero) => (
          <button
            aria-pressed={hero.scenario_code === selectedCode}
            className={hero.scenario_code === selectedCode ? "active" : ""}
            key={hero.scenario_code}
            onClick={() => setSelectedCode(hero.scenario_code)}
            type="button"
          >
            <span>{hero.nickname.slice(0, 1)}</span>
            <strong>{hero.nickname}</strong>
            <small>{hero.representative_age}세 · {RISK_LABELS[hero.risk_profile] ?? hero.risk_profile}</small>
          </button>
        ))}
      </div>

      {selected && (
        <>
          <article className="portfolio-summary-card">
            <div className="portfolio-summary-top">
              <div>
                <span className="mock-chip">가상 목데이터</span>
                <h2>{selected.nickname}</h2>
                <p>{selected.customer_context}</p>
              </div>
              <strong>{formatKrw(selected.total_amount_krw)}</strong>
            </div>

            <div className="allocation-layout">
              <div
                aria-label={selected.asset_allocations.map((item) => `${ASSET_LABELS[item.asset_class_code as AssetClass] ?? item.asset_class_code} ${item.allocation_percent}%`).join(", ")}
                className="home-allocation-donut"
                role="img"
                style={{
                  background: `conic-gradient(${conicGradient(
                    selected.asset_allocations.map((item) => Number(item.allocation_percent)),
                    ALLOCATION_COLORS,
                  )})`,
                }}
              >
                <span>총자산<br /><strong>100%</strong></span>
              </div>
              <ul className="home-allocation-list">
                {selected.asset_allocations.map((item, index) => (
                  <li key={item.asset_class_code}>
                    <i style={{ backgroundColor: ALLOCATION_COLORS[index % ALLOCATION_COLORS.length] }} />
                    <span>{ASSET_LABELS[item.asset_class_code as AssetClass] ?? item.asset_class_code}</span>
                    <strong>{item.allocation_percent}%</strong>
                  </li>
                ))}
              </ul>
            </div>
          </article>

          <article className="risk-review-card">
            <div className="section-heading-row">
              <div>
                <span>규칙 엔진 점검</span>
                <h2>위험·스트레스 확인</h2>
              </div>
              <b className={selected.risk_summary.requires_rebalancing_review ? "review-needed" : "review-ok"}>
                {selected.risk_summary.requires_rebalancing_review ? "리밸런싱 점검 필요" : "현재 기준 내"}
              </b>
            </div>
            <div className="risk-metric-grid">
              <div><span>일반 위험자산</span><strong>{selected.risk_summary.general_risky_asset_percent}%</strong></div>
              <div><span>최대 자산군</span><strong>{selected.risk_summary.dominant_asset_percent}%</strong></div>
              <div className="stress-metric"><span>주식 급락 충격 시 교육용 손실 점검값</span><strong>{selected.risk_summary.estimated_stress_loss_percent}%</strong></div>
            </div>
            <p>고정 충격을 적용한 점검값이며 미래 손실 예측이나 수익률 전망이 아닙니다.</p>
          </article>

          <section className="account-holdings-section">
            <div className="section-heading-row">
              <div><span>계좌별 구성</span><h2>보유 항목</h2></div>
              <small>ETF 종목코드 표시</small>
            </div>
            <div className="account-card-list">
              {selected.accounts.map((account) => (
                <article key={account.account_id}>
                  <header><strong>{account.label}</strong><span>{ACCOUNT_LABELS[account.account_type]}</span></header>
                  <ul>
                    {account.holdings.map((holding) => (
                      <li key={holding.holding_id}>
                        <div>
                          <strong>{holding.instrument_name}</strong>
                          <small>{ASSET_LABELS[holding.asset_class_code] ?? holding.asset_class_code}</small>
                        </div>
                        <div>
                          {holding.etf_isu_code && <code>{holding.etf_isu_code}</code>}
                          <span>{formatKrw(holding.amount_krw)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </section>

          <button className="analyze-hero-button" type="button" onClick={() => onAnalyzeHero(selected.scenario_code)}>
            이 고객 분석하기
          </button>
        </>
      )}
    </section>
  );
}
