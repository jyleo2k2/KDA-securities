import { useRef, useState, type Dispatch, type SetStateAction } from "react";

import {
  ApiError,
  sendAuthenticatedChatStream,
  sendChatStream,
} from "../api/client";
import type {
  ChatResponse,
  CompletedSurveyProfile,
  ConversationContext,
  EducationalPortfolioInput,
  PensionTaxScenarioInput,
} from "../api/types";

const PENSION_TAX_PROMPT = /세액\s*공제|중도\s*해지|연금\s*외\s*수령|16\.5\s*%/;

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
  failedPrompt?: string;
  failedEducationalPortfolio?: EducationalPortfolioInput;
  createdAt: Date;
}

interface UseChatStreamOptions {
  accessToken: string | undefined;
  authenticatedUserId: string | null;
  activeSessionId: string | null;
  conversationContext: ConversationContext | null;
  conversationGenerationRef: { current: number };
  deletingSessionId: string | null;
  pensionTaxInput: PensionTaxScenarioInput | undefined;
  selectedScenario: string;
  surveyProfile: CompletedSurveyProfile | null;
  isCurrentOperation: (
    authGeneration: number,
    userId: string | null,
    token: string | null,
    conversationGeneration?: number,
  ) => boolean;
  onAuthenticatedError: (message: string) => void;
  onConversationContext: Dispatch<SetStateAction<ConversationContext | null>>;
  onComplete: () => void;
  onInputClear: () => void;
  onPersistedSession: (sessionId: string, token: string, userId: string) => void;
  onServerReady: (ready: boolean) => void;
  onStart: () => void;
  getAuthGeneration: () => number;
}

export function useChatStream({
  accessToken,
  authenticatedUserId,
  activeSessionId,
  conversationContext,
  conversationGenerationRef,
  deletingSessionId,
  pensionTaxInput,
  selectedScenario,
  surveyProfile,
  isCurrentOperation,
  onAuthenticatedError,
  onConversationContext,
  onComplete,
  onInputClear,
  onPersistedSession,
  onServerReady,
  onStart,
  getAuthGeneration,
}: UseChatStreamOptions) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [sendingStage, setSendingStage] = useState("답변을 준비하고 있습니다.");
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamingAnswerIsNarration, setStreamingAnswerIsNarration] = useState(false);
  const sendingRef = useRef(false);

  function resetStream() {
    sendingRef.current = false;
    setIsSending(false);
    setStreamingAnswer("");
    setStreamingAnswerIsNarration(false);
  }

  async function submitPrompt(
    prompt: string,
    educationalPortfolio?: EducationalPortfolioInput,
  ) {
    const normalized = prompt.trim();
    if (normalized.length < 2 || sendingRef.current || deletingSessionId) return;

    const requestToken = accessToken ?? null;
    const requestUserId = authenticatedUserId;
    const authGeneration = getAuthGeneration();
    const conversationGeneration = ++conversationGenerationRef.current;
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
    onInputClear();
    setIsSending(true);
    setSendingStage("질문을 확인하고 있습니다.");
    setStreamingAnswer("");
    setStreamingAnswerIsNarration(false);

    const appendAnswerDelta = (delta: string) => {
      if (isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) setStreamingAnswer((current) => current + delta);
    };
    const replaceWithNarration = (answer: string) => {
      if (isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) {
        setStreamingAnswerIsNarration(true);
        setStreamingAnswer(answer);
      }
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
      if (!isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) return;
      const response = streamed.response;
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: response.answer,
        response,
        createdAt: new Date(),
      }]);
      onConversationContext(response.conversation_context ?? conversationContext);
      if (streamed.persisted && streamed.session_id && requestToken && requestUserId) {
        onPersistedSession(streamed.session_id, requestToken, requestUserId);
      }
      onServerReady(true);
    } catch (error) {
      if (!isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) return;
      const message = requestToken
        ? authenticatedErrorMessage(error)
        : "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
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
      if (isCurrentOperation(
        authGeneration,
        requestUserId,
        requestToken,
        conversationGeneration,
      )) {
        resetStream();
        onComplete();
      }
    }
  }

  return {
    isSending,
    messages,
    resetStream,
    sendingStage,
    setMessages,
    streamingAnswer,
    streamingAnswerIsNarration,
    submitPrompt,
  };
}

function authenticatedErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "로그인이 만료되었습니다. 다시 로그인해 주세요.";
  }
  if (error instanceof ApiError && error.status === 503) {
    return "대화 저장소에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.";
  }
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}
