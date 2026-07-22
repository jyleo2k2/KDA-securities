import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  apiErrorMessage,
  deleteChatSession,
  deleteAllChatSessions,
  getBenchmarkSummary,
  sendAuthenticatedChatStream,
} from "./client";


afterEach(() => {
  vi.unstubAllGlobals();
});


describe("chat SSE parser", () => {
  it("preserves a structured error event as an ApiError", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          'event: error\ndata: {"code":"DATA_SOURCE_UNAVAILABLE","message":"Chat data source is unavailable"}\n\n',
        ));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));

    await expect(sendAuthenticatedChatStream(
      "IRP 한도를 알려줘",
      "access-token",
      () => undefined,
      () => undefined,
      () => undefined,
    )).rejects.toMatchObject({
      code: "DATA_SOURCE_UNAVAILABLE",
      message: "Chat data source is unavailable",
    } satisfies Partial<ApiError>);
  });

  it("delivers a verified narration as a full answer replacement", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          'event: answer_delta\ndata: {"delta":"엔진 답변"}\n\n' +
          'event: narration_update\ndata: {"answer":"검증 내레이션"}\n\n' +
          'event: response\ndata: {"response":{"answer":"검증 내레이션"}}\n\n',
        ));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    const deltas: string[] = [];
    const replacements: string[] = [];

    const result = await sendAuthenticatedChatStream(
      "IRP 한도를 알려줘",
      "access-token",
      () => undefined,
      (delta) => deltas.push(delta),
      (answer) => replacements.push(answer),
    );

    expect(deltas).toEqual(["엔진 답변"]);
    expect(replacements).toEqual(["검증 내레이션"]);
    expect(result.response.answer).toBe("검증 내레이션");
  });

  it("sends current holdings as structured educational portfolio input", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          'event: response\ndata: {"response":{"answer":"분석 완료"}}\n\n',
        ));
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(body));
    vi.stubGlobal("fetch", fetchMock);

    await sendAuthenticatedChatStream(
      "현재 보유 ETF를 점검해줘",
      "access-token",
      () => undefined,
      () => undefined,
      () => undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      {
        account_type: "irp",
        age: 35,
        retirement_start_age: 60,
        risk_profile: "risk_neutral",
        loss_tolerance_percent: "20",
        max_etfs: 7,
        current_holdings: [{ isu_code: "069500", amount_krw: "10000000" }],
        new_contribution_krw: "1000000",
      },
    );

    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8000/chat/stream");
    expect(request.headers).toMatchObject({ Authorization: "Bearer access-token" });
    expect(JSON.parse(request.body as string)).toMatchObject({
      educational_portfolio: {
        account_type: "irp",
        current_holdings: [{ isu_code: "069500", amount_krw: "10000000" }],
        new_contribution_krw: "1000000",
      },
    });
  });
});

describe("API error parser", () => {
  it("preserves the REST error code and maps it to a Korean message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({
        detail: {
          code: "RESOURCE_NOT_FOUND",
          message: "Requested resource was not found",
        },
      }),
      { status: 404, headers: { "Content-Type": "application/json" } },
    )));

    try {
      await getBenchmarkSummary();
      throw new Error("Expected getBenchmarkSummary to reject");
    } catch (error) {
      expect(error).toMatchObject({
        code: "RESOURCE_NOT_FOUND",
        message: "Requested resource was not found",
        status: 404,
      } satisfies Partial<ApiError>);
      expect(apiErrorMessage(error as ApiError)).toBe("요청한 정보를 찾을 수 없습니다.");
    }
  });
});

describe("chat session deletion", () => {
  it("sends an authenticated DELETE request for every owned session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await deleteAllChatSessions("access-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/chat/sessions",
      {
        method: "DELETE",
        headers: { Authorization: "Bearer access-token" },
      },
    );
  });

  it("sends an authenticated DELETE request with an encoded session id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await deleteChatSession("session/id", "access-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/chat/sessions/session%2Fid",
      {
        method: "DELETE",
        headers: { Authorization: "Bearer access-token" },
      },
    );
  });
});
