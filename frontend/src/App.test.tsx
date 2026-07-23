// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  aggregatePensionAccounts,
  ApiError,
  getInvestmentProfile,
  getMyPensionAccounts,
} from "./api/client";
import type {
  InvestmentProfileResponse,
  UserPensionPortfolio,
} from "./api/types";
import App from "./App";
import { useSupabaseAuth } from "./auth/useSupabaseAuth";

vi.mock("./api/client", () => ({
  aggregatePensionAccounts: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    code: string | null = null;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  apiErrorMessage: () => "요청에 실패했습니다.",
  getInvestmentProfile: vi.fn(),
  getMyPensionAccounts: vi.fn(),
  getMyPensionContext: vi.fn(),
}));
vi.mock("./auth/useSupabaseAuth", () => ({ useSupabaseAuth: vi.fn() }));
vi.mock("./pages/MainHomeScreen", () => ({
  MainHomeScreen: ({
    aggregation,
    error,
    investmentProfile,
    loading,
    portfolio,
  }: {
    aggregation: { total_amount_krw: string } | null;
    error: string | null;
    investmentProfile: InvestmentProfileResponse | null;
    loading: boolean;
    portfolio: UserPensionPortfolio | null;
  }) => (
    <main>
      {loading
        ? "로딩"
        : error ?? `${portfolio?.owner_id ?? "없음"}:${aggregation?.total_amount_krw ?? "0"}`}
      <span data-testid="saved-profile">
        {investmentProfile?.assessment?.risk_profile ?? "none"}
      </span>
    </main>
  ),
}));
vi.mock("./pages/LoginFlowPage", () => ({
  LoginFlowPage: ({ onStart }: { onStart: () => void }) => (
    <button type="button" onClick={onStart}>시작</button>
  ),
}));
vi.mock("./pages/GuidePage", () => ({ GuidePage: () => <main>챗</main> }));

const savedProfile = {
  assessment: { risk_profile: "active", is_expired: false },
  preferences: null,
} as InvestmentProfileResponse;
const portfolioA = {
  owner_id: "user-a",
  data_boundary: "mock",
  accounts: [{ account_id: "dc-a", holdings: [] }],
} as unknown as UserPensionPortfolio;
const portfolioB = {
  owner_id: "user-b",
  data_boundary: "mock",
  accounts: [{ account_id: "irp-b", holdings: [] }],
} as unknown as UserPensionPortfolio;
let authState: ReturnType<typeof useSupabaseAuth>;

function setUser(id: string, token: string): void {
  authState = {
    session: {
      access_token: token,
      user: {
        id,
        user_metadata: { nickname: id, representative_age: 35 },
      },
    },
    loading: false,
    configured: true,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  } as unknown as ReturnType<typeof useSupabaseAuth>;
}

describe("App owned pension data", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "#/main-home");
    window.localStorage.clear();
    setUser("user-a", "token-a");
    vi.mocked(useSupabaseAuth).mockImplementation(() => authState);
    vi.mocked(getInvestmentProfile).mockResolvedValue(savedProfile);
    vi.mocked(aggregatePensionAccounts).mockResolvedValue({
      total_amount_krw: "60000000",
    } as never);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("clears the previous owner while loading the next owner", async () => {
    let resolveB: ((value: UserPensionPortfolio) => void) | undefined;
    vi.mocked(getMyPensionAccounts)
      .mockResolvedValueOnce(portfolioA)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveB = resolve;
      }));
    const view = render(<App />);
    expect(await screen.findByText("user-a:60000000")).toBeInTheDocument();

    setUser("user-b", "token-b");
    view.rerender(<App />);
    expect(await screen.findByText("로딩")).toBeInTheDocument();
    expect(screen.queryByText("user-a:60000000")).not.toBeInTheDocument();
    resolveB?.(portfolioB);

    await waitFor(() => {
      expect(screen.getByText("user-b:60000000")).toBeInTheDocument();
    });
  });

  it("loads accounts and the latest saved investment profile", async () => {
    vi.mocked(getMyPensionAccounts).mockResolvedValue(portfolioA);
    render(<App />);

    expect(await screen.findByTestId("saved-profile")).toHaveTextContent("active");
    expect(getMyPensionAccounts).toHaveBeenCalledWith("token-a");
    expect(getInvestmentProfile).toHaveBeenCalledWith("token-a");
  });

  it("does not request protected data for an expired session", () => {
    authState = {
      ...authState,
      session: {
        access_token: "expired-token",
        expires_at: Math.floor(Date.now() / 1000) - 1,
        user: { id: "user-a" },
      },
    } as unknown as ReturnType<typeof useSupabaseAuth>;
    render(<App />);

    expect(screen.getByRole("button", { name: "시작" })).toBeInTheDocument();
    expect(getMyPensionAccounts).not.toHaveBeenCalled();
    expect(getInvestmentProfile).not.toHaveBeenCalled();
  });

  it("shows the missing-account notice", async () => {
    vi.mocked(getMyPensionAccounts).mockRejectedValue(
      new ApiError(404, "missing"),
    );
    render(<App />);

    expect(await screen.findByText(
      "이 계정에는 연동된 연금 데이터가 없습니다.",
    )).toBeInTheDocument();
  });
});
