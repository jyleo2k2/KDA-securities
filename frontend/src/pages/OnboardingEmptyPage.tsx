import type { JSX } from "react";

import "./OnboardingEmptyPage.css";

interface OnboardingEmptyPageProps {
  /** 계좌 연결 진입 콜백. 프리뷰/미연동 단계에서는 실제 연결을 수행하지 않는다. */
  onConnect?: () => void;
}

const PREVIEW_ROWS: ReadonlyArray<{ label: string; percent: string; color: string }> = [
  { label: "KODEX 미국S&P500", percent: "32%", color: "#18A860" },
  { label: "TIGER 나스닥100", percent: "18%", color: "#3877E8" },
  { label: "KOSEF 국고채10년", percent: "12%", color: "#F0C000" },
];

const EXPLORE_STRATEGIES: ReadonlyArray<{ title: string; value: string; color: string; bg: string; desc: string }> = [
  { title: "시장 베타", value: "6.75%", color: "#4FB6E6", bg: "#EAF7FC", desc: "지수 ETF로 시장 전체 흐름" },
  { title: "테마", value: "6.00%", color: "#F5871F", bg: "#FFF3E6", desc: "AI·반도체·바이오 분산" },
  { title: "바텀업", value: "6.25%", color: "#1E9E5D", bg: "#E9F8EF", desc: "적격 액티브 ETF 선별" },
];

function Yeongeumi(): JSX.Element {
  return (
    <svg
      className="obe-mascot"
      viewBox="0 0 120 120"
      fill="none"
      stroke="currentColor"
      strokeWidth={3.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label="연금 안내 마스코트 연그미"
    >
      <path className="obe-mascot-body" d="M30 70 Q26 44 46 40 Q60 37 74 40 Q94 44 90 70 Q88 92 60 92 Q32 92 30 70Z" />
      <path d="M38 44 L31 30 L50 39" />
      <path d="M82 44 L89 30 L70 39" />
      <ellipse className="obe-mascot-snout" cx={60} cy={70} rx={14} ry={10} />
      <circle cx={55} cy={70} r={1.9} fill="currentColor" stroke="none" />
      <circle cx={65} cy={70} r={1.9} fill="currentColor" stroke="none" />
      <circle cx={47} cy={58} r={2.4} fill="currentColor" stroke="none" />
      <circle cx={73} cy={58} r={2.4} fill="currentColor" stroke="none" />
      <path d="M42 90 L42 100 M54 92 L54 101 M66 92 L66 101 M78 90 L78 100" />
      <path d="M56 40 L64 40" strokeWidth={4} />
      <path d="M90 64 Q100 60 98 70 Q96 78 104 76" />
      <circle cx={60} cy={20} r={7} stroke="#F0C000" />
      <path d="M57 20 L63 20 M60 16 L60 24" stroke="#F0C000" strokeWidth={2.4} />
    </svg>
  );
}

/**
 * 계좌 미연동 사용자가 홈에 진입했을 때 보여주는 온보딩 빈 화면.
 * - 계좌 카드 자리만 빈 상태(연그미 안내 + "예시" 라벨 미리보기 + 연결 CTA)
 * - 전략·이용자 Pick은 그대로 노출해 둘러보기 허용(부분 노출)
 * 실제 계좌 연결/이전은 이 화면에서 수행하지 않는다(표시 전용).
 */
export function OnboardingEmptyPage({ onConnect }: OnboardingEmptyPageProps): JSX.Element {
  return (
    <main className="obe-stage">
      <svg className="obe-defs" aria-hidden="true" focusable="false">
        <defs>
          <filter id="obe-squiggle">
            <feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves={3} seed={2} result="warp">
              <animate attributeName="seed" values="2;6;2" dur="1.1s" repeatCount="indefinite" />
            </feTurbulence>
            <feDisplacementMap in="SourceGraphic" in2="warp" scale={3} xChannelSelector="R" yChannelSelector="G" />
          </filter>
        </defs>
      </svg>

      <section className="obe-phone" aria-label="계좌 미연동 온보딩 화면">
        <div className="obe-status">
          <span className="obe-status-time">9:41</span>
          <span className="obe-status-icons" aria-hidden="true">● ● ▰</span>
        </div>

        <div className="obe-head">
          <span className="obe-head-dot" />
          <span className="obe-head-title">연금 <span className="obe-head-title-accent">도우미</span></span>
        </div>

        <div className="obe-body">
          <div className="obe-empty">
            <Yeongeumi />
            <h2 className="obe-empty-title">아직 연동된 계좌가 없어요</h2>
            <p className="obe-empty-sub">계좌를 연결하면 이렇게 한눈에 볼 수 있어요</p>
            <div className="obe-preview" aria-label="연결 후 화면 예시">
              <div className="obe-preview-rows">
                {PREVIEW_ROWS.map((row) => (
                  <div className="obe-preview-row" key={row.label}>
                    <span className="obe-preview-dot" style={{ background: row.color }} />
                    <span className="obe-preview-name">{row.label}</span>
                    <span className="obe-preview-pct">{row.percent}</span>
                  </div>
                ))}
              </div>
              <div className="obe-preview-tint" />
              <span className="obe-preview-label">예시</span>
            </div>
            <button type="button" className="obe-connect" onClick={onConnect}>계좌 연결하기</button>
          </div>

          <p className="obe-sec">이런 것도 <span className="obe-sec-accent">둘러보세요</span></p>
          <div className="obe-strats">
            {EXPLORE_STRATEGIES.map((strategy) => (
              <div className="obe-strat" style={{ background: strategy.bg }} key={strategy.title}>
                <span className="obe-strat-title">{strategy.title}</span>
                <span className="obe-strat-value" style={{ color: strategy.color }}>{strategy.value}</span>
                <p className="obe-strat-desc">{strategy.desc}</p>
              </div>
            ))}
          </div>
          <div className="obe-pick">동일 업종·다른 이용자<br />포트폴리오 둘러보기 ›</div>
        </div>

        <nav className="obe-nav" aria-label="하단 탭">
          <span className="obe-nav-item obe-nav-item-on">⌂ 홈 화면</span>
          <span className="obe-nav-item">💬 챗봇</span>
        </nav>
      </section>
    </main>
  );
}
