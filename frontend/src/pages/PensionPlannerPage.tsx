import { useEffect, type JSX } from "react";

import type { DemoUserFinancialContext, RiskProfile } from "../api/types";

export interface PensionPlannerProfile {
  current_age: number;
  risk_profile: RiskProfile;
}

interface PensionPlannerPageProps {
  profile: PensionPlannerProfile | null;
  userContext: DemoUserFinancialContext | null;
  onBack: () => void;
  onOpenProfile: () => void;
}

export function PensionPlannerPage(_props: PensionPlannerPageProps): JSX.Element {
  useEffect(() => {
    function handleCalculatorNavigation(event: MessageEvent): void {
      if (event.origin !== window.location.origin || event.data?.type !== "pension-copilot:navigate-home") return;
      window.location.hash = "#/main-home";
    }
    window.addEventListener("message", handleCalculatorNavigation);
    return () => window.removeEventListener("message", handleCalculatorNavigation);
  }, []);

  return (
    <iframe
      src={`${import.meta.env.BASE_URL}pension-calculator-html/연금계산기.dc.html`}
      style={{ border: 0, display: "block", height: "100vh", width: "100%" }}
      title="예상 연금 계산 및 세액공제 확인"
    />
  );
}
