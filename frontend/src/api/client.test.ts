import { afterEach, describe, expect, it, vi } from "vitest";

import { deleteChatSession, sendChatStream } from "./client";


afterEach(() => {
  vi.unstubAllGlobals();
});


describe("chat SSE parser", () => {
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

    const result = await sendChatStream(
      "IRP 한도를 알려줘",
      () => undefined,
      (delta) => deltas.push(delta),
      (answer) => replacements.push(answer),
    );

    expect(deltas).toEqual(["엔진 답변"]);
    expect(replacements).toEqual(["검증 내레이션"]);
    expect(result.response.answer).toBe("검증 내레이션");
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
        headers: { Authorization: "Bearer access-token" },
      },
    );
  });
});
