// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import App from "./App";
import {
  getInvestmentProfile,
  getMyPensionAccounts,
  getMyPensionContext,
} from "./api/client";
import { useSupabaseAuth } from "./auth/useSupabaseAuth";

vi.mock("./api/client", () => ({
  ApiError: class ApiError extends Error {},
  aggregatePensionAccounts: vi.fn(),
  apiErrorMessage: () => "요청에 실패했습니다.",
  getInvestmentProfile: vi.fn(),
  getMyPensionAccounts: vi.fn(),
  getMyPensionContext: vi.fn(),
}));

vi.mock("./auth/useSupabaseAuth", () => ({
  useSupabaseAuth: vi.fn(),
}));

vi.mock("./pages/GuidePage", () => ({
  GuidePage: () => <main data-testid="guide-page">가이드</main>,
}));

afterEach(() => {
  cleanup();
});

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
    vi.mocked(getInvestmentProfile).mockResolvedValue({ assessment: null, preferences: null });
    vi.mocked(getMyPensionAccounts).mockResolvedValue({ owner_id: "user-1", data_boundary: "unavailable", accounts: [] });
    vi.mocked(getMyPensionContext).mockRejectedValue(new Error("연동 데이터 없음"));
  });

  it("opens the guide directly for an authenticated user", async () => {
    render(<App />);

    expect(await screen.findByTestId("guide-page")).toBeTruthy();
    const guideFrame = screen.getByLabelText("연금 가이드");
    expect(guideFrame.querySelector(".ios-statusbar")).toBeTruthy();
    expect(document.querySelector(".desktop-preview-status")).toBeNull();
  });

  it("loads the supplied profile html from its explicit public file path", async () => {
    window.history.replaceState(null, "", "#/profile-html");

    render(<App />);

    const profileFrame = await screen.findByTitle("내 프로필");
    expect(profileFrame.getAttribute("src")).toBe("/profile-html/index.html");
  });

  it("opens the resurvey flow from the profile screen", async () => {
    window.history.replaceState(null, "", "#/profile-html");

    render(<App />);

    const profileFrame = await screen.findByTitle("내 프로필") as HTMLIFrameElement;
    const frameDocument = profileFrame.contentDocument;
    expect(frameDocument).not.toBeNull();
    if (!frameDocument) return;

    frameDocument.open();
    frameDocument.write('<!doctype html><body><button type="button" data-profile-html-resurvey>진단 다시하기</button></body>');
    frameDocument.close();
    fireEvent.load(profileFrame);
    fireEvent.click(frameDocument.querySelector("[data-profile-html-resurvey]") as HTMLButtonElement);

    expect(await screen.findByRole("button", { name: "투자 성향 진단받기" })).toBeTruthy();
  });

  it("loads the supplied slangi html from its explicit public file path", async () => {
    window.history.replaceState(null, "", "#/slangi");

    render(<App />);

    const slangiFrame = await screen.findByTitle("연그미를 만져 보세요");
    expect(slangiFrame.getAttribute("src")).toBe("/slangi/index.html");
  });
});
