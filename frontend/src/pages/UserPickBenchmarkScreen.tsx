import { useMemo, useState, type JSX } from "react";

import type { AssetAllocation, DemoHeroPortfolio } from "../api/types";
import "./UserPickBenchmarkScreen.css";

interface UserPickBenchmarkScreenProps {
  currentHero: DemoHeroPortfolio | null;
  heroes: DemoHeroPortfolio[];
  onBack: () => void;
}

type FilterKey = "rate" | "likes";

interface AllocationSlice {
  code: string;
  label: string;
  percent: number;
  color: string;
}

interface PickPortfolio {
  id: string;
  scenarioCode: string;
  scenarioName: string;
  ageBand: string;
  rate: string;
  rateNum: number;
  rateColor: string;
  amount: string;
  allocations: AllocationSlice[];
  holdings: string;
  likes: number;
}

const FILTER_LABELS: Record<FilterKey, string> = { rate: "수익률순", likes: "좋아요순" };
const ALLOCATION_COLORS = ["#22A94D", "#7FD79A", "#FDC526", "#CFD4DA"];
const ASSET_LABELS: Record<string, string> = {
  cash: "현금성자산",
  deposit: "원리금보장",
  bond: "채권",
  domestic_equity: "국내주식",
  global_equity: "글로벌주식",
  alternative: "대체자산",
  eligible_tdf: "적격 TDF",
  default_option: "디폴트옵션",
};

function formatKrw(value: string): string {
  return `${Math.round(Number(value)).toLocaleString("ko-KR")}원`;
}

function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function allocationSlices(allocations: AssetAllocation[]): AllocationSlice[] {
  return allocations.slice(0, 4).map((item, index) => ({
    code: item.asset_class_code,
    label: ASSET_LABELS[item.asset_class_code] ?? "기타 자산군",
    percent: Number(item.allocation_percent),
    color: ALLOCATION_COLORS[index],
  }));
}

function toPickPortfolio(hero: DemoHeroPortfolio): PickPortfolio {
  const rateNum = Number(hero.past_performance.trailing_12m_return_pct);
  const allocations = allocationSlices(hero.asset_allocations);
  return {
    id: hero.nickname,
    scenarioCode: hero.scenario_code,
    scenarioName: hero.scenario_name,
    ageBand: hero.age_band,
    rate: formatPercent(rateNum),
    rateNum,
    rateColor: rateNum >= 0 ? "#166F39" : "#2E7CE0",
    amount: formatKrw(hero.total_amount_krw),
    allocations,
    holdings: allocations.map((item) => `${item.label} ${item.percent}%`).join(" · "),
    likes: hero.like_summary.count,
  };
}

function allocationBackground(allocations: AllocationSlice[]): string {
  let position = 0;
  const stops = allocations.map((item) => {
    const start = position;
    position += item.percent;
    return `${item.color} ${start}% ${position}%`;
  });
  stops.push(`#E6E8EB ${position}% 100%`);
  return `conic-gradient(${stops.join(", ")})`;
}

function allocationPercent(portfolio: PickPortfolio, code: string): number {
  return portfolio.allocations.find((item) => item.code === code)?.percent ?? 0;
}

function compareRows(current: PickPortfolio | null, selected: PickPortfolio) {
  return selected.allocations.map((allocation) => {
    const mine = current ? allocationPercent(current, allocation.code) : 0;
    const up = allocation.percent >= mine;
    return { ...allocation, mine, arrow: up ? "▲" : "▼", directionColor: up ? "#22A94D" : "#E0453A" };
  });
}

