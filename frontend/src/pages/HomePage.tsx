import { useEffect, useState } from "react";
import type {
  AssetClass,
  DemoHeroPortfolio,
  DemoUserFinancialContext,
  InvestmentProfileResponse,
} from "../api/types";
import { donutArcPaths } from "../charts";

const ASSET_LABELS: Record<AssetClass, string> = {
  cash: "현금성", deposit: "원리금보장", bond: "채권",
  domestic_equity: "국내주식", global_equity: "글로벌주식",
  alternative: "대체자산", eligible_tdf: "적격 TDF", default_option: "디폴트옵션",
};
const RISK_LABELS: Record<string, string> = {
  stable: "안정형", stable_seeking: "안정추구형", risk_neutral: "위험중립형",
  active: "적극투자형", aggressive: "공격투자형",
  conservative: "안정형", balanced: "균형형", growth: "성장형",
};
const ACCOUNT_LABELS: Record<string, string> = {
  dc: "DC", irp: "IRP", pension_savings: "연금저축",
};
const COLORS = ["#007848", "#8ead52", "#d7a44d", "#6887aa", "#d37c67"];
const formatKrw = (value: string) => `${Math.round(Number(value)).toLocaleString("ko-KR")}원`;
const displayName = (name: string) => name.replace(/\(가상\)/g, "");

interface HomePageProps {
  error: string | null;
  hero: DemoHeroPortfolio | null;
  investmentProfile: InvestmentProfileResponse | null;
  loading: boolean;
  onAnalyzeHero: (scenarioCode: string) => void;
  userContext: DemoUserFinancialContext | null;
}

