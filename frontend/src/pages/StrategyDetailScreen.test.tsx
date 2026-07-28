// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getStrategyPlanningReturns } from "../api/client";
import type {
  AggregationEvaluation,
  StrategyPlanningReturnEvaluation,
  UserPensionPortfolio,
} from "../api/types";
import { StrategyDetailScreen } from "./StrategyDetailScreen";

vi.mock("../api/client", () => ({
  getStrategyPlanningReturns: vi.fn(),
}));

const planningReturnSources = [
  {
    label: "홈 전략 카드 대표구성 정책",
    reference: "strategy-planning-return",
    as_of: "2026-07-24",
  },
];

const stressSource = {
  label: "연금 코파일럿 포트폴리오 스트레스 정책",
  reference: "portfolio-risk-policy",
  as_of: "2026-07-22",
};

function stressRisk(
  worstEstimatedLossPercent: string,
  rateInflationLossPercent: string,
  stagflationLossPercent: string,
): StrategyPlanningReturnEvaluation["stress_risk"] {
  return {
    worst_scenario_code: "equity_drawdown",
    worst_estimated_loss_percent: worstEstimatedLossPercent,
    scenarios: [
      {
        scenario_code: "equity_drawdown",
        estimated_loss_percent: worstEstimatedLossPercent,
      },
      {
        scenario_code: "rate_inflation_shock",
        estimated_loss_percent: rateInflationLossPercent,
      },
      {
        scenario_code: "stagflation",
        estimated_loss_percent: stagflationLossPercent,
      },
    ],
    policy_version: "2026-07-23.1",
    source: stressSource,
    representative_basket_only: true,
    is_forecast: false,
  };
}

const planningReturns: StrategyPlanningReturnEvaluation[] = [
  {
    strategy_id: "market_beta",
    cma_weighted_return_percent: "6.0000",
    uncertainty_discount_percent: "0.2500",
    net_planning_return_percent: "5.7500",
    components: [{ cma_bucket: "global_equity", target_percent: "100", cma_percent: "6" }],
    stress_risk: stressRisk("35.0000", "15.0000", "20.0000"),
    cma_policy_id: "policy",
    policy_version: "2026-07-24.1",
    sources: planningReturnSources,
    annual_review_required: true,
    is_forecast: false,
    warnings: [],
  },
  {
    strategy_id: "factor",
    cma_weighted_return_percent: "6.0000",
    uncertainty_discount_percent: "0.4000",
    net_planning_return_percent: "5.6000",
    components: [{ cma_bucket: "global_equity", target_percent: "100", cma_percent: "6" }],
    stress_risk: stressRisk("35.0000", "15.0000", "20.0000"),
    cma_policy_id: "policy",
    policy_version: "2026-07-24.1",
    sources: planningReturnSources,
    annual_review_required: true,
    is_forecast: false,
    warnings: [],
  },
  {
    strategy_id: "thematic",
    cma_weighted_return_percent: "6.0000",
    uncertainty_discount_percent: "1.0000",
    net_planning_return_percent: "5.0000",
    components: [{ cma_bucket: "global_equity", target_percent: "100", cma_percent: "6" }],
    stress_risk: stressRisk("35.0000", "15.0000", "20.0000"),
    cma_policy_id: "policy",
    policy_version: "2026-07-24.1",
    sources: planningReturnSources,
    annual_review_required: true,
    is_forecast: false,
    warnings: [],
  },
  {
    strategy_id: "barbell",
    cma_weighted_return_percent: "5.0000",
    uncertainty_discount_percent: "0.7500",
    net_planning_return_percent: "4.2500",
    components: [
      { cma_bucket: "global_equity", target_percent: "50", cma_percent: "6" },
      { cma_bucket: "us_10y_treasury", target_percent: "30", cma_percent: "4" },
      { cma_bucket: "cash", target_percent: "20", cma_percent: "3" },
    ],
    stress_risk: stressRisk("19.9000", "10.5000", "12.4000"),
    cma_policy_id: "policy",
    policy_version: "2026-07-24.1",
    sources: planningReturnSources,
    annual_review_required: true,
    is_forecast: false,
    warnings: [],
  },
];

