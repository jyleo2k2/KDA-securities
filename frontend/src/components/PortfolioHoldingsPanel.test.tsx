// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CompletedSurveyProfile, EducationalPortfolioEvaluation } from "../api/types";
import { EducationalPortfolioReview, PortfolioHoldingsPanel } from "./PortfolioHoldingsPanel";

const PROFILE: CompletedSurveyProfile = {
  account_type: "irp",
  account_types: ["irp", "pension_savings"],
  current_age: 35,
  retirement_start_age: 60,
  risk_profile: "risk_neutral",
  loss_tolerance_percent: "20",
};

afterEach(cleanup);

describe("PortfolioHoldingsPanel", () => {
  it("validates and submits current holdings with the completed profile", () => {
    const onAnalyze = vi.fn();
    render(<PortfolioHoldingsPanel surveyProfile={PROFILE} disabled={false} onAnalyze={onAnalyze} />);

    fireEvent.change(screen.getByLabelText("1번째 ETF 종목코드"), { target: { value: "069500" } });
    fireEvent.change(screen.getByLabelText("1번째 ETF 평가금액"), { target: { value: "10000000" } });
    fireEvent.change(screen.getByLabelText("이번 추가 납입 예정금액(원)"), { target: { value: "1000000" } });
    fireEvent.click(screen.getByRole("button", { name: "보유 ETF 분석하기" }));

    expect(onAnalyze).toHaveBeenCalledWith({
      account_type: "irp",
      age: 35,
      retirement_start_age: 60,
      risk_profile: "risk_neutral",
      loss_tolerance_percent: "20",
      max_etfs: 7,
      current_holdings: [{ isu_code: "069500", amount_krw: "10000000" }],
      new_contribution_krw: "1000000",
    });
  });

  it("rejects duplicate ETF codes before calling the engine", () => {
    const onAnalyze = vi.fn();
    render(<PortfolioHoldingsPanel surveyProfile={PROFILE} disabled={false} onAnalyze={onAnalyze} />);

    fireEvent.change(screen.getByLabelText("1번째 ETF 종목코드"), { target: { value: "069500" } });
    fireEvent.change(screen.getByLabelText("1번째 ETF 평가금액"), { target: { value: "10000000" } });
    fireEvent.click(screen.getByRole("button", { name: "+ ETF 추가" }));
    fireEvent.change(screen.getByLabelText("2번째 ETF 종목코드"), { target: { value: "069500" } });
    fireEvent.change(screen.getByLabelText("2번째 ETF 평가금액"), { target: { value: "5000000" } });
    fireEvent.click(screen.getByRole("button", { name: "보유 ETF 분석하기" }));

    expect(screen.getByRole("alert")).toHaveTextContent("같은 ETF는 평가금액을 합쳐 한 줄로 입력해 주세요.");
    expect(onAnalyze).not.toHaveBeenCalled();
  });
});

describe("EducationalPortfolioReview", () => {
  it("shows account limits, sleeve drift, and overlap limitations from engine output", () => {
    const evaluation = {
      engine_name: "educational_portfolio",
      engine_version: "test",
      policy_version: "test",
      usage_label: "교육용",
      evaluated_input: {
        account_type: "irp",
        age: 35,
        retirement_start_age: 60,
        risk_profile: "risk_neutral",
        loss_tolerance_percent: "20",
        current_holdings: [{ isu_code: "069500", amount_krw: "10000000" }],
        new_contribution_krw: "1000000",
      },
      strategy_label: "균형 코어·위성",
      retirement_start_age: 60,
      planning_horizon_years: 25,
      horizon_to_age_55_years: 20,
      horizon_to_age_60_years: 25,
      raw_risk_target_percent: "50.0000",
      final_general_risk_target_percent: "50.0000",
      account_risk_cap_percent: "70.0000",
      account_cap_binding: false,
      loss_tolerance_binding: false,
      stress_loss_proxy_percent: "20.0000",
      target_sleeves: [],
      candidates: [{
        isu_code: "069500",
        isu_name: "KODEX 200",
        sleeve: "core_equity",
        target_percent: "45.0000",
        quality: {},
        region: "domestic",
        strategy: "passive",
        max_correlation_with_selected: "82.0000",
        price_history_source: "KIS",
        account_eligibility: {},
        reasons: [],
      }],
      portfolio_risk: {
        engine_name: "historical_portfolio_risk",
        engine_version: "test",
        policy_version: "test",
        usage_label: "historical_risk_measurement_not_return_forecast",
        status: "complete",
        observation_count: 252,
        observation_start: "2025-07-01",
        observation_end: "2026-07-01",
        annualized_volatility_percent: "12.3000",
        annualized_downside_deviation_percent: "7.1000",
        maximum_drawdown_percent: "15.4000",
        historical_95pct_one_day_loss_percent: "1.7000",
        worst_daily_return_percent: "-3.2000",
        historical_return_used_for_risk_only: true,
        is_return_forecast: false,
        stress_scenarios: [{
          scenario_code: "equity_drawdown",
          estimated_loss_percent: "-18.5000",
          sleeve_shocks_percent: { core_equity: "-35.0000" },
          is_forecast: false,
        }],
        sources: [],
        warnings: [],
      },
      planning_return: {},
      rebalancing: {
        status: "calculated",
        drift_threshold_percent_points: "5.0000",
        current_total_krw: "10000000",
        new_contribution_krw: "1000000",
        projected_total_krw: "11000000",
        unclassified_holding_amount_krw: "0",
        contribution_first: true,
        sell_instruction_produced: false,
        sleeves: [{
          sleeve: "core_equity",
          target_percent: "45.0000",
          current_percent: "100.0000",
          projected_percent_after_contribution: "90.9000",
          drift_before_percent_points: "55.0000",
          drift_after_percent_points: "45.9000",
          contribution_example_krw: "0",
          status: "overweight",
        }],
        warnings: [],
      },
      sources: [],
      warnings: [],
    } satisfies EducationalPortfolioEvaluation;

    const { rerender } = render(<EducationalPortfolioReview evaluation={evaluation} />);

    expect(screen.getByText("70.0%")).toBeInTheDocument();
    expect(screen.getByText("분산 주식")).toBeInTheDocument();
    expect(screen.getByText(/최대 과거 가격 동행성은 82.0%/)).toBeInTheDocument();
    expect(screen.getByText(/구성종목 중복률이 아니라/)).toBeInTheDocument();
    expect(screen.getByText(/매도 주문을 만들지 않으며/)).toBeInTheDocument();
    expect(screen.getByText("12.3%")).toBeInTheDocument();
    expect(screen.getByText("주식시장 급락")).toBeInTheDocument();
    expect(screen.getByText("-18.5%")).toBeInTheDocument();
    expect(screen.getByText(/수익률 예측이 아닙니다/)).toBeInTheDocument();

    rerender(<EducationalPortfolioReview evaluation={{
      ...evaluation,
      portfolio_risk: {
        ...evaluation.portfolio_risk,
        status: "insufficient_common_history",
        observation_count: 20,
        annualized_volatility_percent: null,
        annualized_downside_deviation_percent: null,
        maximum_drawdown_percent: null,
        historical_95pct_one_day_loss_percent: null,
        worst_daily_return_percent: null,
      },
    }} />);
    expect(screen.getByText(/공통 일간 수익률이 60개 미만/)).toBeInTheDocument();
  });
});
