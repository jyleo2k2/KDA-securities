// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import {
  API_REQUEST_CACHE_MODE,
  CACHE_POLICY,
  PERSISTED_USER_STORAGE_KEYS,
  clearPersistedUserState,
  noStoreApiRequest,
  persistSelectedScenario,
  selectedScenarioFromStorage,
} from "./cachePolicy";

describe("PWA cache policy", () => {
  it("precaches only revisioned static assets", () => {
    expect(CACHE_POLICY.staticAssets).toBe("precache revisioned build assets only");
  });

  it("opts every API and stream request out of browser caching", () => {
    expect(API_REQUEST_CACHE_MODE).toBe("no-store");
    expect(noStoreApiRequest()).toEqual({ cache: "no-store" });
    expect(CACHE_POLICY.api).toBe("never cache in the browser or service worker");
    expect(CACHE_POLICY.stream).toBe("never cache; process only the active response body");
  });

  it("keeps the selected scenario only for the active user session", () => {
    window.localStorage.clear();
    persistSelectedScenario("scenario-a");

    expect(selectedScenarioFromStorage()).toBe("scenario-a");

    PERSISTED_USER_STORAGE_KEYS
      .filter((key) => key !== "pension-copilot:selected-scenario")
      .forEach((key) => window.localStorage.setItem(key, "value"));
    clearPersistedUserState();

    expect(selectedScenarioFromStorage()).toBe("");
    expect(PERSISTED_USER_STORAGE_KEYS.every((key) => window.localStorage.getItem(key) === null)).toBe(true);
  });
});
