import { useEffect, useRef, type JSX } from "react";

import type {
  InvestmentProfileResponse,
  RiskProfile,
  UserPensionPortfolio,
} from "../api/types";
import { supabase } from "../auth/supabase";
import {
  latestPortfolioDate,
  portfolioBoundaryLabel,
} from "../ownerPensionPortfolio";

interface ProfileHtmlPageProps {
  displayName: string;
  email: string;
  investmentProfile: InvestmentProfileResponse | null;
  portfolio: UserPensionPortfolio | null;
  onBack: () => void;
  onSignOut?: () => Promise<void>;
}

const PROFILE_LABELS: Record<RiskProfile, string> = {
  stable: "안정형",
  stable_seeking: "안정추구형",
  risk_neutral: "위험중립형",
  active: "적극투자형",
  aggressive: "공격투자형",
};

export function ProfileHtmlPage({
  displayName,
  email,
  investmentProfile,
  portfolio,
  onBack,
  onSignOut,
}: ProfileHtmlPageProps): JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const onBackRef = useRef(onBack);
  const onSignOutRef = useRef(onSignOut ?? signOutFromProfile);

  useEffect(() => {
    onBackRef.current = onBack;
    onSignOutRef.current = onSignOut ?? signOutFromProfile;
  }, [onBack, onSignOut]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    let frameDocument: Document | null = null;
    const handleFrameClick = (event: Event): void => {
      const target = event.target as {
        closest?: (selector: string) => Element | null;
      } | null;
      if (target?.closest?.("[data-profile-html-back]")) onBackRef.current();
      if (target?.closest?.("[data-profile-html-sign-out]")) {
        void onSignOutRef.current();
      }
    };
    const setText = (selector: string, value: string): void => {
      const element = frameDocument?.querySelector(selector);
      if (element) element.textContent = value;
    };
    const connectFrame = (): void => {
      frameDocument?.removeEventListener("click", handleFrameClick);
      frameDocument = iframe.contentDocument;
      frameDocument?.addEventListener("click", handleFrameClick);
      setText("[data-profile-name]", displayName);
      setText("[data-profile-email]", email);
      setText(
        "[data-profile-boundary]",
        portfolio
          ? portfolioBoundaryLabel(portfolio.data_boundary)
          : "계좌 미연결",
      );
      setText(
        "[data-profile-as-of]",
        portfolio ? latestPortfolioDate(portfolio) ?? "-" : "-",
      );
      setText(
        "[data-profile-risk]",
        investmentProfile?.assessment
          ? PROFILE_LABELS[investmentProfile.assessment.risk_profile]
          : "진단 전",
      );
    };

    iframe.addEventListener("load", connectFrame);
    if (iframe.contentDocument?.readyState === "complete") connectFrame();

    return () => {
      iframe.removeEventListener("load", connectFrame);
      frameDocument?.removeEventListener("click", handleFrameClick);
    };
  }, [displayName, email, investmentProfile, portfolio]);

  return (
    <iframe
      ref={iframeRef}
      src={`${import.meta.env.BASE_URL}profile-html/index.html`}
      style={{ border: 0, display: "block", height: "100vh", width: "100%" }}
      title="내 프로필"
    />
  );
}

async function signOutFromProfile(): Promise<void> {
  if (!supabase) return;
  const { error } = await supabase.auth.signOut();
  if (error) throw new Error("로그아웃하지 못했습니다.");
}
