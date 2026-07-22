// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TabBar } from "./TabBar";

describe("TabBar", () => {
  it("renders only home, guide, and profile tabs", () => {
    render(<TabBar activeTab="home" onChange={vi.fn()} />);

    expect(screen.getAllByRole("button")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "홈" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "연금가이드" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "프로필" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "벤치마크" })).not.toBeInTheDocument();
  });
});
