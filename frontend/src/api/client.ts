import type {
  ChatCapabilities,
  ChatResponse,
  ChatSessionSummary,
  PersistedChatResponse,
  PensionTaxScenarioInput,
  ScenarioEvaluation,
  ScenarioSummary,
  StoredChatMessage,
} from "./types";

const API_BASE_URL: string = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseOrThrow<T>(path: string, response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${path} 요청 실패 (${response.status})`;
    try {
      const body = (await response.json()) as {
        detail?: string | Array<{ msg?: string }>;
      };
      if (typeof body.detail === "string") detail = body.detail;
      if (Array.isArray(body.detail)) {
        detail = body.detail
          .map((item) => item.msg)
          .filter(Boolean)
          .join(" ");
      }
    } catch {
      // Keep the safe default when the server does not return JSON.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

function requestHeaders(accessToken?: string): HeadersInit {
  return accessToken
    ? { Authorization: `Bearer ${accessToken}` }
    : {};
}

export async function apiGet<T>(
  path: string,
  accessToken?: string,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: requestHeaders(accessToken),
  });
  return parseOrThrow<T>(path, response);
}

export async function apiPost<TBody, TResult>(
  path: string,
  body: TBody,
  accessToken?: string,
): Promise<TResult> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...requestHeaders(accessToken),
    },
    body: JSON.stringify(body),
  });
  return parseOrThrow<TResult>(path, response);
}

export function getCapabilities(): Promise<ChatCapabilities> {
  return apiGet("/chat/demo/capabilities");
}

export function getScenarios(): Promise<ScenarioSummary[]> {
  return apiGet("/chat/demo/scenarios");
}

export function getMockScenarioEvaluation(
  scenarioCode: string,
): Promise<ScenarioEvaluation> {
  return apiGet(`/engine/mock-scenario/${scenarioCode}`);
}

export function sendChat(
  message: string,
  scenarioCode?: string,
  pensionTax?: PensionTaxScenarioInput,
): Promise<ChatResponse> {
  return apiPost("/chat/demo", {
    message,
    ...(scenarioCode ? { scenario_code: scenarioCode } : {}),
    ...(pensionTax ? { pension_tax: pensionTax } : {}),
  });
}

export function sendAuthenticatedChat(
  message: string,
  accessToken: string,
  scenarioCode?: string,
  sessionId?: string,
  pensionTax?: PensionTaxScenarioInput,
): Promise<PersistedChatResponse> {
  return apiPost(
    "/chat",
    {
      message,
      ...(scenarioCode ? { scenario_code: scenarioCode } : {}),
      ...(sessionId ? { session_id: sessionId } : {}),
      ...(pensionTax ? { pension_tax: pensionTax } : {}),
    },
    accessToken,
  );
}

export function getChatSessions(
  accessToken: string,
): Promise<ChatSessionSummary[]> {
  return apiGet("/chat/sessions", accessToken);
}

export function getStoredChatMessages(
  sessionId: string,
  accessToken: string,
): Promise<StoredChatMessage[]> {
  return apiGet(
    `/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
    accessToken,
  );
}
