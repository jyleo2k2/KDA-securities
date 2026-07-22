import { useState, type JSX } from "react";

import moneyBag from "../assets/main-home/money-bag.png";
import piggy from "../assets/main-home/piggy.png";
import profileIcon from "../assets/main-home/profile-icon.png";
import userPickPreview from "../assets/main-home/user-pick-preview.png";
import type { DemoHeroPortfolio, DemoUserFinancialContext, InvestmentProfileResponse, RiskProfile } from "../api/types";
import "./MainHomeScreen.css";

interface MainHomeScreenProps {
  error: string | null;
  hero: DemoHeroPortfolio | null;
  investmentProfile: InvestmentProfileResponse | null;
  loading: boolean;
  onOpenChat: () => void;
  onOpenPlanner: () => void;
  onOpenStrategyExplore: () => void;
  onOpenUserPick: () => void;
  onResurvey: () => void;
  userContext: DemoUserFinancialContext | null;
}

interface AllocationSlice {
  label: string;
  percent: string;
  color: string;
}

interface HoldingSlice {
  label: string;
  amountKrw: number;
  percent: number;
  color: string;
}

const HOLDING_DONUT_COLORS = ["#18A860", "#3877E8", "#F0C000", "#F5871F", "#8B5FEB", "#2FBFA0", "#B8C0BA"];
const PROFILE_LABELS: Record<RiskProfile, string> = {
  stable: "안정형", stable_seeking: "안정추구형", risk_neutral: "위험중립형", active: "적극투자형", aggressive: "공격투자형",
};
const HOLDING_DONUT_MAX_SLICES = 6;
const HOLDING_DONUT_LABEL_MIN_PERCENT = 5;
const DONUT_SIZE = 174;
const DONUT_CENTER = DONUT_SIZE / 2;
const DONUT_RADIUS = 64;
const DONUT_STROKE_WIDTH = 46;
const DONUT_CIRCUMFERENCE = 2 * Math.PI * DONUT_RADIUS;

function buildHoldingDonutSlices(hero: DemoHeroPortfolio | null): HoldingSlice[] {
  if (!hero) return [];
  const amountsByInstrument = new Map<string, number>();
  for (const account of hero.accounts) {
    for (const holding of account.holdings) {
      const amount = Number(holding.amount_krw);
      amountsByInstrument.set(holding.instrument_name, (amountsByInstrument.get(holding.instrument_name) ?? 0) + amount);
    }
  }
  const sorted = [...amountsByInstrument.entries()].sort((a, b) => b[1] - a[1]);
  const total = Number(hero.total_amount_krw) || sorted.reduce((sum, [, amount]) => sum + amount, 0);
  if (total <= 0) return [];
  const main = sorted.slice(0, HOLDING_DONUT_MAX_SLICES);
  const restAmount = sorted.slice(HOLDING_DONUT_MAX_SLICES).reduce((sum, [, amount]) => sum + amount, 0);
  const entries: Array<[string, number]> = restAmount > 0 ? [...main, ["기타", restAmount]] : main;
  return entries.map(([label, amountKrw], index) => ({
    label,
    amountKrw,
    percent: (amountKrw / total) * 100,
    color: label === "기타" ? HOLDING_DONUT_COLORS[HOLDING_DONUT_COLORS.length - 1] : HOLDING_DONUT_COLORS[index % (HOLDING_DONUT_COLORS.length - 1)],
  }));
}

function polarPoint(centerDeg: number, radius: number): { x: number; y: number } {
  const angleRad = ((centerDeg - 90) * Math.PI) / 180;
  return { x: DONUT_CENTER + radius * Math.cos(angleRad), y: DONUT_CENTER + radius * Math.sin(angleRad) };
}

