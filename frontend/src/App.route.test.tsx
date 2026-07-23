// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import App from "./App";
import { getDemoHeroes, getInvestmentProfile, getMyPensionContext } from "./api/client";
import { useSupabaseAuth } from "./auth/useSupabaseAuth";

vi.mock("./api/client", () => ({
  ApiError: class ApiError extends Error {},
  apiErrorMessage: () => "요청에 실패했습니다.",
  getDemoHeroes: vi.fn(),
  getInvestmentProfile: vi.fn(),
  getMyPensionContext: vi.fn(),
}));

vi.mock("./auth/useSupabaseAuth", () => ({
  useSupabaseAuth: vi.fn(),
}));

vi.mock("./components/TabBar", () => ({
  TabBar: () => <nav>탭</nav>,
}));

vi.mock("./pages/GuidePage", () => ({
  GuidePage: () => <main data-testid="guide-page">가이드</main>,
}));

vi.mock("./pages/LoginFlowPage", () => ({
  LoginFlowPage: () => <main data-testid="login-page">로그인</main>,
}));

describe("initial hash routing", () => {
  afterEach(cleanup);

  beforeEach(() => {
    window.history.replaceState(null, "", "#guide");
    vi.mocked(useSupabaseAuth).mockReturnValue({
      configured: true,
      error: null,
      loading: false,
      session: { access_token: "access-token", user: { id: "user-1", email: "user@example.com" } },
      signIn: vi.fn(),
      signOut: vi.fn(),
    } as never);
    vi.mocked(getDemoHeroes).mockResolvedValue([]);
    vi.mocked(getInvestmentProfile).mockResolvedValue({ assessment: null, preferences: null });
    vi.mocked(getMyPensionContext).mockRejectedValue(new Error("연동 데이터 없음"));
  });

  it("opens the guide directly for an authenticated user", async () => {
    render(<App />);

    expect(await screen.findByTestId("guide-page")).toBeTruthy();
  });

  it("opens the login page from the original frontend URL", async () => {
    window.history.replaceState(null, "", "#/");

    render(<App />);

    expect(await screen.findByTestId("login-page")).toBeTruthy();
    expect(window.location.hash).toBe("#/login");
  });

  it("keeps the explicit login route visible with a stored session", async () => {
    window.history.replaceState(null, "", "#/login");

    render(<App />);

    expect(await screen.findByTestId("login-page")).toBeTruthy();
  });
});
