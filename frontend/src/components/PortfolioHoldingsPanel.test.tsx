// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  ChatVisualization,
  CompletedSurveyProfile,
  EducationalPortfolioEvaluation,
} from "../api/types";
import { EducationalPortfolioReview, PortfolioHoldingsPanel } from "./PortfolioHoldingsPanel";

const PROFILE: CompletedSurveyProfile = {
  account_type: "irp",
  account_types: ["irp", "pension_savings"],
  current_age: 35,
  retirement_start_age: 60,
  risk_profile: "risk_neutral",
  loss_tolerance_percent: "20",
};

const STRATEGY_VISUALIZATIONS: ChatVisualization[] = [
  {
    kind: "sleeve_allocation",
    title: "DC형 목표 자산배분",
    description: "규칙 엔진이 계산한 목표비중이에요.",
    data_boundary: "engine",
    evidence_ids: [],
    items: [
      { label: "주식", value: 48, unit: "%", role: "segment" },
      { label: "채권", value: 52, unit: "%", role: "segment" },
    ],
    series: [],
  },
  {
    kind: "stress_scenarios",
    title: "DC형 스트레스 점검",
    description: "규칙 엔진이 계산한 손실 추정치예요.",
    data_boundary: "engine",
    evidence_ids: [],
    items: [{ label: "주식시장 급락", value: 27.5, unit: "%", role: "value" }],
    series: [],
  },
  {
    kind: "sleeve_allocation",
    title: "연금저축펀드 목표 자산배분",
    description: "규칙 엔진이 계산한 목표비중이에요.",
    data_boundary: "engine",
    evidence_ids: [],
    items: [
      { label: "주식", value: 57.4, unit: "%", role: "segment" },
      { label: "채권", value: 42.6, unit: "%", role: "segment" },
    ],
    series: [],
  },
  {
    kind: "stress_scenarios",
    title: "연금저축펀드 스트레스 점검",
    description: "규칙 엔진이 계산한 손실 추정치예요.",
    data_boundary: "engine",
    evidence_ids: [],
    items: [{ label: "주식시장 급락", value: 30, unit: "%", role: "value" }],
    series: [],
  },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PortfolioHoldingsPanel", () => {
  it("omits the profile-completion card when no profile is available", () => {
    const { container } = render(
      <PortfolioHoldingsPanel surveyProfile={null} disabled={false} onAnalyze={vi.fn()} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

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
    const { rerender } = render(
      <EducationalPortfolioReview
        evaluation={noHoldingsEvaluation}
        visualizations={STRATEGY_VISUALIZATIONS}
      />,
    );

    expect(screen.getByText("위험중립형의 코어·위성 전략")).toBeInTheDocument();
    expect(screen.getByText(/분산 주식 ETF를 코어\(장기 기본 비중\)로 두고/)).toBeInTheDocument();
    expect(
      screen.getByText(/코어는 장기 분산투자, 위성은 제한된 비중의 보조 전략/),
    ).toBeInTheDocument();
    expect(screen.getByText("DC형 목표 자산배분")).toBeInTheDocument();
    expect(screen.getByText("DC형 스트레스 점검")).toBeInTheDocument();
    expect(screen.getByText("연금저축펀드 목표 자산배분")).toBeInTheDocument();
    expect(screen.getByText("연금저축펀드 스트레스 점검")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /주식 45.0%/ })).not.toBeInTheDocument();
    const orderedStrategyContent = [
      screen.getByText("코어·위성 전략"),
      screen.getByText("DC형 목표 자산배분"),
      screen.getByText("DC형 스트레스 점검"),
      screen.getByText("연금저축펀드 목표 자산배분"),
      screen.getByText("연금저축펀드 스트레스 점검"),
      screen.getByText(/^리밸런싱 주기:/),
      screen.getByText("두 가지 수익률 가정"),
    ];
    for (let index = 1; index < orderedStrategyContent.length; index += 1) {
      expect(
        orderedStrategyContent[index - 1].compareDocumentPosition(
          orderedStrategyContent[index],
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
    expect(screen.getByText("조심해서 계산한 경우")).toBeInTheDocument();
    expect(screen.getByText("기본으로 계산한 경우")).toBeInTheDocument();
    expect(screen.getByText(/CMA는 여러 자산의 10년 이상 장기 전망/)).toBeInTheDocument();
    expect(screen.queryByText("어떤 ETF 분야를 살펴볼까?")).not.toBeInTheDocument();
    expect(screen.queryByText(/이 서비스는 “이 ETF를 사세요”라고 정해 주지 않아요/)).not.toBeInTheDocument();
    expect(screen.queryByText("스태그플레이션")).not.toBeInTheDocument();

    rerender(<EducationalPortfolioReview evaluation={{
      ...noHoldingsEvaluation,
      evaluated_input: {
        ...noHoldingsEvaluation.evaluated_input,
        age: 42,
        retirement_start_age: 60,
        loss_tolerance_percent: "5",
      },
      planning_horizon_years: 18,
      raw_risk_target_percent: "48.5000",
      final_general_risk_target_percent: "0",
      loss_tolerance_binding: true,
      stress_loss_proxy_percent: "5.0000",
      target_sleeves: [{
        sleeve: "core_equity",
        target_percent: "0",
        risk_treatment: "general_risky",
        role: "long_term_growth_core",
      }, {
        sleeve: "real_assets",
        target_percent: "0",
        risk_treatment: "general_risky",
        role: "inflation_and_diversification",
      }, {
        sleeve: "tactical",
        target_percent: "0",
        risk_treatment: "general_risky",
        role: "capped_tactical_satellite",
      }, {
        sleeve: "fixed_income",
        target_percent: "62.5",
        risk_treatment: "defensive",
        role: "drawdown_buffer",
      }, {
        sleeve: "cash",
        target_percent: "37.5",
        risk_treatment: "defensive",
        role: "liquidity_and_rebalancing_reserve",
      }],
    }} />);

    expect(screen.getByText("위험중립형 · 손실감내도 우선 방어 배분")).toBeInTheDocument();
    expect(screen.getByText(/선택한 손실감내율 5.0%가 위험중립형의 기본 비중보다 우선 적용돼/)).toBeInTheDocument();
    expect(screen.getByText(/성장자산 비중을 48.5%에서 0.0%로 낮추고 채권과 현금성 자산 중심으로 조정/)).toBeInTheDocument();
    expect(screen.queryByText("위험중립형의 코어·위성 전략")).not.toBeInTheDocument();

    rerender(<EducationalPortfolioReview evaluation={{
      ...noHoldingsEvaluation,
      evaluated_input: {
        ...noHoldingsEvaluation.evaluated_input,
        age: 42,
        retirement_start_age: 60,
        loss_tolerance_percent: "15",
      },
      planning_horizon_years: 18,
      raw_risk_target_percent: "48.5000",
      final_general_risk_target_percent: "27.2000",
      loss_tolerance_binding: true,
      stress_loss_proxy_percent: "15.0000",
    }} />);

    expect(screen.getByText("위험중립형 · 손실감내도 반영 조정 배분")).toBeInTheDocument();
    expect(screen.getByText(/선택한 손실감내율 15.0%가 위험중립형의 기본 비중보다 우선 적용돼/)).toBeInTheDocument();
    expect(screen.getByText(/성장자산 비중을 48.5%에서 27.2%로 낮추고 나머지를 채권과 현금성 자산에 배분/)).toBeInTheDocument();
    expect(screen.queryByText("위험중립형의 코어·위성 전략")).not.toBeInTheDocument();

    const strategyCases = [
      ["stable", "안정형의 자본보전 중심 전략", "수익률 확대보다 손실과 가격 변동을 낮추는"],
      ["stable_seeking", "안정추구형의 방어적 분산 전략", "방어 자산을 중심으로 유지하면서 성장 자산을"],
      ["risk_neutral", "위험중립형의 코어·위성 전략", "코어는 장기 분산투자"],
      ["active", "적극투자형의 성장 코어·위성 전략", "성장 자산 비중이 높은 만큼 정기 점검"],
      ["aggressive", "공격투자형의 바벨형 성장·전술 전략", "성장 자산과 방어 자산의 역할을 분리해"],
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

    const sectorGuideTitle = screen.getByText("위험중립형 ETF 분야 예시");
    const cadenceTitle = screen.getByText("리밸런싱 주기: 3개월마다");
    const reviewLeadTitle = screen.getByText("먼저 볼 내용");
    expect(sectorGuideTitle.closest("details")).toBeNull();
    expect(cadenceTitle.closest("details")).toBeNull();
    expect(
      sectorGuideTitle.compareDocumentPosition(cadenceTitle)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      cadenceTitle.compareDocumentPosition(reviewLeadTitle)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByRole("img", { name: /채권 25%, 반도체 17%, 바이오·헬스케어 14%/ })).toBeInTheDocument();
    expect(screen.getByText(/실제 계산 결과나 계좌별 한도는 변경하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText("각 자산 유형별로 ±5.0%p만큼의 차이가 날 수 있어요.")).toBeInTheDocument();
    expect(screen.getByText("1개 자산군의 비중을 확인해 보세요")).toBeInTheDocument();
    const allocationTitle = screen.getByText("자산 구성과 조정 기준");
    const allocationSection = allocationTitle.closest("section");
    const evidenceDetails = screen.getByText("위험과 수익률 계산 근거").closest("details");
    expect(allocationTitle.closest("details")).toBeNull();
    expect(allocationSection).toHaveClass("portfolio-review-priority");
    expect(
      allocationTitle.compareDocumentPosition(sectorGuideTitle)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.queryByRole("columnheader", { name: "이탈폭" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "납입 후" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "추가 납입 예시" })).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "상태" })).toBeInTheDocument();
    expect(evidenceDetails).not.toHaveAttribute("open");

    expect(screen.getByText("70.0%")).toBeInTheDocument();
    expect(screen.getByText("핵심 주식")).toBeInTheDocument();
    expect(screen.queryByText("AI소프트웨어")).not.toBeInTheDocument();
    expect(screen.queryByText("코리아밸류업")).not.toBeInTheDocument();
    expect(screen.queryByText("ESG")).not.toBeInTheDocument();
    expect(screen.queryByText("운송 및 물류")).not.toBeInTheDocument();
    expect(screen.queryByText("여행 및 레저")).not.toBeInTheDocument();
    expect(screen.getByText(/과거에 같이 오르내린 정도는 최대 82.0%/)).toBeInTheDocument();
    expect(screen.getByText(/같은 회사가 몇 개 겹쳤는지를 뜻하는 숫자는 아니에요/)).toBeInTheDocument();
    expect(screen.getByText(/자동 매도하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText("12.3%")).toBeInTheDocument();
    expect(screen.getByText("주식이 크게 떨어질 때")).toBeInTheDocument();
    expect(screen.getByText("-18.5%")).toBeInTheDocument();
    expect(screen.getByText("내가 견딜 수 있다고 고른 범위 안")).toBeInTheDocument();
    expect(screen.getByText(/내가 고른 손실 범위 20.0%/)).toBeInTheDocument();
    expect(screen.getByText(/가장 큰 충격 가정 18.5%/)).toBeInTheDocument();
    expect(screen.getByText(/포트폴리오 위험정책/)).toBeInTheDocument();
    expect(screen.getByText(/미래 수익 예측은 아니에요/)).toBeInTheDocument();
    expect(screen.getAllByText(/미래 수익을 맞히는 값이 아닙니다/)).toHaveLength(2);
    expect(screen.getByText("현재 보유 ETF 장기 계산용 숫자")).toBeInTheDocument();
    expect(screen.getByText("목표 포트폴리오 장기 계산용 숫자")).toBeInTheDocument();
    expect(screen.getAllByText("6.7%")).toHaveLength(2);
    expect(screen.getAllByText("6.2%")).toHaveLength(4);
    expect(screen.getAllByText(/비슷한 자산의 장기 전망 사용/)).toHaveLength(2);
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
    expect(screen.getByText("내가 고른 손실 범위를 다시 확인할 때")).toBeInTheDocument();
    expect(screen.getAllByText(/자동 매도/)).toHaveLength(2);

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
    expect(screen.getByText("공격투자형 ETF 분야 예시")).toBeInTheDocument();
    expect(screen.getByText("양자컴퓨팅")).toBeInTheDocument();
    expect(screen.getByText("기타 시장 충격")).toBeInTheDocument();
    expect(screen.getByText("기타 자산군")).toBeInTheDocument();
    expect(screen.getByText("추가 점검 필요")).toBeInTheDocument();
    expect(screen.queryByText("unmapped_market_shock")).not.toBeInTheDocument();
    expect(screen.queryByText("unmapped_sleeve")).not.toBeInTheDocument();
    expect(screen.queryByText("unmapped_status")).not.toBeInTheDocument();
  });
});
