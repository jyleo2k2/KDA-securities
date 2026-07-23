// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

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

  it("calculates a pension plan from current ETF value weights", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      calculator: {
        headline: {
          total_krw: "50000000",
          monthly_payout_pretax_krw: "200000",
          monthly_payout_after_tax_krw: "189000",
        },
        assumption: {
          source: {
            label: "CMA source",
            reference: "https://example.com/cma",
            as_of: "2026-07-16",
          },
          notice: "This is a planning assumption, not a forecast.",
        },
      },
      planning_return: {
        net_planning_return_percent: "5.2000",
        sources: [],
      },
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<PortfolioHoldingsPanel surveyProfile={PROFILE} disabled={false} onAnalyze={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("1번째 ETF 종목코드"), { target: { value: "069500" } });
    fireEvent.change(screen.getByLabelText("1번째 ETF 평가금액"), { target: { value: "10000000" } });
    fireEvent.change(screen.getByLabelText("월 납입액"), { target: { value: "300000" } });
    fireEvent.change(screen.getByLabelText("수령기간"), { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: "보유 ETF 기준 수령 계획 계산" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/engine/pension-calculator/portfolio-cma",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          calculator: {
            current_age: 35,
            contribution_end_age: 60,
            current_balance_krw: "10000000",
            monthly_contribution_krw: "300000",
            account_type: "irp",
            risk_profile: "risk_neutral",
            payout_years: 25,
            scenario: "base",
          },
          current_holdings: [{ isu_code: "069500", amount_krw: "10000000" }],
        }),
      }),
    );
    expect(await screen.findByText("장기 수령 계획 예시")).toBeInTheDocument();
    expect(screen.getByText("50,000,000원")).toBeInTheDocument();
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
      target_sleeves: [{
        sleeve: "core_equity",
        target_percent: "45.0000",
        risk_treatment: "general_risky",
        role: "long_term_growth_core",
      }, {
        sleeve: "real_assets",
        target_percent: "5.0000",
        risk_treatment: "general_risky",
        role: "inflation_and_diversification",
      }, {
        sleeve: "tactical",
        target_percent: "0.0000",
        risk_treatment: "general_risky",
        role: "capped_tactical_satellite",
      }, {
        sleeve: "fixed_income",
        target_percent: "43.0000",
        risk_treatment: "defensive",
        role: "drawdown_buffer",
      }, {
        sleeve: "cash",
        target_percent: "7.0000",
        risk_treatment: "defensive",
        role: "liquidity_and_rebalancing_reserve",
      }],
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
        stress_loss_limit_percent: "20.0000",
        worst_stress_loss_percent: "18.5000",
        stress_loss_policy_status: "within_user_limit",
        sources: [{
          label: "포트폴리오 위험정책",
          reference: "docs/30_스펙/포트폴리오_위험정책_계약.md",
          as_of: "2026-07-22",
        }],
        warnings: [],
      },
      planning_return: {
        engine_name: "portfolio_long_term_planning_return",
        engine_version: "test",
        policy_version: "test",
        cma_policy_id: "jpm_2026_usd_educational_v1",
        cma_policy_status: "approved_for_educational_planning_only",
        usage_label: "annualized_long_term_planning_assumption_not_forecast",
        retirement_start_age: 60,
        portfolio_horizon_years: 25,
        cma_source_horizon_min_years: 10,
        cma_source_horizon_max_years: 15,
        annual_review_required: true,
        coverage_weight_percent: "45.0000",
        gross_planning_return_percent: "6.3000",
        net_planning_return_percent: "6.2000",
        conservative_planning_return_percent: "6.2000",
        base_planning_return_percent: "6.7000",
        is_forecast: false,
        historical_performance_used: false,
        risk_adjustment_included: false,
        components: [{
          isu_code: "069500",
          isu_name: "KODEX 200",
          sleeve: "core_equity",
          target_percent: "45.0000",
          cma_assumption_code: "us_large_cap",
          cma_percent: "6.8000",
          uncertainty_discount_percent: "0.5000",
          annual_cost_drag_percent: "0.1000",
          gross_planning_return_percent: "6.3000",
          net_planning_return_percent: "6.2000",
          proxy_used: true,
          warnings: [],
        }],
        sources: [{
          label: "J.P. Morgan 2026 Long-Term Capital Market Assumptions",
          reference: "https://example.com/cma",
          as_of: "2025-09-30",
        }, {
          label: "연금 코파일럿 CMA 매핑·불확실성 할인 정책",
          reference: "backend/app/engine/educational_portfolio.py",
          as_of: "2026-07-16",
        }, {
          label: "계좌별 ETF 비용 마스터",
          reference: "data/cache/returns",
          as_of: "2026-07-16",
        }],
        warnings: [],
      },
      rebalancing: {
        status: "calculated",
        drift_threshold_percent_points: "5.0000",
        cadence: {
          review_interval_months: 3,
          drift_threshold_percent_points: "5.0000",
          rationale: "성장·방어 자산을 함께 쓰므로 분기마다 균형이 흐트러졌는지 확인해요.",
        },
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

    const evaluationWithCurrentHoldingsPlanning = {
      ...evaluation,
      current_holdings_planning_return: evaluation.planning_return,
    };
    const noHoldingsEvaluation = {
      ...evaluation,
      evaluated_input: {
        ...evaluation.evaluated_input,
        current_holdings: [],
        new_contribution_krw: "0",
      },
      rebalancing: {
        ...evaluation.rebalancing,
        status: "not_requested",
        current_total_krw: "0",
        new_contribution_krw: "0",
        projected_total_krw: "0",
        sleeves: [],
      },
    } satisfies EducationalPortfolioEvaluation;
    const { rerender } = render(<EducationalPortfolioReview evaluation={noHoldingsEvaluation} />);

    expect(screen.getByText("위험중립형의 코어·위성 전략")).toBeInTheDocument();
    expect(screen.getByText(/광범위한 주식 ETF를 장기 성장의 코어로 두고/)).toBeInTheDocument();
    expect(screen.getByText(/큰 기본 식사에 작은 반찬을 더하는 전략/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /분산 주식 45.0%, 금·리츠 5.0%, 채권 43.0%, 현금성 7.0%/ })).toBeInTheDocument();
    expect(screen.getByText("보수 계획수익률")).toBeInTheDocument();
    expect(screen.getByText("기준 계획수익률")).toBeInTheDocument();
    expect(screen.getByText(/J.P. Morgan의 LTCMA 장기 자본시장 가정/)).toBeInTheDocument();
    expect(screen.getByText("그러면 어떤 종목을 살까?")).toBeInTheDocument();
    expect(screen.getByText(/ETF 섹터 알아보기에서 각 자산 분류를 채울 ETF 테마/)).toBeInTheDocument();
    expect(screen.queryByText("스태그플레이션")).not.toBeInTheDocument();

    const strategyCases = [
      ["stable", "안정형의 자본보전 중심 전략", "우산, 우비, 여벌 옷"],
      ["stable_seeking", "안정추구형의 방어적 분산 전략", "날씨가 좋으면 조금 더 멀리"],
      ["risk_neutral", "위험중립형의 코어·위성 전략", "큰 기본 식사에 작은 반찬"],
      ["active", "적극투자형의 성장 코어·위성 전략", "작은 도전도 조금 늘리는 전략"],
      ["aggressive", "공격투자형의 바벨형 성장·전술 전략", "양쪽 끝에 무게가 달린 긴 막대"],
    ] as const;
    for (const [riskProfile, title, analogy] of strategyCases) {
      rerender(<EducationalPortfolioReview evaluation={{
        ...noHoldingsEvaluation,
        evaluated_input: {
          ...noHoldingsEvaluation.evaluated_input,
          risk_profile: riskProfile,
        },
      }} />);
      expect(screen.getByText(title)).toBeInTheDocument();
      expect(screen.getByText(new RegExp(analogy))).toBeInTheDocument();
    }

    rerender(<EducationalPortfolioReview evaluation={evaluationWithCurrentHoldingsPlanning} />);

    expect(screen.getByText("70.0%")).toBeInTheDocument();
    expect(screen.getByText("분산 주식")).toBeInTheDocument();
    expect(screen.getByText("위험중립형 섹터 가이드")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /채권 25%, 반도체 17%, 바이오·헬스케어 14%/ })).toBeInTheDocument();
    expect(screen.getByText(/실제 엔진 목표비중·후보 ETF·계좌 한도는 바꾸지 않습니다/)).toBeInTheDocument();
    expect(screen.queryByText("AI소프트웨어")).not.toBeInTheDocument();
    expect(screen.queryByText("코리아밸류업")).not.toBeInTheDocument();
    expect(screen.queryByText("ESG")).not.toBeInTheDocument();
    expect(screen.queryByText("운송 및 물류")).not.toBeInTheDocument();
    expect(screen.queryByText("여행 및 레저")).not.toBeInTheDocument();
    expect(screen.getByText(/최대 과거 가격 동행성은 82.0%/)).toBeInTheDocument();
    expect(screen.getByText(/구성종목 중복률이 아니라/)).toBeInTheDocument();
    expect(screen.getByText(/매도 주문을 만들지 않으며/)).toBeInTheDocument();
    expect(screen.getByText("3개월마다 비중 점검")).toBeInTheDocument();
    expect(screen.getByText(/목표비중은 연령·수령 시점·투자성향·계좌 한도로/)).toBeInTheDocument();
    expect(screen.getByText("12.3%")).toBeInTheDocument();
    expect(screen.getByText("주식시장 급락")).toBeInTheDocument();
    expect(screen.getByText("-18.5%")).toBeInTheDocument();
    expect(screen.getByText("손실감내도 기준 이내")).toBeInTheDocument();
    expect(screen.getByText(/사용자 손실감내도 20.0%/)).toBeInTheDocument();
    expect(screen.getByText(/최악 정책 스트레스 손실 18.5%/)).toBeInTheDocument();
    expect(screen.getByText(/포트폴리오 위험정책/)).toBeInTheDocument();
    expect(screen.getAllByText(/수익률 예측이 아닙니다/)).toHaveLength(3);
    expect(screen.getByText("현재 보유 ETF CMA·비용 계획가정")).toBeInTheDocument();
    expect(screen.getByText("제안 포트폴리오 CMA·비용 계획가정")).toBeInTheDocument();
    expect(screen.getAllByText("6.7%")).toHaveLength(2);
    expect(screen.getAllByText("6.2%")).toHaveLength(4);
    expect(screen.getAllByText(/대체 CMA/)).toHaveLength(2);
    expect(screen.getAllByText("-0.5%")).toHaveLength(2);
    expect(screen.getAllByText("-0.1%")).toHaveLength(2);
    expect(screen.getAllByText(/과거 수익률 미사용/)).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: /J.P. Morgan 2026/ })).toHaveLength(2);

    rerender(<EducationalPortfolioReview evaluation={{
      ...evaluation,
      portfolio_risk: {
        ...evaluation.portfolio_risk,
        worst_stress_loss_percent: "24.0000",
        stress_loss_policy_status: "review_required",
      },
    }} />);
    expect(screen.getByText("손실감내도 재점검 필요")).toBeInTheDocument();
    expect(screen.getByText(/자동 매도 지시는 만들지 않습니다/)).toBeInTheDocument();

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

    rerender(<EducationalPortfolioReview evaluation={{
      ...evaluation,
      evaluated_input: {
        ...evaluation.evaluated_input,
        risk_profile: "aggressive",
      },
      strategy_label: "balanced_core_satellite",
      portfolio_risk: {
        ...evaluation.portfolio_risk,
        stress_scenarios: [{
          ...evaluation.portfolio_risk.stress_scenarios[0],
          scenario_code: "unmapped_market_shock",
        }],
      },
      rebalancing: {
        ...evaluation.rebalancing,
        sleeves: [{
          ...evaluation.rebalancing.sleeves[0],
          sleeve: "unmapped_sleeve",
          status: "unmapped_status",
        }],
      },
    }} />);
    expect(screen.getByText(/코어·위성 전략/)).toBeInTheDocument();
    expect(screen.getByText("공격투자형 섹터 가이드")).toBeInTheDocument();
    expect(screen.getByText("양자컴퓨팅")).toBeInTheDocument();
    expect(screen.getByText("기타 시장 충격")).toBeInTheDocument();
    expect(screen.getByText("기타 자산군")).toBeInTheDocument();
    expect(screen.getByText("추가 점검 필요")).toBeInTheDocument();
    expect(screen.queryByText("unmapped_market_shock")).not.toBeInTheDocument();
    expect(screen.queryByText("unmapped_sleeve")).not.toBeInTheDocument();
    expect(screen.queryByText("unmapped_status")).not.toBeInTheDocument();
  });
});
