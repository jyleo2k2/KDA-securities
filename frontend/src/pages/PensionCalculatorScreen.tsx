import type { JSX } from "react";

export function PensionCalculatorScreen(): JSX.Element {
  return <iframe
    aria-label="연금 계산기"
    src="/pension-calculator/연금계산기.dc.html"
    style={{ border: 0, display: "block", height: "100dvh", width: "100%" }}
    title="연금 계산기"
  />;
}
