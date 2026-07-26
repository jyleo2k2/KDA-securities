import { useEffect, useRef, useState } from "react";

const DEFAULT_TYPING_INTERVAL_MS = 50;
const MAX_TYPING_DURATION_MS = 2_000;

function usePrefersReducedMotion(): boolean {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(() => (
    typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ));

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setPrefersReducedMotion(mediaQuery.matches);
    updatePreference();
    mediaQuery.addEventListener("change", updatePreference);
    return () => mediaQuery.removeEventListener("change", updatePreference);
  }, []);

  return prefersReducedMotion;
}

export function ChatTypingAnswer({
  text,
  animate,
  intervalMs = DEFAULT_TYPING_INTERVAL_MS,
  onProgress,
}: {
  text: string;
  animate: boolean;
  intervalMs?: number;
  onProgress?: () => void;
}) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [displayedText, setDisplayedText] = useState("");
  const [skipped, setSkipped] = useState(false);
  const onProgressRef = useRef(onProgress);
  const showWholeAnswer = !animate || intervalMs <= 0 || prefersReducedMotion || skipped;
  const renderedText = showWholeAnswer ? text : displayedText;

  useEffect(() => {
    onProgressRef.current = onProgress;
  }, [onProgress]);

  useEffect(() => {
    if (showWholeAnswer) {
      setDisplayedText(text);
      return undefined;
    }

    const tokens = text.match(/\s*\S+\s*/g) ?? (text ? [text] : []);
    const tokensPerTick = Math.max(
      1,
      Math.ceil((tokens.length * intervalMs) / MAX_TYPING_DURATION_MS),
    );
    let tokenIndex = 0;
    let timer: number | undefined;
    setDisplayedText("");

    const revealNextToken = () => {
      tokenIndex = Math.min(tokenIndex + tokensPerTick, tokens.length);
      setDisplayedText(tokens.slice(0, tokenIndex).join(""));
      if (tokenIndex < tokens.length) timer = window.setTimeout(revealNextToken, intervalMs);
    };

    revealNextToken();
    return () => window.clearTimeout(timer);
  }, [animate, intervalMs, prefersReducedMotion, skipped, text]);

  useEffect(() => {
    if (renderedText) onProgressRef.current?.();
  }, [renderedText]);

  const completeImmediately = () => {
    setSkipped(true);
    setDisplayedText(text);
  };

  return (
    <div
      className="typing-answer"
      onClick={completeImmediately}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          completeImmediately();
        }
      }}
      role="button"
      tabIndex={0}
      aria-label="답변 타이핑을 건너뛰려면 클릭하세요"
    >
      <p className="message-copy">{renderedText}</p>
    </div>
  );
}
