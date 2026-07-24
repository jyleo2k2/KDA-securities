// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SlangiTouchPage } from "./SlangiTouchPage";

describe("SlangiTouchPage", () => {
  it("renders the supplied slangi HTML without changing it", () => {
    render(<SlangiTouchPage />);

    expect(screen.getByTitle("연그미를 만져 보세요")).toHaveAttribute(
      "src",
      "/slangi/index.html",
    );
  });
});
