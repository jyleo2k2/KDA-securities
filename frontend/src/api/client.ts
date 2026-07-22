import type {
  AccountLinkOptionsResponse,
  BenchmarkSummary,
  ChatCardCatalog,
  CompletedSurveyProfile,
  ConversationContext,
  ChatResponse,
  ChatSessionSummary,
  DemoUserFinancialContext,
  DemoHeroPortfolio,
  EducationalPortfolioInput,
  InvestmentProfileResponse,
  InvestmentProfileSubmission,
  PensionCalculatorEvaluation,
  PensionCalculatorInput,
  PensionCalculatorPortfolioCmaEvaluation,
  PensionCalculatorPortfolioCmaRequest,
  PensionTaxScenarioInput,
  ProfileEvaluation,
  ProfileSurveyInput,
  ScenarioSummary,
  StoredChatMessage,
} from "./types";
import { supabase } from "../auth/supabase";

const API_BASE_URL: string = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number | undefined;
  readonly code: string | null;

  constructor(status: number | undefined, message: string, code: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  RESOURCE_NOT_FOUND: "요청한 정보를 찾을 수 없습니다.",
  DATA_SOURCE_UNAVAILABLE: "데이터를 불러오는 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  SESSION_NOT_FOUND: "요청한 대화 기록을 찾을 수 없습니다.",
  DATABASE_NOT_CONFIGURED: "현재 서비스를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  INVALID_DATE_RANGE: "조회 시작일은 종료일보다 늦을 수 없습니다.",
};

export function apiErrorMessage(
  error: ApiError,
  fallback = "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
): string {
  if (error.code !== null) return ERROR_MESSAGES[error.code] ?? fallback;
  if (error.status === 401) return "로그인이 만료되었습니다. 다시 로그인해 주세요.";
  return fallback;
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
    let code: string | null = null;
    try {
      const body = (await response.json()) as {
        detail?:
          | { code?: unknown; message?: unknown }
          | string
          | Array<{ msg?: string }>;
      };
      if (
        typeof body.detail === "object"
        && body.detail !== null
        && !Array.isArray(body.detail)
      ) {
        if (typeof body.detail.message === "string") detail = body.detail.message;
        if (typeof body.detail.code === "string") code = body.detail.code;
      }
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
    throw new ApiError(response.status, detail, code);
  }
  return (await response.json()) as T;
}

function requestHeaders(accessToken?: string): HeadersInit {
  return accessToken
    ? { Authorization: `Bearer ${accessToken}` }
    : {};
}

async function currentAccessToken(accessToken?: string): Promise<string | undefined> {
  if (!accessToken || !supabase) return accessToken;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? accessToken;
}

async function refreshedAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data, error } = await supabase.auth.refreshSession();
  return error ? null : data.session?.access_token ?? null;
}

export async function apiGet<T>(
  path: string,
  accessToken?: string,
): Promise<T> {
  const token = await currentAccessToken(accessToken);
  let response = await fetch(`${API_BASE_URL}${path}`, {
    headers: requestHeaders(token),
  });
  if (response.status === 401 && accessToken) {
    const refreshedToken = await refreshedAccessToken();
    if (refreshedToken) {
      response = await fetch(`${API_BASE_URL}${path}`, {
        headers: requestHeaders(refreshedToken),
      });
    }
  }
  return parseOrThrow<T>(path, response);
}

export async function apiPost<TBody, TResult>(
  path: string,
  body: TBody,
  accessToken?: string,
  idempotencyKey?: string,
): Promise<TResult> {
  const token = await currentAccessToken(accessToken);
  const request = (requestToken?: string) => fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...requestHeaders(requestToken),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    },
    body: JSON.stringify(body),
  });
  let response = await request(token);
  if (response.status === 401 && accessToken) {
    const refreshedToken = await refreshedAccessToken();
    if (refreshedToken) response = await request(refreshedToken);
  }
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
        } else if (
          event === "error"
          && typeof payload.code === "string"
          && typeof payload.message === "string"
        ) {
          throw new ApiError(undefined, payload.message, payload.code);
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

export function getScenarios(accessToken: string): Promise<ScenarioSummary[]> {
  return apiGet("/chat/scenarios", accessToken);
}

export function getChatCards(): Promise<ChatCardCatalog> {
  return apiGet("/chat/cards");
}

export function getDemoHeroes(accessToken: string): Promise<DemoHeroPortfolio[]> {
  return apiGet("/chat/heroes", accessToken);
}

export function getAccountLinkOptions(): Promise<AccountLinkOptionsResponse> {
  return apiGet("/accounts/link-options");
}

export function evaluateProfileSurvey(
  survey: ProfileSurveyInput,
): Promise<ProfileEvaluation> {
  return apiPost("/engine/profile", survey);
}

export function saveInvestmentProfile(
  submission: InvestmentProfileSubmission,
  accessToken: string,
): Promise<InvestmentProfileResponse> {
  return apiPost("/me/investment-profile", submission, accessToken);
}

export function getInvestmentProfile(
  accessToken: string,
): Promise<InvestmentProfileResponse> {
  return apiGet("/me/investment-profile", accessToken);
}

export function calculatePortfolioCmaPension(
  request: PensionCalculatorPortfolioCmaRequest,
): Promise<PensionCalculatorPortfolioCmaEvaluation> {
  return apiPost("/engine/pension-calculator/portfolio-cma", request);
}

export function calculatePension(
  request: PensionCalculatorInput,
): Promise<PensionCalculatorEvaluation> {
  return apiPost("/engine/pension-calculator", request);
}

interface ChatBodyOptions {
  scenarioCode?: string;
  sessionId?: string;
  conversationContext?: ConversationContext | null;
  pensionTax?: PensionTaxScenarioInput;
  surveyProfile?: CompletedSurveyProfile | null;
  educationalPortfolio?: EducationalPortfolioInput;
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
    ...(options?.educationalPortfolio
      ? { educational_portfolio: options.educationalPortfolio }
      : {}),
  };
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
  educationalPortfolio?: EducationalPortfolioInput,
): Promise<ChatStreamResult> {
  return apiPostStream(
    "/chat/stream",
    buildChatBody(message, {
      scenarioCode,
      sessionId,
      conversationContext,
      pensionTax,
      surveyProfile,
      educationalPortfolio,
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
