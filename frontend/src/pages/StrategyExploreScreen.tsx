import { useEffect, useRef, useState, type JSX, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

import { cardStyle, normalizeIndex, shortestOffset, SWIPE_THRESHOLD_PX } from "./strategyExplore/fanMath";
import { STRATEGIES, type StrategyExploreItem } from "./strategyExplore/strategies";
import "./StrategyExploreScreen.css";

interface StrategyExploreScreenProps {
  onBack: () => void;
}

const STRATEGY_DETAIL_URL = "/strategy-detail";

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function highlightDesc(desc: string, keywords: string[]): ReactNode[] {
  if (!keywords.length) return [desc];
  const pattern = new RegExp(`(${keywords.map(escapeRegExp).join("|")})`, "g");
  return desc.split(pattern).map((part, i) => (keywords.includes(part) ? <strong key={i} className="se-kw">{part}</strong> : <span key={i}>{part}</span>));
}

export function StrategyExploreScreen({ onBack }: StrategyExploreScreenProps): JSX.Element {
  const [active, setActive] = useState(0);
  const current = STRATEGIES[active];
  const pointerStartX = useRef<number | null>(null);

  useEffect(() => {
    document.documentElement.style.setProperty("--se-accent", current.accent);
    return () => { document.documentElement.style.removeProperty("--se-accent"); };
  }, [current.accent]);

  function select(nextIndex: number): void {
    setActive(normalizeIndex(nextIndex, STRATEGIES.length));
  }
  function move(direction: number): void {
    select(active + direction);
  }
  function openStrategyDetail(): void {
    window.location.hash = STRATEGY_DETAIL_URL;
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>): void {
    if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); }
    if (event.key === "ArrowRight") { event.preventDefault(); move(1); }
  }
  function handlePointerDown(event: PointerEvent<HTMLDivElement>): void {
    pointerStartX.current = event.clientX;
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }
  function handlePointerUp(event: PointerEvent<HTMLDivElement>): void {
    if (pointerStartX.current === null) return;
    const delta = event.clientX - pointerStartX.current;
    pointerStartX.current = null;
    if (Math.abs(delta) < SWIPE_THRESHOLD_PX) return;
    move(delta < 0 ? 1 : -1);
  }

  return (
    <main className="se-stage">
      <section className="se-phone" aria-label="추천 전략 둘러보기">
        <div className="se-page">
          <div className="se-statusbar">
            <span className="se-statusbar-time">9:41</span>
            <span className="se-statusbar-icons" aria-hidden="true">● ● ▰</span>
          </div>

          <div className="se-back" onClick={onBack} role="button" tabIndex={0} aria-label="뒤로 가기" onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onBack(); }}>
            <span>‹</span>
          </div>

          <div className="se-brand">
            <span className="se-brand-mark" />
            <span className="se-brand-name">연금 <em>도우미</em></span>
          </div>

          <p className="se-headline">
            <span className="se-brandc">연금 도우미</span>에서
            <br />
            제공하는 <span className="se-accentc">추천 전략</span>들을 확인해보세요!
          </p>
          <p className="se-hint">좌우로 넘기거나 눌러서 전략을 선택하세요!</p>

          <section className="se-fan" aria-roledescription="carousel" aria-labelledby="seFanHeading" tabIndex={0} onKeyDown={handleKeyDown}>
            <h2 id="seFanHeading" className="se-sr-only">추천 전략 선택</h2>

            <div className="se-fan-stage" onPointerDown={handlePointerDown} onPointerUp={handlePointerUp} onPointerCancel={() => { pointerStartX.current = null; }}>
              <ul className="se-fan-cards">
                {STRATEGIES.map((strategy: StrategyExploreItem, i) => {
                  const offset = shortestOffset(i, active, STRATEGIES.length);
                  const distance = Math.abs(offset);
                  const style = cardStyle(offset);
                  const isActive = i === active;
                  const isVisible = distance <= 2;
                  return (
                    <li
                      key={strategy.id}
                      className="se-fan-card"
                      data-active={isActive ? "true" : "false"}
                      aria-hidden={!isActive}
                      style={{
                        "--se-fan-x": style.x,
                        "--se-fan-y": style.y,
                        "--se-fan-rotation": style.rotation,
                        "--se-fan-scale": style.scale,
                        "--se-fan-opacity": style.opacity,
                        zIndex: style.z,
                        pointerEvents: isVisible ? "auto" : "none",
                      } as React.CSSProperties}
                    >
                      <button type="button" className="se-fan-frame" aria-label={`${i + 1}번째 전략: ${strategy.name}`} tabIndex={isVisible ? 0 : -1} onClick={openStrategyDetail}>
                        <img src={strategy.img} alt={strategy.name} draggable="false" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className="se-pill-row">
              <span className="se-pill">
                <span className="se-dot" />
                <span>{current.name}</span>
              </span>
            </div>

            <div className="se-fan-controls">
              <button type="button" className="se-fan-arrow" aria-label="이전 전략" onClick={() => move(-1)}>
                <span aria-hidden="true">&#8249;</span>
              </button>
              <div className="se-fan-dots" aria-label="전략 선택">
                {STRATEGIES.map((strategy, i) => (
                  <button key={strategy.id} type="button" aria-label={`${i + 1}번째 전략 보기`} aria-current={i === active ? "true" : undefined} onClick={() => select(i)} />
                ))}
              </div>
              <button type="button" className="se-fan-arrow" aria-label="다음 전략" onClick={() => move(1)}>
                <span aria-hidden="true">&#8250;</span>
              </button>
            </div>

            <p className="se-sr-only" aria-live="polite">{`${STRATEGIES.length}개 중 ${active + 1}번째 전략, ${current.name}`}</p>
          </section>

          <div className="se-intro">
            <div className="se-intro-card">
              <span className="se-intro-title"><em>전략</em> 소개</span>
              <div className="se-intro-body">
                <div className="se-intro-avatar">
                  <img src={current.img} alt={current.name} onClick={openStrategyDetail} />
                </div>
                <div className="se-intro-summary">
                  <span className="se-intro-label">전략 요약</span>
                  <span className="se-intro-desc">{highlightDesc(current.desc, current.keywords)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
