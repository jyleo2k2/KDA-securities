import type { JSX } from "react";

import "./YeongeumiMascot.css";

interface YeongeumiMascotProps {
  className?: string;
}

/**
 * 연금 안내 마스코트 "연그미". 손그림 라인아트 돼지에 SVG feDisplacementMap 필터로
 * 자글자글 살아있는 효과를 준다. 계좌 미연동 등 데이터가 없는 자리(예: 자산 도넛
 * 자리)에 배치한다. prefers-reduced-motion에서는 필터가 꺼진다.
 */
export function YeongeumiMascot({ className }: YeongeumiMascotProps): JSX.Element {
  return (
    <svg
      className={`yeongeumi-svg${className ? ` ${className}` : ""}`}
      viewBox="0 0 120 120"
      fill="none"
      stroke="currentColor"
      strokeWidth={3.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role="img"
      aria-label="연금 안내 마스코트 연그미"
    >
      <defs>
        <filter id="yeongeumi-squiggle">
          <feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves={3} seed={2} result="warp">
            <animate attributeName="seed" values="2;6;2" dur="1.1s" repeatCount="indefinite" />
          </feTurbulence>
          <feDisplacementMap in="SourceGraphic" in2="warp" scale={3} xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
      <g className="yeongeumi-figure">
        <path className="yeongeumi-body" d="M30 70 Q26 44 46 40 Q60 37 74 40 Q94 44 90 70 Q88 92 60 92 Q32 92 30 70Z" />
        <path d="M38 44 L31 30 L50 39" />
        <path d="M82 44 L89 30 L70 39" />
        <ellipse className="yeongeumi-snout" cx={60} cy={70} rx={14} ry={10} />
        <circle cx={55} cy={70} r={1.9} fill="currentColor" stroke="none" />
        <circle cx={65} cy={70} r={1.9} fill="currentColor" stroke="none" />
        <circle cx={47} cy={58} r={2.4} fill="currentColor" stroke="none" />
        <circle cx={73} cy={58} r={2.4} fill="currentColor" stroke="none" />
        <path d="M42 90 L42 100 M54 92 L54 101 M66 92 L66 101 M78 90 L78 100" />
        <path d="M56 40 L64 40" strokeWidth={4} />
        <path d="M90 64 Q100 60 98 70 Q96 78 104 76" />
      </g>
      {/* 동전은 자글자글 효과에서 제외해 선을 또렷하게 유지한다. */}
      <circle cx={60} cy={20} r={7} stroke="#18A860" />
      <path d="M57 20 L63 20 M60 16 L60 24" stroke="#18A860" strokeWidth={2.4} />
    </svg>
  );
}
