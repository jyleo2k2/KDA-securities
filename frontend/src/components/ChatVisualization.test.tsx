// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ChatVisualization as ChatVisualizationData, SourceEvidence } from "../api/types";
import { ChatVisualization } from "./ChatVisualization";

const visualization: ChatVisualizationData = {
  kind: "asset_allocation",
  title: "자산배분",
  description: "현재 자산군 비중입니다.",
  data_boundary: "mock",
  evidence_ids: ["allocation-source"],
  items: [
    { label: "국내주식", value: 45, unit: "%", role: "segment" },
    { label: "채권", value: 55, unit: "%", role: "segment" },
  ],
  series: [],
};

const sources: SourceEvidence[] = [{
  evidence_id: "allocation-source",
  label: "포트폴리오",
  locator: "demo",
  data_boundary: "mock",
  publisher: "연금 코파일럿",
  as_of: "2026-07-23",
}];

describe("ChatVisualization allocation donut", () => {
  afterEach(cleanup);

  it("shows and hides selected allocation detail with its evidence", () => {
    render(<ChatVisualization visualization={visualization} sources={sources} />);

    expect(screen.getByText("전체")).toHaveClass("allocation-donut-label");
    expect(screen.getByText("100%")).toHaveClass("allocation-donut-total");

    const slice = screen.getByRole("button", { name: "국내주식 45%" });
    fireEvent.click(slice);

    expect(screen.getByText("국내주식 상세")).toBeInTheDocument();
    expect(screen.getByText("비중 45%")).toBeInTheDocument();
    expect(screen.getByText(/계좌 정보 · 포트폴리오 · 연금 코파일럿 · 2026-07-23/)).toBeInTheDocument();

    fireEvent.click(slice);

    expect(screen.queryByText("국내주식 상세")).not.toBeInTheDocument();
  });

  it("renders selected allocation detail safely without matching evidence", () => {
    render(<ChatVisualization visualization={{ ...visualization, evidence_ids: [] }} sources={[]} />);

    fireEvent.click(screen.getByRole("button", { name: "채권 55%" }));

    expect(screen.getByText("채권 상세")).toBeInTheDocument();
    expect(screen.getByText("비중 55%")).toBeInTheDocument();
    expect(screen.queryByLabelText("출처")).not.toBeInTheDocument();
  });

  it("renders the tax summary as three horizontal rows without overflow", () => {
    const { container } = render(
      <ChatVisualization
        visualization={{
          ...visualization,
          kind: "tax_summary",
          title: "세액공제 요약",
          items: [
            { label: "세액공제 대상 납입액", value: 8760000, unit: "KRW", role: "value" },
            { label: "세액공제율", value: 13.2, unit: "%", role: "value" },
            { label: "세액공제액", value: 1156320, unit: "KRW", role: "value" },
          ],
        }}
        sources={sources}
      />,
    );

    const grid = container.querySelector(".tax-summary-grid");
    const rows = container.querySelectorAll(".tax-summary-grid > div");
    expect(grid).toHaveStyle({
      gridTemplateColumns: "minmax(0, 1fr)",
      overflowX: "hidden",
    });
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveStyle({
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
    });
    expect(rows[0].querySelector("span")).toHaveStyle({
      textAlign: "left",
      whiteSpace: "nowrap",
    });
    expect(rows[0].querySelector("strong")).toHaveStyle({
      textAlign: "right",
      whiteSpace: "nowrap",
    });
  });

  it("uses the target-allocation donut style for sleeve allocations", () => {
    const { container } = render(
      <ChatVisualization
        visualization={{
          ...visualization,
          kind: "sleeve_allocation",
          title: "DC형 목표 자산배분",
          items: [
            { label: "주식", value: 48, unit: "%", role: "segment" },
            { label: "금/원자재", value: 7, unit: "%", role: "segment" },
            { label: "현금", value: 19.5, unit: "%", role: "segment" },
            { label: "채권", value: 25.5, unit: "%", role: "segment" },
          ],
        }}
        sources={sources}
      />,
    );

    expect(container.querySelector(".sleeve-allocation-donut")).toBeInTheDocument();
    expect(container.querySelector(".sleeve-allocation-legend")).toBeInTheDocument();
    expect(screen.getByText("DC형 목표 자산배분")).toBeInTheDocument();
    expect(screen.queryByText("IRP & DC형 목표 자산배분")).not.toBeInTheDocument();
    expect(screen.getByText("현재 자산군 비중입니다.")).toHaveStyle({ marginTop: 0 });
    expect(screen.getByText("금/원자재")).toBeInTheDocument();
    expect(container.querySelector("path")).toHaveAttribute("stroke", "none");
    expect(screen.getByText("전체")).toHaveClass("allocation-donut-label");
    expect(screen.getByText("100%")).toHaveClass("allocation-donut-total");

    const equitySlice = screen.getByRole("button", { name: "주식 48%" });
    const pointerDownEvent = new Event("pointerdown", {
      bubbles: true,
      cancelable: true,
    });
    expect(equitySlice.dispatchEvent(pointerDownEvent)).toBe(false);
    expect(pointerDownEvent.defaultPrevented).toBe(true);

    equitySlice.focus();
    expect(equitySlice).toHaveFocus();
    fireEvent.keyDown(equitySlice, { key: "Enter" });
    expect(screen.getByText("주식 상세")).toBeInTheDocument();
  });

  it("prefixes stress-scenario losses with a minus sign", () => {
    render(
      <ChatVisualization
        visualization={{
          ...visualization,
          kind: "stress_scenarios",
          title: "DC형 스트레스 점검",
          items: [{ label: "주식시장 급락", value: 27.3, unit: "%", role: "value" }],
        }}
        sources={sources}
      />,
    );

    expect(screen.getByText("DC형 스트레스 점검")).toBeInTheDocument();
    expect(screen.queryByText("IRP & DC형 스트레스 점검")).not.toBeInTheDocument();
    expect(screen.getByText("현재 자산군 비중입니다.")).toHaveStyle({ marginTop: 0 });
    expect(screen.getByText("-27.3%")).toBeInTheDocument();
  });
});
