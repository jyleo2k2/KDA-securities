export const CHAT_PROMPT_CANDIDATES = [
  "IRP와 연금저축은 뭐가 달라?",
  "내 연금계좌에 돈만 넣어둬도 될까?",
  "ETF가 뭐야?",
  "리밸런싱은 왜 해야 해?",
  "손실이 나면 어떻게 해야 해?",
  "지금 시작해도 늦지 않았을까?",
  "연금계좌 세액공제 한도가 궁금해",
  "투자성향별 연금 운용 방법을 비교해줘",
  "연금은 언제부터 받을 수 있어?",
  "수수료는 장기 수익에 어떤 영향을 줘?",
] as const;

export function pickChatPromptCandidate(random = Math.random): string {
  return CHAT_PROMPT_CANDIDATES[
    Math.floor(random() * CHAT_PROMPT_CANDIDATES.length)
  ];
}
