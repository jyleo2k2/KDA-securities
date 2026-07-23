// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfileHtmlPage } from "./ProfileHtmlPage";

afterEach(cleanup);

describe("ProfileHtmlPage", () => {
  const props = {
    displayName: "박준호",
    email: "user@example.com",
    investmentProfile: null,
    portfolio: null,
    onBack: vi.fn(),
  };

  it("loads the supplied profile html from its explicit public file path", () => {
    render(<ProfileHtmlPage {...props} />);

    expect(screen.getByTitle("내 프로필")).toHaveAttribute(
      "src",
      "/profile-html/index.html",
    );
  });

  it("forwards the profile back button to the supplied callback", () => {
    const onBack = vi.fn();

    render(<ProfileHtmlPage {...props} onBack={onBack} />);

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

  it("writes the authenticated owner data into the supplied profile screen", () => {
    render(
      <ProfileHtmlPage
        {...props}
        investmentProfile={{
          assessment: { risk_profile: "active" } as never,
          preferences: null,
        }}
        portfolio={{
          owner_id: "owner-1",
          data_boundary: "real",
          accounts: [{ as_of_date: "2026-07-23" } as never],
        }}
      />,
    );

    const iframe = screen.getByTitle("내 프로필") as HTMLIFrameElement;
    const frameDocument = iframe.contentDocument;
    expect(frameDocument).not.toBeNull();
    if (!frameDocument) return;

    frameDocument.open();
    frameDocument.write(`<!doctype html><body>
      <span data-profile-name></span><span data-profile-email></span>
      <span data-profile-boundary></span><span data-profile-as-of></span>
      <span data-profile-risk></span>
    </body>`);
    frameDocument.close();
    fireEvent.load(iframe);

    expect(frameDocument.querySelector("[data-profile-name]")).toHaveTextContent("박준호");
    expect(frameDocument.querySelector("[data-profile-boundary]")).toHaveTextContent("실계좌 데이터");
    expect(frameDocument.querySelector("[data-profile-as-of]")).toHaveTextContent("2026-07-23");
    expect(frameDocument.querySelector("[data-profile-risk]")).toHaveTextContent("적극투자형");
  });
});
