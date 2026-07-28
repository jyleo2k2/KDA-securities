import { useEffect, useState } from "react";
import type { FormEvent, KeyboardEvent, ReactNode, RefObject } from "react";

import { pickChatPromptCandidate } from "../chatPromptCandidates";
import type { ConversationMessage } from "../hooks/useChatStream";
import yeongeumiProfile from "../assets/login/piggy-clean.png";
import { ChatIcon } from "./ChatIcon";

const CHAT_MESSAGE_PAGE_SIZE = 40;

function AssistantAvatar() {
  return (
    <div className="assistant-avatar" aria-hidden="true">
      <img src={yeongeumiProfile} alt="" />
    </div>
  );
}

export function ChatMessageList({
  conversationEndRef,
  conversationKey,
  deletingSessionId,
  isSending,
  latestMessageRef,
  messages,
  onRetry,
  renderMessage,
  renderStreamingAnswer,
  sendingStage,
}: {
  conversationEndRef: RefObject<HTMLDivElement | null>;
  conversationKey: string | null;
  deletingSessionId: string | null;
  isSending: boolean;
  latestMessageRef: RefObject<HTMLDivElement | null>;
  messages: ConversationMessage[];
  onRetry: (message: ConversationMessage) => void;
  renderMessage: (message: ConversationMessage) => ReactNode;
  renderStreamingAnswer: () => ReactNode;
  sendingStage: string;
}) {
  const [visibleMessageCount, setVisibleMessageCount] = useState(CHAT_MESSAGE_PAGE_SIZE);
  const visibleMessages = messages.slice(-visibleMessageCount);

  useEffect(() => {
    setVisibleMessageCount(CHAT_MESSAGE_PAGE_SIZE);
  }, [conversationKey]);

  return (
    <div className="message-list" aria-live="polite" aria-atomic="false">
      {visibleMessageCount < messages.length && (
        <button
          className="retry-button"
          type="button"
          onClick={() => setVisibleMessageCount((current) => (
            current + CHAT_MESSAGE_PAGE_SIZE
          ))}
        >
          이전 메시지 더 보기
        </button>
      )}
      {visibleMessages.map((message) => (
        <div
          className={`message-row ${message.role}`}
          key={message.id}
          ref={message.id === messages[messages.length - 1]?.id ? latestMessageRef : undefined}
        >
          {message.role === "assistant" && <AssistantAvatar />}
          <div className="message-group">
            {message.role === "assistant" && <span className="message-sender">연그미</span>}
            <div className="message-bubble">{renderMessage(message)}</div>
            {message.failedPrompt && (
              <button className="retry-button" type="button" onClick={() => onRetry(message)} disabled={isSending || deletingSessionId !== null}>
                <ChatIcon name="refresh" size={15} /> 다시 시도
              </button>
            )}
          </div>
        </div>
      ))}
      {isSending && (
        <div className="message-row assistant">
          <AssistantAvatar />
          <div className="message-group">
            <span className="message-sender">연그미</span>
            {renderStreamingAnswer() ?? (
              <div className="message-bubble typing" aria-label={sendingStage}>
                <span /><span /><span /><small>{sendingStage}</small>
              </div>
            )}
          </div>
        </div>
      )}
      <div ref={conversationEndRef} />
    </div>
  );
}

export function ChatComposer({
  deletingSessionId,
  input,
  isSending,
  onChange,
  onKeyDown,
  onStop,
  onSubmit,
  textareaRef,
}: {
  deletingSessionId: string | null;
  input: string;
  isSending: boolean;
  onChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  onStop: () => void;
  onSubmit: (event: FormEvent) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const [promptCandidate] = useState(pickChatPromptCandidate);

  return (
    <div className="composer-wrap">
      <form className="composer" onSubmit={onSubmit}>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(event) => onChange(event.target.value.slice(0, 1000))}
          onKeyDown={onKeyDown}
          placeholder={`예: ${promptCandidate}`}
          rows={1}
          aria-label="질문 입력"
          disabled={isSending || deletingSessionId !== null}
        />
        {isSending ? (
          <button
            type="button"
            className="composer-stop"
            onClick={onStop}
            aria-label="답변 멈추기"
            title="답변 멈추기"
          >
            <ChatIcon name="stop" size={20} />
          </button>
        ) : (
          <button type="submit" disabled={input.trim().length < 2 || deletingSessionId !== null} aria-label="질문 보내기"><ChatIcon name="send" size={20} /></button>
        )}
      </form>
      <p><ChatIcon name="shield" size={12} /> AI 답변은 투자 판단을 돕는 정보이며, 미래 수익을 보장하지 않습니다.</p>
    </div>
  );
}
