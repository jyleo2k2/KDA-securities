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

  // 전역 `svg { stroke: currentColor; stroke-width: 1.7 }`(index.css)가 fill 전용
  // 상단바 아이콘에 외곽선을 덧그리면 Wi-Fi 호 사이가 메워져 통짜 삼각형이 된다.
  // 전역 규칙이 남아 있는 동안에는 상단바에서 반드시 stroke 를 끈다.
  // index.css 의 전역 `svg { stroke: currentColor; stroke-width: 1.7 }` 가 fill 전용
  // 상단바 아이콘에 외곽선을 덧그리면 Wi-Fi 호 사이가 메워져 통짜 삼각형이 된다.
  // profile-html(iframe)만 정상이던 회귀를 막는 가드.
  it("아이콘 SVG 는 전역 stroke 를 인라인으로 차단한다", () => {
    const { container } = render(<StatusBar />);
    for (const selector of [
      ".ios-statusbar-cellular",
      ".ios-statusbar-wifi",
      ".ios-statusbar-battery",
    ]) {
      const svg = container.querySelector(selector) as SVGElement | null;
      expect(svg, selector).not.toBeNull();
      expect(svg?.style.stroke, selector).toBe("none");
    }
  });

  // 배터리 테두리는 선으로 그리므로 굵기를 명시해 전역 1.7 상속을 막는다.
  it("배터리 테두리는 stroke-width 를 명시한다", () => {
    const { container } = render(<StatusBar />);
    const outline = container.querySelector(".ios-statusbar-battery rect[stroke]");
    expect(outline?.getAttribute("stroke-width")).toBe("1");
  });
});
