import { useEffect, useMemo, useRef, type JSX } from "react";

import {
  calculateCombinedPension,
  calculatePension,
  calculatePensionTaxCredit,
} from "../api/client";
import type {
  AggregationEvaluation,
  DemoUserFinancialContext,
  IncomeBasis,
  PensionCalculatorEvaluation,
  PensionTaxCreditEvaluation,
  RiskProfile,
  UserPensionPortfolio,
} from "../api/types";
import { plannerAccountOptions } from "../ownerPensionPortfolio";
import { STRATEGIES } from "./strategyExplore/strategies";

const MAX_CONTRIBUTION_END_AGE = 65;
const PLANNER_THEME_STRATEGIES = STRATEGIES.map((strategy) => ({
  id: strategy.id,
  implementation: strategy.directness,
  name: strategy.name,
}));

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
  themeId: string;
}

interface PensionPlannerPageProps {
  profile: PensionPlannerProfile | null;
  portfolio: UserPensionPortfolio | null;
  aggregation: AggregationEvaluation | null;
  financialContext: DemoUserFinancialContext | null;
  onBack: () => void;
}

interface PlannerTaxRequest {
  incomeBasis: Exclude<IncomeBasis, "unknown"> | null;
  incomeAmountManwon: number | null;
  paidP: number;
  paidI: number;
  isa: number;
}

export function PensionPlannerPage({
  profile,
  portfolio,
  aggregation,
  financialContext,
  onBack,
}: PensionPlannerPageProps): JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const onBackRef = useRef(onBack);
  const requestSequenceRef = useRef(0);
  const taxRequestSequenceRef = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const taxDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const taxCalculationRef = useRef<PensionTaxCreditEvaluation | null>(null);
  const accountOptions = useMemo(
    () => portfolio && aggregation
      ? plannerAccountOptions(portfolio, aggregation)
      : [],
    [aggregation, portfolio],
  );
  const defaultRequest = useMemo<PlannerRequest>(() => ({
    accountId: "all",
    age: profile?.current_age ?? 35,
    endAge: Math.min(
      MAX_CONTRIBUTION_END_AGE,
      Math.max(60, (profile?.current_age ?? 35) + 1),
    ),
    monthly: 0,
    strategyId: null,
    themeId: PLANNER_THEME_STRATEGIES[0].id,
  }), [profile?.current_age]);
  const currentRequestRef = useRef(defaultRequest);
  const initialTaxRequest = useMemo<PlannerTaxRequest>(() => ({
    incomeBasis: null,
    incomeAmountManwon: financialContext
      ? Number(financialContext.income_amount_krw) / 10_000
      : null,
    paidP: financialContext
      ? Number(financialContext.pension_savings_contribution_krw) / 10_000
      : 0,
    paidI: financialContext
      ? Number(financialContext.irp_contribution_krw) / 10_000
      : 0,
    isa: 0,
  }), [financialContext]);

  useEffect(() => {
    onBackRef.current = onBack;
  }, [onBack]);

  useEffect(() => {
    currentRequestRef.current = defaultRequest;
  }, [defaultRequest]);

  useEffect(() => {
    taxCalculationRef.current = null;
  }, [financialContext?.auth_user_id]);

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
          themeStrategies: PLANNER_THEME_STRATEGIES,
          taxContext: financialContext
            ? {
                ownerId: financialContext.auth_user_id,
                incomeBasis: financialContext.income_basis,
                incomeAmountManwon: initialTaxRequest.incomeAmountManwon,
                paidP: initialTaxRequest.paidP,
                paidI: initialTaxRequest.paidI,
              }
            : null,
          taxCalculation: taxCalculationRef.current,
          ...request,
          calculation: calculation
            ? { ...calculation, selected_risk_profile: profile?.risk_profile }
            : null,
        },
      }, window.location.origin);
    };
    const postTaxState = (
      request: PlannerTaxRequest,
      calculation: PensionTaxCreditEvaluation | null,
    ): void => {
      iframe.contentWindow?.postMessage({
        type: "pension-planner-tax-state",
        payload: { ...request, calculation },
      }, window.location.origin);
    };
    const calculateTax = async (request: PlannerTaxRequest): Promise<void> => {
      if (!financialContext) {
        postTaxState(request, null);
        return;
      }
      const sequence = ++taxRequestSequenceRef.current;
      try {
        const calculation = await calculatePensionTaxCredit({
          tax_year: 2026,
          income_basis: request.incomeBasis ?? "unknown",
          income_amount_krw: request.incomeBasis && request.incomeAmountManwon !== null
            ? String(Math.round(request.incomeAmountManwon * 10_000))
            : null,
          pension_savings_contribution_krw: String(Math.round(request.paidP * 10_000)),
          irp_contribution_krw: String(Math.round(request.paidI * 10_000)),
          dc_employee_additional_contribution_krw: "0",
          isa_maturity_transfer_krw: String(Math.round(request.isa * 10_000)),
          isa_transfer_eligibility_status: request.isa > 0 ? "eligible" : "none",
        });
        if (taxRequestSequenceRef.current === sequence) {
          taxCalculationRef.current = calculation;
          postTaxState(request, calculation);
        }
      } catch {
        if (taxRequestSequenceRef.current === sequence) {
          taxCalculationRef.current = null;
          postTaxState(request, null);
        }
      }
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
        void calculateTax(initialTaxRequest);
      }
      if (event.data?.type === "pension-planner-calculate") {
        scheduleCalculation(event.data.payload as PlannerRequest);
      }
      if (event.data?.type === "pension-planner-tax-calculate") {
        if (taxDebounceRef.current !== null) clearTimeout(taxDebounceRef.current);
        const request = event.data.payload as PlannerTaxRequest;
        taxDebounceRef.current = setTimeout(() => void calculateTax(request), 120);
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
      if (taxDebounceRef.current !== null) clearTimeout(taxDebounceRef.current);
      window.removeEventListener("message", handleMessage);
      iframe.removeEventListener("load", connectFrame);
      frameDocument?.removeEventListener("click", handleFrameClick);
    };
  }, [
    accountOptions,
    financialContext,
    initialTaxRequest,
    portfolio,
    profile,
  ]);

  return (
    <main className="app-phone-stage pension-planner-stage">
      <section className="app-phone-frame pension-planner-frame" aria-label="연금 계산기">
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