export function UserPickBenchmarkScreen({ currentHero, heroes, onBack }: UserPickBenchmarkScreenProps): JSX.Element {
  const [filter, setFilter] = useState<FilterKey>("rate");
  const [filterOpen, setFilterOpen] = useState(false);
  const [sheetId, setSheetId] = useState<string | null>(null);
  const portfolios = useMemo(() => heroes.map(toPickPortfolio), [heroes]);
  const currentPortfolio = useMemo(() => currentHero ? toPickPortfolio(currentHero) : null, [currentHero]);
  const sorted = [...portfolios].sort((left, right) => filter === "likes"
    ? right.likes - left.likes
    : right.rateNum - left.rateNum);
  const sheetPortfolio = portfolios.find((portfolio) => portfolio.scenarioCode === sheetId) ?? null;

  function selectFilter(next: FilterKey): void {
    setFilter(next);
    setFilterOpen(false);
  }

  return (
    <main className="ub-stage">
      <section className="ub-phone" aria-label="대표고객 포트폴리오 비교">
        <div className="ub-page">
          <div className="ub-statusbar"><span>9:41</span><div className="ub-statusbar-battery" /></div>
          <div className="ub-topbar">
            <button type="button" className="ub-back-btn" onClick={onBack} aria-label="뒤로 가기"><svg width="11" height="20" viewBox="0 0 11 20" fill="none"><path d="M9.5 1L1.5 10L9.5 19" stroke="#1E2124" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg></button>
            <span className="ub-topbar-title">이용자 <span className="ub-topbar-title-accent">Pick 비교</span>하기</span>
            <div className="ub-topbar-spacer" />
          </div>

          <div className="ub-head">
            <div className="ub-head-label">내 포트폴리오</div>
            <div className="ub-mine-card">
              <div className="ub-mine-title-row"><div className="ub-mine-title-bar" /><span className="ub-mine-title">현재 포트폴리오</span></div>
              {currentPortfolio ? <>
                <div className="ub-mine-body">
                  <div className="ub-mine-donut" style={{ background: allocationBackground(currentPortfolio.allocations) }}><div className="ub-mine-donut-inner">자산군</div></div>
                  <div className="ub-mine-facts">
                    <div className="ub-mine-fact-row"><span className="ub-mine-fact-label">ID</span><span className="ub-mine-fact-value">{currentPortfolio.id}</span></div>
                    <div className="ub-mine-fact-row"><span className="ub-mine-fact-label">연령대</span><span className="ub-mine-fact-value">{currentPortfolio.ageBand}</span></div>
                    <div className="ub-mine-fact-row" style={{ alignItems: "baseline" }}><span className="ub-mine-fact-label">금액</span><span className="ub-mine-fact-amount">{currentPortfolio.amount}</span></div>
                  </div>
                </div>
                <div className="ub-alloc-block"><div className="ub-alloc-title">포트폴리오 구성 비율</div><div className="ub-alloc-bar">{currentPortfolio.allocations.map((item) => <div key={item.code} style={{ width: `${item.percent}%`, background: item.color }} />)}</div><div className="ub-alloc-legend">{currentPortfolio.allocations.map((item) => <span className="ub-alloc-legend-item" key={item.code}><span className="ub-alloc-legend-dot" style={{ background: item.color }} />{item.label} {item.percent}%</span>)}</div></div>
                <div className="ub-strategy-row"><div className="ub-strategy-line"><span className="ub-strategy-label">대표 시나리오</span><span className="ub-strategy-name">{currentPortfolio.scenarioName}</span></div></div>
              </> : <p className="ub-card-no-strategy">내 포트폴리오를 불러오는 중입니다.</p>}
            </div>

            <div className="ub-list-head"><span className="ub-list-head-label">대표고객 포트폴리오</span><button type="button" className="ub-filter-btn" onClick={() => setFilterOpen((open) => !open)}><svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M3 5h18M6 12h12M10 19h4" stroke="#22A94D" strokeWidth="2.2" strokeLinecap="round" /></svg><span className="ub-filter-btn-label">{FILTER_LABELS[filter]}</span><svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2.5 4.5L6 8L9.5 4.5" stroke="#22A94D" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg></button></div>
            {filterOpen && <div className="ub-chip-row">{(Object.keys(FILTER_LABELS) as FilterKey[]).map((key) => <button type="button" key={key} onClick={() => selectFilter(key)} className={`ub-chip${filter === key ? " ub-chip-active" : ""}`}>{FILTER_LABELS[key]}</button>)}</div>}
          </div>

          <div className="ub-scroll">
            {sorted.length === 0 ? <p className="ub-card-no-strategy">대표고객 포트폴리오를 불러오는 중입니다.</p> : sorted.map((portfolio) => <button type="button" key={portfolio.scenarioCode} className="ub-card" onClick={() => setSheetId(portfolio.scenarioCode)}>
              <div className="ub-card-top"><div className="ub-card-info"><div className="ub-card-info-row"><span className="ub-card-info-label">ID</span><span className="ub-card-info-value">{portfolio.id}</span></div><div className="ub-card-info-row"><span className="ub-card-info-label">연령대</span><span className="ub-card-info-sector">{portfolio.ageBand}</span></div></div><div className="ub-card-rate-wrap"><div className="ub-card-rate-label">과거 12개월 수익률</div><div className="ub-card-rate-value" style={{ color: portfolio.rateColor }}>{portfolio.rate}</div></div></div>
              <div className="ub-card-amount-row"><span className="ub-card-amount-label">금액</span><span className="ub-card-amount-value">{portfolio.amount}</span></div>
              <div className="ub-card-alloc"><div className="ub-card-alloc-title">포트폴리오 구성 비율</div><div className="ub-card-alloc-bar">{portfolio.allocations.map((item) => <div key={item.code} style={{ width: `${item.percent}%`, background: item.color }} />)}</div><div className="ub-card-holdings">{portfolio.holdings}</div></div>
              <div className="ub-card-strategy"><div className="ub-strategy-line"><span className="ub-strategy-label">대표 시나리오</span><span className="ub-strategy-name">{portfolio.scenarioName}</span></div><div className="ub-card-likes-row"><span className="ub-card-likes"><svg width="15" height="15" viewBox="0 0 24 24" fill="#22A94D"><path d="M12 21s-7.5-4.6-10-9.1C.3 8.8 2 5.5 5.2 5.5c1.9 0 3.2 1.1 3.8 2 .6-.9 1.9-2 3.8-2 3.2 0 4.9 3.3 3.2 6.4C19.5 16.4 12 21 12 21z" /></svg><span className="ub-card-likes-value">{portfolio.likes.toLocaleString("ko-KR")}</span></span></div></div>
            </button>)}
          </div>
          <div className="ub-fade" />

          {sheetPortfolio && <div className="ub-sheet-overlay"><button type="button" className="ub-sheet-backdrop" aria-label="닫기" onClick={() => setSheetId(null)} /><div className="ub-sheet"><div className="ub-sheet-handle-row"><div className="ub-sheet-handle" /></div><div className="ub-sheet-body"><div className="ub-sheet-header"><div><div className="ub-sheet-name"><span className="ub-sheet-name-accent">{sheetPortfolio.id}</span>님</div><div className="ub-sheet-name">포트폴리오</div></div><div className="ub-sheet-follow"><svg width="34" height="34" viewBox="0 0 24 24" fill="#FDC526"><path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.8 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8L12 2z" /></svg><div className="ub-sheet-follow-count">좋아요 {sheetPortfolio.likes.toLocaleString("ko-KR")}</div></div></div><div className="ub-sheet-summary"><div className="ub-sheet-donut" style={{ background: allocationBackground(sheetPortfolio.allocations) }}><div className="ub-sheet-donut-inner"><div className="ub-sheet-donut-label">과거 12개월</div><div className="ub-sheet-donut-rate" style={{ color: sheetPortfolio.rateColor }}>{sheetPortfolio.rate}</div></div></div><div className="ub-sheet-alloc-list">{sheetPortfolio.allocations.map((allocation) => <div className="ub-sheet-alloc-row" key={allocation.code}><span className="ub-sheet-alloc-label"><span className="ub-sheet-alloc-dot" style={{ background: allocation.color }} />{allocation.label}</span><span className="ub-sheet-alloc-pct">{allocation.percent}%</span></div>)}</div></div><div className="ub-sheet-compare-title">내 포트폴리오와 <span className="ub-sheet-compare-accent">비교</span></div><div className="ub-sheet-table"><div className="ub-sheet-table-head"><span>자산군</span><span className="ub-sheet-table-head-mine">내 비중</span><span className="ub-sheet-table-head-theirs">대표고객</span></div>{compareRows(currentPortfolio, sheetPortfolio).map((row) => <div className="ub-sheet-row" key={row.code}><div><div className="ub-sheet-row-name">{row.label}</div></div><span className="ub-sheet-row-mine">{row.mine}%</span><span className="ub-sheet-row-theirs" style={{ color: row.directionColor }}><span className="ub-sheet-row-arrow">{row.arrow}</span>{row.percent}%</span></div>)}</div><p className="ub-strategy-detail">과거 12개월 수익률과 대표고객 목데이터를 비교용으로 표시합니다. 미래 수익을 예측하지 않습니다.</p><div className="ub-sheet-actions"><button type="button" className="ub-sheet-close-btn" onClick={() => setSheetId(null)}>닫기</button><button type="button" className="ub-sheet-benchmark-btn" onClick={() => setSheetId(null)}>이 포트폴리오 참고하기</button></div></div></div></div>}
        </div>
      </section>
    </main>
  );
}
