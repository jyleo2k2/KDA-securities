import { useEffect, useRef, type JSX } from "react";

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

export function PensionPlannerPage({ onBack }: PensionPlannerPageProps): JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const onBackRef = useRef(onBack);

  useEffect(() => {
    onBackRef.current = onBack;
  }, [onBack]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    let frameDocument: Document | null = null;
    const handleFrameClick = (event: Event): void => {
      const target = event.target as { closest?: (selector: string) => Element | null } | null;
      if (target?.closest?.("[data-pension-planner-back]")) onBackRef.current();
    };
    const connectFrame = (): void => {
      frameDocument?.removeEventListener("click", handleFrameClick);
      frameDocument = iframe.contentDocument;
      frameDocument?.addEventListener("click", handleFrameClick);
    };

    iframe.addEventListener("load", connectFrame);
    if (iframe.contentDocument?.readyState === "complete") connectFrame();

    return () => {
      iframe.removeEventListener("load", connectFrame);
      frameDocument?.removeEventListener("click", handleFrameClick);
    };
  }, []);

  return (
    <iframe
      ref={iframeRef}
      src={`${import.meta.env.BASE_URL}pension-calculator-html/연금계산기.dc.html`}
      style={{ border: 0, display: "block", height: "100vh", width: "100%" }}
      title="예상 연금 계산 및 세액공제 확인"
    />
  );
}
