import type { ChatCard } from "../api/types";
import { ChatIcon } from "./ChatIcon";

interface ThemeCard {
  number: number;
  title: string;
  message: string;
}

export function ChatQuestionRecommendations({
  cards,
  onSubmit,
}: {
  cards: ChatCard[];
  onSubmit: (message: string) => void;
}) {
  return (
    <section className="chat-home-card-section" aria-labelledby="chat-question-heading">
      <header className="chat-home-section-heading">
        <p>추천 질문</p>
        <h2 id="chat-question-heading">챗봇에게 무엇이든 물어보세요</h2>
      </header>
      <div className="prompt-carousel" aria-label="챗봇 추천 질문">
        {cards.map((card) => (
          <button type="button" key={card.card_id} onClick={() => onSubmit(card.message)}>
            <span className="design-prompt-copy"><small>추천 질문</small><strong>{card.title}</strong><em>{card.message}</em></span>
          </button>
        ))}
      </div>
    </section>
  );
}

export function ChatEtfThemeCards({
  allVisible,
  onSubmit,
  onToggle,
  themeCards,
}: {
  allVisible: boolean;
  onSubmit: (message: string) => void;
  onToggle: () => void;
  themeCards: readonly ThemeCard[];
}) {
  const initialCount = 5;
  const remainingCount = themeCards.length - initialCount;
  const renderCard = (card: ThemeCard) => (
    <button
      type="button"
      key={card.title}
      aria-label={`${card.title} ETF 테마 설명 보기`}
      onClick={() => onSubmit(card.message)}
    >
      <span className="sector-card-icon"><ChatIcon name="chart" size={19} /></span>
      <span><small>ETF 테마 {card.number}</small><strong>{card.title}</strong></span>
      <ChatIcon name="chevron" size={16} />
    </button>
  );

  return (
    <section className="chat-home-card-section etf-theme-section" aria-labelledby="etf-theme-heading">
      <header className="chat-home-section-heading">
        <p>ETF 테마</p>
        <h2 id="etf-theme-heading">ETF 섹터 알아보기</h2>
        <span>테마의 구성과 유의점을 교육용으로 확인해 보세요.</span>
      </header>
      <div className="sector-card-grid" aria-label="ETF 섹터 카드">
        {themeCards.slice(0, initialCount).map(renderCard)}
        <button
          type="button"
          className="sector-card-toggle"
          aria-expanded={allVisible}
          aria-label={allVisible ? "ETF 테마 목록 접기" : `나머지 ETF 테마 ${remainingCount}개 더보기`}
          onClick={onToggle}
        >
          <span className="sector-card-icon"><ChatIcon name="chart" size={19} /></span>
          <span>
            <small>{allVisible ? "ETF 테마 목록" : `+${remainingCount}개`}</small>
            <strong>{allVisible ? "접기" : "더보기"}</strong>
          </span>
          <ChatIcon name="chevron" size={16} />
        </button>
        {allVisible && themeCards.slice(initialCount).map(renderCard)}
      </div>
    </section>
  );
}
