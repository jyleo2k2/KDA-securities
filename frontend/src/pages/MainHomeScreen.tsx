import { useState, type JSX } from "react";

import moneyBag from "../assets/main-home/money-bag.png";
import piggy from "../assets/main-home/piggy.png";
import userPickPreview from "../assets/main-home/user-pick-preview.png";
import type { DemoHeroPortfolio, DemoUserFinancialContext } from "../api/types";
import "./MainHomeScreen.css";

interface MainHomeScreenProps {
  error: string | null;
  hero: DemoHeroPortfolio | null;
  loading: boolean;
  onOpenChat: () => void;
  onResurvey: () => void;
  userContext: DemoUserFinancialContext | null;
}

interface AllocationSlice {
  label: string;
  percent: string;
  color: string;
}

const DONUT_GRADIENT =
  "conic-gradient(#18A860 0deg 86deg, #35B877 86deg 144deg, #6ECFA0 144deg 187deg, #2E8B57 187deg 230deg, #9BDDBF 230deg 259deg, #48C078 259deg 302deg, #C5EAD5 302deg 331deg, #E3E7E4 331deg 360deg)";

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
  { title: "시장 베타", value: "+6.75%", valueColor: "#18A860", desc: "국내·미국·글로벌 광범위지수 ETF로 시장 전체 수익을 추구해요.", footnote: "글로벌주식 CMA 7.0% · 할인 0.25%p", bg: "#F5FAF6" },
  { title: "팩터", value: "+6.60%", valueColor: "#18A860", desc: "가치·퀄리티·모멘텀·저변동 ETF로 초과수익 요인에 투자해요.", footnote: "글로벌주식 CMA 7.0% · 할인 0.40%p", bg: "#F5FAF6" },
  { title: "테마", value: "+6.00%", valueColor: "#E8A600", desc: "AI·반도체·바이오·인프라 ETF로 유망 테마 성장을 추구해요.", footnote: "글로벌주식 CMA 7.0% · 할인 1.00%p", bg: "#FFF9E8" },
  { title: "탑다운", value: "구성별 산정", valueColor: "#18A860", desc: "지역·국가·산업·채권만기 ETF를 조합해 하향식으로 배분해요.", warning: "※ 지역·자산 비중이 매번 달라 실제 구성 확정 후 가중 계산이 필요해요.", footnote: "실제 구성 가중 CMA · 할인 0.75%p", bg: "#F5FAF6" },
  { title: "바텀업", value: "+6.25%", valueColor: "#18A860", desc: "연금 적격 액티브주식 ETF로 종목·산업을 선별해 투자해요.", footnote: "지역별 주식 CMA · 할인 0.75%p", bg: "#F5FAF6" },
  { title: "바벨", value: "비중별 산정", valueColor: "#E8A600", desc: "주식 ETF와 단기채·현금성 ETF를 양극단으로 배분해요.", warning: "※ 두 자산군 비중이 고정돼있지 않아 구성 ETF별 할인율을 각각 적용해야 해요.", footnote: "실제 구성 가중 CMA · 구성별 할인", bg: "#FFF9E8" },
  { title: "변동성 관리", value: "비중별 산정", valueColor: "#18A860", desc: "저변동 ETF와 채권·현금성 ETF로 변동폭을 관리해요.", warning: "※ 변동성 목표에 따라 자산 비중이 조정돼 구성 ETF별로 할인율이 달라져요.", footnote: "실제 구성 가중 CMA · 구성별 할인", bg: "#F5FAF6" },
  { title: "롱숏·시장중립", value: "산정 예정", valueColor: "#8A9691", desc: "적격 시장중립·절대수익 ETF로 시장 방향과 무관한 수익을 추구해요.", warning: "※ 별도 CMA가 아직 없어 편입 상품 확정 전까지 수익률을 산출하지 않아요.", footnote: "별도 CMA 필요 · 잠정 할인 0.75%p", bg: "#F5FAF6" },
  { title: "이벤트드리븐", value: "산정 예정", valueColor: "#8A9691", desc: "기업행동·합병·스핀오프 ETF 이벤트에서 기회를 포착해요.", warning: "※ 별도 CMA가 아직 없어 편입 상품 확정 전까지 수익률을 산출하지 않아요.", footnote: "별도 CMA 필요 · 잠정 할인 0.75%p", bg: "#FFF9E8" },
  { title: "추세추종·글로벌 매크로", value: "+5.65%", valueColor: "#18A860", desc: "적격 멀티에셋·추세 ETF로 글로벌 매크로 흐름을 추종해요.", footnote: "글로벌 60/40 CMA 6.4% · 할인 0.75%p", bg: "#F5FAF6" },
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

