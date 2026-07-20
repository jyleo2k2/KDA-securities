import { type FormEvent, type KeyboardEvent, type ReactNode, type RefObject } from "react";

interface ChatComposerProps {
  input: string;
  disabled: boolean;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  sendIcon: ReactNode;
}

export function ChatComposer({
  input,
  disabled,
  textareaRef,
  onInputChange,
  onSubmit,
  onKeyDown,
  sendIcon,
}: ChatComposerProps) {
  return (
    <div className="composer-wrap">
      <form className="composer" onSubmit={onSubmit}>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(event) => onInputChange(event.target.value.slice(0, 1000))}
          onKeyDown={onKeyDown}
          placeholder="연금에 대해 무엇이든 물어보세요"
          rows={1}
          aria-label="질문 입력"
          disabled={disabled}
        />
        <button type="submit" disabled={input.trim().length < 2 || disabled} aria-label="질문 보내기">{sendIcon}</button>
      </form>
      <p>AI 답변은 투자 판단을 돕는 정보이며, 미래 수익을 보장하지 않습니다.</p>
    </div>
  );
}
