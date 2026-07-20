import { type ReactNode, type RefObject } from "react";

import type { ConversationMessage } from "../hooks/useChatStream";

interface ChatConversationProps {
  messages: ConversationMessage[];
  isSending: boolean;
  sendingStage: string;
  streamingAnswer: string;
  conversationEndRef: RefObject<HTMLDivElement | null>;
  latestMessageRef: RefObject<HTMLDivElement | null>;
  renderAssistant: (message: ConversationMessage) => ReactNode;
  renderRetry: (message: ConversationMessage) => ReactNode;
  renderStreamingAnswer: () => ReactNode;
  renderIcon: (name: "spark" | "send") => ReactNode;
}

export function ChatConversation({
  messages,
  isSending,
  sendingStage,
  streamingAnswer,
  conversationEndRef,
  latestMessageRef,
  renderAssistant,
  renderRetry,
  renderStreamingAnswer,
  renderIcon,
}: ChatConversationProps) {
  return (
    <>
      {messages.length > 0 && (
        <div className="message-list">
          {messages.map((message) => (
            <div
              className={`message-row ${message.role}`}
              key={message.id}
              ref={message.id === messages[messages.length - 1]?.id ? latestMessageRef : undefined}
            >
              {message.role === "assistant" && <div className="assistant-avatar">{renderIcon("spark")}</div>}
              <div className="message-group">
                <div className="message-bubble">{renderAssistant(message)}</div>
                {renderRetry(message)}
              </div>
            </div>
          ))}
          {isSending && (
            <div className="message-row assistant">
              <div className="assistant-avatar">{renderIcon("spark")}</div>
              {streamingAnswer ? (
                <div className="message-bubble" aria-live="polite">{renderStreamingAnswer()}</div>
              ) : (
                <div className="message-bubble typing" aria-label={sendingStage}>
                  <span /><span /><span /><small>{sendingStage}</small>
                </div>
              )}
            </div>
          )}
          <div ref={conversationEndRef} />
        </div>
      )}

    </>
  );
}
