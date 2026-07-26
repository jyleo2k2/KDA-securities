import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type JSX,
  type UIEvent,
} from "react";

import taxCreditMissed from "../assets/main-home/tax-credit-missed.png";
import piggy from "../assets/main-home/piggy.webp";
import profileIcon from "../assets/main-home/profile-icon.webp";
import userPickPreview from "../assets/main-home/user-pick-preview.png";
import type {
  AggregationEvaluation,
  AssetClass,
  InvestmentProfileResponse,
  RiskProfile,
  StrategyPlanningReturnEvaluation,
  UserPensionPortfolio,
} from "../api/types";
import { getStrategyPlanningReturns } from "../api/client";
import { StatusBar } from "../components/StatusBar";
import { YeongeumiMascot } from "../components/YeongeumiMascot";
import { latestPortfolioDate } from "../ownerPensionPortfolio";
import "./MainHomeScreen.css";

interface MainHomeScreenProps {
  aggregation: AggregationEvaluation | null;
  displayName: string;
  error: string | null;
  investmentProfile: InvestmentProfileResponse | null;
  initialScrollTop?: number;
  loading: boolean;
  onOpenChat: () => void;
  onOpenPlanner: () => void;
  onOpenProfile: () => void;
  onOpenSlangi: () => void;
  onScrollPositionChange?: (scrollTop: number) => void;
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
  assetClass: AssetClass;
  label: string;
  percent: number;
  color: string;
}

interface HoldingDetail {
  accountName: string;
  amountKrw: string;
  holdingId: string;
  instrumentName: string;
}

const PROFILE_LABELS: Record<RiskProfile, string> = {
  stable: "안정형", stable_seeking: "안정추구형", risk_neutral: "위험중립형", active: "적극투자형", aggressive: "공격투자형",
};
const HOLDING_PIE_COLORS = ["#2f8f6b", "#3f7bc4", "#c98a2e", "#d9743f", "#7b5fc0", "#2fa3a3", "#8f9aa6"];
const HOLDING_PIE_MAX_SLICES = 6;
const HOLDING_PIE_LABEL_MIN_PERCENT = 10;
const PIE_SIZE = 174;
const PIE_CENTER = PIE_SIZE / 2;
const PIE_RADIUS = 78;
const PIE_INNER_RADIUS = 48;
const PIE_LABEL_RADIUS = 63;
const PIE_SELECT_OFFSET = 7;

