import type {
  ChatCapabilities,
  CompletedSurveyProfile,
  ConversationContext,
  ChatResponse,
  ChatSessionSummary,
  PersistedChatResponse,
  PensionTaxScenarioInput,
  ProfileEvaluation,
  ProfileSurveyInput,
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

export interface ChatStreamResult {
  response: ChatResponse;
  persisted?: boolean;
  session_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  idempotency_replayed?: boolean;
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
  idempotencyKey?: string,
): Promise<TResult> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...requestHeaders(accessToken),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    body: JSON.stringify(body),
  });
  return parseOrThrow<TResult>(path, response);
}

async function apiPostStream<TBody>(
  path: string,
  body: TBody,
  onPhase: (message: string) => void,
  accessToken?: string,
  idempotencyKey?: string,
): Promise<ChatStreamResult> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...requestHeaders(accessToken),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) return parseOrThrow(path, response);
  if (!response.body) throw new Error("스트리밍 응답을 받을 수 없습니다.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatStreamResult | null = null;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = block.match(/^event: (.+)$/m)?.[1];
      const data = block.match(/^data: (.+)$/m)?.[1];
      if (event && data) {
        const payload = JSON.parse(data) as Record<string, unknown>;
        if (event === "phase" && typeof payload.message === "string") {
          onPhase(payload.message);
        } else if (event === "error" && typeof payload.detail === "string") {
          throw new Error(payload.detail);
        } else if (event === "response") {
          result = payload as unknown as ChatStreamResult;
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (result === null) throw new Error("최종 챗봇 응답을 받지 못했습니다.");
  return result;
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

export function evaluateProfileSurvey(
  survey: ProfileSurveyInput,
): Promise<ProfileEvaluation> {
  return apiPost("/engine/profile", survey);
}

export function sendChat(
  message: string,
  options?: string | {
    scenarioCode?: string;
    conversationContext?: ConversationContext | null;
    pensionTax?: PensionTaxScenarioInput;
    surveyProfile?: CompletedSurveyProfile | null;
  },
): Promise<ChatResponse> {
  const requestOptions = typeof options === "string"
    ? { scenarioCode: options }
    : options;
  return apiPost("/chat/demo", {
    message,
    ...(requestOptions?.scenarioCode
      ? { scenario_code: requestOptions.scenarioCode }
      : {}),
    ...(requestOptions?.conversationContext
      ? { conversation_context: requestOptions.conversationContext }
      : {}),
    ...(requestOptions?.pensionTax
      ? { pension_tax: requestOptions.pensionTax }
      : {}),
    ...(requestOptions?.surveyProfile
      ? { survey_profile: requestOptions.surveyProfile }
      : {}),
  });
}

export function sendChatStream(
  message: string,
  onPhase: (message: string) => void,
  options?: string | {
    scenarioCode?: string;
    conversationContext?: ConversationContext | null;
    pensionTax?: PensionTaxScenarioInput;
  },
): Promise<ChatStreamResult> {
  const requestOptions = typeof options === "string"
    ? { scenarioCode: options }
    : options;
  return apiPostStream(
    "/chat/demo/stream",
    {
      message,
      ...(requestOptions?.scenarioCode
        ? { scenario_code: requestOptions.scenarioCode }
        : {}),
      ...(requestOptions?.conversationContext
        ? { conversation_context: requestOptions.conversationContext }
        : {}),
      ...(requestOptions?.pensionTax
        ? { pension_tax: requestOptions.pensionTax }
        : {}),
    },
    onPhase,
  );
}

export function sendAuthenticatedChat(
  message: string,
  accessToken: string,
  scenarioCode?: string,
  sessionId?: string,
  idempotencyKey?: string,
  conversationContext?: ConversationContext | null,
  pensionTax?: PensionTaxScenarioInput,
  surveyProfile?: CompletedSurveyProfile | null,
): Promise<PersistedChatResponse> {
  return apiPost(
    "/chat",
    {
      message,
      ...(scenarioCode ? { scenario_code: scenarioCode } : {}),
      ...(sessionId ? { session_id: sessionId } : {}),
      ...(conversationContext
        ? { conversation_context: conversationContext }
        : {}),
      ...(pensionTax ? { pension_tax: pensionTax } : {}),
      ...(surveyProfile ? { survey_profile: surveyProfile } : {}),
    },
    accessToken,
    idempotencyKey,
  );
}

export function sendAuthenticatedChatStream(
  message: string,
  accessToken: string,
  onPhase: (message: string) => void,
  scenarioCode?: string,
  sessionId?: string,
  idempotencyKey?: string,
  conversationContext?: ConversationContext | null,
  pensionTax?: PensionTaxScenarioInput,
): Promise<ChatStreamResult> {
  return apiPostStream(
    "/chat/stream",
    {
      message,
      ...(scenarioCode ? { scenario_code: scenarioCode } : {}),
      ...(sessionId ? { session_id: sessionId } : {}),
      ...(conversationContext
        ? { conversation_context: conversationContext }
        : {}),
      ...(pensionTax ? { pension_tax: pensionTax } : {}),
    },
    onPhase,
    accessToken,
    idempotencyKey,
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