export function MainHomeScreen({ error, hero, loading, onOpenChat, onResurvey, userContext }: MainHomeScreenProps): JSX.Element {
  const [infoOpen, setInfoOpen] = useState(false);
  const allocationSlices: AllocationSlice[] = hero?.asset_allocations.slice(0, 4).map((item, index) => ({ label: ASSET_LABELS[item.asset_class_code] ?? "기타 자산", percent: `${item.allocation_percent}%`, color: ALLOCATION_COLORS[index] })) ?? [];
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
      </div>

      <div className="mhs-body">
        <div className="mhs-greeting-card">
          <div className="mhs-greeting-copy">
            <p className="mhs-greeting-title">슬랑이를 <span className="mhs-greeting-title-accent">만져 보세요!</span></p>
            <p className="mhs-greeting-sub">톡톡 두드리면 오늘의 저축 팁을 알려드려요</p>
          </div>
          <img src={piggy} alt="송향이" className="mhs-greeting-img" />
        </div>
        <button type="button" className="mhs-resurvey-button" onClick={onResurvey}>재설문하기</button>

        <h2 className="mhs-section-title">내 연금 <span className="mhs-section-title-gold">자산</span></h2>

        <div className="mhs-asset-card">
          <p className="mhs-asset-label">총 연금 자산</p>
          <p className="mhs-asset-total">{loading ? "불러오는 중…" : totalBalance}</p>
          <p className="mhs-asset-gain">{error ?? (userContext ? `${userContext.nickname}님 · ${userContext.as_of_date} 기준 목데이터` : "연금 데이터를 확인해 주세요.")}</p>

          <div className="mhs-donut-wrap">
            <div className="mhs-donut-outer" style={{ background: DONUT_GRADIENT }}>
              <div className="mhs-donut-inner" />
            </div>
          </div>

          <div className="mhs-allocation-grid">
            {allocationSlices.map((slice) => (
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
            <p className="mhs-summary-sub-label">시황</p>
            <p className="mhs-summary-text">{hero?.risk_summary.requires_rebalancing_review ? "규칙 엔진 기준으로 리밸런싱 점검이 필요해요." : "현재 계좌 구성은 규칙 엔진 기준을 확인했어요."}</p>
            <div className="mhs-summary-cta-row">
              <span className="mhs-summary-cta">자세히 진단받기 <span className="mhs-summary-cta-chevron">›</span></span>
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
            <button type="button" className="mhs-tax-button">완료율 확인하기 <span>→</span></button>
          </div>
        </div>

        <div className="mhs-strategy-heading-row">
          <h2 className="mhs-section-title mhs-section-title-tight">
            전략 설명<br />
            <span className="mhs-section-title-gold">교육용 전략 안내</span>
          </h2>
          <span className="mhs-strategy-more">시나리오·더보기 +</span>
        </div>

        <div className="mhs-strategy-scroll">
          {STRATEGY_CARDS.map((card) => (
            <div className="mhs-strategy-card" style={{ background: card.bg }} key={card.title}>
              <span className="mhs-strategy-card-title">{card.title}</span>
              <p className="mhs-strategy-card-value" style={{ color: card.valueColor }}>교육용 안내</p>
              <p className="mhs-strategy-card-desc">{card.desc}</p>
              {card.warning && <p className="mhs-strategy-card-warning">{card.warning}</p>}
              <p className="mhs-strategy-card-footnote">{card.footnote}</p>
            </div>
          ))}
        </div>
        <p className="mhs-strategy-disclaimer">전략별 특징을 설명하는 교육용 화면이며, 미래 수익을 보장하거나 예측하지 않아요.</p>

        <h2 className="mhs-section-title">
          이용자 <span className="mhs-section-title-accent">Pick</span> <span className="mhs-section-title-note">(다른 사람 포트폴리오 벤치마킹 가능)</span>
        </h2>
        <div className="mhs-userpick-card">
          <img src={userPickPreview} alt="이용자 포트폴리오 미리보기" className="mhs-userpick-img" />
          <div className="mhs-userpick-overlay">
            <p className="mhs-userpick-text">동일 업종 및 다른 이용자의<br />포트폴리오를 <span className="mhs-userpick-text-accent">만나보세요!</span></p>
            <span className="mhs-userpick-cta">지금 둘러보기 <span className="mhs-userpick-cta-chevron">›</span></span>
          </div>
        </div>
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
