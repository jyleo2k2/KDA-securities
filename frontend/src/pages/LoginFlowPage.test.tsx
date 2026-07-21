// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import { LoginFlowPage } from "./LoginFlowPage";

const onStart = vi.fn();
const onAuthenticated = vi.fn();
let auth: SupabaseAuthState;

function renderLogin(): void {
  render(<LoginFlowPage auth={auth} onAuthenticated={onAuthenticated} onStart={onStart} />);
}

function openForm(): void {
  fireEvent.click(screen.getByRole("button", { name: "로그인" }));
}

function fillLoginForm(): void {
  fireEvent.change(screen.getByLabelText("아이디"), { target: { value: "junho46" } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "password" } });
}

describe("LoginFlowPage", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    auth = {
      session: null,
      loading: false,
      configured: true,
      error: null,
      signIn: vi.fn().mockResolvedValue(undefined),
      signOut: vi.fn(),
    };
  });

  it("shows success only after Supabase sign-in resolves", async () => {
    renderLogin();
    openForm();
    fillLoginForm();
    fireEvent.click(screen.getByRole("button", { name: "로그인하기" }));

    await waitFor(() => {
      expect(auth.signIn).toHaveBeenCalledWith("junho46", "password");
    });
    expect(onAuthenticated).toHaveBeenCalledOnce();
    expect(screen.getByText("로그인 성공!")).toBeInTheDocument();
  });

  it("keeps the form visible and shows the auth error when sign-in fails", async () => {
    auth = {
      session: null,
      loading: false,
      configured: true,
      error: "이메일 또는 비밀번호를 확인해 주세요.",
      signIn: vi.fn().mockRejectedValue(new Error("invalid credentials")),
      signOut: vi.fn(),
    };
    renderLogin();
    openForm();
    fillLoginForm();
    fireEvent.click(screen.getByRole("button", { name: "로그인하기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("이메일 또는 비밀번호를 확인해 주세요.");
    expect(screen.queryByText("로그인 성공!")).not.toBeInTheDocument();
    expect(onAuthenticated).not.toHaveBeenCalled();
  });

  it("disables the submit button while sign-in is pending", async () => {
    let resolveSignIn: (() => void) | undefined;
    auth = {
      session: null,
      loading: false,
      configured: true,
      error: null,
      signIn: vi.fn().mockImplementation(() => new Promise<void>((resolve) => {
        resolveSignIn = resolve;
      })),
      signOut: vi.fn(),
    };
    renderLogin();
    openForm();
    fillLoginForm();
    fireEvent.click(screen.getByRole("button", { name: "로그인하기" }));

    expect(await screen.findByRole("button", { name: "로그인 중..." })).toBeDisabled();
    resolveSignIn?.();
  });

  it("shows the signup preparation notice", () => {
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: "회원가입" }));

    expect(screen.getByRole("status")).toHaveTextContent("회원가입은 준비 중입니다.");
  });
});
