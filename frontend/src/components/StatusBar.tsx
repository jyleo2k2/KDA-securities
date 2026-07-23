import type { JSX } from "react";

import "./StatusBar.css";

interface StatusBarProps {
  /** 상태바 전경색. 밝은 배경 위 기본값은 진한 잉크색. */
  tone?: "dark" | "light";
  time?: string;
}

// iPhone(노치 계열, 390pt 폭) 상단 상태바 목업.
// 시간 좌측 정렬, 우측에 셀룰러·와이파이·배터리. 실제 iOS 레이아웃 근사치.
export function StatusBar({ tone = "dark", time = "9:41" }: StatusBarProps): JSX.Element {
  return (
    <div className={`ios-statusbar ios-statusbar--${tone}`} aria-hidden="true">
      <span className="ios-statusbar-time">{time}</span>
      <span className="ios-statusbar-icons">
        <svg className="ios-statusbar-cellular" width="18" height="12" viewBox="0 0 18 12" fill="none">
          <rect x="0" y="8" width="3" height="4" rx="1" fill="currentColor" />
          <rect x="5" y="5.5" width="3" height="6.5" rx="1" fill="currentColor" />
          <rect x="10" y="3" width="3" height="9" rx="1" fill="currentColor" />
          <rect x="15" y="0" width="3" height="12" rx="1" fill="currentColor" />
        </svg>
        <svg className="ios-statusbar-wifi" width="17" height="12" viewBox="0 0 17 12" fill="none">
          <path d="M8.5 2.4c2.6 0 5 1 6.8 2.7l1.4-1.5A11.6 11.6 0 0 0 8.5.4 11.6 11.6 0 0 0 .3 3.6l1.4 1.5A9.6 9.6 0 0 1 8.5 2.4Z" fill="currentColor" />
          <path d="M8.5 6.1c1.6 0 3 .6 4.1 1.7l1.4-1.5a8 8 0 0 0-11 0l1.4 1.5A5.8 5.8 0 0 1 8.5 6.1Z" fill="currentColor" />
          <path d="M8.5 9.7 10.7 7.4a4.2 4.2 0 0 0-4.4 0L8.5 9.7Z" fill="currentColor" />
        </svg>
        <span className="ios-statusbar-battery">
          <span className="ios-statusbar-battery-cap" />
        </span>
      </span>
    </div>
  );
}
