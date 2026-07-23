// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

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

describe("initial hash routing", () => {
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

  it("loads the supplied profile html from its explicit public file path", async () => {
    window.history.replaceState(null, "", "#/profile-html");

    render(<App />);

    const profileFrame = await screen.findByTitle("내 프로필");
    expect(profileFrame.getAttribute("src")).toBe("/profile-html/index.html");
  });
});
