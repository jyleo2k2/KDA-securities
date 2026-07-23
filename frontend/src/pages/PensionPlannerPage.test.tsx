// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PensionPlannerPage } from "./PensionPlannerPage";

afterEach(cleanup);

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

  it("forwards the calculator back button to the supplied callback", () => {
    const onBack = vi.fn();

    render(
      <PensionPlannerPage
        onBack={onBack}
        onOpenProfile={vi.fn()}
        profile={null}
        userContext={null}
      />,
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
});
