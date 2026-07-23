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
  label: "교육용 포트폴리오",
  locator: "demo",
  data_boundary: "mock",
  publisher: "연금 코파일럿",
  as_of: "2026-07-23",
}];

describe("ChatVisualization allocation donut", () => {
  afterEach(cleanup);

  it("shows and hides selected allocation detail with its evidence", () => {
    render(<ChatVisualization visualization={visualization} sources={sources} />);

    const slice = screen.getByRole("button", { name: "국내주식 45%" });
    fireEvent.click(slice);

    expect(screen.getByText("국내주식 상세")).toBeInTheDocument();
    expect(screen.getByText("비중 45%")).toBeInTheDocument();
    expect(screen.getByText(/계좌 데이터 · 교육용 포트폴리오 · 연금 코파일럿 · 2026-07-23/)).toBeInTheDocument();

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
});
