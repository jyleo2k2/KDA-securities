import { describe, expect, it } from "vitest";

import {
  CHAT_PROMPT_CANDIDATES,
  pickChatPromptCandidate,
} from "./chatPromptCandidates";

describe("chat prompt candidates", () => {
  it("keeps ten distinct beginner-friendly questions", () => {
    expect(CHAT_PROMPT_CANDIDATES).toHaveLength(10);
    expect(new Set(CHAT_PROMPT_CANDIDATES)).toHaveLength(10);
  });

  it("selects candidates across the Math.random range", () => {
    expect(pickChatPromptCandidate(() => 0)).toBe(CHAT_PROMPT_CANDIDATES[0]);
    expect(pickChatPromptCandidate(() => 0.999999)).toBe(
      CHAT_PROMPT_CANDIDATES[CHAT_PROMPT_CANDIDATES.length - 1],
    );
  });
});
