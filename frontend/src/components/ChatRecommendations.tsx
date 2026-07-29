import {
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

import type { ChatCard } from "../api/types";
import { ChatIcon } from "./ChatIcon";

const ETF_THEME_DRAG_THRESHOLD_PX = 5;
const CHAT_QUESTION_DRAG_THRESHOLD_PX = 5;

const ETF_THEME_RAIL_CSS = `
.etf-theme-rail {
  display: grid;
  grid-auto-flow: column;
  grid-template-rows: repeat(3, auto);
  grid-auto-columns: calc(42% - 4px);
  gap: 10px;
  margin: 16px 0 0;
  padding: 2px 0 10px;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  cursor: grab;
}
.etf-theme-rail::-webkit-scrollbar { display: none; }
.etf-theme-rail.is-dragging {
  scroll-snap-type: none;
  user-select: none;
}
.etf-theme-rail.is-dragging,
.etf-theme-rail.is-dragging .etf-theme-rail-card { cursor: grabbing; }
.etf-theme-rail-card {
  scroll-snap-align: start;
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 9px;
  min-height: 78px;
  padding: 13px 12px;
  border: 1.5px solid #e6e8eb;
  border-radius: 14px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  font: inherit;
}
.etf-theme-rail-card:hover { border-color: #a9d8ba; background: #f4fbf4; }
.etf-theme-rail-card > span:last-of-type { display: grid; gap: 3px; min-width: 0; }
.etf-theme-rail-card small { color: #9aa0a6; font-size: 11.5px; font-weight: 700; }
.etf-theme-rail-card strong { color: #0f1113; font-size: 14px; font-weight: 800; word-break: keep-all; line-height: 1.3; }
`;

interface ThemeCard {
  number: number;
  title: string;
  message: string;
}

export function ChatQuestionRecommendations({
  cards,
  isLoading,
  onSubmit,
  onRetry,
}: {
  cards: ChatCard[];
  isLoading: boolean;
  onSubmit: (message: string) => void;
  onRetry: () => void;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const suppressClick = useRef(false);
  const drag = useRef<{
    moved: boolean;
    pointerId: number;
    startScrollLeft: number;
    startX: number;
  } | null>(null);
  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    drag.current = {
      moved: false,
      pointerId: event.pointerId,
      startScrollLeft: event.currentTarget.scrollLeft,
      startX: event.clientX,
    };
  };
  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const currentDrag = drag.current;
    if (!currentDrag || currentDrag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - currentDrag.startX;
    if (!currentDrag.moved && Math.abs(deltaX) < CHAT_QUESTION_DRAG_THRESHOLD_PX) return;
    if (!currentDrag.moved) {
      currentDrag.moved = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      setIsDragging(true);
    }
    event.preventDefault();
    event.currentTarget.scrollLeft = currentDrag.startScrollLeft - deltaX;
  };
  const finishPointerDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const currentDrag = drag.current;
    if (!currentDrag || currentDrag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    suppressClick.current = currentDrag.moved;
    if (currentDrag.moved) {
      window.setTimeout(() => {
        suppressClick.current = false;
      }, 0);
    }
    drag.current = null;
    setIsDragging(false);
  };

  return (
    <section className="chat-home-card-section" aria-labelledby="chat-question-heading">
      <header className="chat-home-section-heading">
        <p>빠른 시작</p>
        <h2 id="chat-question-heading">이런 질문부터 시작해 보세요</h2>
        <span>궁금한 카드를 누르면 연그미가 바로 설명해 드려요.</span>
      </header>
      {isLoading ? (
        <div
          className="chat-question-grid chat-question-grid-loading"
          aria-busy="true"
          aria-label="챗봇 추천 질문 로딩"
        >
          {Array.from({ length: 3 }, (_, index) => (
            <div className="chat-question-skeleton" key={index} aria-hidden="true">
              <i /><i /><i />
            </div>
          ))}
        </div>
      ) : cards.length > 0 ? (
        <div
          className={`chat-question-grid chat-question-grid-ready${isDragging ? " is-dragging" : ""}`}
          aria-label="챗봇 추천 질문"
          style={{
            cursor: isDragging ? "grabbing" : "grab",
            scrollSnapType: isDragging ? "none" : undefined,
            userSelect: isDragging ? "none" : undefined,
          }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={finishPointerDrag}
          onPointerCancel={finishPointerDrag}
        >
          {cards.map((card, index) => (
            <button
              type="button"
              key={card.card_id}
              style={{ cursor: isDragging ? "grabbing" : undefined }}
              onClick={() => {
                if (suppressClick.current) {
                  suppressClick.current = false;
                  return;
                }
                onSubmit(card.message);
              }}
            >
              <span className="chat-question-icon">
                <ChatIcon name={index === 0 ? "book" : index === 1 ? "shield" : "spark"} size={18} />
              </span>
              <span className="design-prompt-copy"><small>추천 {index + 1}</small><strong>{card.title}</strong><em>{card.message}</em></span>
              <ChatIcon name="chevron" size={17} />
            </button>
          ))}
        </div>
      ) : (
        <div className="chat-question-load-error" aria-live="polite">
          <span>추천 질문을 불러오지 못했어요.</span>
          <button type="button" onClick={onRetry}>다시 시도</button>
        </div>
      )}
    </section>
  );
}

export function ChatEtfThemeCards({
  onSubmit,
  themeCards,
}: {
  onSubmit: (message: string) => void;
  themeCards: readonly ThemeCard[];
}) {
  const [isDragging, setIsDragging] = useState(false);
  const drag = useRef<{
    moved: boolean;
    pointerId: number;
    startScrollLeft: number;
    startX: number;
  } | null>(null);
  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    drag.current = {
      moved: false,
      pointerId: event.pointerId,
      startScrollLeft: event.currentTarget.scrollLeft,
      startX: event.clientX,
    };
  };
  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const currentDrag = drag.current;
    if (!currentDrag || currentDrag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - currentDrag.startX;
    if (!currentDrag.moved && Math.abs(deltaX) < ETF_THEME_DRAG_THRESHOLD_PX) return;
    if (!currentDrag.moved) {
      currentDrag.moved = true;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      setIsDragging(true);
    }
    event.preventDefault();
    event.currentTarget.scrollLeft = currentDrag.startScrollLeft - deltaX;
  };
  const finishPointerDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const currentDrag = drag.current;
    if (!currentDrag || currentDrag.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    drag.current = null;
    setIsDragging(false);
  };
  const renderCard = (card: ThemeCard) => (
    <button
      type="button"
      key={card.title}
      className="etf-theme-rail-card"
      aria-label={`${card.title} ETF 테마 설명 보기`}
      onClick={() => onSubmit(card.message)}
    >
      <span className="sector-card-icon"><ChatIcon name="chart" size={19} /></span>
      <span><small>ETF 테마 {card.number}</small><strong>{card.title}</strong></span>
    </button>
  );

  return (
    <section className="chat-home-card-section etf-theme-section" aria-labelledby="etf-theme-heading">
      <style>{ETF_THEME_RAIL_CSS}</style>
      <header className="chat-home-section-heading">
        <p>ETF 테마</p>
        <h2 id="etf-theme-heading">ETF 섹터 알아보기</h2>
        <span>테마의 구성과 유의점을 확인해 보세요.</span>
      </header>
      <div
        className={`etf-theme-rail${isDragging ? " is-dragging" : ""}`}
        role="group"
        aria-label="ETF 섹터 카드 목록 (옆으로 넘겨 보기)"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishPointerDrag}
        onPointerCancel={finishPointerDrag}
      >
        {themeCards.map(renderCard)}
      </div>
    </section>
  );
}
