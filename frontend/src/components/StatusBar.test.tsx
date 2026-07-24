// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StatusBar } from "./StatusBar";

afterEach(cleanup);

describe("StatusBar", () => {
  it("renders the iOS clock and tone class", () => {
    const { container } = render(<StatusBar className="desktop-preview-status" />);
    expect(container.querySelector(".ios-statusbar-time")).toHaveTextContent("9:41");
    expect(container.querySelector(".ios-statusbar--dark")).not.toBeNull();
    expect(container.querySelector(".desktop-preview-status")).not.toBeNull();
    expect(container.querySelector(".ios-statusbar-island")).not.toBeNull();
    expect(container.querySelector(".ios-statusbar-lens")).not.toBeNull();
    expect(container.querySelector(".ios-statusbar-cellular")).not.toBeNull();
    expect(container.querySelector(".ios-statusbar-wifi")).not.toBeNull();
    expect(container.querySelector(".ios-statusbar-battery")).not.toBeNull();
  });

  it("switches to the light tone on demand", () => {
    const { container } = render(<StatusBar tone="light" time="10:08" />);
    expect(container.querySelector(".ios-statusbar-time")).toHaveTextContent("10:08");
    expect(container.querySelector(".ios-statusbar--light")).not.toBeNull();
  });
});
