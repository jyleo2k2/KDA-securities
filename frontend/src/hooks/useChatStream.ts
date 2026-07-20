import { useRef, useState, type Dispatch, type SetStateAction } from "react";

import {
  ApiError,
  sendAuthenticatedChatStream,
  sendChatStream,
  type ChatStreamResult,
} from "../api/client";
import type {
  ChatResponse,
  CompletedSurveyProfile,
  ConversationContext,
  EducationalPortfolioInput,
  PensionTaxScenarioInput,
} from "../api/types";

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
  failedPrompt?: string;
  failedEducationalPortfolio?: EducationalPortfolioInput;
  createdAt: Date;
}

const PENSION_TAX_PROMPT = /세액\s*공제|중도\s*해지|연금\s*외\s*수령|16\.5\s*%/;

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "로그인이 만료되었습니다. 다시 로그인해 주세요.";
  }
  if (error instanceof ApiError && error.status === 503) {
    return "대화 저장소에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  }
  return error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
}

interface UseChatStreamOptions {
  accessToken?: string;
  authenticatedUserId: string | null;
  activeSessionId: string | null;
  conversationContext: ConversationContext | null;
  selectedScenario: string;
  pensionTaxInput?: PensionTaxScenarioInput;
  surveyProfile: CompletedSurveyProfile | null;
  blocked: boolean;
  onResponse: (response: ChatResponse, result: ChatStreamResult | null) => void;
  onAuthenticatedError: (message: string) => void;
  onServerReady: (ready: boolean) => void;
  onStart: () => void;
  onSettled: () => void;
}

export function useChatStream({
  accessToken,
  authenticatedUserId,
  activeSessionId,
  conversationContext,
  selectedScenario,
  pensionTaxInput,
  surveyProfile,
  blocked,
  onResponse,
  onAuthenticatedError,
  onServerReady,
  onStart,
  onSettled,
}: UseChatStreamOptions) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [sendingStage, setSendingStage] = useState("답변을 준비하고 있습니다.");
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamingAnswerIsNarration, setStreamingAnswerIsNarration] = useState(false);
  const sendingRef = useRef(false);
  const requestGenerationRef = useRef(0);
  const currentAuthRef = useRef({
    userId: authenticatedUserId,
    token: accessToken ?? null,
  });

  currentAuthRef.current = {
    userId: authenticatedUserId,
    token: accessToken ?? null,
  };

  const cancelStream = () => {
    requestGenerationRef.current += 1;
    sendingRef.current = false;
    setIsSending(false);
    setStreamingAnswer("");
    setStreamingAnswerIsNarration(false);
  };

  const submitPrompt = async (
    prompt: string,
    educationalPortfolio?: EducationalPortfolioInput,
  ) => {
    const normalized = prompt.trim();
    if (normalized.length < 2 || sendingRef.current || blocked) return;

    const requestToken = accessToken ?? null;
    const requestUserId = authenticatedUserId;
    const requestGeneration = ++requestGenerationRef.current;
    const isCurrentRequest = () => (
      requestGenerationRef.current === requestGeneration
      && currentAuthRef.current.userId === requestUserId
      && currentAuthRef.current.token === requestToken
    );

    sendingRef.current = true;
    onStart();
    const userMessage: ConversationMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text: normalized,
      createdAt: new Date(),
    };
    const idempotencyKey = crypto.randomUUID();
    setMessages((current) => [...current, userMessage]);
    setIsSending(true);
    setSendingStage("질문을 확인하고 있습니다.");
    setStreamingAnswer("");
    setStreamingAnswerIsNarration(false);

    const appendAnswerDelta = (delta: string) => {
      if (isCurrentRequest()) setStreamingAnswer((current) => current + delta);
    };
    const replaceWithNarration = (answer: string) => {
      if (!isCurrentRequest()) return;
      setStreamingAnswerIsNarration(true);
      setStreamingAnswer(answer);
    };
    const taxInput = !requestToken && PENSION_TAX_PROMPT.test(normalized)
      ? pensionTaxInput
      : undefined;

    try {
      const streamed = requestToken
        ? await sendAuthenticatedChatStream(
            normalized,
            requestToken,
            setSendingStage,
            appendAnswerDelta,
            replaceWithNarration,
            undefined,
            activeSessionId || undefined,
            idempotencyKey,
            conversationContext,
            taxInput,
            surveyProfile,
            educationalPortfolio,
          )
        : await sendChatStream(
            normalized,
            setSendingStage,
            appendAnswerDelta,
            replaceWithNarration,
            {
              scenarioCode: selectedScenario || undefined,
              conversationContext,
              pensionTax: taxInput,
              surveyProfile,
              educationalPortfolio,
            },
          );
      if (!isCurrentRequest()) return;
      const response = streamed.response;
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: response.answer,
        response,
        createdAt: new Date(),
      }]);
      onResponse(response, streamed.persisted ? streamed : null);
      onServerReady(true);
    } catch (error) {
      if (!isCurrentRequest()) return;
      const message = requestToken
        ? errorMessage(error)
        : error instanceof Error
          ? error.message
          : "서버 연결을 확인해 주세요.";
      if (requestToken) onAuthenticatedError(message);
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: message,
        failedPrompt: normalized,
        failedEducationalPortfolio: educationalPortfolio,
        createdAt: new Date(),
      }]);
      onServerReady(error instanceof ApiError && error.status !== 503);
    } finally {
      if (!isCurrentRequest()) return;
      sendingRef.current = false;
      setIsSending(false);
      setStreamingAnswer("");
      setStreamingAnswerIsNarration(false);
      onSettled();
    }
  };

  return {
    messages,
    setMessages: setMessages as Dispatch<SetStateAction<ConversationMessage[]>>,
    isSending,
    sendingStage,
    streamingAnswer,
    streamingAnswerIsNarration,
    cancelStream,
    submitPrompt,
  };
}
