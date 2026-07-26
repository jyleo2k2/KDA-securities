import { afterEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  refreshSession: vi.fn(),
}));

vi.mock("../auth/supabase", () => ({
  supabase: { auth },
}));

import { getRebalancingProfile } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  auth.getSession.mockReset();
  auth.refreshSession.mockReset();
});

describe("rebalancing profile API", () => {
  it("requests the server-restored profile with the current access token", async () => {
    auth.getSession.mockResolvedValue({
      data: { session: { access_token: "access-token" } },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      account_type: "irp",
      account_types: ["irp"],
      current_age: 35,
      retirement_start_age: 60,
      risk_profile: "active",
      loss_tolerance_percent: "30",
    })));
    vi.stubGlobal("fetch", fetchMock);

    await expect(getRebalancingProfile("access-token")).resolves.toMatchObject({
      account_type: "irp",
      loss_tolerance_percent: "30",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/chat/rebalancing-profile",
      {
        cache: "no-store",
        headers: { Authorization: "Bearer access-token" },
      },
    );
  });
});
