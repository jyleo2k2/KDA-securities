// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  AggregationEvaluation,
  InvestmentProfileResponse,
  UserPensionPortfolio,
} from "../api/types";
import { MainHomeScreen } from "./MainHomeScreen";

afterEach(cleanup);

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
    renderHome();

    expect(screen.getByText(/위 원그래프나 자산 비중을 누르면/))
      .toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "글로벌주식 70.0%" }));

    expect(screen.getByText("SOL 미국S&P500")).toBeInTheDocument();
    expect(screen.getByText("ACE 미국나스닥100")).toBeInTheDocument();
    expect(screen.getAllByText("퇴직연금 DC")).toHaveLength(2);
    expect(screen.queryByText("KOSEF 국고채10년")).not.toBeInTheDocument();
  });

  it("keeps the one-line diagnosis action connected to chat", () => {
    const onOpenChat = vi.fn();
    renderHome({ onOpenChat });

    expect(screen.getByText("내 포트폴리오 한 줄 진단")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {
      name: /내 포트폴리오 자세히 진단받기/,
    }));
    expect(onOpenChat).toHaveBeenCalledOnce();
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

  it("opens the supplied profile screen from the header icon", () => {
    const onOpenProfile = vi.fn();
    renderHome({ onOpenProfile });

    fireEvent.click(screen.getByRole("button", { name: "프로필 열기" }));
    expect(onOpenProfile).toHaveBeenCalledOnce();
  });

  it("keeps the approved strategy cards", () => {
    renderHome();

    expect(screen.getByText("전략별 계획수익률")).toBeInTheDocument();
    expect(screen.getByText("6.75%")).toBeInTheDocument();
    expect(screen.getAllByText("산정 전")).toHaveLength(5);
  });
});
