import type { ChatCard } from "../api/types";

export function ChatRecommendations({
  cards,
  onSelect,
}: {
  cards: ChatCard[];
  onSelect: (message: string) => void;
}) {
  return (
    <div className="prompt-carousel" aria-label="챗봇 추천 질문">
      {cards.map((card) => (
        <button type="button" key={card.card_id} onClick={() => onSelect(card.message)}>
          <span className="design-prompt-copy"><small>추천 질문</small><strong>{card.title}</strong><em>{card.message}</em></span>
        </button>
      ))}
    </div>
  );
}
