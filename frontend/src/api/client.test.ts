import { afterEach, describe, expect, it, vi } from "vitest";

import { sendChatStream } from "./client";


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
