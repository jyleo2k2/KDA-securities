import type { JSX } from "react";

import "./StatusBar.css";

interface StatusBarProps {
  /** 상태바 전경색. 밝은 배경 위 기본값은 진한 잉크색. */
  tone?: "dark" | "light";
  time?: string;
  className?: string;
}

// index.css 의 전역 `svg { stroke: currentColor; stroke-width: 1.7 }` 는 선으로 그리는
// UI 아이콘용이다. 상단바 아이콘은 Figma 원본을 fill 로만 그린 도형이라 그 외곽선이
// 덧그려지면 신호막대가 두꺼워지고 Wi-Fi 호 사이 여백이 메워져 통짜 삼각형이 된다.
// profile-html(iframe)만 정상이던 이유가 이 전역 규칙의 적용 여부였다.
// CSS 대신 인라인 스타일로 끄는 이유: 전역 요소 선택자를 확실히 이기고, 테스트에서
// DOM 으로 직접 검증할 수 있다(vitest 는 CSS 본문을 읽지 못한다).
const NO_STROKE = { stroke: "none" } as const;

// Figma "StatusBar" 컴포넌트(Page 3, node 501:57) 재현.
// 아이폰 14 다이나믹 아일랜드형 상단바: 좌측 시각 · 중앙 검정 아일랜드(카메라 렌즈) ·
// 우측 셀룰러 신호 + Wi-Fi + 배터리. 전경색(tone)은 화면 배경에 맞춰 적응하고, 아일랜드는 항상 검정.
export function StatusBar({ tone = "dark", time = "9:41", className }: StatusBarProps): JSX.Element {
  return (
    <div className={`ios-statusbar ios-statusbar--${tone}${className ? ` ${className}` : ""}`} aria-hidden="true">
      <span className="ios-statusbar-time">{time}</span>
      <span className="ios-statusbar-island">
        <span className="ios-statusbar-lens" />
      </span>
      <span className="ios-statusbar-icons">
        {/* 실제 Figma 에셋(assets/main-home/icon-signal.svg) 정밀 path — 4단 신호막대. */}
        <svg className="ios-statusbar-cellular" style={NO_STROKE} shapeRendering="geometricPrecision" width="18" height="12" viewBox="0 0 18 12" fill="none">
          <path d="M10 3c0-.552.448-1 1-1h1c.552 0 1 .448 1 1v8c0 .552-.448 1-1 1h-1c-.552 0-1-.448-1-1V3Z" fill="currentColor" />
          <path d="M15 1c0-.552.448-1 1-1h1c.552 0 1 .448 1 1v10c0 .552-.448 1-1 1h-1c-.552 0-1-.448-1-1V1Z" fill="currentColor" />
          <path d="M5 6.5c0-.552.448-1 1-1h1c.552 0 1 .448 1 1V11c0 .552-.448 1-1 1H6c-.552 0-1-.448-1-1V6.5Z" fill="currentColor" />
          <path d="M0 9c0-.552.448-1 1-1h1c.552 0 1 .448 1 1v2c0 .552-.448 1-1 1H1c-.552 0-1-.448-1-1V9Z" fill="currentColor" />
        </svg>
        {/* 실제 Figma 에셋(assets/main-home/icon-wifi.svg) 정밀 path. */}
        <svg className="ios-statusbar-wifi" style={NO_STROKE} shapeRendering="geometricPrecision" width="17" height="11.834" viewBox="0 0 17 11.834" fill="none">
          <path d="M8.5 2.588c2.467 0 4.839.967 6.627 2.702.134.134.35.132.482-.004l1.287-1.326a.352.352 0 0 0-.003-.518c-4.692-4.589-12.094-4.589-16.786 0a.352.352 0 0 0-.004.518L1.39 5.286c.132.136.348.138.482.004C3.66 3.555 6.034 2.588 8.5 2.588Zm.036 4.001c1.355 0 2.662.514 3.667 1.443.135.132.349.129.482-.006l1.285-1.326a.353.353 0 0 0-.006-.522c-3.059-2.904-7.796-2.904-10.856 0a.353.353 0 0 0-.009.522L4.39 8.026c.132.135.346.138.482.006 1.004-.928 2.31-1.442 3.664-1.443Zm2.614 2.588a.35.35 0 0 1-.105.262l-2.223 2.29a.353.353 0 0 1-.494 0l-2.223-2.29a.35.35 0 0 1-.105-.262.353.353 0 0 1 .115-.258c1.42-1.225 3.5-1.225 4.92 0a.353.353 0 0 1 .115.258Z" fill="currentColor" fillRule="evenodd" clipRule="evenodd" />
        </svg>
        {/* 배터리: iOS 스타일. 테두리 + 단자 + 채움(약 80%). */}
        <svg className="ios-statusbar-battery" style={NO_STROKE} shapeRendering="geometricPrecision" width="27.4" height="13" viewBox="0 0 28 13" fill="none">
          {/* 테두리만 선으로 그린다. strokeWidth 를 명시해 전역 1.7 상속을 막는다. */}
          <rect x=".5" y=".5" width="24" height="12" rx="3.8" stroke="currentColor" strokeWidth="1" strokeOpacity=".35" vectorEffect="non-scaling-stroke" />
          <rect x="2" y="2" width="17" height="9" rx="2.2" fill="currentColor" />
          <path d="M26.5 4.5v4c.8-.34 1.3-1.1 1.3-2s-.5-1.66-1.3-2Z" fill="currentColor" fillOpacity=".4" />
        </svg>
      </span>
    </div>
  );
}
