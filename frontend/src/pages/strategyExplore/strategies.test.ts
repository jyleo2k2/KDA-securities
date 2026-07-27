import { describe, expect, it } from "vitest";

import { STRATEGIES } from "./strategies";

describe("strategy catalog", () => {
  it("labels the pig strategy as barbell instead of target", () => {
    const barbell = STRATEGIES.find((strategy) => strategy.id === "barbell");

    expect(barbell).toMatchObject({
      name: "바벨 전략",
      directness: "ETF로 구현 가능",
      bucket: "코어·안정화 조합",
    });
    expect(barbell?.desc).toContain("성장자산과 현금·단기채");
    expect(STRATEGIES.some((strategy) => strategy.id === "target")).toBe(false);
    expect(STRATEGIES.some((strategy) => strategy.name === "타깃 전략")).toBe(false);
  });
});
