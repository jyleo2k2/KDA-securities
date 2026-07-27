import { useEffect, useState } from "react";
import type { FormEvent, KeyboardEvent, ReactNode, RefObject } from "react";

import type { ConversationMessage } from "../hooks/useChatStream";
import { ChatIcon } from "./ChatIcon";

const CHAT_MESSAGE_PAGE_SIZE = 40;

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
          {message.role === "assistant" && <div className="assistant-avatar"><span>연금</span></div>}
          <div className="message-group">
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
          <div className="assistant-avatar"><span>연금</span></div>
          {renderStreamingAnswer() ?? (
            <div className="message-bubble typing" aria-label={sendingStage}>
              <span /><span /><span /><small>{sendingStage}</small>
            </div>
          )}
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
  return (
    <div className="composer-wrap">
      <form className="composer" onSubmit={onSubmit}>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(event) => onChange(event.target.value.slice(0, 1000))}
          onKeyDown={onKeyDown}
          placeholder="연금에 대해 무엇이든 물어보세요"
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
      <p>AI 답변은 투자 판단을 돕는 정보이며, 미래 수익을 보장하지 않습니다.</p>
    </div>
  );
}
