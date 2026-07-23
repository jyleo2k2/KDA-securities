import { useEffect, useMemo, useRef, type JSX } from "react";

import {
  calculateCombinedPension,
  calculatePension,
} from "../api/client";
import type {
  AggregationEvaluation,
  PensionCalculatorEvaluation,
  RiskProfile,
  UserPensionPortfolio,
} from "../api/types";
import { plannerAccountOptions } from "../ownerPensionPortfolio";

export interface PensionPlannerProfile {
  current_age: number;
  risk_profile: RiskProfile;
}

interface PlannerRequest {
  accountId: string;
  age: number;
  endAge: number;
  monthly: number;
  strategyId: string | null;
}

interface PensionPlannerPageProps {
  profile: PensionPlannerProfile | null;
  portfolio: UserPensionPortfolio | null;
  aggregation: AggregationEvaluation | null;
  onBack: () => void;
}

export function PensionPlannerPage({
  profile,
  portfolio,
  aggregation,
  onBack,
}: PensionPlannerPageProps): JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const onBackRef = useRef(onBack);
  const requestSequenceRef = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const accountOptions = useMemo(
    () => portfolio && aggregation
      ? plannerAccountOptions(portfolio, aggregation)
      : [],
    [aggregation, portfolio],
  );
  const defaultRequest = useMemo<PlannerRequest>(() => ({
    accountId: "all",
    age: profile?.current_age ?? 35,
    endAge: Math.min(70, Math.max(60, (profile?.current_age ?? 35) + 1)),
    monthly: 0,
    strategyId: null,
  }), [profile?.current_age]);
  const currentRequestRef = useRef(defaultRequest);

  useEffect(() => {
    onBackRef.current = onBack;
  }, [onBack]);

  useEffect(() => {
    currentRequestRef.current = defaultRequest;
  }, [defaultRequest]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    let frameDocument: Document | null = null;
    const postState = (
      request: PlannerRequest,
      calculation: PensionCalculatorEvaluation | null,
    ): void => {
      iframe.contentWindow?.postMessage({
        type: "pension-planner-state",
        payload: {
          accounts: accountOptions,
          ...request,
          calculation: calculation
            ? { ...calculation, selected_risk_profile: profile?.risk_profile }
            : null,
        },
      }, window.location.origin);
    };
    const calculate = async (request: PlannerRequest): Promise<void> => {
      currentRequestRef.current = request;
      if (!profile || !portfolio || accountOptions.length === 0) {
        postState(request, null);
        return;
      }
      const sequence = ++requestSequenceRef.current;
      try {
        const calculation = request.accountId === "all"
          ? await calculateCombinedPension({
              current_age: request.age,
              contribution_end_age: request.endAge,
              accounts: portfolio.accounts.map((account) => ({
                account_id: account.account_id,
                account_name: account.account_name,
                account_type: account.account_type,
                current_balance_krw: account.market_value_krw,
              })),
              risk_profile: profile.risk_profile,
              strategy_id: request.strategyId,
              payout_years: 25,
              scenario: "base",
            })
          : await (() => {
              const account = portfolio.accounts.find(
                (item) => item.account_id === request.accountId,
              );
              if (!account) throw new Error("selected account is unavailable");
              return calculatePension({
                current_age: request.age,
                contribution_end_age: request.endAge,
                current_balance_krw: account.market_value_krw,
                monthly_contribution_krw: String(request.monthly * 10_000),
                account_type: account.account_type,
                risk_profile: profile.risk_profile,
                strategy_id: request.strategyId,
                payout_years: 25,
                scenario: "base",
              });
            })();
        if (requestSequenceRef.current === sequence) {
          const resolvedRequest = request.strategyId
            ? request
            : {
                ...request,
                strategyId: calculation.strategies.find(
                  (strategy) => strategy.risk_profile === profile.risk_profile,
                )?.strategy_id ?? null,
              };
          currentRequestRef.current = resolvedRequest;
          postState(resolvedRequest, calculation);
        }
      } catch {
        if (requestSequenceRef.current === sequence) postState(request, null);
      }
    };
    const scheduleCalculation = (request: PlannerRequest): void => {
      if (debounceRef.current !== null) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => void calculate(request), 120);
    };
    const handleMessage = (event: MessageEvent): void => {
      if (
        event.source !== iframe.contentWindow
        || (event.origin && event.origin !== window.location.origin)
      ) return;
      if (event.data?.type === "pension-planner-ready") {
        void calculate(currentRequestRef.current);
      }
      if (event.data?.type === "pension-planner-calculate") {
        scheduleCalculation(event.data.payload as PlannerRequest);
      }
    };
    const handleFrameClick = (event: Event): void => {
      const target = event.target as {
        closest?: (selector: string) => Element | null;
      } | null;
      if (target?.closest?.("[data-pension-planner-back]")) onBackRef.current();
    };
    const connectFrame = (): void => {
      frameDocument?.removeEventListener("click", handleFrameClick);
      frameDocument = iframe.contentDocument;
      frameDocument?.addEventListener("click", handleFrameClick);
    };

    window.addEventListener("message", handleMessage);
    iframe.addEventListener("load", connectFrame);
    if (iframe.contentDocument?.readyState === "complete") {
      connectFrame();
      void calculate(currentRequestRef.current);
    }

    return () => {
      if (debounceRef.current !== null) clearTimeout(debounceRef.current);
      window.removeEventListener("message", handleMessage);
      iframe.removeEventListener("load", connectFrame);
      frameDocument?.removeEventListener("click", handleFrameClick);
    };
  }, [accountOptions, portfolio, profile]);

  return (
    <main className="pension-planner-stage">
      <section className="pension-planner-frame" aria-label="연금 계산기">
    <iframe
      ref={iframeRef}
      src={`${import.meta.env.BASE_URL}pension-calculator-html/연금계산기.dc.html`}
      style={{ border: 0, display: "block", height: "100%", width: "100%" }}
      title="예상 연금 계산 및 세액공제 확인"
    />
      </section>
    </main>
  );
}
