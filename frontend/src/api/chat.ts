import { apiGet, apiPost } from "./client";
import type {
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ChatSession,
  DemoChatResponse,
} from "./types";

export function sendDemoChat(
  request: Omit<ChatRequest, "session_id">,
  signal?: AbortSignal,
): Promise<DemoChatResponse> {
  return apiPost("/chat/demo", request, { signal });
}

export function sendAuthenticatedChat(
  request: ChatRequest,
  accessToken: string,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  return apiPost("/chat", request, { accessToken, signal });
}

export function listChatSessions(
  accessToken: string,
  signal?: AbortSignal,
): Promise<ChatSession[]> {
  return apiGet("/chat/sessions", { accessToken, signal });
}

export function getChatMessages(
  sessionId: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<ChatMessage[]> {
  return apiGet(`/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
    accessToken,
    signal,
  });
}
