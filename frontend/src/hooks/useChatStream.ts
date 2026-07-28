import { useRef, useState, type Dispatch, type SetStateAction } from "react";

import {
  ApiError,
  apiErrorMessage,
  sendAuthenticatedChatStream,
} from "../api/client";
import type {
  ChatResponse,
  CompletedSurveyProfile,
  ConversationContext,
  EducationalPortfolioInput,
} from "../api/types";

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  requestPrompt?: string;
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
  const [sendingStage, setSendingStage] = useState("질문을 이해하고 있어요.");
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamingAnswerIsNarration, setStreamingAnswerIsNarration] = useState(false);
  const sendingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const stoppedByUserRef = useRef(false);

  function resetStream() {
    // 화면 상태만 비우면 서버는 계속 답변을 만든다. 진행 중인 요청을 함께 끊는다.
    abortRef.current?.abort();
    sendingRef.current = false;
    abortRef.current = null;
    setIsSending(false);
    setStreamingAnswer("");
    setStreamingAnswerIsNarration(false);
  }

  // 사용자가 정지 버튼을 눌렀을 때만 안내 말풍선을 남긴다.
  function stopStream() {
    if (!sendingRef.current) return;
    stoppedByUserRef.current = true;
    abortRef.current?.abort();
  }

  async function submitPrompt(
    prompt: string,
    educationalPortfolio?: EducationalPortfolioInput,
  ) {
    const normalized = prompt.trim();
    if (normalized.length < 2 || sendingRef.current || deletingSessionId) return;

    if (!accessToken) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "user",
          text: normalized,
          createdAt: new Date(),
        },
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: "로그인이 필요해요. 로그인 후 다시 질문해 주세요.",
          createdAt: new Date(),
        },
      ]);
      onInputClear();
      onAuthenticatedError("로그인이 필요해요. 로그인 후 다시 질문해 주세요.");
      return;
    }

    const requestToken = accessToken;
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

    const controller = new AbortController();
    abortRef.current = controller;
    stoppedByUserRef.current = false;

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

    try {
      const streamed = await sendAuthenticatedChatStream(
        normalized,
        requestToken,
        setSendingStage,
        appendAnswerDelta,
        replaceWithNarration,
        selectedScenario || undefined,
        activeSessionId || undefined,
        idempotencyKey,
        conversationContext,
        undefined,
        surveyProfile,
        educationalPortfolio,
        controller.signal,
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
        requestPrompt: normalized,
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
      // 사용자가 직접 멈춘 경우는 실패가 아니므로 오류 말풍선을 남기지 않는다.
      if (stoppedByUserRef.current) {
        setMessages((current) => [...current, {
          id: crypto.randomUUID(),
          role: "assistant",
          text: "답변을 멈췄어요. 다시 물어보시면 이어서 도와드릴게요.",
          failedPrompt: normalized,
          failedEducationalPortfolio: educationalPortfolio,
          createdAt: new Date(),
        }]);
        return;
      }
      // 새 대화 시작이나 사용자 전환으로 끊긴 요청은 조용히 버린다.
      if (controller.signal.aborted) return;
      const message = requestToken
        ? authenticatedErrorMessage(error)
        : "답변을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.";
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
    stopStream,
    streamingAnswer,
    streamingAnswerIsNarration,
    submitPrompt,
  };
}

function authenticatedErrorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.code === "string") return apiErrorMessage(error);
  if (error instanceof ApiError && error.status === 401) {
    return "로그인이 만료되었습니다. 다시 로그인해 주세요.";
  }
  if (error instanceof ApiError && error.status === 503) {
    return "대화를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.";
  }
  return "답변을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.";
}
