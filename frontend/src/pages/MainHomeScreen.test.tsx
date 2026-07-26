// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getStrategyPlanningReturns } from "../api/client";
import type {
  AggregationEvaluation,
  InvestmentProfileResponse,
  StrategyPlanningReturnEvaluation,
  UserPensionPortfolio,
} from "../api/types";
import { MainHomeScreen } from "./MainHomeScreen";

vi.mock("../api/client", () => ({ getStrategyPlanningReturns: vi.fn() }));

afterEach(cleanup);

const strategyPlanningReturns = [
  ["market_beta", "7.0000", "0.2500", "6.7500"],
  ["factor", "7.0000", "0.4000", "6.6000"],
  ["thematic", "7.0000", "1.0000", "6.0000"],
  ["top_down", "6.4000", "0.7500", "5.6500"],
  ["bottom_up", "7.0000", "0.7500", "6.2500"],
  ["barbell", "5.5000", "0.7500", "4.7500"],
  ["volatility_managed", "5.3800", "0.7500", "4.6300"],
  ["market_neutral", "4.1500", "0.7500", "3.4000"],
  ["event_driven", "5.0500", "0.7500", "4.3000"],
  ["trend_global_macro", "6.4000", "0.7500", "5.6500"],
].map(([strategy_id, cma_weighted_return_percent, uncertainty_discount_percent, net_planning_return_percent]) => ({
  strategy_id,
  cma_weighted_return_percent,
  uncertainty_discount_percent,
  net_planning_return_percent,
  components: [],
  cma_policy_id: "jpm_2026_usd_educational_v2",
  policy_version: "2026-07-24.1",
  sources: [],
  annual_review_required: true,
  is_forecast: false,
  warnings: [],
})) as StrategyPlanningReturnEvaluation[];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getStrategyPlanningReturns).mockResolvedValue(strategyPlanningReturns);
});

const aggregation = {
  total_amount_krw: "60000000",
  asset_class_totals: [
    {
      asset_class: "global_equity",
      amount_krw: "42000000",
      weight_percent: "70.00",
    },
    {
      asset_class: "bond",
      amount_krw: "18000000",
      weight_percent: "30.00",
    },
  ],
  per_account: [],
  overlaps: [],
  notice: "합산 수치는 표시용",
  evidence: [],
} as unknown as AggregationEvaluation;
const portfolio = {
  owner_id: "owner-1",
  data_boundary: "mock",
  accounts: [{
    account_id: "dc-1",
    account_name: "퇴직연금 DC",
    as_of_date: "2026-07-23",
    holdings: [
      {
        holding_id: "global-1",
        instrument_name: "SOL 미국S&P500",
        asset_class: "global_equity",
        amount_krw: "30000000",
      },
      {
        holding_id: "global-2",
        instrument_name: "ACE 미국나스닥100",
        asset_class: "global_equity",
        amount_krw: "12000000",
      },
      {
        holding_id: "bond-1",
        instrument_name: "KOSEF 국고채10년",
        asset_class: "bond",
        amount_krw: "18000000",
      },
    ],
  }],
} as unknown as UserPensionPortfolio;

function renderHome(
  overrides: Partial<Parameters<typeof MainHomeScreen>[0]> = {},
) {
  return render(
    <MainHomeScreen
      aggregation={aggregation}
      displayName="박준호"
      error={null}
      investmentProfile={null}
      loading={false}
      onOpenChat={vi.fn()}
      onOpenPlanner={vi.fn()}
      onOpenProfile={vi.fn()}
      onRequestPortfolioDiagnosis={vi.fn()}
      onOpenSlangi={vi.fn()}
      onOpenStrategyExplore={vi.fn()}
      onOpenUserPick={vi.fn()}
      portfolio={portfolio}
      {...overrides}
    />,
  );
}