export function HomePage({ error, hero, investmentProfile, loading, onAnalyzeHero, userContext }: HomePageProps) {
  const [selectedAssetClass, setSelectedAssetClass] = useState<string | null>(null);
  useEffect(() => {
    setSelectedAssetClass(null);
  }, [hero?.scenario_code]);
  if (loading) return <section className="home-dashboard"><p className="home-loading">내 연금 데이터를 불러오는 중입니다…</p></section>;
  if (!userContext) return <section className="home-dashboard"><p className="home-error">{error ?? "로그인한 사용자의 연금 데이터를 찾지 못했습니다."}</p></section>;
  const savedRiskProfile = investmentProfile?.assessment && !investmentProfile.assessment.is_expired
    ? investmentProfile.assessment.risk_profile
    : null;

  return <section className="home-dashboard">
    <header className="home-hero-heading">
      <span>연금계좌 운용 가이드</span>
      <h1>{displayName(userContext.nickname)}님의<br />연금 현황이에요</h1>
      <p>{userContext.customer_context}</p>
    </header>
    {error && <p className="home-error">{error}</p>}
    {hero ? <>
      <article className="portfolio-summary-card">
        <div className="portfolio-summary-top"><div>
          <h2>{hero.scenario_name}</h2>
          <p>{userContext.age_band} · {userContext.representative_age}세 · {RISK_LABELS[savedRiskProfile ?? hero.risk_profile] ?? "기타 투자성향"} · 투자기간 {hero.investment_horizon_years}년</p>
        </div><strong>{formatKrw(userContext.total_pension_balance_krw)}</strong></div>
        <p className="peer-metric-note">{userContext.as_of_date} 기준 계좌 현황입니다.</p>
        <div className="risk-metric-grid">
          <div><span>DC</span><strong>{formatKrw(userContext.dc_balance_krw)}</strong></div>
          <div><span>IRP</span><strong>{formatKrw(userContext.irp_balance_krw)}</strong></div>
          <div><span>연금저축</span><strong>{formatKrw(userContext.pension_savings_balance_krw)}</strong></div>
        </div>
        <div className="allocation-layout">
          <svg className="home-allocation-donut" viewBox="0 0 100 100" aria-label="자산군 비중을 탭해 상세 보기">{donutArcPaths(hero.asset_allocations.map((item) => Number(item.allocation_percent))).map((d, index) => { const item = hero.asset_allocations[index]; const selected = selectedAssetClass === item.asset_class_code; return <path key={item.asset_class_code} d={d} fill={COLORS[index % COLORS.length]} className={selectedAssetClass && !selected ? "is-dim" : ""} transform={selected ? "translate(2 0)" : undefined} role="button" tabIndex={0} aria-label={`${ASSET_LABELS[item.asset_class_code as AssetClass] ?? "기타 자산군"} ${item.allocation_percent}%`} onClick={() => setSelectedAssetClass(selected ? null : item.asset_class_code)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedAssetClass(selected ? null : item.asset_class_code); } }} />; })}<text x="50" y="48" textAnchor="middle">총자산</text><text x="50" y="60" textAnchor="middle" className="home-donut-total">100%</text></svg>
          <ul className="home-allocation-list">{hero.asset_allocations.map((item, index) => <li key={item.asset_class_code}><button type="button" className={selectedAssetClass === item.asset_class_code ? "is-selected" : ""} onClick={() => setSelectedAssetClass(selectedAssetClass === item.asset_class_code ? null : item.asset_class_code)}><i style={{ backgroundColor: COLORS[index % COLORS.length] }} /><span>{ASSET_LABELS[item.asset_class_code as AssetClass] ?? "기타 자산군"}</span><strong>{item.allocation_percent}%</strong></button></li>)}</ul>
        </div>
        {selectedAssetClass && (() => { const allocation = hero.asset_allocations.find((item) => item.asset_class_code === selectedAssetClass); if (!allocation) return null; const holdings = hero.accounts.flatMap((account) => account.holdings.filter((holding) => holding.asset_class_code === selectedAssetClass).map((holding) => ({ account, holding }))); return <section className="home-allocation-detail" aria-live="polite"><strong>{ASSET_LABELS[allocation.asset_class_code as AssetClass] ?? "기타 자산군"} 상세</strong><p>비중 {allocation.allocation_percent}% · 평가 금액 {formatKrw(allocation.amount_krw)} · {allocation.account_count}개 계좌</p><ul>{holdings.map(({ account, holding }) => <li key={holding.holding_id}>{account.label} ({ACCOUNT_LABELS[account.account_type]}) · {holding.instrument_name}{holding.etf_isu_code ? ` · ${holding.etf_isu_code}` : ""}</li>)}</ul><small>목데이터 · {hero.past_performance.source_label} · {hero.past_performance.period_end}</small></section>; })()}
      </article>
      <article className="risk-review-card">
        <div className="section-heading-row"><div><span>규칙 엔진 점검</span><h2>위험·스트레스 확인</h2></div><b className={hero.risk_summary.requires_rebalancing_review ? "review-needed" : "review-ok"}>{hero.risk_summary.requires_rebalancing_review ? "리밸런싱 점검 필요" : "현재 기준 내"}</b></div>
        <div className="risk-metric-grid"><div><span>일반 위험자산</span><strong>{hero.risk_summary.general_risky_asset_percent}%</strong></div><div><span>최대 자산군</span><strong>{hero.risk_summary.dominant_asset_percent}%</strong></div><div className="stress-metric"><span>주식 급락 충격 시 교육용 손실 점검값</span><strong>{hero.risk_summary.estimated_stress_loss_percent}%</strong></div></div>
        <p>고정 충격을 적용한 점검값이며 미래 손실 예측이나 수익률 전망이 아닙니다.</p>
      </article>
      <section className="account-holdings-section"><div className="section-heading-row"><div><span>계좌별 구성</span><h2>보유 항목</h2></div><small>ETF 종목코드 표시</small></div><div className="account-card-list">{hero.accounts.map((account) => <article key={account.account_id}><header><strong>{account.label}</strong><span>{ACCOUNT_LABELS[account.account_type]}</span></header><ul>{account.holdings.map((holding) => <li key={holding.holding_id}><div><strong>{holding.instrument_name}</strong><small>{ASSET_LABELS[holding.asset_class_code] ?? "기타 자산군"}</small></div><div>{holding.etf_isu_code && <code>{holding.etf_isu_code}</code>}<span>{formatKrw(holding.amount_krw)}</span></div></li>)}</ul></article>)}</div></section>
      <button className="analyze-hero-button" type="button" onClick={() => onAnalyzeHero(hero.scenario_code)}>내 연금 분석하기</button>
    </> : <article className="portfolio-summary-card"><h2>{userContext.scenario_name}</h2><p>총 연금 잔액 {formatKrw(userContext.total_pension_balance_krw)}</p></article>}
  </section>;
}
