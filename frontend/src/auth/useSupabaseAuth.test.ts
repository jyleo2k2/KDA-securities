import { describe, expect, it } from "vitest";

import { normalizeLoginId } from "./useSupabaseAuth";

describe("normalizeLoginId", () => {
  it("adds the demo domain to a short presentation ID", () => {
    expect(normalizeLoginId("seoyeon34")).toBe(
      "seoyeon34@kda-demo.invalid",
    );
  });

  it("keeps a full email address unchanged", () => {
    expect(normalizeLoginId("member@example.com")).toBe("member@example.com");
  });
});
