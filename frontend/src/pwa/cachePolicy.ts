/**
 * Browser Cache Storage is reserved for revisioned app assets. FastAPI data is
 * always fetched fresh because it can be authenticated, user-specific, or SSE.
 */
export const API_REQUEST_CACHE_MODE: RequestCache = "no-store";

export const CACHE_POLICY = {
  staticAssets: "precache revisioned build assets only",
  api: "never cache in the browser or service worker",
  stream: "never cache; process only the active response body",
} as const;

export function noStoreApiRequest(): Pick<RequestInit, "cache"> {
  return { cache: API_REQUEST_CACHE_MODE };
}
