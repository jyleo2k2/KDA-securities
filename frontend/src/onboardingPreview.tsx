import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { OnboardingEmptyPage } from "./pages/OnboardingEmptyPage";

const container = document.getElementById("onboarding-preview-root");
if (!container) {
  throw new Error("#onboarding-preview-root element is missing");
}

createRoot(container).render(
  <StrictMode>
    {/* 프리뷰: 연결은 수행하지 않고 로그만 남긴다. */}
    <OnboardingEmptyPage onConnect={() => console.info("[preview] 계좌 연결하기 클릭 — 프리뷰라 연결하지 않음")} />
  </StrictMode>,
);
