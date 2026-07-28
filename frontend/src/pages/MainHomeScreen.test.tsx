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
  it("메인 홈에 연금 KDA 브랜드명을 표시한다", () => {
    const { container } = renderHome();

    expect(screen.getByLabelText("연금 KDA 메인 홈")).toBeInTheDocument();
    expect(container.querySelector(".mhs-header-title")).toHaveTextContent("연금 KDA");
    expect(container.querySelector(".mhs-header-title-accent")).toHaveTextContent("KDA");
  });

  it("places the pension asset section before the promo carousel", () => {
    renderHome();

    const assetHeading = screen.getByRole("heading", { name: "내 연금 자산" });
    const carousel = screen.getByRole("region", { name: "홈 추천 카드" });

    expect(assetHeading.compareDocumentPosition(carousel) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("scrolls the 연금KDA Pick section into view when opened from chat", () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    renderHome({ focusStrategyPickRequestId: "strategy-pick-request-1" });

    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });

  it("shows the authenticated owner's engine aggregation", () => {
    renderHome();

    expect(screen.getByText("만져 보세요!")).toBeInTheDocument();
    expect(screen.getByAltText("슬랑이")).toBeInTheDocument();
    expect(screen.getByText("60,000,000원")).toBeInTheDocument();
    expect(document.querySelector(".mhs-asset-gain"))
      .toHaveTextContent("박준호님 · 진단 전 · 2026-07-23 기준");
    expect(screen.getAllByText("글로벌주식")).not.toHaveLength(0);
    expect(screen.getByText("70.0%")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "총 연금 자산 자산군 비중" }),
    ).toBeInTheDocument();
    expect(screen.getByText("글로벌주식 비중이 70.00%로 가장 높아요."))
      .toBeInTheDocument();
  });

  it("shows only the Slangi supporting description", () => {
    renderHome();

    expect(screen.queryByText("지금 놓치고 있는 세액공제액이 얼마인지 확인해 보세요.")).not.toBeInTheDocument();
    expect(screen.getByText("슬랑이를 눌러 1원씩 적립해보세요")).toBeInTheDocument();
  });

  it("removes the investment profile section from the promo carousel", () => {
    const { container } = renderHome();

    expect(container.querySelector(".mhs-promo-profile")).not.toBeInTheDocument();
    expect(screen.queryByText("저장 투자성향")).not.toBeInTheDocument();
    expect(screen.queryByText("최근 진단")).not.toBeInTheDocument();
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

    const { container } = renderHome({ investmentProfile, onOpenPlanner });

    expect(document.querySelector(".mhs-asset-gain"))
      .toHaveTextContent("박준호님 · 적극투자형 · 2026-07-23 기준");
    expect(container.querySelector(".mhs-promo-profile")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /완료율 확인하기/ }));
    expect(onOpenPlanner).toHaveBeenCalledWith("tax");
  });

  it("shows the tax credit card first and loops every 2.5 seconds", () => {
    vi.useFakeTimers();
    const { container } = renderHome();
    const track = container.querySelector(".mhs-promo-track");

    expect(track).toHaveStyle({ transform: "translateX(-0%)" });
    act(() => vi.advanceTimersByTime(2500));
    expect(track).toHaveStyle({ transform: "translateX(-100%)" });
    // 마지막 카드 다음에는 되감지 않고 복제 슬라이드까지 같은 방향으로 이어간다.
    act(() => vi.advanceTimersByTime(2500));
    expect(track).toHaveStyle({ transform: "translateX(-200%)" });
    act(() => vi.advanceTimersByTime(2500));
    expect(track).toHaveStyle({ transform: "translateX(-300%)" });
    expect(track).not.toHaveClass("is-snapping");
    // 전환이 끝나면 애니메이션 없이 원본 첫 카드로 되돌아간다.
    act(() => vi.advanceTimersByTime(380));
    expect(track).toHaveStyle({ transform: "translateX(-0%)" });
    expect(track).toHaveClass("is-snapping");

    vi.useRealTimers();
  });

  it("keeps the tax credit card still while the touring guide locks the home body", () => {
    vi.useFakeTimers();
    const { container } = renderHome();
    const body = container.querySelector(".mhs-body") as HTMLElement;
    const track = container.querySelector(".mhs-promo-track");

    body.inert = true;
    act(() => vi.advanceTimersByTime(2500));
    expect(track).toHaveStyle({ transform: "translateX(-0%)" });

    body.inert = false;
    act(() => vi.advanceTimersByTime(2500));
    expect(track).toHaveStyle({ transform: "translateX(-100%)" });

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

    fireEvent.pointerDown(screen.getByRole("button", { name: "또래 최다 운용 전략 보기" }), {
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

  it("wraps forward past the last promo card without a reverse motion", () => {
    vi.useFakeTimers();
    const { container } = renderHome();
    const carousel = screen.getByRole("region", { name: "홈 추천 카드" });
    const track = container.querySelector(".mhs-promo-track");

    fireEvent.keyDown(carousel, { key: "ArrowRight" });
    expect(track).toHaveStyle({ transform: "translateX(-100%)" });

    // 마지막 카드에서 오른쪽으로 넘기면 되감지 않고 복제 슬라이드로 이어간다.
    fireEvent.keyDown(carousel, { key: "ArrowRight" });
    expect(track).toHaveStyle({ transform: "translateX(-200%)" });
    fireEvent.keyDown(carousel, { key: "ArrowRight" });
    expect(track).toHaveStyle({ transform: "translateX(-300%)" });
    expect(track).not.toHaveClass("is-snapping");

    act(() => vi.advanceTimersByTime(380));
    expect(track).toHaveStyle({ transform: "translateX(-0%)" });
    expect(track).toHaveClass("is-snapping");

    // 첫 카드에서 왼쪽으로 넘기면 그대로 마지막 카드로 되돌아간다.
    fireEvent.keyDown(carousel, { key: "ArrowLeft" });
    expect(track).toHaveStyle({ transform: "translateX(-200%)" });

    vi.useRealTimers();
  });

  it("keeps the first dot active while the wrap-around motion runs", () => {
    vi.useFakeTimers();
    renderHome();
    const carousel = screen.getByRole("region", { name: "홈 추천 카드" });
    const firstDot = screen.getByRole("button", { name: "1번째 카드 보기" });

    fireEvent.keyDown(carousel, { key: "ArrowRight" });
    expect(firstDot).not.toHaveAttribute("aria-current");

    // 복제 슬라이드로 이동하는 동안에도 선택 상태는 첫 카드를 가리킨다.
    fireEvent.keyDown(carousel, { key: "ArrowRight" });
    expect(firstDot).not.toHaveAttribute("aria-current");
    fireEvent.keyDown(carousel, { key: "ArrowRight" });
    expect(firstDot).toHaveAttribute("aria-current", "true");
    act(() => vi.advanceTimersByTime(380));
    expect(firstDot).toHaveAttribute("aria-current", "true");

    vi.useRealTimers();
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

    fireEvent.click(screen.getByRole("button", { name: "3번째 카드 보기" }));
    fireEvent.click(screen.getByRole("button", { name: "연그미와 놀기 열기" }));
    expect(onOpenSlangi).toHaveBeenCalledOnce();
  });

  it("opens the strategy introduction from the age-group promo card", () => {
    const onOpenStrategyExplore = vi.fn();
    renderHome({ onOpenStrategyExplore });

    fireEvent.click(screen.getByRole("button", { name: "2번째 카드 보기" }));
    const card = screen.getByRole("button", { name: "또래 최다 운용 전략 보기" });
    expect(card).toHaveTextContent("고객님 연령대가 가장 많이 운용하는 전략을 확인해봐요!");
    expect(card).toHaveTextContent("또래 최다 운용 전략 보기");
    expect(card.querySelector(".mhs-strategy-promo-cta i")).toHaveTextContent("₩");

    fireEvent.click(card);

    expect(onOpenStrategyExplore).toHaveBeenCalledOnce();
  });

  it("shows calculated planning returns for every approved strategy card", async () => {
    renderHome();

    const strategyHeading = screen.getByRole("heading", { name: "연금KDA's Pick" });
    expect(strategyHeading).toBeInTheDocument();
    expect(strategyHeading.querySelector(".mhs-section-title-gold")).toHaveTextContent("Pick");
    expect(screen.getByText("연금 KDA가 전략 별로 증권사와 연결시켜드려요!")).toBeInTheDocument();
    expect(screen.queryByText("전략 설명")).not.toBeInTheDocument();
    expect(screen.queryByText("전략별 계획수익률")).not.toBeInTheDocument();
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
    expect(screen.getByText("기업 특징 따라 ETF 고르는 전략입니다.")).toBeInTheDocument();
    expect(screen.queryByText(/장기 계산용 가정/)).not.toBeInTheDocument();
    expect(screen.queryByText("시장 전체 따라가기")).not.toBeInTheDocument();
    expect(await screen.findByText("6.75%")).toBeInTheDocument();
    expect(screen.getByText("4.75%")).toBeInTheDocument();
    expect(screen.getByText("4.63%")).toBeInTheDocument();
    expect(screen.getByText("3.40%")).toBeInTheDocument();
    expect(screen.getByText("4.30%")).toBeInTheDocument();
    expect(screen.queryByText("산정 전")).not.toBeInTheDocument();
  });

  it("opens the strategy introduction from a card click without capturing the pointer", () => {
    const onOpenStrategyExplore = vi.fn();
    renderHome({ onOpenStrategyExplore });
    const strategyScroll = screen.getByRole("region", { name: "전략 카드 목록" });
    const firstCard = screen.getByRole("button", {
      name: "시장 베타 전략 소개 화면 열기",
    });
    Object.assign(strategyScroll, {
      hasPointerCapture: vi.fn(() => false),
      releasePointerCapture: vi.fn(),
      setPointerCapture: vi.fn(),
    });

    fireEvent.pointerDown(firstCard, {
      button: 0,
      clientX: 240,
      pointerId: 1,
      pointerType: "mouse",
    });
    fireEvent.pointerUp(firstCard, {
      clientX: 240,
      pointerId: 1,
      pointerType: "mouse",
    });
    fireEvent.click(firstCard);

    expect(strategyScroll.setPointerCapture).not.toHaveBeenCalled();
    expect(onOpenStrategyExplore).toHaveBeenCalledOnce();
  });

  it("scrolls strategy cards by mouse drag without opening a dragged card", () => {
    const onOpenStrategyExplore = vi.fn();
    renderHome({ onOpenStrategyExplore });
    const strategyScroll = screen.getByRole("region", { name: "전략 카드 목록" });
    const firstCard = screen.getByRole("button", {
      name: "시장 베타 전략 소개 화면 열기",
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
