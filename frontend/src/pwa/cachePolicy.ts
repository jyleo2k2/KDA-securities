/**
 * Browser Cache Storage is reserved for revisioned app assets. FastAPI data is
 * always fetched fresh because it can be authenticated, user-specific, or SSE.
 */
export const API_REQUEST_CACHE_MODE: RequestCache = "no-store";

export const PERSISTED_USER_STORAGE_KEYS = [
  "pension-copilot:survey-profile",
  "pension-copilot:mvp-profile-version",
  "pension-copilot:selected-scenario",
] as const;

export const CACHE_POLICY = {
  staticAssets: "precache revisioned build assets only",
  api: "never cache in the browser or service worker",
  stream: "never cache; process only the active response body",
} as const;

export function noStoreApiRequest(): Pick<RequestInit, "cache"> {
  return { cache: API_REQUEST_CACHE_MODE };
}

export function selectedScenarioFromStorage(): string {
  return window.localStorage.getItem("pension-copilot:selected-scenario") ?? "";
}

export function persistSelectedScenario(scenarioCode: string): void {
  window.localStorage.setItem("pension-copilot:selected-scenario", scenarioCode);
}

export function clearPersistedUserState(): void {
  PERSISTED_USER_STORAGE_KEYS.forEach((key) => window.localStorage.removeItem(key));
}
