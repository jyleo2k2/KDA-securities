// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PensionPlannerPage } from "./PensionPlannerPage";

describe("PensionPlannerPage", () => {
  it("renders the supplied calculator HTML without changing its theme", () => {
    render(
      <PensionPlannerPage
        onBack={vi.fn()}
        onOpenProfile={vi.fn()}
        profile={null}
        userContext={null}
      />,
    );

    expect(screen.getByTitle("예상 연금 계산 및 세액공제 확인")).toHaveAttribute(
      "src",
      "/pension-calculator-html/연금계산기.dc.html",
    );
  });
});
