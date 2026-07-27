// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getBenchmarkFollows } from "../api/client";
import { ProfileFollowingScreen } from "./ProfileFollowingScreen";

vi.mock("../api/client", () => ({
  getBenchmarkFollows: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProfileFollowingScreen", () => {
  it("shows only the portfolios followed by the authenticated owner", async () => {
    vi.mocked(getBenchmarkFollows).mockResolvedValue([
      { portfolio_id: "꾸준한거북이", is_following: true, follow_count: 1205 },
      { portfolio_id: "배당모으미", is_following: false, follow_count: 876 },
    ]);

    render(<ProfileFollowingScreen accessToken="owner-a-token" onBack={vi.fn()} />);

    expect(await screen.findByText("꾸준한거북이")).toBeInTheDocument();
    expect(screen.queryByText("배당모으미")).not.toBeInTheDocument();
    expect(screen.getByText("운용 기간")).toBeInTheDocument();
    expect(screen.getByText("3년 8개월")).toBeInTheDocument();
    expect(screen.queryByText("포트폴리오 구성 비율")).not.toBeInTheDocument();
    expect(screen.queryByText("투자전략")).not.toBeInTheDocument();
    expect(screen.getByLabelText("팔로우 1,205")).toBeInTheDocument();
    expect(getBenchmarkFollows).toHaveBeenCalledWith("owner-a-token");
  });

  it("clears the previous owner and reloads when the account token changes", async () => {
    vi.mocked(getBenchmarkFollows)
      .mockResolvedValueOnce([
        { portfolio_id: "꾸준한거북이", is_following: true, follow_count: 1205 },
      ])
      .mockResolvedValueOnce([
        { portfolio_id: "배당모으미", is_following: true, follow_count: 877 },
      ]);

    const { rerender } = render(
      <ProfileFollowingScreen accessToken="owner-a-token" onBack={vi.fn()} />,
    );
    expect(await screen.findByText("꾸준한거북이")).toBeInTheDocument();

    rerender(<ProfileFollowingScreen accessToken="owner-b-token" onBack={vi.fn()} />);

    await waitFor(() => {
      expect(screen.queryByText("꾸준한거북이")).not.toBeInTheDocument();
      expect(screen.getByText("배당모으미")).toBeInTheDocument();
    });
    expect(getBenchmarkFollows).toHaveBeenLastCalledWith("owner-b-token");
  });
});
