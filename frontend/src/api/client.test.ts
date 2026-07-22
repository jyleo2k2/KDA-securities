import { afterEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  refreshSession: vi.fn(),
}));

vi.mock("../auth/supabase", () => ({
  supabase: { auth },
}));

import {
  ApiError,
  apiGet,
  apiPost,
  deleteChatSession,
  getDemoHeroes,
  getMyPensionContext,
  getStoredChatMessages,
  sendAuthenticatedChatStream,
} from "./client";


afterEach(() => {
  vi.unstubAllGlobals();
  auth.getSession.mockReset();
  auth.refreshSession.mockReset();
});

describe("authenticated REST retry", () => {
  it("refreshes once and retries a GET with the refreshed token", async () => {
    auth.getSession.mockResolvedValue({
      data: { session: { access_token: "expired-token" } },
    });
    auth.refreshSession.mockResolvedValue({
      data: { session: { access_token: "fresh-token" } },
      error: null,
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiGet<{ ok: boolean }>("/protected", "expired-token"))
      .resolves.toEqual({ ok: true });

    expect(auth.refreshSession).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenNthCalledWith(1, "http://127.0.0.1:8000/protected", {
      cache: "no-store",
      headers: { Authorization: "Bearer expired-token" },
    });
    expect(fetchMock).toHaveBeenNthCalledWith(2, "http://127.0.0.1:8000/protected", {
      cache: "no-store",
      headers: { Authorization: "Bearer fresh-token" },
    });
  });

  it("refreshes once and retries a POST with the refreshed token", async () => {
    auth.getSession.mockResolvedValue({
      data: { session: { access_token: "expired-token" } },
    });
    auth.refreshSession.mockResolvedValue({
      data: { session: { access_token: "fresh-token" } },
      error: null,
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiPost<{ name: string }, { ok: boolean }>(
      "/protected",
      { name: "pension" },
      "expired-token",
    )).resolves.toEqual({ ok: true });

    expect(auth.refreshSession).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer fresh-token",
      },
    });
  });

  it("does not retry again after refresh fails", async () => {
    auth.getSession.mockResolvedValue({
      data: { session: { access_token: "expired-token" } },
    });
    auth.refreshSession.mockResolvedValue({
      data: { session: null },
      error: new Error("invalid refresh token"),
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { message: "Unauthorized" } }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    ));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiGet("/protected", "expired-token"))
      .rejects.toMatchObject({ status: 401 });

    expect(auth.refreshSession).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledOnce();
  });
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
          'event: response\ndata: {"response":{"answer":"검증 내레이션","salutation":"박준호(가상)님"}}\n\n',
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
    expect(result.response.salutation).toBe("박준호님");
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

describe("demo customer display names", () => {
  it("removes the demo marker from hero and pension-context names", async () => {
    auth.getSession.mockResolvedValue({ data: { session: { access_token: "access-token" } } });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([{ nickname: "박준호(가상)", scenario_code: "dc_dormant" }])))
      .mockResolvedValueOnce(new Response(JSON.stringify({ nickname: "이서연(가상)", scenario_code: "tax_contribution_uninvested" })));
    vi.stubGlobal("fetch", fetchMock);

    const heroes = await getDemoHeroes("access-token");
    const context = await getMyPensionContext("access-token");

    expect(heroes[0]?.nickname).toBe("박준호");
    expect(context.nickname).toBe("이서연");
  });

  it("removes the demo marker from stored chat salutations", async () => {
    auth.getSession.mockResolvedValue({ data: { session: { access_token: "access-token" } } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{
      id: "message-1",
      role: "assistant",
      content: "안녕하세요.",
      response: { answer: "안녕하세요.", salutation: "정민재(가상)님" },
    }]))));

    const messages = await getStoredChatMessages("session-1", "access-token");

    expect(messages[0]?.response?.salutation).toBe("정민재님");
  });
});


describe("chat session deletion", () => {
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
        cache: "no-store",
        headers: { Authorization: "Bearer access-token" },
      },
    );
  });
});
