import { useState, type JSX } from "react";

import taxCreditMissed from "../assets/main-home/tax-credit-missed.png";
import piggy from "../assets/main-home/piggy.webp";
import profileIcon from "../assets/main-home/profile-icon.webp";
import userPickPreview from "../assets/main-home/user-pick-preview.png";
import type {
  AggregationEvaluation,
  InvestmentProfileResponse,
  RiskProfile,
  UserPensionPortfolio,
} from "../api/types";
import { latestPortfolioDate } from "../ownerPensionPortfolio";
import "./MainHomeScreen.css";

interface MainHomeScreenProps {
  aggregation: AggregationEvaluation | null;
  displayName: string;
  error: string | null;
  investmentProfile: InvestmentProfileResponse | null;
  loading: boolean;
  onOpenChat: () => void;
  onOpenPlanner: () => void;
  onOpenProfile: () => void;
  onOpenStrategyExplore: () => void;
  onOpenUserPick: () => void;
  portfolio: UserPensionPortfolio | null;
}

interface AllocationSlice {
  label: string;
  percent: string;
  color: string;
}

interface HoldingSlice {
  label: string;
  percent: number;
  color: string;
}

const PROFILE_LABELS: Record<RiskProfile, string> = {
  stable: "안정형", stable_seeking: "안정추구형", risk_neutral: "위험중립형", active: "적극투자형", aggressive: "공격투자형",
};
const HOLDING_PIE_COLORS = ["#2f8f6b", "#3f7bc4", "#c98a2e", "#d9743f", "#7b5fc0", "#2fa3a3", "#8f9aa6"];
const HOLDING_PIE_MAX_SLICES = 6;
const PIE_SIZE = 174;
const PIE_CENTER = PIE_SIZE / 2;
const PIE_RADIUS = 78;
const PIE_INNER_RADIUS = 48;
const PIE_SELECT_OFFSET = 7;

function buildHoldingPieSlices(
  aggregation: AggregationEvaluation | null,
): HoldingSlice[] {
  return aggregation?.asset_class_totals
    .slice()
    .sort((left, right) => Number(right.weight_percent) - Number(left.weight_percent))
    .slice(0, HOLDING_PIE_MAX_SLICES)
    .map((item, index) => ({
      label: ASSET_LABELS[item.asset_class] ?? "기타 자산",
      percent: Number(item.weight_percent),
      color: HOLDING_PIE_COLORS[index % HOLDING_PIE_COLORS.length],
    })) ?? [];
}

function polarPoint(centerDeg: number, radius: number): { x: number; y: number } {
  const angleRad = ((centerDeg - 90) * Math.PI) / 180;
  return { x: PIE_CENTER + radius * Math.cos(angleRad), y: PIE_CENTER + radius * Math.sin(angleRad) };
}

