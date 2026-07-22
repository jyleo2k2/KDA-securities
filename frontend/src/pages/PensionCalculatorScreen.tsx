import type { JSX } from "react";

interface PensionCalculatorScreenProps {
  onBack: () => void;
}

export function PensionCalculatorScreen({ onBack }: PensionCalculatorScreenProps): JSX.Element {
  return <main style={{ height: "100dvh", position: "relative" }}>
    <iframe
      aria-label="연금 계산기"
      src="/pension-calculator/연금계산기.dc.html"
      style={{ border: 0, display: "block", height: "100dvh", width: "100%" }}
      title="연금 계산기"
    />
    <button
      type="button"
      aria-label="홈 화면으로 돌아가기"
      onClick={onBack}
      style={{ background: "transparent", border: 0, cursor: "pointer", height: 52, left: "max(calc(50% - 183px), 12px)", padding: 0, position: "absolute", top: 44, width: 36 }}
    />
  </main>;
}
