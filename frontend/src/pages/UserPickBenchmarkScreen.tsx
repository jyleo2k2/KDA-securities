import { useState, type JSX } from "react";

import "./UserPickBenchmarkScreen.css";

interface UserPickBenchmarkScreenProps {
  onBack: () => void;
}

type FilterKey = "rate" | "period" | "job" | "likes";

interface RawPortfolio {
  id: string;
  sector: string;
  rate: string;
  rateNum: number;
  rateColor: string;
  months: number;
  period: string;
  a1: number;
  a2: number;
  a3: number;
  amount: string;
  s1: string;
  s2: string;
  s3: string;
  holdings: string;
  feas: "direct" | "product" | null;
  strategyName: string | null;
  strategyDetail: string | null;
  likes: string;
}

const RAW_PORTFOLIOS: RawPortfolio[] = [
  { id: "꾸준한거북이", sector: "2차전지 종사자", rate: "+18.2%", rateNum: 18.2, rateColor: "#166F39", months: 44, period: "운용 3년 8개월", a1: 55, a2: 19, a3: 18, amount: "2,860만원", s1: "38%", s2: "27%", s3: "20%", holdings: "국내주식 38% · 해외주식·ETF 27% · 채권 20% · 현금성자산 15%", feas: "direct", strategyName: "테마", strategyDetail: "테마 선정·교체 규칙 일부 정의, 모델 비중 미정", likes: "1,204" },
  { id: "배당모으미", sector: "금융업 종사자", rate: "+9.6%", rateNum: 9.6, rateColor: "#166F39", months: 30, period: "운용 2년 6개월", a1: 34, a2: 30, a3: 22, amount: "5,120만원", s1: "34%", s2: "30%", s3: "22%", holdings: "국내주식 34% · 해외주식·ETF 30% · 채권 22% · 현금성자산 14%", feas: "direct", strategyName: "팩터", strategyDetail: "가치·퀄리티·모멘텀 비중 미정", likes: "876" },
  { id: "느긋한바벨러", sector: "자산운용 종사자", rate: "+6.1%", rateNum: 6.1, rateColor: "#166F39", months: 62, period: "운용 5년 2개월", a1: 30, a2: 20, a3: 34, amount: "8,430만원", s1: "30%", s2: "20%", s3: "34%", holdings: "국내주식 30% · 해외주식·ETF 20% · 채권 34% · 현금성자산 16%", feas: "direct", strategyName: "바벨", strategyDetail: "성장·안전자산 구성 비중을 연령별로만 일부 정의", likes: "642" },
  { id: "중립러버", sector: "IT업 종사자", rate: "+3.8%", rateNum: 3.8, rateColor: "#166F39", months: 14, period: "운용 1년 2개월", a1: 26, a2: 24, a3: 28, amount: "3,270만원", s1: "26%", s2: "24%", s3: "28%", holdings: "국내주식 26% · 해외주식·ETF 24% · 채권 28% · 현금성자산 22%", feas: "product", strategyName: "롱숏·시장중립", strategyDetail: "계좌 적격 상품과 실제 성과 데이터 없음", likes: "415" },
  { id: "초보투자자", sector: "학생", rate: "-2.4%", rateNum: -2.4, rateColor: "#2E7CE0", months: 5, period: "운용 5개월", a1: 62, a2: 12, a3: 8, amount: "540만원", s1: "62%", s2: "12%", s3: "8%", holdings: "국내주식 62% · 해외주식·ETF 12% · 채권 8% · 현금성자산 18%", feas: null, strategyName: null, strategyDetail: null, likes: "37" },
];

const FILTER_LABELS: Record<FilterKey, string> = { rate: "수익률순", period: "운용기간순", job: "직업군별", likes: "좋아요순" };

function likesNum(value: string): number {
  return parseInt(value.replace(/[^0-9]/g, ""), 10) || 0;
}

function badgeClass(feas: "direct" | "product"): string {
  return feas === "direct" ? "ub-strategy-badge" : "ub-strategy-badge ub-strategy-badge-product";
}

function sheetDonut(p: RawPortfolio): string {
  return `conic-gradient(#22A94D 0 ${p.a1}%, #7FD79A ${p.a1}% ${p.a1 + p.a2}%, #FDC526 ${p.a1 + p.a2}% ${p.a1 + p.a2 + p.a3}%, #E6E8EB ${p.a1 + p.a2 + p.a3}% 100%)`;
}

