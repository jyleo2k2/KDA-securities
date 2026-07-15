const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface ApiRequestOptions {
  accessToken?: string;
  signal?: AbortSignal;
}

interface ErrorPayload {
  detail?: unknown;
}

function requestHeaders(options: ApiRequestOptions): HeadersInit {
  const headers: Record<string, string> = {};
  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }
  return headers;
}

async function parseOrThrow<T>(path: string, response: Response): Promise<T> {
  if (!response.ok) {
    let message = `${path} 요청 실패 (${response.status})`;
    try {
      const payload = (await response.json()) as ErrorPayload;
      if (typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // JSON 오류 본문이 없으면 상태 코드 기반 메시지를 유지한다.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export async function apiGet<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: requestHeaders(options),
    signal: options.signal,
  });
  return parseOrThrow<T>(path, response);
}

export async function apiPost<TBody, TResult>(
  path: string,
  body: TBody,
  options: ApiRequestOptions = {},
): Promise<TResult> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      ...requestHeaders(options),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: options.signal,
  });
  return parseOrThrow<TResult>(path, response);
}