function donutSlicePath(startDeg: number, endDeg: number): string {
  const outerStart = polarPoint(startDeg, PIE_RADIUS);
  const outerEnd = polarPoint(endDeg, PIE_RADIUS);
  const innerEnd = polarPoint(endDeg, PIE_INNER_RADIUS);
  const innerStart = polarPoint(startDeg, PIE_INNER_RADIUS);
  const largeArcFlag = endDeg - startDeg > 180 ? 1 : 0;
  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${PIE_RADIUS} ${PIE_RADIUS} 0 ${largeArcFlag} 1 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerEnd.x} ${innerEnd.y}`,
    `A ${PIE_INNER_RADIUS} ${PIE_INNER_RADIUS} 0 ${largeArcFlag} 0 ${innerStart.x} ${innerStart.y}`,
    "Z",
  ].join(" ");
}

function HoldingPie({ slices, selectedIndex, onSelect }: {
  slices: HoldingSlice[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}): JSX.Element {
  let cumulativePercent = 0;
  const centerLabel = selectedIndex === null ? "총자산" : slices[selectedIndex]?.label ?? "총자산";
  const centerValue = selectedIndex === null ? "100%" : `${slices[selectedIndex]?.percent.toFixed(1)}%`;
  return (
    <svg width={PIE_SIZE} height={PIE_SIZE} viewBox={`0 0 ${PIE_SIZE} ${PIE_SIZE}`} role="img" aria-label="총 연금 자산 자산군 비중">
      {slices.map((slice, index) => {
        const startDeg = cumulativePercent * 3.6;
        const endDeg = (cumulativePercent + slice.percent) * 3.6;
        const midDeg = (startDeg + endDeg) / 2;
        cumulativePercent += slice.percent;
        const selected = selectedIndex === index;
        const dimmed = selectedIndex !== null && !selected;
        const shift = selected ? polarPoint(midDeg, PIE_SELECT_OFFSET) : { x: PIE_CENTER, y: PIE_CENTER };
        const shape = slice.percent >= 99.999
          ? <circle cx={PIE_CENTER} cy={PIE_CENTER} r={PIE_RADIUS} fill={slice.color} />
          : <path d={donutSlicePath(startDeg, endDeg)} fill={slice.color} stroke="#fff" strokeWidth={2} strokeLinejoin="round" />;
        return (
          <g
            key={slice.label}
            role="button"
            tabIndex={0}
            aria-label={`${slice.label} ${slice.percent.toFixed(1)}%`}
            aria-pressed={selected}
            onClick={() => onSelect(index)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(index);
              }
            }}
            style={{
              cursor: "pointer",
              opacity: dimmed ? 0.32 : 1,
              transform: `translate(${shift.x - PIE_CENTER}px, ${shift.y - PIE_CENTER}px)`,
              transition: "opacity 140ms ease, transform 160ms ease",
            }}
          >
            {shape}
          </g>
        );
      })}
      <text x={PIE_CENTER} y={PIE_CENTER - 6} textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={600} fill="#8A9691">
        {centerLabel}
      </text>
      <text x={PIE_CENTER} y={PIE_CENTER + 12} textAnchor="middle" dominantBaseline="central" fontSize={18} fontWeight={800} fill="#333">
        {centerValue}
      </text>
    </svg>
  );
}

interface StrategyCard {
  title: string;
  value: string;
  valueColor: string;
  desc: string;
  warning?: string;
  footnote: string;
  bg: string;
}

const STRATEGY_CARDS: StrategyCard[] = [
  { title: "시장 베타", value: "6.75%", valueColor: "#4FB6E6", desc: "광범위지수 ETF로 시장 전체 흐름을 따라가는 코어 전략이에요.", footnote: "계획수익률 · 글로벌주식 CMA 7.0% · 할인 0.25%p", bg: "#EAF7FC" },
  { title: "팩터", value: "6.60%", valueColor: "#24386E", desc: "가치·퀄리티·모멘텀 등 검증된 요인을 규칙 기반 ETF로 담아요.", footnote: "계획수익률 · 글로벌주식 CMA 7.0% · 할인 0.40%p", bg: "#EAEDF3" },
  { title: "테마", value: "6.00%", valueColor: "#F5871F", desc: "AI·반도체·바이오 등 성장 테마를 분산해 담아요.", footnote: "계획수익률 · 글로벌주식 CMA 7.0% · 할인 1.00%p", bg: "#FFF3E6" },
  { title: "탑다운", value: "산정 전", valueColor: "#3B4148", desc: "거시 흐름에 따라 국가·지역·산업·채권 비중을 조절해요.", warning: "※ 지역·자산 비중 확정 후 계산해요.", footnote: "실제 구성 가중 CMA · 할인 0.75%p", bg: "#EEF0F1" },
  { title: "바텀업", value: "6.25%", valueColor: "#1E9E5D", desc: "기업과 산업을 분석해 연금 적격 액티브 ETF를 선별해요.", footnote: "계획수익률 · 지역별 주식 CMA · 할인 0.75%p", bg: "#E9F8EF" },
  { title: "바벨", value: "산정 전", valueColor: "#1E2124", desc: "성장자산과 단기채·현금성 자산을 양쪽에 배치해요.", warning: "※ 성장·방어 비중 확정 후 계산해요.", footnote: "실제 구성 가중 CMA · 구성별 할인", bg: "#F5F5F5" },
  { title: "변동성 관리", value: "산정 전", valueColor: "#9CA7AE", desc: "저변동 ETF와 채권으로 목표 변동성에 맞춰 비중을 조절해요.", warning: "※ 목표 변동성에 따른 비중 확정 후 계산해요.", footnote: "실제 구성 가중 CMA · 구성별 할인", bg: "#F1F2F3" },
  { title: "롱숏·시장중립", value: "산정 전", valueColor: "#7B4FC0", desc: "매수·매도를 함께 활용하는 적격 시장중립 상품을 찾아요.", warning: "※ 연금 적격 상품과 별도 CMA가 아직 확정되지 않았어요.", footnote: "별도 CMA 필요 · 잠정 할인 0.75%p", bg: "#F3EEFB" },
  { title: "이벤트드리븐", value: "산정 전", valueColor: "#B8860B", desc: "합병·분할·자사주 등 공시된 기업행동에서 후보를 살펴봐요.", warning: "※ 연금 적격 상품과 별도 CMA가 아직 확정되지 않았어요.", footnote: "별도 CMA 필요 · 잠정 할인 0.75%p", bg: "#FFF8DE" },
  { title: "추세추종·글로벌 매크로", value: "5.65%", valueColor: "#2F6FE0", desc: "멀티에셋 ETF로 글로벌 추세를 규칙 기반으로 따라가요.", footnote: "계획수익률 · 글로벌 60/40 CMA 6.4% · 할인 0.75%p", bg: "#EAF1FE" },
];

const PORTFOLIO_INFO_CATEGORIES: Array<{ title: string; desc: string }> = [
  { title: "주식형", desc: "ETF 중 주식을 투자하는 상품" },
  { title: "보험", desc: "보험에서 가입한 연금 상품" },
  { title: "은행", desc: "은행에서 가입한 연금 상품" },
  { title: "원자재·외화형", desc: "ETF 중 원자재, 금, 달러 등에 투자하는 상품" },
  { title: "부동산", desc: "ETF 중 리츠 상품에 투자하는 상품" },
  { title: "채권형", desc: "ETF 중 채권을 투자하는 상품" },
  { title: "현금성", desc: "예수금 등 현금 자산" },
];

const ASSET_LABELS: Record<string, string> = { cash: "현금성", deposit: "원리금보장", bond: "채권", domestic_equity: "국내주식", global_equity: "글로벌주식", alternative: "대체자산", eligible_tdf: "적격 TDF", default_option: "디폴트옵션" };
const ALLOCATION_COLORS = ["#18A860", "#35B877", "#6ECFA0", "#2E8B57"];
const formatKrw = (amount: string) => `${Math.round(Number(amount)).toLocaleString("ko-KR")}원`;

function buildPortfolioOneLineSummary(
  aggregation: AggregationEvaluation | null,
): string {
  if (!aggregation || aggregation.asset_class_totals.length === 0) {
    return "포트폴리오 구성을 불러오면 가장 큰 자산 비중을 알려드려요.";
  }
  const dominant = aggregation.asset_class_totals.reduce((largest, current) => (
    Number(current.weight_percent) > Number(largest.weight_percent)
      ? current
      : largest
  ));
  const dominantLabel = ASSET_LABELS[dominant.asset_class] ?? "기타 자산";
  return `${dominantLabel} 비중이 ${dominant.weight_percent}%로 가장 높아요.`;
}

export function MainHomeScreen({ aggregation, displayName, error, investmentProfile, loading, onOpenChat, onOpenPlanner, onOpenProfile, onOpenStrategyExplore, onOpenUserPick, portfolio }: MainHomeScreenProps): JSX.Element {
  const [infoOpen, setInfoOpen] = useState(false);
  const [selectedHolding, setSelectedHolding] = useState<number | null>(null);
  const allocationSlices: AllocationSlice[] = aggregation?.asset_class_totals
    .slice(0, 4)
    .map((item, index) => ({
      label: ASSET_LABELS[item.asset_class] ?? "기타 자산",
      percent: `${item.weight_percent}%`,
      color: ALLOCATION_COLORS[index],
    })) ?? [];
  const holdingSlices = buildHoldingPieSlices(aggregation);
  const activeHolding = selectedHolding !== null ? holdingSlices[selectedHolding] ?? null : null;
  const toggleHolding = (index: number) => setSelectedHolding((current) => (current === index ? null : index));
  const totalBalance = aggregation ? formatKrw(aggregation.total_amount_krw) : "-";
  const asOfDate = portfolio ? latestPortfolioDate(portfolio) : null;

  return (
    <main className="mhs-stage">
    <section className="mhs-phone" aria-label="연금 도우미 메인 홈">
    <div className="mhs-page">
      <div className="mhs-statusbar">
        <span className="mhs-statusbar-time">9:41</span>
        <span className="mhs-statusbar-icons" aria-hidden="true">● ● ▰</span>
      </div>

      <div className="mhs-header">
        <span className="mhs-header-dot" />
        <span className="mhs-header-title">연금 <span className="mhs-header-title-accent">도우미</span></span>
        <button type="button" className="mhs-profile-button" onClick={onOpenProfile} aria-label="프로필 열기">
          <img src={profileIcon} alt="" className="mhs-profile-icon" />
        </button>
      </div>

      <div className="mhs-body">
        <div className="mhs-greeting-card">
          <div className="mhs-greeting-copy">
            <p className="mhs-greeting-title">슬랑이를 <span className="mhs-greeting-title-accent">만져 보세요!</span></p>
            <p className="mhs-greeting-sub">톡톡 두드리면 오늘의 저축 팁을 알려드려요</p>
          </div>
          <img src={piggy} alt="송향이" className="mhs-greeting-img" />
        </div>
        {investmentProfile?.assessment && <p className="mhs-greeting-sub">저장 투자성향 · {PROFILE_LABELS[investmentProfile.assessment.risk_profile]} · {investmentProfile.assessment.assessed_on} 진단{investmentProfile.assessment.is_expired ? " · 만료" : ""}</p>}
        <h2 className="mhs-section-title">내 연금 <span className="mhs-section-title-gold">자산</span></h2>

        <div className="mhs-asset-card">
          <p className="mhs-asset-label">총 연금 자산</p>
          <p className="mhs-asset-total">{loading ? "불러오는 중…" : totalBalance}</p>
          <p className="mhs-asset-gain">{error ?? (asOfDate ? `${displayName}님 · ${asOfDate} 기준` : "연금 데이터를 확인해 주세요.")}</p>

          <div className="mhs-pie-wrap">
            {holdingSlices.length > 0 ? (
              <HoldingPie slices={holdingSlices} selectedIndex={selectedHolding} onSelect={toggleHolding} />
            ) : (
              <div className="mhs-pie-empty" style={{ background: "#EEF0F1" }} />
            )}
          </div>

          <div className="mhs-allocation-grid">
            {(holdingSlices.length > 0
              ? holdingSlices.map((slice, index) => ({ label: slice.label, percent: `${slice.percent.toFixed(1)}%`, color: slice.color, index }))
              : allocationSlices.map((slice) => ({ ...slice, index: null as number | null }))
            ).map((slice) => {
              const selectable = slice.index !== null;
              const active = selectable && slice.index === selectedHolding;
              const dim = selectable && selectedHolding !== null && !active;
              return (
                <span
                  className="mhs-allocation-item"
                  key={slice.label}
                  role={selectable ? "button" : undefined}
                  tabIndex={selectable ? 0 : undefined}
                  onClick={selectable ? () => toggleHolding(slice.index as number) : undefined}
                  onKeyDown={selectable ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      toggleHolding(slice.index as number);
                    }
                  } : undefined}
                  style={selectable ? { cursor: "pointer", opacity: dim ? 0.4 : 1, fontWeight: active ? 900 : undefined } : undefined}
                >
                  <span className="mhs-allocation-dot" style={{ background: slice.color }} />
                  <span className="mhs-allocation-label">{slice.label}</span>
                  <span className="mhs-allocation-percent">{slice.percent}</span>
                </span>
              );
            })}
          </div>

          {holdingSlices.length > 0 && (
            <p className="mhs-asset-gain" style={{ marginTop: 12, textAlign: "center" }} aria-live="polite">
              {activeHolding
                ? `${activeHolding.label} · 전체 자산의 ${activeHolding.percent.toFixed(1)}%예요.`
                : "조각을 누르면 해당 자산군의 비중을 자세히 볼 수 있어요."}
            </p>
          )}

          <div className="mhs-portfolio-block">
            <span className="mhs-portfolio-heading">
              포트폴리오{" "}
              <span className="mhs-portfolio-info-icon" onClick={() => setInfoOpen(true)}>
                ⓘ
              </span>
            </span>
            <div className="mhs-portfolio-bar">
              <span className="mhs-portfolio-bar-equity" />
              <span className="mhs-portfolio-bar-bond" />
            </div>
            <div className="mhs-portfolio-legend">
              <span className="mhs-portfolio-legend-item">
                <span className="mhs-portfolio-legend-swatch mhs-swatch-equity" />
                {allocationSlices[0]?.label ?? "-"} <span className="mhs-portfolio-legend-percent">{allocationSlices[0]?.percent ?? "-"}</span>
              </span>
              <span className="mhs-portfolio-legend-item">
                <span className="mhs-portfolio-legend-swatch mhs-swatch-bond" />
                {allocationSlices[1]?.label ?? "-"} <span className="mhs-portfolio-legend-percent">{allocationSlices[1]?.percent ?? "-"}</span>
              </span>
            </div>
          </div>

          <div className="mhs-summary-subcard">
            <span className="mhs-summary-label">한 줄 요약</span>
            <p className="mhs-summary-sub-label">포트폴리오 구성</p>
            <p className="mhs-summary-text">{buildPortfolioOneLineSummary(aggregation)}</p>
            <div className="mhs-summary-cta-row">
              <button type="button" className="mhs-summary-cta mhs-summary-cta-button" onClick={onOpenChat}>자세히 진단받기 <span className="mhs-summary-cta-chevron">›</span></button>
            </div>
          </div>
        </div>

        <h2 className="mhs-section-title">세액공제</h2>
        <div className="mhs-tax-card">
          <span className="mhs-tax-icon-wrap">
            <img src={taxCreditMissed} alt="놓친 세액공제액 찾기" className="mhs-tax-icon" />
          </span>
          <div className="mhs-tax-copy">
            <p className="mhs-tax-title">세액공제 준비, 지금 몇 <span className="mhs-tax-title-accent">%</span>?</p>
            <p className="mhs-tax-sub">지금 놓치고 있는 세액공제액이 얼마인지 확인해 보세요.</p>
            <button type="button" className="mhs-tax-button" onClick={onOpenPlanner}>완료율 확인하기 <span>→</span></button>
          </div>
        </div>

        <div className="mhs-strategy-heading-row">
          <h2 className="mhs-section-title mhs-section-title-tight">
            전략 설명<br />
            <span className="mhs-section-title-gold">전략별 계획수익률</span>
          </h2>
          <button type="button" className="mhs-strategy-more" onClick={onOpenStrategyExplore}>시나리오·더보기 +</button>
        </div>

        <div className="mhs-strategy-scroll">
          {STRATEGY_CARDS.map((card) => (
            <button
              type="button"
              className="mhs-strategy-card mhs-strategy-card-button"
              style={{ background: card.bg }}
              key={card.title}
              onClick={onOpenStrategyExplore}
              aria-label={`${card.title} 전략 상세 보기`}
            >
              <span className="mhs-strategy-card-title">{card.title}</span>
              <p className="mhs-strategy-card-value" style={{ color: card.valueColor }}>{card.value}</p>
              <p className="mhs-strategy-card-desc">{card.desc}</p>
              {card.warning && <p className="mhs-strategy-card-warning">{card.warning}</p>}
              <p className="mhs-strategy-card-footnote">{card.footnote}</p>
            </button>
          ))}
        </div>
        <p className="mhs-strategy-disclaimer">계획수익률은 운용 가정이며 미래 수익을 보장하지 않아요.</p>

        <h2 className="mhs-section-title">
          이용자 <span className="mhs-section-title-accent">Pick</span> <span className="mhs-section-title-note">(다른 사람 포트폴리오 벤치마킹 가능)</span>
        </h2>
        <button type="button" className="mhs-userpick-card mhs-userpick-card-button" onClick={onOpenUserPick}>
          <img src={userPickPreview} alt="이용자 포트폴리오 미리보기" className="mhs-userpick-img" />
          <div className="mhs-userpick-overlay">
            <p className="mhs-userpick-text">동일 업종 및 다른 이용자의<br />포트폴리오를 <span className="mhs-userpick-text-accent">만나보세요!</span></p>
            <span className="mhs-userpick-cta">지금 둘러보기 <span className="mhs-userpick-cta-chevron">›</span></span>
          </div>
        </button>
      </div>

      {infoOpen && (
        <div className="mhs-sheet-overlay">
          <div className="mhs-sheet-backdrop" onClick={() => setInfoOpen(false)} />
          <div className="mhs-sheet">
            <div className="mhs-sheet-header">
              <span className="mhs-sheet-title">포트폴리오</span>
              <span className="mhs-sheet-close" onClick={() => setInfoOpen(false)}>✕</span>
            </div>
            <div className="mhs-sheet-body">
              <ul className="mhs-sheet-list">
                <li className="mhs-sheet-item"><span className="mhs-sheet-bullet">•</span>ETF 상품에 대해 분류해서 보여드려요.</li>
                <li className="mhs-sheet-item"><span className="mhs-sheet-bullet">•</span>ETF가 아닌 종목은 모두 '기타' 항목에 포함돼요.</li>
                <li className="mhs-sheet-item"><span className="mhs-sheet-bullet">•</span>만약 보험사나 은행 계좌를 통해 투자하신 종목이 있다면 각각 '보험', '은행'으로 분류해요.</li>
                <li className="mhs-sheet-item mhs-sheet-item-block">
                  <span className="mhs-sheet-item-row"><span className="mhs-sheet-bullet">•</span>포트폴리오는 아래 기준으로 분류해서 보여드려요.</span>
                  <div className="mhs-sheet-categories">
                    {PORTFOLIO_INFO_CATEGORIES.map((category) => (
                      <div key={category.title}>
                        <p className="mhs-sheet-category-title">◦ {category.title}</p>
                        <p className="mhs-sheet-category-desc">{category.desc}</p>
                      </div>
                    ))}
                  </div>
                </li>
                <li className="mhs-sheet-item"><span className="mhs-sheet-bullet">•</span>ETF가 아닌 펀드상품과 리츠상품도 곧 분류해드릴게요.</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      <div className="mhs-tab-toggle">
        <span className="mhs-tab-toggle-item mhs-tab-toggle-item-active">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 10l9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" />
          </svg>
          홈 화면
        </span>
        <span className="mhs-tab-toggle-item" onClick={onOpenChat}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#A0AAA4" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.6-.8L3 21l1.8-5.4a8.5 8.5 0 0 1-.8-3.6A8.38 8.38 0 0 1 12.5 3 8.38 8.38 0 0 1 21 11.5z" />
          </svg>
          챗봇
        </span>
      </div>
    </div>
    </section>
    </main>
  );
}
