// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestorInfoForm } from "./InvestorInfoForm";

describe("InvestorInfoForm", () => {
  afterEach(cleanup);

  it("shows one question at a time and keeps an answer when returning", () => {
    render(<InvestorInfoForm onBack={vi.fn()} onSubmit={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    expect(screen.getByRole("alert")).toHaveTextContent("투자권유와 투자자정보 제공 여부를 선택해 주세요.");

    fireEvent.click(screen.getByRole("button", { name: "희망" }));
    fireEvent.click(screen.getByRole("button", { name: "제공" }));
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    expect(screen.getByText("고객님의 연령대는 어떻게 되시나요?")).toBeInTheDocument();
    expect(screen.getByLabelText("진행 상황 1 / 17")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "만 19세~만 40세" }));
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    expect(screen.getByText("고객님의 총 자산규모(순자산)는 어느 정도 되시나요?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "이전" }));
    expect(screen.getByRole("button", { name: "만 19세~만 40세" })).toHaveAttribute("aria-pressed", "true");
  });

  it("allows multiple selections for questions that support them", () => {
    render(<InvestorInfoForm onBack={vi.fn()} onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "미희망" }));
    fireEvent.click(screen.getByRole("button", { name: "제공" }));
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    const firstOptions = ["만 19세 미만", "1억 원 미만", "2천만 원 미만", "10% 미만", "0~9%", "0~9%"];
    for (const option of firstOptions) {
      fireEvent.click(screen.getByRole("button", { name: option }));
      fireEvent.click(screen.getByRole("button", { name: "다음" }));
    }

    expect(screen.getByText("고객님께서 투자경험이 있는 금융상품을 모두 선택해 주세요.")).toBeInTheDocument();
    const deposit = screen.getByRole("button", { name: "예금, CMA, MMF, RP, 국공채 등" });
    const stock = screen.getByRole("button", { name: "주식, 주식형펀드, 원금비보장형 ELS/DLS, 고위험회사채" });
    fireEvent.click(deposit);
    fireEvent.click(stock);
    expect(deposit).toHaveAttribute("aria-pressed", "true");
    expect(stock).toHaveAttribute("aria-pressed", "true");
  });

  it("submits the existing 17-question payload after the final screen", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<InvestorInfoForm onBack={vi.fn()} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByRole("button", { name: "미희망" }));
    fireEvent.click(screen.getByRole("button", { name: "제공" }));
    fireEvent.click(screen.getByRole("button", { name: "다음" }));

    const firstOptions = [
      "만 19세 미만", "1억 원 미만", "2천만 원 미만", "10% 미만", "0~9%", "0~9%",
      "예금, CMA, MMF, RP, 국공채 등", "투자경험 없음", "교육비", "금융투자상품에 투자해 본 경험이 없음",
      "1년 미만", "투자 수익을 고려하나 원금 보존이 더 중요함", "제한적인 손실을 감수하여 시중금리 수준의 수익을 기대",
      "투자경험 없음", "예", "동의", "만 55세",
    ];
    for (const [index, option] of firstOptions.entries()) {
      fireEvent.click(screen.getByRole("button", { name: option }));
      fireEvent.click(screen.getByRole("button", { name: index === firstOptions.length - 1 ? "진단 완료" : "다음" }));
    }

    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      survey: expect.objectContaining({ answers: expect.arrayContaining([expect.objectContaining({ question_code: "retirement_start_age", selected_values: ["55"] })]) }),
      investment_advice_desired: false,
      investor_information_provided: true,
    }));
  });
});
