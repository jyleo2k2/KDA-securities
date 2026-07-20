import type {
  BenchmarkSummary,
  ChatCardCatalog,
  CompletedSurveyProfile,
  ConversationContext,
  ChatResponse,
  ChatSessionSummary,
  DemoUserFinancialContext,
  DemoHeroPortfolio,
  PensionTaxScenarioInput,
  ProfileEvaluation,
  ProfileSurveyInput,
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

export async function apiDelete(
  path: string,
  accessToken: string,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "DELETE",
    headers: requestHeaders(accessToken),
  });
  if (!response.ok) await parseOrThrow<never>(path, response);
}

async function apiPostStream<TBody>(
  path: string,
  body: TBody,
  onPhase: (message: string) => void,
  onAnswerDelta: (delta: string) => void,
  onNarrationUpdate: (answer: string) => void,
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
        } else if (
          event === "answer_delta" && typeof payload.delta === "string"
        ) {
          onAnswerDelta(payload.delta);
        } else if (
          event === "narration_update" && typeof payload.answer === "string"
        ) {
          onNarrationUpdate(payload.answer);
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

export function getBenchmarkSummary(): Promise<BenchmarkSummary> {
  return apiGet("/benchmark/summary");
}

export function getScenarios(): Promise<ScenarioSummary[]> {
  return apiGet("/chat/demo/scenarios");
}

export function getChatCards(): Promise<ChatCardCatalog> {
  return apiGet("/chat/cards");
}

export function getDemoHeroes(): Promise<DemoHeroPortfolio[]> {
  return apiGet("/chat/demo/heroes");
}

export function evaluateProfileSurvey(
  survey: ProfileSurveyInput,
): Promise<ProfileEvaluation> {
  return apiPost("/engine/profile", survey);
}

interface ChatBodyOptions {
  scenarioCode?: string;
  sessionId?: string;
  conversationContext?: ConversationContext | null;
  pensionTax?: PensionTaxScenarioInput;
  surveyProfile?: CompletedSurveyProfile | null;
}

function buildChatBody(message: string, options?: ChatBodyOptions) {
  return {
    message,
    ...(options?.scenarioCode ? { scenario_code: options.scenarioCode } : {}),
    ...(options?.sessionId ? { session_id: options.sessionId } : {}),
    ...(options?.conversationContext
      ? { conversation_context: options.conversationContext }
      : {}),
    ...(options?.pensionTax ? { pension_tax: options.pensionTax } : {}),
    ...(options?.surveyProfile
      ? { survey_profile: options.surveyProfile }
      : {}),
  };
}

export function sendChatStream(
  message: string,
  onPhase: (message: string) => void,
  onAnswerDelta: (delta: string) => void,
  onNarrationUpdate: (answer: string) => void,
  options?: ChatBodyOptions,
): Promise<ChatStreamResult> {
  return apiPostStream(
    "/chat/demo/stream",
    buildChatBody(message, options),
    onPhase,
    onAnswerDelta,
    onNarrationUpdate,
  );
}

export function sendAuthenticatedChatStream(
  message: string,
  accessToken: string,
  onPhase: (message: string) => void,
  onAnswerDelta: (delta: string) => void,
  onNarrationUpdate: (answer: string) => void,
  scenarioCode?: string,
  sessionId?: string,
  idempotencyKey?: string,
  conversationContext?: ConversationContext | null,
  pensionTax?: PensionTaxScenarioInput,
  surveyProfile?: CompletedSurveyProfile | null,
): Promise<ChatStreamResult> {
  return apiPostStream(
    "/chat/stream",
    buildChatBody(message, {
      scenarioCode,
      sessionId,
      conversationContext,
      pensionTax,
      surveyProfile,
    }),
    onPhase,
    onAnswerDelta,
    onNarrationUpdate,
    accessToken,
    idempotencyKey,
  );
}

export function getChatSessions(
  accessToken: string,
): Promise<ChatSessionSummary[]> {
  return apiGet("/chat/sessions", accessToken);
}

export function getMyPensionContext(
  accessToken: string,
): Promise<DemoUserFinancialContext> {
  return apiGet("/me/pension-context", accessToken);
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

export function deleteChatSession(
  sessionId: string,
  accessToken: string,
): Promise<void> {
  return apiDelete(
    `/chat/sessions/${encodeURIComponent(sessionId)}`,
    accessToken,
  );
}
