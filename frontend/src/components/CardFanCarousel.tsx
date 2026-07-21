import { useId, useRef, useState, type CSSProperties, type ReactNode } from "react";

import "./CardFanCarousel.css";

export interface CardFanCarouselItem {
  id: string;
  imageSrc: string;
  imageAlt: string;
  content?: ReactNode;
}

export interface CardFanCarouselProps {
  items: readonly CardFanCarouselItem[];
  ariaLabel?: string;
  initialIndex?: number;
  onIndexChange?: (index: number) => void;
}

type CardStyle = CSSProperties & {
  "--fan-x": string;
  "--fan-y": string;
  "--fan-rotation": string;
  "--fan-scale": string;
  "--fan-opacity": string;
};

const SWIPE_THRESHOLD_PX = 42;

function normalizeIndex(index: number, length: number) {
  return ((index % length) + length) % length;
}

function shortestOffset(index: number, activeIndex: number, length: number) {
  const direct = index - activeIndex;
  const wrapped = direct > 0 ? direct - length : direct + length;
  return Math.abs(direct) <= Math.abs(wrapped) ? direct : wrapped;
}

function cardStyle(offset: number): CardStyle {
  const distance = Math.abs(offset);
  const visibleDistance = Math.min(distance, 4);

  return {
    "--fan-x": `${offset * 31}%`,
    "--fan-y": `${visibleDistance * 5.5}%`,
    "--fan-rotation": `${offset * 7.5}deg`,
    "--fan-scale": `${Math.max(0.68, 1 - visibleDistance * 0.075)}`,
    "--fan-opacity": distance > 4 ? "0" : `${Math.max(0.48, 1 - distance * 0.13)}`,
    zIndex: Math.max(0, 20 - distance),
  };
}

export function CardFanCarousel({
  items,
  ariaLabel = "카드 슬라이드",
  initialIndex = 0,
  onIndexChange,
}: CardFanCarouselProps) {
  const headingId = useId();
  const pointerStartX = useRef<number | null>(null);
  const [activeIndex, setActiveIndex] = useState(() =>
    items.length === 0 ? 0 : normalizeIndex(initialIndex, items.length),
  );

  if (items.length === 0) {
    return null;
  }

  const select = (nextIndex: number) => {
    const normalized = normalizeIndex(nextIndex, items.length);
    setActiveIndex(normalized);
    onIndexChange?.(normalized);
  };

  const move = (direction: -1 | 1) => select(activeIndex + direction);

  const finishSwipe = (clientX: number) => {
    if (pointerStartX.current === null) {
      return;
    }

    const delta = clientX - pointerStartX.current;
    pointerStartX.current = null;

    if (Math.abs(delta) < SWIPE_THRESHOLD_PX) {
      return;
    }

    move(delta < 0 ? 1 : -1);
  };

  return (
    <section
      className="card-fan-carousel"
      aria-roledescription="carousel"
      aria-labelledby={headingId}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          move(-1);
        }
        if (event.key === "ArrowRight") {
          event.preventDefault();
          move(1);
        }
      }}
    >
      <h2 id={headingId} className="card-fan-carousel__sr-only">
        {ariaLabel}
      </h2>

      <div
        className="card-fan-carousel__stage"
        onPointerDown={(event) => {
          pointerStartX.current = event.clientX;
          event.currentTarget.setPointerCapture?.(event.pointerId);
        }}
        onPointerUp={(event) => finishSwipe(event.clientX)}
        onPointerCancel={() => {
          pointerStartX.current = null;
        }}
      >
        <ul className="card-fan-carousel__cards">
          {items.map((item, index) => {
            const offset = shortestOffset(index, activeIndex, items.length);
            const active = index === activeIndex;

            return (
              <li
                key={item.id}
                className="card-fan-carousel__card"
                style={cardStyle(offset)}
                aria-hidden={!active}
                data-active={active ? "true" : "false"}
              >
                <button
                  type="button"
                  className="card-fan-carousel__card-button"
                  aria-label={`${index + 1}번째 카드: ${item.imageAlt}`}
                  tabIndex={active ? 0 : -1}
                  onClick={() => select(index)}
                >
                  <img src={item.imageSrc} alt={item.imageAlt} draggable={false} />
                  {item.content ? (
                    <span className="card-fan-carousel__content">{item.content}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="card-fan-carousel__controls">
        <button
          type="button"
          className="card-fan-carousel__arrow"
          aria-label="이전 카드"
          onClick={() => move(-1)}
        >
          <span aria-hidden="true">&#8249;</span>
        </button>

        <div className="card-fan-carousel__dots" aria-label="카드 선택">
          {items.map((item, index) => (
            <button
              key={item.id}
              type="button"
              aria-label={`${index + 1}번째 카드 보기`}
              aria-current={index === activeIndex ? "true" : undefined}
              onClick={() => select(index)}
            />
          ))}
        </div>

        <button
          type="button"
          className="card-fan-carousel__arrow"
          aria-label="다음 카드"
          onClick={() => move(1)}
        >
          <span aria-hidden="true">&#8250;</span>
        </button>
      </div>

      <p className="card-fan-carousel__sr-only" aria-live="polite">
        {items.length}개 중 {activeIndex + 1}번째 카드, {items[activeIndex].imageAlt}
      </p>
    </section>
  );
}
