// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestorInfoForm } from "./InvestorInfoForm";

function answer(questionOptions: Array<[string, string]>): void {
  for (const [question, option] of questionOptions) fireEvent.click(within(screen.getByLabelText(question)).getByRole("button", { name: option }));
}

describe("InvestorInfoForm", () => {
  afterEach(cleanup);

  it("groups the questions into three screens and fills the progress bar per screen", () => {
    render(<InvestorInfoForm onBack={vi.fn()} onSubmit={vi.fn()} />);

    expect(screen.getByText("고객님의 연령대는 어떻게 되시나요?")).toBeInTheDocument();
    expect(screen.getByText("고객님의 총자산 중 투자성 상품의 비중은 어느 정도 되시나요?")).toBeInTheDocument();
    expect(screen.queryByText("고객님의 총자산 중 대출성 상품의 비중은 어느 정도 되시나요?")).not.toBeInTheDocument();
    expect(screen.getByLabelText("진행 상황 1 / 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "미희망" }));
    fireEvent.click(screen.getByRole("button", { name: "미제공" }));
    expect(screen.getByRole("button", { name: "미제공" })).toHaveClass("iif-segmented-negative");
    answer([
      ["고객님의 연령대는 어떻게 되시나요?", "만 19세 미만"],
      ["고객님의 총 자산규모(순자산)는 어느 정도 되시나요?", "1억 원 미만"],
      ["고객님의 연간 소득 현황은 어느 정도 되시나요?", "2천만 원 미만"],
      ["고객님의 전체 자산 중 금융자산의 비중은 어느 정도 되시나요?", "10% 미만"],
      ["고객님의 총자산 중 투자성 상품의 비중은 어느 정도 되시나요?", "0~9%"],
    ]);
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    expect(screen.getByLabelText("진행 상황 2 / 3")).toBeInTheDocument();
    expect(screen.getByText("고객님의 총자산 중 대출성 상품의 비중은 어느 정도 되시나요?")).toBeInTheDocument();
    expect(screen.getByText("고객님의 투자 자금의 투자 예정 기간은 얼마나 되시나요?")).toBeInTheDocument();
    expect(screen.queryByText("고객님의 연령대는 어떻게 되시나요?")).not.toBeInTheDocument();
  });

  it("keeps answers when returning to an earlier screen", () => {
    render(<InvestorInfoForm onBack={vi.fn()} onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "미희망" }));
    fireEvent.click(screen.getByRole("button", { name: "제공" }));
    answer([
      ["고객님의 연령대는 어떻게 되시나요?", "만 19세~만 40세"],
      ["고객님의 총 자산규모(순자산)는 어느 정도 되시나요?", "1억 원 미만"],
      ["고객님의 연간 소득 현황은 어느 정도 되시나요?", "2천만 원 미만"],
      ["고객님의 전체 자산 중 금융자산의 비중은 어느 정도 되시나요?", "10% 미만"],
      ["고객님의 총자산 중 투자성 상품의 비중은 어느 정도 되시나요?", "0~9%"],
    ]);
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    fireEvent.click(screen.getByRole("button", { name: "이전" }));

    expect(screen.getByRole("button", { name: "만 19세~만 40세" })).toHaveAttribute("aria-pressed", "true");
  });

  it("submits the existing 17-question payload after all three screens", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<InvestorInfoForm onBack={vi.fn()} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole("button", { name: "미희망" }));
    fireEvent.click(screen.getByRole("button", { name: "제공" }));
    answer([
      ["고객님의 연령대는 어떻게 되시나요?", "만 19세 미만"],
      ["고객님의 총 자산규모(순자산)는 어느 정도 되시나요?", "1억 원 미만"],
      ["고객님의 연간 소득 현황은 어느 정도 되시나요?", "2천만 원 미만"],
      ["고객님의 전체 자산 중 금융자산의 비중은 어느 정도 되시나요?", "10% 미만"],
      ["고객님의 총자산 중 투자성 상품의 비중은 어느 정도 되시나요?", "0~9%"],
    ]);
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    answer([
      ["고객님의 총자산 중 대출성 상품의 비중은 어느 정도 되시나요?", "0~9%"],
      ["고객님께서 투자경험이 있는 금융상품을 모두 선택해 주세요.", "예금, CMA, MMF, RP, 국공채 등"],
      ["금융투자상품 투자경험 기간은 얼마나 되시나요?", "투자경험 없음"],
      ["고객님께서 금융상품을 투자하는 목적을 모두 선택해 주세요.", "교육비"],
      ["금융상품에 대한 지식·이해도는 어느 정도라고 생각하시나요?", "금융투자상품에 투자해 본 경험이 없음"],
      ["고객님의 투자 자금의 투자 예정 기간은 얼마나 되시나요?", "1년 미만"],
    ]);
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    answer([
      ["고객님께서 금융상품 투자를 통해 기대하는 수익과 감내할 수 있는 손실의 중요도는 어떻게 되시나요?", "투자 수익을 고려하나 원금 보존이 더 중요함"],
      ["기대수익률 및 손실감내도에 가장 가까운 항목을 선택해 주세요.", "제한적인 손실을 감수하여 시중금리 수준의 수익을 기대"],
      ["고객님의 파생상품에 대한 투자경험은 얼마나 되시나요?", "투자경험 없음"],
      ["고객님께서는 취약투자자에 해당되십니까?", "예"],
      ["투자자정보를 24개월간 유효하게 관리하는 데 동의하시나요?", "동의"],
      ["연금 수령을 시작할 나이를 선택해 주세요.", "만 55세"],
    ]);
    fireEvent.click(screen.getByRole("button", { name: "투자자정보확인서 제출" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      survey: expect.objectContaining({ answers: expect.arrayContaining([expect.objectContaining({ question_code: "retirement_start_age", selected_values: ["55"] })]) }),
      investment_advice_desired: false,
      investor_information_provided: true,
    }));
  });
});
