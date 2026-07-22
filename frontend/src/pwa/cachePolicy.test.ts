import { describe, expect, it } from "vitest";

import {
  API_REQUEST_CACHE_MODE,
  CACHE_POLICY,
  noStoreApiRequest,
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
});
