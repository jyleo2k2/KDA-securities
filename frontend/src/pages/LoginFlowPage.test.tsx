// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getAccountLinkOptions, saveInvestmentProfile } from "../api/client";
import type { AccountLinkOptionsResponse, InvestmentProfileResponse } from "../api/types";
import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import { LoginFlowPage } from "./LoginFlowPage";

vi.mock("../api/client", () => ({ getAccountLinkOptions: vi.fn(), saveInvestmentProfile: vi.fn() }));
vi.mock("./InvestorInfoForm", () => ({
  InvestorInfoForm: ({ onSubmit }: { onSubmit: (submission: never) => Promise<void> }) => (
    <button
      type="button"
      onClick={() => void onSubmit({
        survey: { answers: [] },
        investment_advice_desired: false,
        investor_information_provided: true,
      } as never)}
    >
      테스트 설문 저장
    </button>
  ),
}));

const onStart = vi.fn();
const onAuthenticated = vi.fn();
const onProfileSaved = vi.fn();
let auth: SupabaseAuthState;
const linkOptions: AccountLinkOptionsResponse = {
  data_boundary: "mock",
  notice: "현재 MVP는 목데이터 기반 조회·분석 화면입니다. 실제 계좌 연결, 계좌 이전, 자동 매매는 발생하지 않습니다.",
  options: [
    { code: "dc", display_name: "DC형 퇴직연금", category_label: "직접 운용 계좌", diagnosable: true, description: null },
    { code: "irp", display_name: "IRP", category_label: "개인 연금계좌", diagnosable: true, description: null },
    { code: "pension_savings", display_name: "연금저축", category_label: "개인 연금계좌", diagnosable: true, description: null },
    { code: "db", display_name: "DB형 퇴직연금", category_label: "회사 운용 계좌", diagnosable: false, description: "가입 여부만 확인하며 운용 진단에서는 제외됩니다." },
  ],
};
const savedProfile = {
  assessment: {
    assessed_at: "2026-07-22T04:30:07.229204+00:00",
    assessed_on: "2026-07-22",
    valid_until: "2028-07-21",
    is_expired: false,
    risk_profile: "aggressive",
  },
  preferences: null,
} as InvestmentProfileResponse;

function renderLogin(): ReturnType<typeof render> {
  return render(<LoginFlowPage auth={auth} onAuthenticated={onAuthenticated} onProfileSaved={onProfileSaved} onStart={onStart} />);
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
    vi.mocked(getAccountLinkOptions).mockResolvedValue(linkOptions);
    vi.mocked(saveInvestmentProfile).mockResolvedValue(savedProfile);
  });

  it("renders the Figma dynamic-island status bar on the intro screen", () => {
    const { container } = renderLogin();
    expect(container.querySelector(".ios-statusbar")).not.toBeNull();
    expect(container.querySelector(".ios-statusbar-island")).not.toBeNull();
    expect(container.querySelector(".ios-statusbar-time")).toHaveTextContent("9:41");
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

  it("loads account metadata and requires consent before entering the app", async () => {
    renderLogin();
    openForm();
    fillLoginForm();
    fireEvent.click(screen.getByRole("button", { name: "로그인하기" }));
    await screen.findByText("로그인 성공!");

    fireEvent.click(screen.getByRole("button", { name: "시작하기" }));

    expect(await screen.findByText("DC형 퇴직연금")).toBeInTheDocument();
    expect(screen.queryByText("DB형 퇴직연금")).not.toBeInTheDocument();
    expect(screen.getByText("마이데이터를 통해 내 연금계좌를 안전하게 연동해서 가져와요.")).toBeInTheDocument();
    const continueButton = screen.getByRole("button", { name: "연동 내 연금계좌 보기" });
    expect(continueButton).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "필수 정보 이용 내용을 확인했습니다." }));
    expect(continueButton).toBeEnabled();
    fireEvent.click(continueButton);
    expect(screen.getByRole("heading", { name: "연금 계좌에 연동하고 있어요" })).toBeInTheDocument();
    expect(onStart).not.toHaveBeenCalled();
  });

  it("returns to the success screen from account consent", async () => {
    renderLogin();
    openForm();
    fillLoginForm();
    fireEvent.click(screen.getByRole("button", { name: "로그인하기" }));
    await screen.findByText("로그인 성공!");
    fireEvent.click(screen.getByRole("button", { name: "시작하기" }));
    await screen.findByText("DC형 퇴직연금");

    fireEvent.click(screen.getByRole("button", { name: "로그인 성공 화면으로 돌아가기" }));

    expect(screen.getByText("로그인 성공!")).toBeInTheDocument();
  });

  it("retries when account metadata fails to load", async () => {
    vi.mocked(getAccountLinkOptions)
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce(linkOptions);
    renderLogin();
    openForm();
    fillLoginForm();
    fireEvent.click(screen.getByRole("button", { name: "로그인하기" }));
    await screen.findByText("로그인 성공!");
    fireEvent.click(screen.getByRole("button", { name: "시작하기" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("연결 가능한 계좌 정보를 불러오지 못했습니다.");
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    expect(await screen.findByText("DC형 퇴직연금")).toBeInTheDocument();
    expect(getAccountLinkOptions).toHaveBeenCalledTimes(2);
  });

  it("shows the assessment result before entering the app", async () => {
    auth = {
      ...auth,
      session: { access_token: "access-token", user: { id: "user-1" } },
    } as SupabaseAuthState;
    const { container } = render(<LoginFlowPage auth={auth} displayName="이정수" onAuthenticated={onAuthenticated} onProfileSaved={onProfileSaved} onStart={onStart} resurvey />);

    fireEvent.click(screen.getByRole("button", { name: "투자 성향 진단받기" }));
    fireEvent.click(screen.getByRole("button", { name: "테스트 설문 저장" }));

    await waitFor(() => expect(saveInvestmentProfile).toHaveBeenCalledWith(expect.any(Object), "access-token"));
    expect(onProfileSaved).toHaveBeenCalledWith(savedProfile);
    expect(await screen.findByText("이정수님의 투자성향은")).toBeInTheDocument();
    expect(container.querySelector(".irs-type")).toHaveTextContent("공격투자형 입니다.");
    expect(onStart).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "서비스 시작하기" }));
    expect(onStart).toHaveBeenCalledOnce();
  });

  it("enters the home screen from success when a saved profile exists", async () => {
    render(<LoginFlowPage auth={auth} hasSavedProfile onAuthenticated={onAuthenticated} onProfileSaved={onProfileSaved} onStart={onStart} />);
    openForm();
    fillLoginForm();
    fireEvent.click(screen.getByRole("button", { name: "로그인하기" }));
    await screen.findByText("로그인 성공!");

    fireEvent.click(screen.getByRole("button", { name: "시작하기" }));

    expect(onStart).toHaveBeenCalledOnce();
    expect(getAccountLinkOptions).not.toHaveBeenCalled();
  });

  it("waits on the success screen while the saved profile is still loading", async () => {
    render(<LoginFlowPage auth={auth} onAuthenticated={onAuthenticated} onProfileSaved={onProfileSaved} onStart={onStart} profileLoading />);
    openForm();
    fillLoginForm();
    fireEvent.click(screen.getByRole("button", { name: "로그인하기" }));
    await screen.findByText("로그인 성공!");

    expect(screen.getByRole("button", { name: "정보를 확인하는 중..." })).toBeDisabled();
    expect(onStart).not.toHaveBeenCalled();
  });
});
