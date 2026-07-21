// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSupabaseAuth } from "./auth/useSupabaseAuth";
import App from "./App";

vi.mock("./auth/useSupabaseAuth", () => ({
  useSupabaseAuth: vi.fn(),
}));

vi.mock("./components/TabBar", () => ({
  TabBar: () => <nav aria-label="탭 바" />,
}));

vi.mock("./pages/HomePage", () => ({
  HomePage: ({ onSignOut }: { onSignOut: () => void }) => (
    <main>
      <h1>홈 화면</h1>
      <button onClick={onSignOut} type="button">로그아웃</button>
    </main>
  ),
}));

vi.mock("./pages/GuidePage", () => ({
  GuidePage: () => <main>가이드 화면</main>,
}));

vi.mock("./pages/ProfilePage", () => ({
  ProfilePage: () => <main>프로필 화면</main>,
}));

vi.mock("./pages/BenchmarkPage", () => ({
  BenchmarkPage: () => <main>벤치마크 화면</main>,
}));

vi.mock("./pages/LoginFlowPage", () => ({
  LoginFlowPage: () => <main>로그인 화면</main>,
}));

const signOut = vi.fn();

function mockAuth({
  configured = true,
  loading = false,
  session = null,
}: {
  configured?: boolean;
  loading?: boolean;
  session?: object | null;
} = {}): void {
  vi.mocked(useSupabaseAuth).mockReturnValue({
    configured,
    loading,
    session,
    error: null,
    signIn: vi.fn(),
    signOut,
  } as unknown as ReturnType<typeof useSupabaseAuth>);
}

describe("App authentication gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    window.history.replaceState(null, "", "#home");
  });

  afterEach(cleanup);

  it("shows a splash while checking the session", () => {
    mockAuth({ loading: true });
    render(<App />);

    expect(screen.getByLabelText("로그인 상태 확인 중")).toBeInTheDocument();
  });

  it("blocks every hash route when Supabase is configured and no session exists", () => {
    window.history.replaceState(null, "", "#guide");
    mockAuth();
    render(<App />);

    expect(screen.getByText("로그인 화면")).toBeInTheDocument();
    expect(screen.queryByText("가이드 화면")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("탭 바")).not.toBeInTheDocument();
  });

  it("renders the existing app for an authenticated session", () => {
    mockAuth({ session: {} });
    render(<App />);

    expect(screen.getByText("홈 화면")).toBeInTheDocument();
    expect(screen.getByLabelText("탭 바")).toBeInTheDocument();
  });

  it("allows local demo browsing when Supabase is not configured", () => {
    window.history.replaceState(null, "", "#login");
    mockAuth({ configured: false });
    render(<App />);

    expect(screen.getByText("홈 화면")).toBeInTheDocument();
  });

  it("passes the temporary home logout action to Supabase auth", () => {
    mockAuth({ session: {} });
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    expect(signOut).toHaveBeenCalledOnce();
  });

  it("returns to the login gate after the authenticated session disappears", () => {
    mockAuth({ session: {} });
    const view = render(<App />);
    expect(screen.getByText("홈 화면")).toBeInTheDocument();

    mockAuth();
    view.rerender(<App />);

    expect(screen.getByText("로그인 화면")).toBeInTheDocument();
  });
});
