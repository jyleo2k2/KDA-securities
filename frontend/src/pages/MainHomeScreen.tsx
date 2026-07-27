import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type JSX,
  type PointerEvent as ReactPointerEvent,
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
  onRequestPortfolioDiagnosis: () => void;
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
const STRATEGY_PLANNING_RETURN_RETRY_MS = 3_000;
const PROMO_DRAG_START_THRESHOLD_PX = 5;
const PROMO_DRAG_THRESHOLD_PX = 40;
const PROMO_COUNT = 2;
const PROMO_TRANSITION_MS = 380;
const STRATEGY_DRAG_THRESHOLD_PX = 5;

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
  { strategyId: "market_beta", title: "시장 베타 전략", valueColor: "#4FB6E6", desc: "시장 수익률을 포트폴리오의 기준 수익원으로 활용하는 장기 분산 전략입니다.", bg: "#EAF7FC" },
  { strategyId: "factor", title: "팩터 전략", valueColor: "#24386E", desc: "재무 건전성·가격 수준·추세 등 기업 특성을 기준으로 ETF를 선택하는 전략입니다.", bg: "#EAEDF3" },
  { strategyId: "thematic", title: "테마 전략", valueColor: "#F5871F", desc: "산업 구조 변화가 예상되는 분야에 집중해 성장 기회를 찾는 위성 전략입니다.", bg: "#FFF3E6" },
  { strategyId: "top_down", title: "탑다운 전략", valueColor: "#3B4148", desc: "금리·물가·경기 같은 거시 환경을 분석해 국가·산업·자산군 비중을 조정합니다.", bg: "#EEF0F1" },
  { strategyId: "bottom_up", title: "바텀업 전략", valueColor: "#1E9E5D", desc: "개별 기업의 경쟁력·재무상태·성장성을 분석해 투자 대상을 선별하는 전략입니다.", bg: "#E9F8EF" },
  { strategyId: "barbell", title: "바벨 전략", valueColor: "#1E2124", desc: "성장자산과 단기채·현금성자산을 함께 배분해 상·하방 위험에 대응합니다.", bg: "#F5F5F5" },
  { strategyId: "volatility_managed", title: "변동성 관리 전략", valueColor: "#9CA7AE", desc: "목표 변동성에 맞춰 주식·채권·현금성자산 비중을 조절하는 위험관리 전략입니다.", bg: "#F1F2F3" },
  { strategyId: "market_neutral", title: "롱숏·시장중립 전략", valueColor: "#7B4FC0", desc: "매수와 헤지 포지션을 함께 활용해 시장 방향성 노출을 낮추는 전략입니다.", bg: "#F3EEFB" },
  { strategyId: "event_driven", title: "이벤트드리븐 전략", valueColor: "#B8860B", desc: "합병·분할·자사주 매입 등 기업 이벤트가 가격에 반영되는 과정을 활용합니다.", bg: "#FFF8DE" },
  { strategyId: "trend_global_macro", title: "추세추종·글로벌 매크로 전략", valueColor: "#2F6FE0", desc: "자산 가격 추세와 글로벌 거시 환경을 규칙에 따라 활용하는 멀티에셋 전략입니다.", bg: "#EAF1FE" },
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
  onRequestPortfolioDiagnosis,
  onOpenSlangi,
  onScrollPositionChange,
  onOpenStrategyExplore,
  onOpenUserPick,
  portfolio,
}: MainHomeScreenProps): JSX.Element {
  const [infoOpen, setInfoOpen] = useState(false);
  const [activePromo, setActivePromo] = useState(0);
  const [promoTimerKey, setPromoTimerKey] = useState(0);
  // 마지막 카드에서 첫 카드로 갈 때도 오른쪽으로 흐르게 하려고 트랙 위치를 인덱스와 분리한다.
  // 복제 슬라이드(PROMO_COUNT)까지 이동한 뒤 전환이 끝나면 애니메이션 없이 0으로 되돌린다.
  const [promoOffset, setPromoOffset] = useState(0);
  const [isPromoSnapping, setIsPromoSnapping] = useState(false);
  const [selectedHolding, setSelectedHolding] = useState<number | null>(null);
  const [strategyPlanningReturns, setStrategyPlanningReturns] = useState<StrategyPlanningReturnEvaluation[] | null>(null);
  const [isPromoDragging, setIsPromoDragging] = useState(false);
  const [isStrategyDragging, setIsStrategyDragging] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const promoTouchStartX = useRef<number | null>(null);
  const promoPointerDrag = useRef<{
    moved: boolean;
    pointerId: number;
    startX: number;
  } | null>(null);
  const strategyDrag = useRef<{
    moved: boolean;
    pointerId: number;
    startScrollLeft: number;
    startX: number;
  } | null>(null);
  const suppressStrategyClick = useRef(false);
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
  const selectPromo = (index: number) => {
    setActivePromo(index);
    setPromoOffset(index);
    setIsPromoSnapping(false);
    setPromoTimerKey((current) => current + 1);
  };
  const movePromo = (direction: -1 | 1) => {
    const next = (activePromo + direction + PROMO_COUNT) % PROMO_COUNT;
    setActivePromo(next);
    setIsPromoSnapping(false);
    // 끝에서 앞으로 넘어갈 때는 복제 슬라이드까지 계속 오른쪽으로 민다.
    // 반대 방향으로 되감기면 뒤로 튕기는 모션이 보이기 때문이다.
    setPromoOffset(direction === 1 && next === 0 ? PROMO_COUNT : next);
    setPromoTimerKey((current) => current + 1);
  };
  const handlePromoPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    promoPointerDrag.current = {
      moved: false,
      pointerId: event.pointerId,
      startX: event.clientX,
    };
  };
  const handlePromoPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = promoPointerDrag.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.startX;
    if (!drag.moved && Math.abs(deltaX) < PROMO_DRAG_START_THRESHOLD_PX) return;
    if (!drag.moved) {
      drag.moved = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      setIsPromoDragging(true);
    }
    event.preventDefault();
  };
  const finishPromoPointerDrag = (
    event: ReactPointerEvent<HTMLElement>,
    cancelled = false,
  ) => {
    const drag = promoPointerDrag.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    promoPointerDrag.current = null;
    setIsPromoDragging(false);
    const deltaX = event.clientX - drag.startX;
    if (cancelled || !drag.moved || Math.abs(deltaX) < PROMO_DRAG_THRESHOLD_PX) return;
    movePromo(deltaX < 0 ? 1 : -1);
  };
  const handleStrategyPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    strategyDrag.current = {
      moved: false,
      pointerId: event.pointerId,
      startScrollLeft: event.currentTarget.scrollLeft,
      startX: event.clientX,
    };
    suppressStrategyClick.current = false;
  };
  const handleStrategyPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = strategyDrag.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.startX;
    if (!drag.moved && Math.abs(deltaX) < STRATEGY_DRAG_THRESHOLD_PX) return;
    if (!drag.moved) {
      drag.moved = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      setIsStrategyDragging(true);
    }
    event.preventDefault();
    event.currentTarget.scrollLeft = drag.startScrollLeft - deltaX;
  };
  const finishStrategyDrag = (
    event: ReactPointerEvent<HTMLDivElement>,
    cancelled = false,
  ) => {
    const drag = strategyDrag.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    suppressStrategyClick.current = !cancelled && drag.moved;
    strategyDrag.current = null;
    setIsStrategyDragging(false);
    window.setTimeout(() => {
      suppressStrategyClick.current = false;
    }, 0);
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
    let retryTimer: number | undefined;
    const loadStrategyPlanningReturns = () => {
      getStrategyPlanningReturns()
        .then((returns) => { if (active) setStrategyPlanningReturns(returns); })
        .catch(() => {
          if (active) {
            retryTimer = window.setTimeout(
              loadStrategyPlanningReturns,
              STRATEGY_PLANNING_RETURN_RETRY_MS,
            );
          }
        });
    };
    loadStrategyPlanningReturns();
    return () => {
      active = false;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, []);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => {
      setActivePromo((current) => (current + 1) % PROMO_COUNT);
      setPromoOffset((current) => (current >= PROMO_COUNT ? 1 : current + 1));
      setIsPromoSnapping(false);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [promoTimerKey]);
  // 복제 슬라이드에 도착하면 전환이 끝난 뒤 애니메이션 없이 원본 첫 카드로 되돌린다.
  useEffect(() => {
    if (promoOffset < PROMO_COUNT) return;
    // 모션 축소 환경은 전환이 없으므로 기다리지 않고 곧바로 되돌린다.
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const timer = window.setTimeout(() => {
      setIsPromoSnapping(true);
      setPromoOffset(0);
    }, reducedMotion ? 0 : PROMO_TRANSITION_MS);
    return () => window.clearTimeout(timer);
  }, [promoOffset]);
  const totalBalance = aggregation ? formatKrw(aggregation.total_amount_krw) : "-";
  const asOfDate = portfolio ? latestPortfolioDate(portfolio) : null;
  const assessment = investmentProfile?.assessment;
  const profileLabel = assessment
    ? PROFILE_LABELS[assessment.risk_profile]
    : "진단 전";

  return (
    <main className="app-phone-stage mhs-stage">
    <section className="app-phone-frame mhs-phone" aria-label="연금 KDA 메인 홈">
    <div className="mhs-page">
      <StatusBar />

      <div className="mhs-header">
        <span className="mhs-header-dot" />
        <span className="mhs-header-title">연금 <span className="mhs-header-title-accent">KDA</span></span>
        <button type="button" className="mhs-profile-button" onClick={onOpenProfile} aria-label="프로필 열기">
          <img src={profileIcon} alt="" className="mhs-profile-icon" />
        </button>
      </div>

      <div className="mhs-body" ref={bodyRef} onScroll={handleBodyScroll}>
        <section
          className={`mhs-promo-carousel${isPromoDragging ? " is-dragging" : ""}`}
          aria-label="홈 추천 카드"
          aria-roledescription="캐러셀"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") movePromo(-1);
            if (event.key === "ArrowRight") movePromo(1);
          }}
          onPointerDown={handlePromoPointerDown}
          onPointerMove={handlePromoPointerMove}
          onPointerUp={finishPromoPointerDrag}
          onPointerCancel={(event) => finishPromoPointerDrag(event, true)}
          onDragStart={(event) => event.preventDefault()}
          onTouchStart={(event) => {
            promoTouchStartX.current = event.touches[0]?.clientX ?? null;
          }}
          onTouchEnd={(event) => {
            const startX = promoTouchStartX.current;
            const endX = event.changedTouches[0]?.clientX;
            promoTouchStartX.current = null;
            if (startX === null || endX === undefined || Math.abs(endX - startX) < PROMO_DRAG_THRESHOLD_PX) return;
            movePromo(endX < startX ? 1 : -1);
          }}
        >
          <div className="mhs-promo-viewport">
            <div
              className={`mhs-promo-track${isPromoSnapping ? " is-snapping" : ""}`}
              style={{ transform: `translateX(-${promoOffset * 100}%)` }}
            >
              <div className="mhs-promo-slide" aria-hidden={activePromo !== 0}>
                <div className="mhs-tax-card">
                  <div className="mhs-tax-main">
                    <span className="mhs-tax-icon-wrap">
                      <img src={taxCreditMissed} alt="놓친 세액공제액 찾기" className="mhs-tax-icon" />
                    </span>
                    <div className="mhs-tax-copy">
                      <p className="mhs-tax-title">세액공제 준비, 지금 몇 <span className="mhs-tax-title-accent">%</span>?</p>
                      <button
                        type="button"
                        className="mhs-tax-button"
                        onClick={onOpenPlanner}
                        tabIndex={activePromo === 0 ? 0 : -1}
                      >
                        완료율 확인하기 <span>→</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div className="mhs-promo-slide" aria-hidden={activePromo !== 1}>
                <button
                  type="button"
                  className="mhs-greeting-card mhs-greeting-card-button"
                  onClick={onOpenSlangi}
                  aria-label="연그미와 놀기 열기"
                  tabIndex={activePromo === 1 ? 0 : -1}
                >
                  <div className="mhs-greeting-main">
                    <div className="mhs-greeting-copy">
                      <p className="mhs-greeting-title">슬랑이를 <span className="mhs-greeting-title-accent">만져 보세요!</span></p>
                      <p className="mhs-greeting-sub">슬랑이를 눌러 1원씩 적립해보세요</p>
                    </div>
                    <img src={piggy} alt="슬랑이" className="mhs-greeting-img" />
                  </div>
                </button>
              </div>
              {/* 끝에서 첫 카드로 이어지는 모션만을 위한 복제본. 보조기술과 탭 순서에서는 제외한다. */}
              <div className="mhs-promo-slide" aria-hidden="true">
                <div className="mhs-tax-card">
                  <div className="mhs-tax-main">
                    <span className="mhs-tax-icon-wrap">
                      <img src={taxCreditMissed} alt="" className="mhs-tax-icon" />
                    </span>
                    <div className="mhs-tax-copy">
                      <p className="mhs-tax-title">세액공제 준비, 지금 몇 <span className="mhs-tax-title-accent">%</span>?</p>
                      <button type="button" className="mhs-tax-button" tabIndex={-1}>
                        완료율 확인하기 <span>→</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="mhs-promo-dots" aria-label="추천 카드 선택">
            {[0, 1].map((promoIndex, dotIndex) => (
              <button
                key={promoIndex}
                type="button"
                className={`mhs-promo-dot${activePromo === promoIndex ? " is-active" : ""}`}
                onClick={() => selectPromo(promoIndex)}
                aria-label={`${dotIndex + 1}번째 카드 보기`}
                aria-current={activePromo === promoIndex ? "true" : undefined}
              />
            ))}
          </div>
        </section>
        <h2 className="mhs-section-title">내 연금 <span className="mhs-section-title-gold">자산</span></h2>

        <div className="mhs-asset-card">
          <p className="mhs-asset-label">총 연금 자산</p>
          <p className="mhs-asset-total">{loading ? "불러오는 중…" : totalBalance}</p>
          <p className="mhs-asset-gain">
            {error ?? (asOfDate ? (
              <>
                <span>{displayName}님 · {profileLabel}</span>
                <span> · {asOfDate} 기준</span>
              </>
            ) : "연금 데이터를 확인해 주세요.")}
          </p>

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
              <button type="button" className="mhs-summary-cta mhs-summary-cta-button" onClick={onRequestPortfolioDiagnosis}>내 포트폴리오 자세히 진단받기 <span className="mhs-summary-cta-chevron">›</span></button>
            </div>
          </div>
        </div>

        <div className="mhs-strategy-heading-row">
          <h2 className="mhs-section-title mhs-section-title-tight">
            연금KDA&apos;s <span className="mhs-section-title-gold">Pick</span>
          </h2>
          <button type="button" className="mhs-strategy-more" onClick={onOpenStrategyExplore}>시나리오·더보기 +</button>
        </div>
        <p className="mhs-strategy-intro">연금 KDA가 운용하는 전략들을 따라해보세요!</p>

        <div
          className={`mhs-strategy-scroll${isStrategyDragging ? " is-dragging" : ""}`}
          role="region"
          aria-label="전략 카드 목록"
          onPointerDown={handleStrategyPointerDown}
          onPointerMove={handleStrategyPointerMove}
          onPointerUp={finishStrategyDrag}
          onPointerCancel={(event) => finishStrategyDrag(event, true)}
          onClickCapture={(event) => {
            if (!suppressStrategyClick.current) return;
            event.preventDefault();
            event.stopPropagation();
            suppressStrategyClick.current = false;
          }}
        >
          {STRATEGY_CARDS.map((card) => {
            const planningReturn = strategyPlanningReturns?.find(
              (item) => item.strategy_id === card.strategyId,
            );
            const value = planningReturn
              ? formatPlanningPercent(planningReturn.net_planning_return_percent)
              : "계산 중…";
            return (
            <button
              type="button"
              className="mhs-strategy-card mhs-strategy-card-button"
              style={{ background: card.bg }}
              key={card.title}
              onClick={onOpenStrategyExplore}
              aria-label={`${card.title} 소개 화면 열기`}
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
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