const SHEET_ALLOC_COLORS = ["#22A94D", "#7FD79A", "#FDC526", "#CFD4DA"];
const SHEET_ALLOC_LABELS = ["국내주식", "해외주식·ETF", "채권", "현금성자산"];

function sheetAlloc(p: RawPortfolio): Array<{ color: string; label: string; pct: string }> {
  const pcts = [p.a1, p.a2, p.a3, 100 - p.a1 - p.a2 - p.a3];
  return pcts.map((pct, i) => ({ color: SHEET_ALLOC_COLORS[i], label: SHEET_ALLOC_LABELS[i], pct: `${pct}%` }));
}

const COMPARE_ROWS = [
  { name: "TIGER 200", cat: "국내주식", mineN: 42, key: "a1" as const },
  { name: "TIGER 미국S&P500", cat: "해외주식·ETF", mineN: 26, key: "a2" as const },
  { name: "KODEX 국고채", cat: "채권", mineN: 18, key: "a3" as const },
];

function sheetRows(p: RawPortfolio): Array<{ name: string; cat: string; mine: string; theirs: string; arrow: string; color: string }> {
  return COMPARE_ROWS.map((row) => {
    const theirsN = p[row.key];
    const up = theirsN >= row.mineN;
    return { name: row.name, cat: row.cat, mine: `${row.mineN}%`, theirs: `${theirsN}%`, arrow: up ? "▲" : "▼", color: up ? "#22A94D" : "#E0453A" };
  });
}

