// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getAccountLinkOptions, saveInvestmentProfile } from "../api/client";
import type { AccountLinkOptionsResponse, InvestmentProfileResponse } from "../api/types";
import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import { LoginFlowPage } from "./LoginFlowPage";

vi.mock("../api/client", () => ({ getAccountLinkOptions: vi.fn(), saveInvestmentProfile: vi.fn(), getInvestmentProfile: vi.fn() }));

const onStart = vi.fn();
const onAuthenticated = vi.fn();
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

const savedProfile: InvestmentProfileResponse = {
  assessment: { assessed_at: "2026-07-22T00:00:00Z", assessed_on: "2026-07-22", valid_until: "2028-07-21", is_expired: false, validity_policy_version: "2026-07-20.1", total_score: 25, min_score: 10, max_score: 56, score_percent: "32.61", risk_profile: "risk_neutral", engine_name: "investor_profile", engine_version: "2026-07-22.1", rule_version: "shinhan-personal-general-login-union-2026-07-22", provisional: false, answers: [] },
  preferences: { investment_advice_desired: true, investor_information_provided: true, confirmed_at: "2026-07-22T00:00:00Z", policy_version: "2026-07-20.1" },
};

function selectCompleteSurvey(provide = "제공"): void {
  fireEvent.click(screen.getByRole("button", { name: "희망" }));
  fireEvent.click(screen.getByRole("button", { name: provide }));
  ["만19세 미만", "1억원 미만", "2천만원 미만", "10% 미만"].forEach((name) => fireEvent.click(screen.getByRole("button", { name })));
  screen.getAllByRole("button", { name: "0~9%" }).forEach((button) => fireEvent.click(button));
  ["예금, CMA, MMF, RP, 국공채 등", "1년 이상~3년 미만", "교육비", "금융투자상품에 투자해 본 경험이 없음", "1년 이상~2년 미만", "투자 수익을 고려하나 원금 보존이 더 중요함", "제한적인 손실을 감수하여 시중금리 수준의 수익을 기대", "1년 ~ 3년 미만", "예", "동의", "만 55세"].forEach((name) => fireEvent.click(screen.getByRole("button", { name })));
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
    expect(screen.getByText("DB형 퇴직연금")).toBeInTheDocument();
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

  it("submits every server-defined survey answer for scoring and storage", async () => {
    auth.session = { access_token: "token", user: { user_metadata: {} } } as unknown as SupabaseAuthState["session"];
    render(<LoginFlowPage auth={auth} onAuthenticated={onAuthenticated} onStart={onStart} resurvey />);
    selectCompleteSurvey();
    fireEvent.click(screen.getByRole("button", { name: "투자자정보확인서 제출" }));

    await waitFor(() => expect(saveInvestmentProfile).toHaveBeenCalledOnce());
    const [submission, token] = vi.mocked(saveInvestmentProfile).mock.calls[0];
    expect(token).toBe("token");
    expect(submission.investment_advice_desired).toBe(true);
    expect(submission.investor_information_provided).toBe(true);
    expect(submission.survey.answers.map((answer) => answer.question_code)).toEqual(["age_band", "total_net_assets", "annual_income", "financial_asset_share", "investment_product_share", "loan_product_share", "investment_experience_product", "investment_experience_period", "investment_purpose", "financial_knowledge", "investment_horizon", "risk_attitude", "loss_tolerance", "derivative_experience", "vulnerable_investor", "validity_consent", "retirement_start_age"]);
  }, 15000);

  it("blocks investment advice when investor information is not provided", () => {
    auth.session = { access_token: "token", user: { user_metadata: {} } } as unknown as SupabaseAuthState["session"];
    render(<LoginFlowPage auth={auth} onAuthenticated={onAuthenticated} onStart={onStart} resurvey />);
    selectCompleteSurvey("미제공");
    fireEvent.click(screen.getByRole("button", { name: "투자자정보확인서 제출" }));

    expect(screen.getByRole("alert")).toHaveTextContent("투자자정보 제공에 동의해야 투자권유를 받을 수 있어요");
    expect(saveInvestmentProfile).not.toHaveBeenCalled();
  }, 15000);
});
