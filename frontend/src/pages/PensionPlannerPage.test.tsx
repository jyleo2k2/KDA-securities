// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  calculateCombinedPension,
  calculatePensionTaxCredit,
} from "../api/client";
import pensionCalculatorHtml from "../../public/pension-calculator-html/연금계산기.dc.html?raw";
import { PensionPlannerPage } from "./PensionPlannerPage";

vi.mock("../api/client", () => ({
  calculateCombinedPension: vi.fn(),
  calculatePension: vi.fn(),
  calculatePensionTaxCredit: vi.fn(),
}));

afterEach(cleanup);

describe("PensionPlannerPage", () => {
  const props = {
    aggregation: null,
    financialContext: null,
    onBack: vi.fn(),
    portfolio: null,
    profile: null,
  };

  it("renders the supplied calculator HTML without changing its theme", () => {
    render(<PensionPlannerPage {...props} />);

    expect(screen.getByTitle("예상 연금 계산 및 세액공제 확인")).toHaveAttribute(
      "src",
      "/pension-calculator-html/연금계산기.dc.html",
    );
    expect(screen.getByTitle("예상 연금 계산 및 세액공제 확인")).toHaveStyle({
      height: "100%",
    });
  });

  it("moves every monetary slider in 1만원 increments", () => {
    const calculatorDocument = new DOMParser().parseFromString(
      pensionCalculatorHtml,
      "text/html",
    );
    const monetaryRanges = [
      "onMonthly",
      "onPaidP",
      "onPaidI",
      "onIsa",
    ].map((handler) => calculatorDocument.querySelector<HTMLInputElement>(
      `input[type="range"][oninput*="${handler}"]`,
    ));

    expect(monetaryRanges).not.toContain(null);
    expect(monetaryRanges.map((range) => range?.step)).toEqual([
      "1",
      "1",
      "1",
      "1",
    ]);
  });

  it("forwards the calculator back button to the supplied callback", () => {
    const onBack = vi.fn();

    render(
      <PensionPlannerPage {...props} onBack={onBack} />,
    );

    const iframe = screen.getByTitle("예상 연금 계산 및 세액공제 확인") as HTMLIFrameElement;
    const frameDocument = iframe.contentDocument;
    expect(frameDocument).not.toBeNull();
    if (!frameDocument) return;

    frameDocument.open();
    frameDocument.write('<!doctype html><body><button type="button" data-pension-planner-back>뒤로 가기</button></body>');
    frameDocument.close();
    fireEvent.load(iframe);
    fireEvent.click(frameDocument.querySelector("[data-pension-planner-back]") as HTMLButtonElement);

    expect(onBack).toHaveBeenCalledOnce();
  });

  it("calculates all owned accounts through the combined engine", async () => {
    vi.mocked(calculateCombinedPension).mockResolvedValue({
      headline: {},
      yearly: [],
      strategies: [],
      tax: {},
      assumption: {},
      warnings: [],
    } as never);
    render(
      <PensionPlannerPage
        {...props}
        aggregation={{ total_amount_krw: "60000000" } as never}
        portfolio={{
          owner_id: "owner-1",
          data_boundary: "mock",
          accounts: [
            {
              account_id: "dc-1",
              account_name: "회사 DC",
              account_type: "dc",
              market_value_krw: "40000000",
              holdings: [],
            },
            {
              account_id: "irp-1",
              account_name: "개인 IRP",
              account_type: "irp",
              market_value_krw: "20000000",
              holdings: [],
            },
          ] as never,
        }}
        profile={{ current_age: 35, risk_profile: "risk_neutral" }}
      />,
    );

    const iframe = screen.getByTitle("예상 연금 계산 및 세액공제 확인") as HTMLIFrameElement;
    window.dispatchEvent(new MessageEvent("message", {
      data: { type: "pension-planner-ready" },
      origin: window.location.origin,
      source: iframe.contentWindow,
    }));

    await waitFor(() => expect(calculateCombinedPension).toHaveBeenCalledWith(
      expect.objectContaining({
        contribution_end_age: 60,
        accounts: [
          expect.objectContaining({ account_id: "dc-1" }),
          expect.objectContaining({ account_id: "irp-1" }),
        ],
      }),
    ));
  });

  it("caps the default contribution end age at 65", async () => {
    vi.mocked(calculateCombinedPension).mockResolvedValue({
      headline: {},
      yearly: [],
      strategies: [],
      tax: {},
      assumption: {},
      warnings: [],
    } as never);
    render(
      <PensionPlannerPage
        {...props}
        aggregation={{ total_amount_krw: "40000000" } as never}
        portfolio={{
          owner_id: "owner-1",
          data_boundary: "mock",
          accounts: [
            {
              account_id: "dc-1",
              account_name: "회사 DC",
              account_type: "dc",
              market_value_krw: "40000000",
              holdings: [],
            },
          ] as never,
        }}
        profile={{ current_age: 64, risk_profile: "risk_neutral" }}
      />,
    );

    const iframe = screen.getByTitle("예상 연금 계산 및 세액공제 확인") as HTMLIFrameElement;
    window.dispatchEvent(new MessageEvent("message", {
      data: { type: "pension-planner-ready" },
      origin: window.location.origin,
      source: iframe.contentWindow,
    }));

    await waitFor(() => expect(calculateCombinedPension).toHaveBeenCalledWith(
      expect.objectContaining({ contribution_end_age: 65 }),
    ));
  });

  it("forwards the calculated monthly payout to the calculator frame", async () => {
    vi.mocked(calculateCombinedPension).mockResolvedValue({
      headline: { monthly_payout_after_tax_krw: "1351219" },
      yearly: [],
      strategies: [],
      tax: {},
      assumption: {},
      warnings: [],
    } as never);
    render(
      <PensionPlannerPage
        {...props}
        aggregation={{ total_amount_krw: "40000000" } as never}
        portfolio={{
          owner_id: "owner-1",
          data_boundary: "mock",
          accounts: [
            {
              account_id: "dc-1",
              account_name: "회사 DC",
              account_type: "dc",
              market_value_krw: "40000000",
              holdings: [],
            },
          ] as never,
        }}
        profile={{ current_age: 35, risk_profile: "risk_neutral" }}
      />,
    );

    const iframe = screen.getByTitle("예상 연금 계산 및 세액공제 확인") as HTMLIFrameElement;
    const postMessage = vi.spyOn(iframe.contentWindow as Window, "postMessage");
    window.dispatchEvent(new MessageEvent("message", {
      data: { type: "pension-planner-ready" },
      origin: window.location.origin,
      source: iframe.contentWindow,
    }));

    await waitFor(() => expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        payload: expect.objectContaining({
          calculation: expect.objectContaining({
            headline: expect.objectContaining({
              monthly_payout_after_tax_krw: "1351219",
            }),
          }),
        }),
      }),
      window.location.origin,
    ));
    postMessage.mockRestore();
  });

  it("forwards all ten investment theme strategies to the calculator frame", async () => {
    vi.mocked(calculateCombinedPension).mockResolvedValue({
      headline: {},
      yearly: [],
      strategies: [],
      tax: {},
      assumption: {},
      warnings: [],
    } as never);
    render(
      <PensionPlannerPage
        {...props}
        aggregation={{ total_amount_krw: "40000000" } as never}
        portfolio={{
          owner_id: "owner-1",
          data_boundary: "mock",
          accounts: [
            {
              account_id: "dc-1",
              account_name: "회사 DC",
              account_type: "dc",
              market_value_krw: "40000000",
              holdings: [],
            },
          ] as never,
        }}
        profile={{ current_age: 35, risk_profile: "risk_neutral" }}
      />,
    );

    const iframe = screen.getByTitle("예상 연금 계산 및 세액공제 확인") as HTMLIFrameElement;
    const postMessage = vi.spyOn(iframe.contentWindow as Window, "postMessage");
    window.dispatchEvent(new MessageEvent("message", {
      data: { type: "pension-planner-ready" },
      origin: window.location.origin,
      source: iframe.contentWindow,
    }));

    await waitFor(() => expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        payload: expect.objectContaining({
          themeStrategies: [
            expect.objectContaining({ id: "market-beta", name: "시장 베타 전략" }),
            expect.objectContaining({ id: "factor", name: "팩터 전략" }),
            expect.objectContaining({ id: "theme", name: "테마 전략" }),
            expect.objectContaining({ id: "topdown", name: "탑다운 전략" }),
            expect.objectContaining({ id: "bottomup", name: "바텀업 전략" }),
            expect.objectContaining({ id: "barbell", name: "바벨 전략" }),
            expect.objectContaining({ id: "volatility", name: "변동성 관리 전략" }),
            expect.objectContaining({ id: "longshort", name: "롱숏·시장중립 전략" }),
            expect.objectContaining({ id: "eventdriven", name: "이벤트드리븐 전략" }),
            expect.objectContaining({ id: "trend", name: "추세추종·글로벌 매크로 전략" }),
          ],
        }),
      }),
      window.location.origin,
    ));
    postMessage.mockRestore();
  });

  it("loads the signed-in owner's contributions and classifies an entered income through the tax engine", async () => {
    vi.mocked(calculateCombinedPension).mockResolvedValue({
      headline: {},
      yearly: [],
      strategies: [],
      tax: {},
      assumption: {},
      warnings: [],
    } as never);
    vi.mocked(calculatePensionTaxCredit)
      .mockResolvedValueOnce({
        rate_determined: false,
        rate_scenarios: [],
      } as never)
      .mockResolvedValueOnce({
        rate_determined: true,
        additional_tax_credit_krw: "204600",
        rate_scenarios: [{
          local_inclusive_display_rate_percent: "16.5",
        }],
      } as never);

    render(
      <PensionPlannerPage
        {...props}
        aggregation={{ total_amount_krw: "60000000" } as never}
        financialContext={{
          auth_user_id: "owner-1",
          income_basis: "gross_salary",
          income_amount_krw: "55000000",
          pension_savings_contribution_krw: "3840000",
          irp_contribution_krw: "4920000",
        } as never}
        portfolio={{
          owner_id: "owner-1",
          data_boundary: "mock",
          accounts: [{
            account_id: "irp-1",
            account_name: "개인 IRP",
            account_type: "irp",
            market_value_krw: "60000000",
            holdings: [],
          }] as never,
        }}
        profile={{ current_age: 35, risk_profile: "risk_neutral" }}
      />,
    );

    const iframe = screen.getByTitle("예상 연금 계산 및 세액공제 확인") as HTMLIFrameElement;
    const postMessage = vi.spyOn(iframe.contentWindow as Window, "postMessage");
    window.dispatchEvent(new MessageEvent("message", {
      data: { type: "pension-planner-ready" },
      origin: window.location.origin,
      source: iframe.contentWindow,
    }));

    await waitFor(() => expect(calculatePensionTaxCredit).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        income_basis: "unknown",
        income_amount_krw: null,
        pension_savings_contribution_krw: "3840000",
        irp_contribution_krw: "4920000",
      }),
    ));
    await waitFor(() => expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        payload: expect.objectContaining({
          taxContext: expect.objectContaining({
            ownerId: "owner-1",
            paidP: 384,
            paidI: 492,
          }),
        }),
      }),
      window.location.origin,
    ));

    window.dispatchEvent(new MessageEvent("message", {
      data: {
        type: "pension-planner-tax-calculate",
        payload: {
          incomeBasis: "gross_salary",
          incomeAmountManwon: 5000,
          paidP: 384,
          paidI: 492,
          isa: 0,
        },
      },
      origin: window.location.origin,
      source: iframe.contentWindow,
    }));

    await waitFor(() => expect(calculatePensionTaxCredit).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        income_basis: "gross_salary",
        income_amount_krw: "50000000",
      }),
    ));
    await waitFor(() => expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "pension-planner-tax-state",
        payload: expect.objectContaining({
          incomeBasis: "gross_salary",
          incomeAmountManwon: 5000,
          calculation: expect.objectContaining({ rate_determined: true }),
        }),
      }),
      window.location.origin,
    ));
    postMessage.mockRestore();
  });
});