function HoldingDonut({ slices }: { slices: HoldingSlice[] }): JSX.Element {
  let cumulativePercent = 0;
  return (
    <svg width={DONUT_SIZE} height={DONUT_SIZE} viewBox={`0 0 ${DONUT_SIZE} ${DONUT_SIZE}`} role="img" aria-label="총 연금 자산 보유 종목 비중">
      {slices.map((slice) => {
        const segmentLength = (slice.percent / 100) * DONUT_CIRCUMFERENCE;
        const dashArray = `${segmentLength} ${DONUT_CIRCUMFERENCE - segmentLength}`;
        const dashOffset = -((cumulativePercent / 100) * DONUT_CIRCUMFERENCE);
        const labelCenterDeg = (cumulativePercent + slice.percent / 2) * 3.6;
        cumulativePercent += slice.percent;
        const labelPoint = polarPoint(labelCenterDeg, DONUT_RADIUS);
        return (
          <g key={slice.label}>
            <circle
              cx={DONUT_CENTER}
              cy={DONUT_CENTER}
              r={DONUT_RADIUS}
              fill="none"
              stroke={slice.color}
              strokeWidth={DONUT_STROKE_WIDTH}
              strokeDasharray={dashArray}
              strokeDashoffset={dashOffset}
              transform={`rotate(-90 ${DONUT_CENTER} ${DONUT_CENTER})`}
            />
            {slice.percent >= HOLDING_DONUT_LABEL_MIN_PERCENT && (
              <text x={labelPoint.x} y={labelPoint.y} textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight={800} fill="#fff">
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
  title: string;
  value: string;
  valueColor: string;
  desc: string;
  warning?: string;
  footnote: string;
  bg: string;
}

const STRATEGY_CARDS: StrategyCard[] = [
  { title: "시장 베타", value: "+6.75%", valueColor: "#4FB6E6", desc: "국내·미국·글로벌 광범위지수 ETF로 시장 전체 수익을 그대로 따라가요. 개별 종목을 고르지 않아 관리가 단순하고 코어 자산으로 쓰기 좋아요. 장기 시장수익 확보를 목표로 하는 안정적인 전략이에요.", footnote: "글로벌주식 CMA 7.0% · 할인 0.25%p", bg: "#EAF7FC" },
  { title: "팩터", value: "+6.60%", valueColor: "#24386E", desc: "가치·퀄리티·모멘텀·저변동 등 초과수익 요인을 골라 담아요. 투명한 규칙 기반 ETF로 구성해 종목 추격매수 없이 운용해요. 시장 평균 대비 꾸준한 초과성과를 노리는 전략이에요.", footnote: "글로벌주식 CMA 7.0% · 할인 0.40%p", bg: "#EAEDF3" },
  { title: "테마", value: "+6.00%", valueColor: "#F5871F", desc: "AI·반도체·바이오·인프라 등 유망 테마 ETF에 분산 투자해요. 구조적 성장 근거와 최근 상대성과를 함께 확인한 종목만 편입해요. 단일 테마 비중은 제한해 과열 위험을 관리하는 전략이에요.", footnote: "글로벌주식 CMA 7.0% · 할인 1.00%p", bg: "#FFF3E6" },
  { title: "탑다운", value: "구성별 산정", valueColor: "#3B4148", desc: "거시 흐름부터 짚어 국가·지역·산업·채권만기 비중을 조절해요. 하향식으로 유망 자산을 좁혀가며 포트폴리오를 구성해요. 실제 구성이 매번 달라져 확정 후 가중 계산이 필요한 전략이에요.", warning: "※ 지역·자산 비중이 매번 달라 실제 구성 확정 후 가중 계산이 필요해요.", footnote: "실제 구성 가중 CMA · 할인 0.75%p", bg: "#EEF0F1" },
  { title: "바텀업", value: "+6.25%", valueColor: "#1E9E5D", desc: "연금 적격 액티브주식 ETF로 개별 기업을 실사하듯 선별해요. 종목·산업 단위로 꼼꼼히 뜯어보고 투자 후보를 좁혀가요. 시장 평균이 아닌 선별한 기업의 성장에 기대는 전략이에요.", footnote: "지역별 주식 CMA · 할인 0.75%p", bg: "#E9F8EF" },
  { title: "바벨", value: "비중별 산정", valueColor: "#1E2124", desc: "성장자산과 단기채·현금성 자산을 양극단으로 나눠 보유해요. 중간 위험 자산 없이 공격과 방어 자산만으로 균형을 맞춰요. 두 자산군 비중이 고정돼 있지 않아 구성별 할인율을 각각 적용하는 전략이에요.", warning: "※ 두 자산군 비중이 고정돼있지 않아 구성 ETF별 할인율을 각각 적용해야 해요.", footnote: "실제 구성 가중 CMA · 구성별 할인", bg: "#F5F5F5" },
  { title: "변동성 관리", value: "비중별 산정", valueColor: "#9CA7AE", desc: "저변동 ETF와 채권·현금성 ETF로 자산의 변동폭을 관리해요. 실현변동성이 목표를 넘으면 비중을 비례해 축소해요. 위험을 조절해 흔들림을 다스리는 데 초점을 둔 전략이에요.", warning: "※ 변동성 목표에 따라 자산 비중이 조정돼 구성 ETF별로 할인율이 달라져요.", footnote: "실제 구성 가중 CMA · 구성별 할인", bg: "#F1F2F3" },
  { title: "롱숏·시장중립", value: "산정 예정", valueColor: "#7B4FC0", desc: "적격 시장중립·절대수익형 상품으로 매수와 매도를 함께 써요. 시장 방향과 무관한 수익을 추구해 변동성 완충 역할을 해요. 계좌에 담을 적격 상품 확정 전까지는 수익률을 산출하지 않는 전략이에요.", warning: "※ 별도 CMA가 아직 없어 편입 상품 확정 전까지 수익률을 산출하지 않아요.", footnote: "별도 CMA 필요 · 잠정 할인 0.75%p", bg: "#F3EEFB" },
  { title: "이벤트드리븐", value: "산정 예정", valueColor: "#B8860B", desc: "합병·분할·자사주 등 이미 공시된 기업행동에서 기회를 찾아요. 가격 변화가 예상되는 이벤트 중심으로 후보를 선별해요. 적격 공모펀드가 없다면 매매 신호가 아닌 교육 정보로만 제공하는 전략이에요.", warning: "※ 별도 CMA가 아직 없어 편입 상품 확정 전까지 수익률을 산출하지 않아요.", footnote: "별도 CMA 필요 · 잠정 할인 0.75%p", bg: "#FFF8DE" },
  { title: "추세추종·글로벌 매크로", value: "+5.65%", valueColor: "#2F6FE0", desc: "적격 멀티에셋·추세 ETF로 글로벌 매크로 흐름을 추종해요. 최근 위험조정 성과가 강한 자산을 규칙 기반으로 편입해요. 월별 관찰과 정기 교체를 원칙으로 방향성에 올라타는 전략이에요.", footnote: "글로벌 60/40 CMA 6.4% · 할인 0.75%p", bg: "#EAF1FE" },
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

function buildPortfolioOneLineSummary(hero: DemoHeroPortfolio | null): string {
  if (!hero || hero.asset_allocations.length === 0) {
    return "포트폴리오 구성을 불러오면 가장 큰 자산 비중을 알려드려요.";
  }
  const dominant = hero.asset_allocations.reduce((largest, current) => (
    Number(current.allocation_percent) > Number(largest.allocation_percent) ? current : largest
  ));
  const equityPercent = hero.asset_allocations
    .filter((item) => item.asset_class_code === "domestic_equity" || item.asset_class_code === "global_equity")
    .reduce((sum, item) => sum + Number(item.allocation_percent), 0);
  const dominantLabel = ASSET_LABELS[dominant.asset_class_code] ?? "기타 자산";
  return `${dominantLabel} 비중이 가장 높고, 전체 주식 비중은 ${equityPercent.toFixed(1)}%예요.`;
}

export function MainHomeScreen({ error, hero, investmentProfile, loading, onOpenChat, onOpenPlanner, onOpenStrategyExplore, onOpenUserPick, onResurvey, userContext }: MainHomeScreenProps): JSX.Element {
  const [infoOpen, setInfoOpen] = useState(false);
  const allocationSlices: AllocationSlice[] = hero?.asset_allocations.slice(0, 4).map((item, index) => ({ label: ASSET_LABELS[item.asset_class_code] ?? "기타 자산", percent: `${item.allocation_percent}%`, color: ALLOCATION_COLORS[index] })) ?? [];
  const holdingSlices = buildHoldingDonutSlices(hero);
  const totalBalance = userContext ? formatKrw(userContext.total_pension_balance_krw) : "-";

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
        <img src={profileIcon} alt="프로필" className="mhs-profile-icon" />
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
        <button type="button" className="mhs-resurvey-button" onClick={onResurvey}>재설문하기</button>

        <h2 className="mhs-section-title">내 연금 <span className="mhs-section-title-gold">자산</span></h2>

        <div className="mhs-asset-card">
          <p className="mhs-asset-label">총 연금 자산</p>
          <p className="mhs-asset-total">{loading ? "불러오는 중…" : totalBalance}</p>
          <p className="mhs-asset-gain">{error ?? (userContext ? `${userContext.nickname.replace(/\(가상\)/g, "")}님 · ${userContext.as_of_date} 기준` : "연금 데이터를 확인해 주세요.")}</p>

          <div className="mhs-donut-wrap">
            {holdingSlices.length > 0 ? <HoldingDonut slices={holdingSlices} /> : (
              <div className="mhs-donut-outer" style={{ background: "#EEF0F1" }}>
                <div className="mhs-donut-inner" />
              </div>
            )}
          </div>

          <div className="mhs-allocation-grid">
            {(holdingSlices.length > 0
              ? holdingSlices.map((slice) => ({ label: slice.label, percent: `${slice.percent.toFixed(1)}%`, color: slice.color }))
              : allocationSlices
            ).map((slice) => (
              <span className="mhs-allocation-item" key={slice.label}>
                <span className="mhs-allocation-dot" style={{ background: slice.color }} />
                <span className="mhs-allocation-label">{slice.label}</span>
                <span className="mhs-allocation-percent">{slice.percent}</span>
              </span>
            ))}
          </div>

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
            <p className="mhs-summary-text">{buildPortfolioOneLineSummary(hero)}</p>
            <div className="mhs-summary-cta-row">
              <button type="button" className="mhs-summary-cta mhs-summary-cta-button" onClick={onOpenChat}>자세히 진단받기 <span className="mhs-summary-cta-chevron">›</span></button>
            </div>
          </div>
        </div>

        <h2 className="mhs-section-title">세액공제</h2>
        <div className="mhs-tax-card">
          <span className="mhs-tax-icon-wrap">
            <img src={moneyBag} alt="돈 주머니" className="mhs-tax-icon" />
          </span>
          <div className="mhs-tax-copy">
            <p className="mhs-tax-title">세액공제 준비, 지금 몇 <span className="mhs-tax-title-accent">%</span>?</p>
            <p className="mhs-tax-sub">연금저축·IRP 납입 현황과 남은 여력을 확인해 보세요.</p>
            <button type="button" className="mhs-tax-button" onClick={onOpenPlanner}>완료율 확인하기 <span>→</span></button>
          </div>
        </div>

        <div className="mhs-strategy-heading-row">
          <h2 className="mhs-section-title mhs-section-title-tight">
            전략 설명<br />
            <span className="mhs-section-title-gold">교육용 전략 안내</span>
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
              <p className="mhs-strategy-card-value" style={{ color: card.valueColor }}>교육용 안내</p>
              <p className="mhs-strategy-card-desc">{card.desc}</p>
              {card.warning && <p className="mhs-strategy-card-warning">{card.warning}</p>}
              <p className="mhs-strategy-card-footnote">{card.footnote}</p>
            </button>
          ))}
        </div>
        <p className="mhs-strategy-disclaimer">전략별 특징을 설명하는 교육용 화면이며, 미래 수익을 보장하거나 예측하지 않아요.</p>

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
