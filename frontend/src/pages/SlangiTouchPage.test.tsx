// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { SlangiTouchPage } from "./SlangiTouchPage";

afterEach(cleanup);

describe("SlangiTouchPage", () => {
  it("renders the supplied slangi HTML without changing it", () => {
    const { getByTitle } = render(
      <MemoryRouter>
        <SlangiTouchPage />
      </MemoryRouter>,
    );

    expect(getByTitle("연그미를 만져 보세요")).toHaveAttribute(
      "src",
      "/slangi/index.html",
    );
  });

  it("returns to the main home only for the embedded slangi page's back event", () => {
    const { getByTitle } = render(
      <MemoryRouter initialEntries={["/slangi"]}>
        <Routes>
          <Route path="/slangi" element={<SlangiTouchPage />} />
          <Route path="/main-home" element={<p>메인 홈</p>} />
        </Routes>
      </MemoryRouter>,
    );

    const iframe = getByTitle("연그미를 만져 보세요") as HTMLIFrameElement;
    act(() => {
      window.dispatchEvent(new MessageEvent("message", {
        data: { type: "slangi-back" },
        origin: window.location.origin,
        source: iframe.contentWindow,
      }));
    });

    expect(screen.getByText("메인 홈")).toBeInTheDocument();
  });
});