function buildHoldingPieSlices(
  aggregation: AggregationEvaluation | null,
): HoldingSlice[] {
  return aggregation?.asset_class_totals
    .slice()
    .sort((left, right) => Number(right.weight_percent) - Number(left.weight_percent))
    .slice(0, HOLDING_PIE_MAX_SLICES)
    .map((item, index) => ({
      assetClass: item.asset_class,
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
        const labelPoint = polarPoint(midDeg, PIE_LABEL_RADIUS);
        const shape = slice.percent >= 99.999
          ? <circle cx={PIE_CENTER} cy={PIE_CENTER} r={PIE_RADIUS} fill={slice.color} />
          : <path d={donutSlicePath(startDeg, endDeg)} fill={slice.color} stroke="#fff" strokeWidth={2} strokeLinejoin="round" />;
        return (
          <g
            className="mhs-pie-slice"
            key={slice.label}
            role="button"
            tabIndex={0}
            aria-label={`${slice.label} ${slice.percent.toFixed(1)}%`}
            aria-pressed={selected}
            onClick={(event) => { event.stopPropagation(); onSelect(index); }}
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
            {slice.percent >= HOLDING_PIE_LABEL_MIN_PERCENT && (
              <text x={labelPoint.x} y={labelPoint.y} textAnchor="middle" dominantBaseline="central" fontSize={12} pointerEvents="none" style={{ fill: "#fff", stroke: "none" }}>
                {Math.round(slice.percent)}%
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

interface StrategyCard {
  strategyId: string;
  title: string;
  valueColor: string;
  desc: string;
  bg: string;
}

const STRATEGY_CARDS: StrategyCard[] = [
  { strategyId: "market_beta", title: "시장 전체 따라가기", valueColor: "#4FB6E6", desc: "많은 회사가 든 ETF로 주식시장 전체를 넓게 따라가요.", bg: "#EAF7FC" },
  { strategyId: "factor", title: "회사 특징 고르기", valueColor: "#24386E", desc: "좋은 회사·싼 가격·꾸준한 흐름 같은 특징을 살펴봐요.", bg: "#EAEDF3" },
  { strategyId: "thematic", title: "성장 분야 살펴보기", valueColor: "#F5871F", desc: "AI·반도체·바이오처럼 한 분야의 기회를 조금씩 살펴봐요.", bg: "#FFF3E6" },
  { strategyId: "top_down", title: "큰 경제 흐름 보기", valueColor: "#3B4148", desc: "금리·물가·경기를 보고 나라와 산업 비율을 살펴봐요.", bg: "#EEF0F1" },
  { strategyId: "bottom_up", title: "회사 하나씩 살펴보기", valueColor: "#1E9E5D", desc: "전문가가 회사를 골라 담는 펀드를 작은 비중으로 살펴봐요.", bg: "#E9F8EF" },
  { strategyId: "barbell", title: "성장·안전 나누기", valueColor: "#1E2124", desc: "성장할 돈과 채권·현금 같은 안전한 돈을 나눠 둬요.", bg: "#F5F5F5" },
  { strategyId: "volatility_managed", title: "가격 흔들림 줄이기", valueColor: "#9CA7AE", desc: "가격이 너무 크게 출렁이면 채권·현금 비율을 늘려요.", bg: "#F1F2F3" },
  { strategyId: "market_neutral", title: "시장 흔들림 줄이기", valueColor: "#7B4FC0", desc: "시장이 오르내려도 덜 흔들리게 만든 상품을 살펴봐요.", bg: "#F3EEFB" },
  { strategyId: "event_driven", title: "회사 큰 소식 보기", valueColor: "#B8860B", desc: "합병·분할처럼 회사에 큰 일이 생긴 뒤를 살펴봐요.", bg: "#FFF8DE" },
  { strategyId: "trend_global_macro", title: "세계 시장 흐름 보기", valueColor: "#2F6FE0", desc: "주식·채권 등 세계 시장의 큰 흐름을 함께 살펴봐요.", bg: "#EAF1FE" },
];

function strategyPlanningFootnote(
  planningReturn: StrategyPlanningReturnEvaluation | undefined,
): string {
  if (!planningReturn) return "장기 계산용 가정을 불러오는 중이에요.";
  return `장기 계산용 가정 · 대표 구성 전망 ${formatPlanningPercent(planningReturn.cma_weighted_return_percent)} · 여유 폭 ${formatPlanningPercent(planningReturn.uncertainty_discount_percent)}p`;
}

function formatPlanningPercent(value: string): string {
  const [whole, decimal = ""] = value.split(".");
  return `${whole}.${decimal.padEnd(2, "0").slice(0, 2)}%`;
}

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

function buildHoldingDetails(
  portfolio: UserPensionPortfolio | null,
  assetClass: AssetClass | null,
): HoldingDetail[] {
  if (!portfolio || !assetClass) return [];
  return portfolio.accounts
    .flatMap((account) => account.holdings
      .filter((holding) => holding.asset_class === assetClass)
      .map((holding) => ({
        accountName: account.account_name,
        amountKrw: holding.amount_krw,
        holdingId: `${account.account_id}:${holding.holding_id}`,
        instrumentName: holding.instrument_name,
      })))
    .sort((left, right) => Number(right.amountKrw) - Number(left.amountKrw));
}

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

export function MainHomeScreen({
  aggregation,
  displayName,
  error,
  investmentProfile,
  initialScrollTop = 0,
  loading,
  onOpenChat,
  onOpenPlanner,
  onOpenProfile,
  onOpenSlangi,
  onScrollPositionChange,
  onOpenStrategyExplore,
  onOpenUserPick,
  portfolio,
}: MainHomeScreenProps): JSX.Element {
  const [infoOpen, setInfoOpen] = useState(false);
  const [selectedHolding, setSelectedHolding] = useState<number | null>(null);
  const [strategyPlanningReturns, setStrategyPlanningReturns] = useState<StrategyPlanningReturnEvaluation[] | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const allocationSlices: AllocationSlice[] = aggregation?.asset_class_totals
    .slice(0, 4)
    .map((item, index) => ({
      label: ASSET_LABELS[item.asset_class] ?? "기타 자산",
      percent: `${item.weight_percent}%`,
      color: ALLOCATION_COLORS[index],
    })) ?? [];
  const holdingSlices = buildHoldingPieSlices(aggregation);
  const selectedHoldingSlice = selectedHolding === null
    ? null
    : holdingSlices[selectedHolding] ?? null;
  const selectedHoldingDetails = buildHoldingDetails(
    portfolio,
    selectedHoldingSlice?.assetClass ?? null,
  );
  const toggleHolding = (index: number) => setSelectedHolding((current) => (current === index ? null : index));
  const handleBodyScroll = (event: UIEvent<HTMLDivElement>) => {
    onScrollPositionChange?.(event.currentTarget.scrollTop);
  };
  useLayoutEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = initialScrollTop;
  }, [initialScrollTop]);
  useEffect(() => {
    if (selectedHolding === null) return;
    const clear = () => setSelectedHolding(null);
    document.addEventListener("click", clear);
    return () => document.removeEventListener("click", clear);
  }, [selectedHolding]);
  useEffect(() => {
    let active = true;
    getStrategyPlanningReturns()
      .then((returns) => { if (active) setStrategyPlanningReturns(returns); })
      .catch(() => { if (active) setStrategyPlanningReturns([]); });
    return () => { active = false; };
  }, []);
  const totalBalance = aggregation ? formatKrw(aggregation.total_amount_krw) : "-";
  const asOfDate = portfolio ? latestPortfolioDate(portfolio) : null;

  return (
    <main className="app-phone-stage mhs-stage">
    <section className="app-phone-frame mhs-phone" aria-label="연금 도우미 메인 홈">
    <div className="mhs-page">
      <StatusBar />

      <div className="mhs-header">
        <span className="mhs-header-dot" />
        <span className="mhs-header-title">연금 <span className="mhs-header-title-accent">도우미</span></span>
        <button type="button" className="mhs-profile-button" onClick={onOpenProfile} aria-label="프로필 열기">
          <img src={profileIcon} alt="" className="mhs-profile-icon" />
        </button>
      </div>

      <div className="mhs-body" ref={bodyRef} onScroll={handleBodyScroll}>
        <button type="button" className="mhs-greeting-card mhs-greeting-card-button" onClick={onOpenSlangi} aria-label="연그미와 놀기 열기">
          <div className="mhs-greeting-copy">
            <p className="mhs-greeting-title">슬랑이를 <span className="mhs-greeting-title-accent">만져 보세요!</span></p>
            <p className="mhs-greeting-sub">톡톡 두드리면 오늘의 저축 팁을 알려드려요</p>
          </div>
          <img src={piggy} alt="슬랑이" className="mhs-greeting-img" />
        </button>
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
              <YeongeumiMascot className="mhs-pie-mascot" />
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
                  className={`mhs-allocation-item${selectable ? " is-selectable" : ""}`}
                  key={slice.label}
                  role={selectable ? "button" : undefined}
                  tabIndex={selectable ? 0 : undefined}
                  onClick={selectable ? (event) => { event.stopPropagation(); toggleHolding(slice.index as number); } : undefined}
                  onKeyDown={selectable ? (event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      event.stopPropagation();
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

          <section className="mhs-portfolio-block" aria-labelledby="mhs-portfolio-heading">
            <div className="mhs-portfolio-heading-row">
              <h3 className="mhs-portfolio-heading" id="mhs-portfolio-heading">자산별 투자 종목</h3>
              <button
                type="button"
                className="mhs-portfolio-info-icon"
                onClick={() => setInfoOpen(true)}
                aria-label="포트폴리오 분류 기준 보기"
              >
                ⓘ
              </button>
            </div>
            <p className="mhs-portfolio-guide">
              위 원그래프나 자산 비중을 누르면 실제 보유 종목을 확인할 수 있어요.
            </p>
            {selectedHoldingSlice ? (
              <div className="mhs-holding-detail" aria-live="polite">
                <div className="mhs-holding-detail-heading">
                  <span>
                    <i style={{ background: selectedHoldingSlice.color }} />
                    {selectedHoldingSlice.label}
                  </span>
                  <strong>{selectedHoldingSlice.percent.toFixed(1)}%</strong>
                </div>
                {selectedHoldingDetails.length > 0 ? (
                  <ul className="mhs-holding-list">
                    {selectedHoldingDetails.map((holding) => (
                      <li key={holding.holdingId}>
                        <span>
                          <strong>{holding.instrumentName}</strong>
                          <small>{holding.accountName}</small>
                        </span>
                        <b>{formatKrw(holding.amountKrw)}</b>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mhs-holding-empty">이 자산군의 상세 종목 정보가 아직 연결되지 않았어요.</p>
                )}
              </div>
            ) : (
              <button
                type="button"
                className="mhs-portfolio-select-prompt"
                onClick={(event) => {
                  event.stopPropagation();
                  if (holdingSlices.length > 0) setSelectedHolding(0);
                }}
                disabled={holdingSlices.length === 0}
              >
                {holdingSlices.length > 0 ? "가장 큰 자산의 보유 종목 먼저 보기" : "연금계좌를 연결하면 보유 종목을 보여드려요"}
              </button>
            )}
          </section>

          <div className="mhs-summary-subcard">
            <span className="mhs-summary-label">내 포트폴리오 한 줄 진단</span>
            <p className="mhs-summary-sub-label">현재 자산 비중 기준</p>
            <p className="mhs-summary-text">{buildPortfolioOneLineSummary(aggregation)}</p>
            <div className="mhs-summary-cta-row">
              <button type="button" className="mhs-summary-cta mhs-summary-cta-button" onClick={onOpenChat}>내 포트폴리오 자세히 진단받기 <span className="mhs-summary-cta-chevron">›</span></button>
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
          {STRATEGY_CARDS.map((card) => {
            const planningReturn = strategyPlanningReturns?.find(
              (item) => item.strategy_id === card.strategyId,
            );
            const value = planningReturn
              ? formatPlanningPercent(planningReturn.net_planning_return_percent)
              : strategyPlanningReturns === null ? "계산 중…" : "확인 필요";
            return (
            <button
              type="button"
              className="mhs-strategy-card mhs-strategy-card-button"
              style={{ background: card.bg }}
              key={card.title}
              onClick={onOpenStrategyExplore}
              aria-label={`${card.title} 전략 상세 보기`}
            >
              <span className="mhs-strategy-card-title">{card.title}</span>
              <p className="mhs-strategy-card-value" style={{ color: card.valueColor }}>{value}</p>
              <p className="mhs-strategy-card-desc">{card.desc}</p>
              <p className="mhs-strategy-card-footnote">{strategyPlanningFootnote(planningReturn)}</p>
            </button>
            );
          })}
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
          <div className="mhs-sheet-backdrop" onClick={() => setInfoOpen(false)} aria-hidden="true" />
          <div className="mhs-sheet">
            <div className="mhs-sheet-header">
              <span className="mhs-sheet-title">포트폴리오</span>
              <button
                type="button"
                className="mhs-sheet-close"
                onClick={() => setInfoOpen(false)}
                aria-label="포트폴리오 안내 닫기"
              >
                ✕
              </button>
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