describe("MainHomeScreen", () => {
  it("shows the authenticated owner's engine aggregation", () => {
    renderHome();

    expect(screen.getByText(/슬랑이를/)).toBeInTheDocument();
    expect(screen.getByAltText("슬랑이")).toBeInTheDocument();
    expect(screen.getByText("60,000,000원")).toBeInTheDocument();
    expect(screen.getByText("박준호님 · 2026-07-23 기준")).toBeInTheDocument();
    expect(screen.getAllByText("글로벌주식")).not.toHaveLength(0);
    expect(screen.getByText("70.0%")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "총 연금 자산 자산군 비중" }),
    ).toBeInTheDocument();
    expect(screen.getByText("글로벌주식 비중이 70.00%로 가장 높아요."))
      .toBeInTheDocument();
  });

  it("shows the real holdings for the selected donut asset class", () => {
    const { container } = renderHome();

    expect(screen.getByText(/위 원그래프나 자산 비중을 누르면/))
      .toBeInTheDocument();
    const donutSlice = screen.getByRole("button", { name: "글로벌주식 70.0%" });
    expect(donutSlice).toHaveClass("mhs-pie-slice");
    expect(container.querySelectorAll(".mhs-allocation-item.is-selectable")).toHaveLength(2);
    fireEvent.click(donutSlice);

    expect(screen.getByText("SOL 미국S&P500")).toBeInTheDocument();
    expect(screen.getByText("ACE 미국나스닥100")).toBeInTheDocument();
    expect(screen.getAllByText("퇴직연금 DC")).toHaveLength(2);
    expect(screen.queryByText("KOSEF 국고채10년")).not.toBeInTheDocument();
  });

  it("shows the largest asset holdings from the first-view prompt", () => {
    // The prompt opens the detail, and the same click must not reach the
    // document-level dismiss listener that closes it again.
    const documentClick = vi.fn();
    document.addEventListener("click", documentClick);
    renderHome();

    fireEvent.click(screen.getByRole("button", {
      name: "가장 큰 자산의 보유 종목 먼저 보기",
    }));

    expect(documentClick).not.toHaveBeenCalled();
    expect(screen.getByText("SOL 미국S&P500")).toBeInTheDocument();
    expect(screen.getByText("ACE 미국나스닥100")).toBeInTheDocument();
    expect(screen.queryByText("KOSEF 국고채10년")).not.toBeInTheDocument();
    document.removeEventListener("click", documentClick);
  });

  it("separates portfolio diagnosis from the regular chat tab", () => {
    const onOpenChat = vi.fn();
    const onRequestPortfolioDiagnosis = vi.fn();
    renderHome({ onOpenChat, onRequestPortfolioDiagnosis });

    expect(screen.getByText("내 포트폴리오 한 줄 진단")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {
      name: /내 포트폴리오 자세히 진단받기/,
    }));
    expect(onRequestPortfolioDiagnosis).toHaveBeenCalledOnce();
    expect(onOpenChat).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("챗봇"));
    expect(onOpenChat).toHaveBeenCalledOnce();
    expect(onRequestPortfolioDiagnosis).toHaveBeenCalledOnce();
  });

  it("restores and reports the home scroll position", () => {
    const onScrollPositionChange = vi.fn();
    const { container } = renderHome({
      initialScrollTop: 420,
      onScrollPositionChange,
    });
    const body = container.querySelector(".mhs-body");
    expect(body).not.toBeNull();
    expect(body).toHaveProperty("scrollTop", 420);

    fireEvent.scroll(body as Element, { target: { scrollTop: 680 } });
    expect(onScrollPositionChange).toHaveBeenLastCalledWith(680);
  });

  it("shows the saved investment profile and opens the calculator", () => {
    const onOpenPlanner = vi.fn();
    const investmentProfile = {
      assessment: {
        assessed_on: "2026-07-22",
        risk_profile: "active",
        is_expired: false,
      },
      preferences: null,
    } as InvestmentProfileResponse;

    renderHome({ investmentProfile, onOpenPlanner });

    expect(screen.getByText(
      "저장 투자성향 · 적극투자형 · 2026-07-22 진단",
    )).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /완료율 확인하기/ }));
    expect(onOpenPlanner).toHaveBeenCalledOnce();
  });

  it("shows the tax credit card first and loops every 2.5 seconds", () => {
    vi.useFakeTimers();
    const { container } = renderHome();
    const track = container.querySelector(".mhs-promo-track");

    expect(track).toHaveStyle({ transform: "translateX(-0%)" });
    act(() => vi.advanceTimersByTime(2500));
    expect(track).toHaveStyle({ transform: "translateX(-100%)" });
    act(() => vi.advanceTimersByTime(2500));
    expect(track).toHaveStyle({ transform: "translateX(-0%)" });

    vi.useRealTimers();
  });

  it("supports dots, arrow keys, touch swipes, and mouse drags", () => {
    const { container } = renderHome();
    const carousel = screen.getByRole("region", { name: "홈 추천 카드" });
    const track = container.querySelector(".mhs-promo-track");
    Object.assign(carousel, {
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn(),
      setPointerCapture: vi.fn(),
    });

    fireEvent.click(screen.getByRole("button", { name: "2번째 카드 보기" }));
    expect(track).toHaveStyle({ transform: "translateX(-100%)" });

    fireEvent.keyDown(carousel, { key: "ArrowLeft" });
    expect(track).toHaveStyle({ transform: "translateX(-0%)" });

    fireEvent.touchStart(carousel, { touches: [{ clientX: 280 }] });
    fireEvent.touchEnd(carousel, { changedTouches: [{ clientX: 180 }] });
    expect(track).toHaveStyle({ transform: "translateX(-100%)" });

    fireEvent.pointerDown(screen.getByRole("button", { name: "연그미와 놀기 열기" }), {
      button: 0,
      clientX: 180,
      pointerId: 1,
      pointerType: "mouse",
    });
    fireEvent.pointerMove(carousel, {
      clientX: 280,
      pointerId: 1,
      pointerType: "mouse",
    });
    expect(carousel).toHaveClass("is-dragging");
    expect(carousel.setPointerCapture).toHaveBeenCalledWith(1);

    fireEvent.pointerUp(carousel, {
      clientX: 280,
      pointerId: 1,
      pointerType: "mouse",
    });
    expect(carousel).not.toHaveClass("is-dragging");
    expect(track).toHaveStyle({ transform: "translateX(-0%)" });
  });

  it("opens the supplied profile screen from the header icon", () => {
    const onOpenProfile = vi.fn();
    renderHome({ onOpenProfile });

    fireEvent.click(screen.getByRole("button", { name: "프로필 열기" }));
    expect(onOpenProfile).toHaveBeenCalledOnce();
  });

  it("opens the slangi touch screen from the yeongeumi card", () => {
    const onOpenSlangi = vi.fn();
    renderHome({ onOpenSlangi });

    fireEvent.click(screen.getByRole("button", { name: "2번째 카드 보기" }));
    fireEvent.click(screen.getByRole("button", { name: "연그미와 놀기 열기" }));
    expect(onOpenSlangi).toHaveBeenCalledOnce();
  });

  it("shows calculated planning returns for every approved strategy card", async () => {
    renderHome();

    expect(screen.getByText("전략별 계획수익률")).toBeInTheDocument();
    expect(screen.getByText("시장 베타 전략")).toBeInTheDocument();
    expect(screen.getByText("팩터 전략")).toBeInTheDocument();
    expect(screen.getByText("테마 전략")).toBeInTheDocument();
    expect(screen.getByText("탑다운 전략")).toBeInTheDocument();
    expect(screen.getByText("바텀업 전략")).toBeInTheDocument();
    expect(screen.getByText("바벨 전략")).toBeInTheDocument();
    expect(screen.getByText("변동성 관리 전략")).toBeInTheDocument();
    expect(screen.getByText("롱숏·시장중립 전략")).toBeInTheDocument();
    expect(screen.getByText("이벤트드리븐 전략")).toBeInTheDocument();
    expect(screen.getByText("추세추종·글로벌 매크로 전략")).toBeInTheDocument();
    expect(screen.getByText(/재무 건전성·가격 수준·추세/)).toBeInTheDocument();
    expect(screen.queryByText("시장 전체 따라가기")).not.toBeInTheDocument();
    expect(await screen.findByText("6.75%")).toBeInTheDocument();
    expect(screen.getByText("4.75%")).toBeInTheDocument();
    expect(screen.getByText("4.63%")).toBeInTheDocument();
    expect(screen.getByText("3.40%")).toBeInTheDocument();
    expect(screen.getByText("4.30%")).toBeInTheDocument();
    expect(screen.queryByText("산정 전")).not.toBeInTheDocument();
  });

  it("scrolls strategy cards by mouse drag without opening a dragged card", () => {
    const onOpenStrategyExplore = vi.fn();
    renderHome({ onOpenStrategyExplore });
    const strategyScroll = screen.getByRole("region", { name: "전략 카드 목록" });
    const firstCard = screen.getByRole("button", {
      name: "시장 베타 전략 전략 상세 보기",
    });
    Object.defineProperty(strategyScroll, "scrollLeft", {
      configurable: true,
      value: 120,
      writable: true,
    });
    Object.assign(strategyScroll, {
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn(),
      setPointerCapture: vi.fn(),
    });

    fireEvent.pointerDown(firstCard, {
      button: 0,
      clientX: 240,
      pointerId: 1,
      pointerType: "mouse",
    });
    fireEvent.pointerMove(strategyScroll, {
      clientX: 140,
      pointerId: 1,
      pointerType: "mouse",
    });

    expect(strategyScroll).toHaveProperty("scrollLeft", 220);
    expect(strategyScroll).toHaveClass("is-dragging");

    fireEvent.pointerUp(strategyScroll, {
      clientX: 140,
      pointerId: 1,
      pointerType: "mouse",
    });
    fireEvent.click(firstCard);

    expect(strategyScroll).not.toHaveClass("is-dragging");
    expect(onOpenStrategyExplore).not.toHaveBeenCalled();

    fireEvent.click(firstCard);
    expect(onOpenStrategyExplore).toHaveBeenCalledOnce();
  });

  it("retries the planning-return request when the API starts after the home screen", async () => {
    vi.useFakeTimers();
    vi.mocked(getStrategyPlanningReturns)
      .mockRejectedValueOnce(new Error("API starting"))
      .mockResolvedValueOnce(strategyPlanningReturns);

    try {
      renderHome();

      await act(async () => { await Promise.resolve(); });
      expect(screen.getAllByText("계산 중…")).toHaveLength(10);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3_000);
      });

      expect(screen.getByText("6.75%")).toBeInTheDocument();
      expect(getStrategyPlanningReturns).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