export function UserPickBenchmarkScreen({ onBack }: UserPickBenchmarkScreenProps): JSX.Element {
  const [filter, setFilter] = useState<FilterKey>("rate");
  const [filterOpen, setFilterOpen] = useState(false);
  const [sheetId, setSheetId] = useState<string | null>(null);

  const sorted = [...RAW_PORTFOLIOS].sort((a, b) => {
    if (filter === "period") return b.months - a.months;
    if (filter === "job") return a.sector.localeCompare(b.sector, "ko") || b.rateNum - a.rateNum;
    if (filter === "likes") return likesNum(b.likes) - likesNum(a.likes);
    return b.rateNum - a.rateNum;
  });

  const sheetPortfolio = RAW_PORTFOLIOS.find((p) => p.id === sheetId) ?? null;

  function selectFilter(next: FilterKey): void {
    setFilter(next);
    setFilterOpen(false);
  }

  return (
    <main className="ub-stage">
      <section className="ub-phone" aria-label="투자 벤치마킹하기">
        <div className="ub-page">
          <div className="ub-statusbar">
            <span>9:41</span>
            <div className="ub-statusbar-battery" />
          </div>

          <div className="ub-topbar">
            <button type="button" className="ub-back-btn" onClick={onBack} aria-label="뒤로 가기">
              <svg width="11" height="20" viewBox="0 0 11 20" fill="none"><path d="M9.5 1L1.5 10L9.5 19" stroke="#1E2124" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
            <span className="ub-topbar-title">투자 <span className="ub-topbar-title-accent">벤치마킹</span>하기</span>
            <div className="ub-topbar-spacer" />
          </div>

          <div className="ub-head">
            <div className="ub-head-label">내 포트폴리오</div>

            <div className="ub-mine-card">
              <div className="ub-mine-title-row">
                <div className="ub-mine-title-bar" />
                <span className="ub-mine-title">현재 포트폴리오</span>
              </div>
              <div className="ub-mine-body">
                <div className="ub-mine-donut">
                  <div className="ub-mine-donut-inner">4자산군</div>
                </div>
                <div className="ub-mine-facts">
                  <div className="ub-mine-fact-row"><span className="ub-mine-fact-label">ID</span><span className="ub-mine-fact-value">투자하는너구리</span></div>
                  <div className="ub-mine-fact-row"><span className="ub-mine-fact-label">직업군</span><span className="ub-mine-fact-value">반도체 종사자</span></div>
                  <div className="ub-mine-fact-row" style={{ alignItems: "baseline" }}><span className="ub-mine-fact-label">금액</span><span className="ub-mine-fact-amount">1,240만원</span></div>
                </div>
              </div>

              <div className="ub-alloc-block">
                <div className="ub-alloc-title">포트폴리오 구성 비율</div>
                <div className="ub-alloc-bar">
                  <div style={{ width: "42%", background: "#22A94D" }} />
                  <div style={{ width: "26%", background: "#7FD79A" }} />
                  <div style={{ width: "18%", background: "#FDC526" }} />
                  <div style={{ width: "14%", background: "#CFD4DA" }} />
                </div>
                <div className="ub-alloc-legend">
                  <span className="ub-alloc-legend-item"><span className="ub-alloc-legend-dot" style={{ background: "#22A94D" }} />국내주식 42%</span>
                  <span className="ub-alloc-legend-item"><span className="ub-alloc-legend-dot" style={{ background: "#7FD79A" }} />해외주식·ETF 26%</span>
                  <span className="ub-alloc-legend-item"><span className="ub-alloc-legend-dot" style={{ background: "#FDC526" }} />채권 18%</span>
                  <span className="ub-alloc-legend-item"><span className="ub-alloc-legend-dot" style={{ background: "#CFD4DA" }} />현금성자산 14%</span>
                </div>
              </div>

              <div className="ub-strategy-row">
                <div className="ub-strategy-line">
                  <span className="ub-strategy-label">투자전략</span>
                  <span className="ub-strategy-name">탑다운</span>
                  <span className="ub-strategy-badge">직접 구현 가능</span>
                </div>
                <div className="ub-strategy-detail">국가·산업·채권 비중 결정 규칙 미정</div>
              </div>
            </div>

            <div className="ub-list-head">
              <span className="ub-list-head-label">추천 벤치마킹 포트폴리오</span>
              <button type="button" className="ub-filter-btn" onClick={() => setFilterOpen((open) => !open)}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M3 5h18M6 12h12M10 19h4" stroke="#22A94D" strokeWidth="2.2" strokeLinecap="round" /></svg>
                <span className="ub-filter-btn-label">{FILTER_LABELS[filter]}</span>
                <svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M2.5 4.5L6 8L9.5 4.5" stroke="#22A94D" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </button>
            </div>
            {filterOpen && (
              <div className="ub-chip-row">
                {(Object.keys(FILTER_LABELS) as FilterKey[]).map((key) => (
                  <div key={key} onClick={() => selectFilter(key)} className={`ub-chip${filter === key ? " ub-chip-active" : ""}`}>{FILTER_LABELS[key]}</div>
                ))}
              </div>
            )}
          </div>

          <div className="ub-scroll">
            {sorted.map((p) => (
              <button type="button" key={p.id} className="ub-card" onClick={() => setSheetId(p.id)}>
                <div className="ub-card-top">
                  <div className="ub-card-info">
                    <div className="ub-card-info-row"><span className="ub-card-info-label">ID</span><span className="ub-card-info-value">{p.id}</span></div>
                    <div className="ub-card-info-row"><span className="ub-card-info-label">직업군</span><span className="ub-card-info-sector">{p.sector}</span></div>
                    <div className="ub-card-period">{p.period}</div>
                  </div>
                  <div className="ub-card-rate-wrap">
                    <div className="ub-card-rate-label">수익률</div>
                    <div className="ub-card-rate-value" style={{ color: p.rateColor }}>{p.rate}</div>
                  </div>
                </div>

                <div className="ub-card-amount-row">
                  <span className="ub-card-amount-label">금액</span>
                  <span className="ub-card-amount-value">{p.amount}</span>
                </div>

                <div className="ub-card-alloc">
                  <div className="ub-card-alloc-title">포트폴리오 구성 비율</div>
                  <div className="ub-card-alloc-bar">
                    <div style={{ width: p.s1, background: "#22A94D" }} />
                    <div style={{ width: p.s2, background: "#7FD79A" }} />
                    <div style={{ width: p.s3, background: "#FDC526" }} />
                    <div style={{ flex: 1, background: "#CFD4DA" }} />
                  </div>
                  <div className="ub-card-holdings">{p.holdings}</div>
                </div>

                <div className="ub-card-strategy">
                  <div className="ub-strategy-line">
                    <span className="ub-strategy-label">투자전략</span>
                    {p.strategyName ? (
                      <>
                        <span className="ub-strategy-name">{p.strategyName}</span>
                        <span className={badgeClass(p.feas as "direct" | "product")}>{p.feas === "direct" ? "직접 구현 가능" : "상품 확인 후 가능"}</span>
                      </>
                    ) : (
                      <span className="ub-card-no-strategy">투자 전략 없음</span>
                    )}
                  </div>
                  {p.strategyDetail && <div className="ub-strategy-detail">{p.strategyDetail}</div>}
                  <div className="ub-card-likes-row">
                    <span className="ub-card-likes">
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="#22A94D"><path d="M12 21s-7.5-4.6-10-9.1C.3 8.8 2 5.5 5.2 5.5c1.9 0 3.2 1.1 3.8 2 .6-.9 1.9-2 3.8-2 3.2 0 4.9 3.3 3.2 6.4C19.5 16.4 12 21 12 21z" /></svg>
                      <span className="ub-card-likes-value">{p.likes}</span>
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div className="ub-fade" />

          {sheetPortfolio && (
            <div className="ub-sheet-overlay">
              <button type="button" className="ub-sheet-backdrop" aria-label="닫기" onClick={() => setSheetId(null)} />
              <div className="ub-sheet">
                <div className="ub-sheet-handle-row"><div className="ub-sheet-handle" /></div>
                <div className="ub-sheet-body">
                  <div className="ub-sheet-header">
                    <div>
                      <div className="ub-sheet-name"><span className="ub-sheet-name-accent">{sheetPortfolio.id}</span>님</div>
                      <div className="ub-sheet-name">포트폴리오</div>
                    </div>
                    <div className="ub-sheet-follow">
                      <svg width="34" height="34" viewBox="0 0 24 24" fill="#FDC526"><path d="M12 2l2.9 6.3 6.9.8-5.1 4.7 1.4 6.8L12 17.8 5.9 20.6l1.4-6.8L2.2 9.1l6.9-.8L12 2z" /></svg>
                      <div className="ub-sheet-follow-count">팔로우 {sheetPortfolio.likes}</div>
                    </div>
                  </div>

                  <div className="ub-sheet-summary">
                    <div className="ub-sheet-donut" style={{ background: sheetDonut(sheetPortfolio) }}>
                      <div className="ub-sheet-donut-inner">
                        <div className="ub-sheet-donut-label">벤치마크</div>
                        <div className="ub-sheet-donut-rate" style={{ color: sheetPortfolio.rateColor }}>{sheetPortfolio.rate}</div>
                      </div>
                    </div>
                    <div className="ub-sheet-alloc-list">
                      {sheetAlloc(sheetPortfolio).map((a) => (
                        <div className="ub-sheet-alloc-row" key={a.label}>
                          <span className="ub-sheet-alloc-label"><span className="ub-sheet-alloc-dot" style={{ background: a.color }} />{a.label}</span>
                          <span className="ub-sheet-alloc-pct">{a.pct}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="ub-sheet-compare-title">내 포트폴리오와 <span className="ub-sheet-compare-accent">비교</span></div>
                  <div className="ub-sheet-table">
                    <div className="ub-sheet-table-head">
                      <span>ETF 종목</span>
                      <span className="ub-sheet-table-head-mine">내 비중</span>
                      <span className="ub-sheet-table-head-theirs">이 회원</span>
                    </div>
                    {sheetRows(sheetPortfolio).map((r) => (
                      <div className="ub-sheet-row" key={r.name}>
                        <div><div className="ub-sheet-row-name">{r.name}</div><div className="ub-sheet-row-cat">{r.cat}</div></div>
                        <span className="ub-sheet-row-mine">{r.mine}</span>
                        <span className="ub-sheet-row-theirs" style={{ color: r.color }}><span className="ub-sheet-row-arrow">{r.arrow}</span>{r.theirs}</span>
                      </div>
                    ))}
                  </div>

                  <div className="ub-sheet-actions">
                    <button type="button" className="ub-sheet-close-btn" onClick={() => setSheetId(null)}>닫기</button>
                    <button type="button" className="ub-sheet-benchmark-btn">이 포트폴리오 벤치마킹</button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