const pensionAggregation: AggregationEvaluation = {
  engine_name: "portfolio_aggregation",
  engine_version: "2026-07-15.1",
  total_amount_krw: "12400000",
  asset_class_totals: [
    { asset_class: "bond", amount_krw: "2232000", weight_percent: "18" },
    { asset_class: "domestic_equity", amount_krw: "5208000", weight_percent: "42" },
    { asset_class: "cash", amount_krw: "1736000", weight_percent: "14" },
    { asset_class: "global_equity", amount_krw: "3224000", weight_percent: "26" },
  ],
  per_account: [],
  overlaps: [],
  notice: "합산 수치는 표시용입니다.",
  evidence: [],
};

const pensionPortfolio: UserPensionPortfolio = {
  owner_id: "owner-1",
  data_boundary: "real",
  accounts: [
    {
      account_id: "account-1",
      account_type: "irp",
      account_name: "IRP",
      data_kind: "real",
      origin: "provider_import",
      snapshot_id: "snapshot-1",
      as_of_date: "2026-07-26",
      contributed_principal_krw: "12000000",
      market_value_krw: "12400000",
      holdings: [],
    },
  ],
};

beforeEach(() => {
  vi.mocked(getStrategyPlanningReturns).mockResolvedValue(planningReturns);
});

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("StrategyDetailScreen", () => {
  it("returns to the strategy list from the back button", () => {
    const onBack = vi.fn();

    render(<StrategyDetailScreen onBack={onBack} />);
    fireEvent.click(screen.getByRole("button", { name: "뒤로 가기" }));

    expect(onBack).toHaveBeenCalledOnce();
  });

  it("explains the selected strategy in the intended reading order", async () => {
    window.location.hash = "#/strategy-detail?strategy=factor";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(document.querySelector(".sd-brand")).toHaveTextContent("연금 KDA");
    expect(screen.getByText("제휴 투자전략")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("팩터 전략");
    expect(document.querySelector(".sd-hero")).toHaveTextContent(
      /재무·가치·추세 등 기업 특성으로 ETF를 고릅니다/,
    );
    expect(document.querySelector(".sd-desc")?.querySelectorAll(".sd-highlight").length).toBeGreaterThan(0);
    expect(screen.queryByText("구현 방법")).not.toBeInTheDocument();

    const timeline = screen.getByRole("list", { name: "전략 이해 순서" });
    const headings = within(timeline)
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);

    expect(headings).toEqual([
      "이 전략은 이렇게 운용해요",
      "이런 운용 방식을 원한다면 살펴보세요",
      "내 연금과 자산군 비교",
      "장점과 위험을 함께 확인해요",
    ]);
    expect(timeline).toHaveTextContent(/코어 자산을 보완/);
    expect(timeline).toHaveTextContent("기업 특성");
    expect(timeline).toHaveTextContent(/정해 둔 기업 특성을 가진 종목/);
    expect(timeline).toHaveTextContent(/시장 전체 투자에 기업의 재무·가치·추세 기준을 더해/);
    expect(timeline.querySelectorAll(".sd-step-keyword")).toHaveLength(4);
    expect(timeline).toHaveTextContent("1단계 · 운용 방식");
    expect(timeline).toHaveTextContent("2단계 · 이런 분께 좋아요");
    expect(timeline).toHaveTextContent("3단계 · 자산군 비교");
    expect(timeline).toHaveTextContent("4단계 · 장단점과 위험");
    expect(timeline).toHaveTextContent(/기업 특성을 정해진 기준으로 선별/);
    expect(timeline).toHaveTextContent(/선택한 팩터의 부진이 오래 이어질 수 있고/);
    expect(timeline).toHaveTextContent("결정 전에 확인할 3가지");
    expect(timeline.querySelectorAll(".sd-highlight").length).toBeGreaterThan(0);
    expect(await screen.findByText("국내 상장 해외주식형 ETF·공모펀드")).toBeInTheDocument();
  });

  it("shows theme engine composition, age allocation, and suitable profile in the reading flow", async () => {
    window.location.hash = "#/strategy-detail?strategy=theme";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.getByText(/적합 투자성향 · 공격투자형/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "내 연금과 자산군 비교" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "테마 전략 편입 상품군" })).toBeInTheDocument();
    expect(screen.getByText("국내 상장 해외주식형 ETF·공모펀드").parentElement).toHaveTextContent("100%");
    expect(screen.getByText(/기준: 홈 전략 카드 대표구성 정책 · 2026.07.24/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "연령대별 테마 활용 비중 예시" })).toBeInTheDocument();
    expect(screen.getByText("공격투자형 운용안")).toBeInTheDocument();
    expect(screen.getByText("20대").parentElement).toHaveTextContent("10%");
    expect(screen.getByText("30대").parentElement).toHaveTextContent("8%");
    expect(screen.getByText("40대").parentElement).toHaveTextContent("4%");
    expect(screen.getByText("50~54세").parentElement).toHaveTextContent("2%");
    expect(screen.getByText("AI")).toBeInTheDocument();
    expect(screen.getByText("반도체")).toBeInTheDocument();
    expect(screen.getByText(/기준: 연금 KDA 공격형 전략 운용안/)).toBeInTheDocument();
    expect(screen.queryByText("구현 방법")).not.toBeInTheDocument();
  });

  it("shows all engine-applied asset classes for a mixed strategy", async () => {
    window.location.hash = "#/strategy-detail?strategy=barbell";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(await screen.findByText("국내 상장 해외주식형 ETF·공모펀드")).toBeInTheDocument();
    expect(screen.getByText("국내 상장 해외주식형 ETF·공모펀드").parentElement).toHaveTextContent("50%");
    expect(screen.getByText("국내 상장 해외채권형 ETF·공모펀드").parentElement).toHaveTextContent("30%");
    expect(screen.getByText("현금성 자산").parentElement).toHaveTextContent("20%");
    expect(screen.queryByText("global_equity")).not.toBeInTheDocument();
  });

  it("shows the policy stress loss for every strategy without presenting it as a limit", async () => {
    window.location.hash = "#/strategy-detail?strategy=barbell";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    const riskCard = (await screen.findByRole("heading", { name: "정책 스트레스 시나리오" }))
      .closest(".sd-stress-risk");
    expect(riskCard).not.toBeNull();
    expect(riskCard).toHaveTextContent("19.9%");
    expect(riskCard).toHaveTextContent("가장 큰 손실 · 주식 급락");
    expect(riskCard).toHaveTextContent(/바벨 전략의 대표 구성에 적용한 참고값/);
    expect(riskCard).toHaveTextContent(/미래 최대손실, 손실 한도를 뜻하지 않으며/);
    expect(riskCard).toHaveTextContent(/실제 손실은 더 커질 수 있어요/);
    expect(riskCard).toHaveTextContent(
      "기준: 연금 코파일럿 포트폴리오 스트레스 정책 · 2026.07.22",
    );

    fireEvent.click(within(riskCard as HTMLElement).getByText("시나리오별 손실 추정치 보기"));
    expect(within(riskCard as HTMLElement).getByText("주식 급락").parentElement)
      .toHaveTextContent("19.9%");
    expect(within(riskCard as HTMLElement).getByText("금리·물가 충격").parentElement)
      .toHaveTextContent("10.5%");
    expect(within(riskCard as HTMLElement).getByText("경기 둔화·고물가").parentElement)
      .toHaveTextContent("12.4%");
  });

  it("connects the strategy composition with the signed-in owner's pension allocation", async () => {
    window.location.hash = "#/strategy-detail?strategy=barbell";

    render(
      <StrategyDetailScreen
        aggregation={pensionAggregation}
        onBack={vi.fn()}
        portfolio={pensionPortfolio}
      />,
    );

    expect(screen.getByRole("heading", { name: "내 연금과 자산군 비교" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "내 연금 현재 구성" })).toBeInTheDocument();
    expect(screen.getByText("12,400,000원")).toBeInTheDocument();
    expect(screen.getByLabelText(/내 연금 현재 자산군 구성/)).toHaveAttribute(
      "aria-label",
      expect.stringContaining("국내주식형 ETF·펀드 42%"),
    );
    const currentPensionPanel = screen
      .getByRole("heading", { name: "내 연금 현재 구성" })
      .closest(".sd-comparison-panel");
    expect(currentPensionPanel).not.toBeNull();
    expect(
      within(currentPensionPanel as HTMLElement)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "국내주식형 ETF·펀드42%",
      "해외주식형 ETF·펀드26%",
      "채권형 ETF·펀드18%",
      "현금성14%",
    ]);
    expect(
      [...(currentPensionPanel as HTMLElement).querySelectorAll(".sd-composition-bar > span")]
        .map((segment) => (segment as HTMLElement).style.width),
    ).toEqual(["42%", "26%", "18%", "14%"]);
    expect(screen.getByText(/기준: 연결된 연금계좌 합산 · 2026.07.26/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "바벨 전략 편입 상품군" })).toBeInTheDocument();
    expect(screen.getByLabelText(/바벨 전략 연금계좌 편입 상품군 구성/)).toHaveAttribute(
      "aria-label",
      expect.stringContaining("해외채권형 ETF·공모펀드 30%"),
    );
    expect(screen.queryByText(/내 연금 비중을 자동으로 변경하지 않아요/)).not.toBeInTheDocument();
    expect(screen.queryByText(/연금계좌에서는 이렇게 투자해요/)).not.toBeInTheDocument();
  });

  it("keeps a clear state when the engine composition cannot be loaded", async () => {
    vi.mocked(getStrategyPlanningReturns).mockRejectedValueOnce(new Error("offline"));

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText(/자산군 구성을 불러오지 못했어요/)).toBeInTheDocument();
    });
  });

  it("removes the difficult-term glossary to keep the four-step flow concise", () => {
    window.location.hash = "#/strategy-detail?strategy=factor";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.queryByRole("heading", { name: "낯선 용어도 바로 풀어드려요" })).not.toBeInTheDocument();
    expect(document.querySelector(".sd-glossary")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /제휴 증권사에서 더 살펴보세요/ })).not.toBeInTheDocument();
    expect(screen.queryByText("이제 실제 상품을 확인할 차례예요")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "제휴 증권사로 이동" })).toHaveTextContent(
      "제휴 증권사에서 상품 확인하기",
    );
  });

  it("opens the partner broker from the final action", () => {
    const onPartnerBrokerClick = vi.fn();

    render(
      <StrategyDetailScreen
        onBack={vi.fn()}
        onPartnerBrokerClick={onPartnerBrokerClick}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "제휴 증권사로 이동" }));

    expect(onPartnerBrokerClick).toHaveBeenCalledOnce();
  });

  it("shows the final confirmation below the partner broker action", () => {
    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.getByText("비용·수수료와 제휴 관계를 확인했습니다. 투자 결과에 따라 원금 손실이 발생할 수 있으며, 실제 거래는 고객님의 판단으로 진행됩니다.")).toBeInTheDocument();
  });

  it("falls back to the first strategy when the hash has no valid id", () => {
    window.location.hash = "#/strategy-detail";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("시장 베타 전략");
  });

  it("uses plain wording when a strategy needs an account-specific product check", () => {
    window.location.hash = "#/strategy-detail?strategy=longshort";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.getByText("계좌별 매수 가능 상품 확인")).toBeInTheDocument();
    expect(screen.getByText(/연금계좌에서 매수할 수 있는 상품인지/)).toBeInTheDocument();
    expect(screen.queryByText("계좌 적격 상품 확인 필요")).not.toBeInTheDocument();
  });

  it("shows the barbell strategy with its matching detail", () => {
    window.location.hash = "#/strategy-detail?strategy=barbell";

    render(<StrategyDetailScreen onBack={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("바벨 전략");
    expect(document.querySelector(".sd-hero")).toHaveTextContent(/성장자산과 단기채·현금을 함께 두어 위험을 완충/);
    expect(screen.getByRole("list", { name: "전략 이해 순서" })).toHaveTextContent(/한쪽에는 장기 성장자산을/);
    expect(screen.getByText("ETF로 구현 가능")).toBeInTheDocument();
    expect(screen.queryByText("타깃 전략")).not.toBeInTheDocument();
  });
});
