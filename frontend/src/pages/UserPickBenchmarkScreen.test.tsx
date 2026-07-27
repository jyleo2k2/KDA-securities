// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UserPickBenchmarkScreen } from "./UserPickBenchmarkScreen";

const mocks = vi.hoisted(() => ({
  getBenchmarkFollows: vi.fn(),
  getDemoHeroes: vi.fn(),
  getMyPensionContext: vi.fn(),
  getSession: vi.fn(),
  setBenchmarkFollow: vi.fn(),
}));

vi.mock("../api/client", () => ({
  getBenchmarkFollows: mocks.getBenchmarkFollows,
  getDemoHeroes: mocks.getDemoHeroes,
  getMyPensionContext: mocks.getMyPensionContext,
  setBenchmarkFollow: mocks.setBenchmarkFollow,
}));

vi.mock("../auth/supabase", () => ({
  supabase: {
    auth: {
      getSession: mocks.getSession,
    },
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getSession.mockResolvedValue({ data: { session: null } });
  mocks.getBenchmarkFollows.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("UserPickBenchmarkScreen", () => {
  it("renders the supplied benchmark HTML", () => {
    render(<UserPickBenchmarkScreen onBack={vi.fn()} />);

    expect(screen.getByTitle("투자 벤치마킹하기")).toHaveAttribute("src", "/benchmark-html/투자 벤치마킹.dc.html");
  });

  it("leaves to home only on the list back message from the iframe", () => {
    const onBack = vi.fn();
    render(<UserPickBenchmarkScreen onBack={onBack} />);
    const iframe = screen.getByTitle("투자 벤치마킹하기") as HTMLIFrameElement;

    // 다른 출처/타입 메시지는 무시한다.
    window.dispatchEvent(new MessageEvent("message", {
      data: { type: "benchmark-html-back" },
      origin: window.location.origin,
      source: window,
    }));
    expect(onBack).not.toHaveBeenCalled();

    // iframe(목록 뒤로가기)에서 온 메시지만 홈으로 나간다.
    window.dispatchEvent(new MessageEvent("message", {
      data: { type: "benchmark-html-back" },
      origin: window.location.origin,
      source: iframe.contentWindow,
    }));
    expect(onBack).toHaveBeenCalledOnce();
  });

  it("sends the logged-in owner's past return matched by scenario", async () => {
    mocks.getSession.mockResolvedValue({
      data: { session: { access_token: "owner-access-token" } },
    });
    mocks.getMyPensionContext.mockResolvedValue({
      scenario_code: "owner-scenario",
    });
    mocks.getDemoHeroes.mockResolvedValue([
      {
        scenario_code: "another-scenario",
        past_performance: { trailing_12m_return_pct: "18.20" },
      },
      {
        scenario_code: "owner-scenario",
        past_performance: { trailing_12m_return_pct: "7.72" },
      },
    ]);

    render(<UserPickBenchmarkScreen onBack={vi.fn()} />);
    const iframe = screen.getByTitle("투자 벤치마킹하기") as HTMLIFrameElement;
    const postMessage = vi.spyOn(iframe.contentWindow!, "postMessage");

    fireEvent.load(iframe);

    await waitFor(() => {
      expect(postMessage).toHaveBeenCalledWith(
        {
          type: "benchmark-owner-return",
          trailing12mReturnPct: 7.72,
        },
        window.location.origin,
      );
    });
  });

  it("hydrates persisted follow state into the benchmark iframe", async () => {
    mocks.getSession.mockResolvedValue({
      data: { session: { access_token: "owner-access-token" } },
    });
    mocks.getMyPensionContext.mockRejectedValue(new Error("not needed"));
    mocks.getDemoHeroes.mockResolvedValue([]);
    mocks.getBenchmarkFollows.mockResolvedValue([
      {
        portfolio_id: "꾸준한거북이",
        is_following: true,
        follow_count: 1205,
      },
    ]);

    render(<UserPickBenchmarkScreen onBack={vi.fn()} />);
    const iframe = screen.getByTitle("투자 벤치마킹하기") as HTMLIFrameElement;
    const postMessage = vi.spyOn(iframe.contentWindow!, "postMessage");

    fireEvent.load(iframe);

    await waitFor(() => {
      expect(postMessage).toHaveBeenCalledWith(
        {
          type: "benchmark-follow-state",
          items: [
            {
              portfolio_id: "꾸준한거북이",
              is_following: true,
              follow_count: 1205,
            },
          ],
        },
        window.location.origin,
      );
    });
  });

  it("persists a follow request and returns the server count to the iframe", async () => {
    mocks.getSession.mockResolvedValue({
      data: { session: { access_token: "owner-access-token" } },
    });
    mocks.getMyPensionContext.mockRejectedValue(new Error("not needed"));
    mocks.getDemoHeroes.mockResolvedValue([]);
    mocks.getBenchmarkFollows.mockResolvedValue([
      {
        portfolio_id: "꾸준한거북이",
        is_following: false,
        follow_count: 1204,
      },
    ]);
    mocks.setBenchmarkFollow.mockResolvedValue({
      portfolio_id: "꾸준한거북이",
      is_following: true,
      follow_count: 1205,
    });

    render(<UserPickBenchmarkScreen onBack={vi.fn()} />);
    const iframe = screen.getByTitle("투자 벤치마킹하기") as HTMLIFrameElement;
    const postMessage = vi.spyOn(iframe.contentWindow!, "postMessage");

    await waitFor(() => {
      expect(mocks.getBenchmarkFollows).toHaveBeenCalledWith("owner-access-token");
    });

    window.dispatchEvent(new MessageEvent("message", {
      data: {
        type: "benchmark-follow-toggle",
        portfolioId: "꾸준한거북이",
        following: true,
      },
      origin: window.location.origin,
      source: iframe.contentWindow,
    }));

    await waitFor(() => {
      expect(mocks.setBenchmarkFollow).toHaveBeenCalledWith(
        "꾸준한거북이",
        true,
        "owner-access-token",
      );
      expect(postMessage).toHaveBeenCalledWith(
        {
          type: "benchmark-follow-state",
          items: [
            {
              portfolio_id: "꾸준한거북이",
              is_following: true,
              follow_count: 1205,
            },
          ],
        },
        window.location.origin,
      );
    });
  });
});
