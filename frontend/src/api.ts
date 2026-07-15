import type { ChatCapabilities, ChatResponse, ScenarioSummary } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let detail = "요청을 처리하지 못했습니다.";
    try {
      const body = (await response.json()) as { detail?: string | Array<{ msg?: string }> };
      if (typeof body.detail === "string") detail = body.detail;
      if (Array.isArray(body.detail)) detail = body.detail.map((item) => item.msg).filter(Boolean).join(" ");
    } catch {
      // Keep the safe default when the server does not return JSON.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function getCapabilities(): Promise<ChatCapabilities> {
  return request("/chat/demo/capabilities");
}

export function getScenarios(): Promise<ScenarioSummary[]> {
  return request("/chat/demo/scenarios");
}

export function sendChat(message: string, scenarioCode?: string): Promise<ChatResponse> {
  return request("/chat/demo", {
    method: "POST",
    body: JSON.stringify({
      message,
      ...(scenarioCode ? { scenario_code: scenarioCode } : {}),
    }),
  });
}
