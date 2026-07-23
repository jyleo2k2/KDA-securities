// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("./supabase", () => ({
  isSupabaseConfigured: true,
  supabase: { auth },
}));

import { useSupabaseAuth } from "./useSupabaseAuth";

describe("useSupabaseAuth initial session", () => {
  afterEach(() => {
    auth.getSession.mockReset();
    auth.onAuthStateChange.mockReset();
    auth.signOut.mockReset();
  });

  it("uses the getSession result instead of a stale INITIAL_SESSION event", async () => {
    auth.getSession.mockResolvedValue({ data: { session: null }, error: null });
    auth.onAuthStateChange.mockImplementation((listener) => {
      listener("INITIAL_SESSION", {
        access_token: "expired-token",
        expires_at: Math.floor(Date.now() / 1000) - 1,
      });
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });

    const { result } = renderHook(() => useSupabaseAuth());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.session).toBeNull();
  });

  it("clears the current browser session after a local sign out", async () => {
    auth.getSession.mockResolvedValue({
      data: { session: { access_token: "active-token", user: { id: "user-1" } } },
      error: null,
    });
    auth.onAuthStateChange.mockReturnValue({
      data: { subscription: { unsubscribe: vi.fn() } },
    });
    auth.signOut.mockResolvedValue({ error: null });

    const { result } = renderHook(() => useSupabaseAuth());
    await waitFor(() => expect(result.current.session).not.toBeNull());

    await act(async () => {
      await result.current.signOut();
    });

    expect(auth.signOut).toHaveBeenCalledWith({ scope: "local" });
    expect(result.current.session).toBeNull();
  });
});
