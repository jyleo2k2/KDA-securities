// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfileHtmlPage } from "./ProfileHtmlPage";

afterEach(cleanup);

describe("ProfileHtmlPage", () => {
  it("loads the supplied profile html from its explicit public file path", () => {
    render(<ProfileHtmlPage onBack={vi.fn()} />);

    expect(screen.getByTitle("내 프로필")).toHaveAttribute(
      "src",
      "/profile-html/index.html",
    );
  });

  it("forwards the profile back button to the supplied callback", () => {
    const onBack = vi.fn();

    render(<ProfileHtmlPage onBack={onBack} />);

    const iframe = screen.getByTitle("내 프로필") as HTMLIFrameElement;
    const frameDocument = iframe.contentDocument;
    expect(frameDocument).not.toBeNull();
    if (!frameDocument) return;

    frameDocument.open();
    frameDocument.write('<!doctype html><body><button type="button" data-profile-html-back>뒤로 가기</button></body>');
    frameDocument.close();
    fireEvent.load(iframe);
    fireEvent.click(frameDocument.querySelector("[data-profile-html-back]") as HTMLButtonElement);

    expect(onBack).toHaveBeenCalledOnce();
  });
});
