import bottomup from "../../assets/strategy-explore/bottomup.webp";
import eventdriven from "../../assets/strategy-explore/eventdriven.webp";
import factor from "../../assets/strategy-explore/factor.webp";
import longshort from "../../assets/strategy-explore/longshort.webp";
import marketBeta from "../../assets/strategy-explore/market-beta.webp";
import target from "../../assets/strategy-explore/target.webp";
import theme from "../../assets/strategy-explore/theme.webp";
import topdown from "../../assets/strategy-explore/topdown.webp";
import trend from "../../assets/strategy-explore/trend.webp";
import volatility from "../../assets/strategy-explore/volatility.webp";

export interface StrategyExploreItem {
  id: string;
  name: string;
  accent: string;
  role: string;
  img: string;
  desc: string;
  keywords: string[];
  directness: string;
  bucket: string;
  accountApplication: string;
  howItWorks: string;
  easyWords: { word: string; meaning: string }[];
}

// 각 전략의 정성 설명은 docs/team/주식 전략을 활용한 연금 포트폴리오 운용안.md 근거다.
// 전략별 자산배분 %·수익률 등 수치는 문서에 근거가 없어 화면에 넣지 않는다(수치 환각 금지 규칙).
export const STRATEGIES: StrategyExploreItem[] = [
  { id: "market-beta", name: "시장 베타 전략", accent: "#4FB6E6", role: "공무원", img: marketBeta, desc: "주식시장 전체를 넓게 따라가는 기본 투자예요.", keywords: ["시장 전체", "기본 투자"], directness: "직접 구현 가능", bucket: "오래 가져갈 기본 투자", accountApplication: "한국·미국처럼 큰 시장을 한꺼번에 담는 ETF·펀드로 나눠요.", howItWorks: "한 회사만 고르지 않고 많은 회사에 나눠 담아요. 오늘 내일의 전망만 보고 모두 팔지 않고 오래 가져가요.", easyWords: [{ word: "시장 베타", meaning: "주식시장 전체가 오르내리는 움직임이에요." }, { word: "지수 ETF", meaning: "많은 회사를 한꺼번에 담아 시장을 따라가는 상품이에요." }] },
  { id: "factor", name: "팩터 전략", accent: "#24386E", role: "회계사", img: factor, desc: "좋은 회사·싼 가격·꾸준한 흐름 같은 특징을 골라 담는 전략이에요.", keywords: ["회사 특징", "기본 투자"], directness: "직접 구현 가능", bucket: "오래 가져갈 기본 투자", accountApplication: "좋은 회사, 상대적으로 싼 회사, 가격 움직임이 덜한 회사를 담은 ETF로 나눠요.", howItWorks: "정해 둔 회사 특징을 가진 ETF를 골라 담아요. 최근 많이 오른 흐름만 믿고 크게 바꾸지 않아요.", easyWords: [{ word: "팩터", meaning: "회사를 고를 때 보는 공통 특징이에요." }, { word: "퀄리티", meaning: "빚이 너무 많지 않고 돈을 꾸준히 버는 좋은 회사라는 뜻이에요." }, { word: "가치", meaning: "회사 실력에 비해 가격이 너무 비싸지 않은지를 보는 방법이에요." }, { word: "모멘텀", meaning: "최근 오르던 흐름이 이어지는지 살펴보는 방법이에요." }, { word: "최소변동성", meaning: "가격이 비교적 덜 출렁이는 회사를 고르는 방법이에요." }] },
  { id: "theme", name: "테마 전략", accent: "#F5871F", role: "스타트업 창업가", img: theme, desc: "반도체·바이오처럼 한 분야의 성장 기회를 살펴보는 전략이에요.", keywords: ["성장 분야", "작은 비중"], directness: "직접 구현 가능", bucket: "작은 비중으로 기회를 보는 투자", accountApplication: "AI·반도체·바이오·인프라처럼 여러 회사가 든 테마 ETF를 조금씩 담아요.", howItWorks: "한 가지 테마에 연금 돈을 몰아넣지 않아요. 성장 근거와 사고팔기 쉬운 정도를 함께 보고 작은 비중으로만 살펴봐요.", easyWords: [{ word: "테마 ETF", meaning: "비슷한 분야의 여러 회사를 한데 모은 상품이에요." }, { word: "밸류에이션", meaning: "회사의 가격이 실력에 비해 너무 비싼지 보는 방법이에요." }] },
  { id: "topdown", name: "탑다운 전략", accent: "#3B4148", role: "거시경제 애널리스트", img: topdown, desc: "금리·물가·경기 같은 큰 흐름을 보고 투자 대상을 좁혀가는 전략이에요.", keywords: ["큰 경제 흐름", "작은 비중"], directness: "직접 구현 가능", bucket: "작은 비중으로 기회를 보는 투자", accountApplication: "나라·산업·채권의 기간 비중을 조금씩 조절해 담아요.", howItWorks: "경제 전체의 날씨를 먼저 보고, 그다음 나라나 산업을 살펴봐요. 한 가지 예상에 연금 돈을 크게 걸지는 않아요.", easyWords: [{ word: "거시경제", meaning: "금리·물가·경기처럼 나라 전체의 큰 경제 흐름이에요." }, { word: "채권 만기", meaning: "채권에 맡긴 돈을 돌려받는 시점이에요." }] },
  { id: "bottomup", name: "바텀업 전략", accent: "#1E9E5D", role: "기업실사 담당자", img: bottomup, desc: "회사를 하나씩 살펴보고 좋은 회사를 고르는 전략이에요.", keywords: ["회사 살펴보기", "작은 비중"], directness: "직접 구현 가능", bucket: "작은 비중으로 기회를 보는 투자", accountApplication: "전문가가 여러 회사를 골라 담는 주식형 펀드로 살펴봐요.", howItWorks: "회사가 무엇을 팔고 돈을 잘 버는지 차근차근 봐요. 한 회사에 몰아넣지 않고 작은 비중에서만 활용해요.", easyWords: [{ word: "바텀업", meaning: "경제 전체보다 회사 하나하나를 먼저 보는 방법이에요." }, { word: "액티브 펀드", meaning: "전문가가 회사를 골라 담는 펀드예요." }, { word: "GARP", meaning: "너무 비싸지 않은 성장 회사를 찾는 방법이에요." }] },
  { id: "target", name: "타깃 전략", accent: "#333333", role: "프리랜서 겸 공무원 부업러", img: target, desc: "은퇴 시기가 가까워질수록 안전한 돈을 늘리는 전략이에요.", keywords: ["은퇴 시기", "안전하게"], directness: "직접 구현 가능", bucket: "은퇴가 가까울수록 안전하게", accountApplication: "연금을 받기 시작할 나이에 맞춰 주식·채권·현금 비율을 조절해요.", howItWorks: "은퇴까지 시간이 많이 남았으면 주식을 조금 더 담고, 가까워질수록 채권과 현금을 늘려요.", easyWords: [{ word: "위험자산", meaning: "주식처럼 가격이 크게 오르내릴 수 있는 자산이에요." }, { word: "안정화 자산", meaning: "채권·현금처럼 가격 흔들림을 줄여주는 자산이에요." }] },
  { id: "volatility", name: "변동성 관리 전략", accent: "#9CA7AE", role: "리스크 매니저", img: volatility, desc: "가격이 너무 크게 출렁일 때 안전한 자산을 늘리는 전략이에요.", keywords: ["가격 흔들림", "안전하게"], directness: "직접 구현 가능", bucket: "흔들림을 줄이는 안전 투자", accountApplication: "가격이 덜 흔들리는 ETF와 채권·현금의 비율을 조절해요.", howItWorks: "시장이 평소보다 크게 흔들리면 주식 비율을 줄이고 채권·현금을 늘려요. 너무 빠르게 오르내리는 길을 조금 완만하게 만드는 방법이에요.", easyWords: [{ word: "변동성", meaning: "가격이 위아래로 흔들리는 크기예요." }, { word: "저변동 ETF", meaning: "가격이 비교적 덜 흔들리는 회사들을 모은 ETF예요." }] },
  { id: "longshort", name: "롱숏·시장중립 전략", accent: "#7B4FC0", role: "헤지펀드 매니저", img: longshort, desc: "시장 전체의 오르내림에 덜 흔들리도록 설계한 전략이에요.", keywords: ["시장 흔들림 줄이기", "상품 확인"], directness: "상품 확인 후 가능", bucket: "작은 비중으로 기회를 보는 투자", accountApplication: "연금계좌에서 살 수 있는 시장중립·절대수익형 펀드가 있을 때만 살펴봐요.", howItWorks: "오를 것 같은 쪽과 내릴 것 같은 쪽을 함께 살펴 시장 전체의 흔들림을 줄여요. 연금계좌에 맞는 상품이 없으면 쓰지 않아요.", easyWords: [{ word: "롱", meaning: "가격이 오를 것으로 보고 투자하는 쪽이에요." }, { word: "숏", meaning: "가격이 내릴 때의 움직임도 함께 활용하는 쪽이에요." }, { word: "시장중립", meaning: "시장이 오르거나 내려도 덜 흔들리게 만드는 방법이에요." }] },
  { id: "eventdriven", name: "이벤트드리븐 전략", accent: "#F5C518", role: "M&A 전문 변호사·자문역", img: eventdriven, desc: "합병처럼 회사에 큰 일이 생겼을 때의 변화를 살펴보는 전략이에요.", keywords: ["회사 큰 소식", "상품 확인"], directness: "상품 확인 후 가능", bucket: "작은 비중으로 기회를 보는 투자", accountApplication: "연금계좌에서 살 수 있는 관련 펀드가 있을 때만 살펴봐요.", howItWorks: "합병·분할·자사주처럼 이미 발표된 회사 소식을 보고 변화를 살펴봐요. 연금계좌에 맞는 펀드가 없으면 종목을 추천하지 않고 정보로만 알려줘요.", easyWords: [{ word: "기업행동", meaning: "합병·분할처럼 회사가 하는 큰 변화예요." }, { word: "스페셜 시추에이션", meaning: "회사에 특별한 일이 생긴 상황을 이용하는 투자 방법이에요." }] },
  { id: "trend", name: "추세추종·글로벌 매크로 전략", accent: "#2F6FE0", role: "국제 정세 담당 애널리스트", img: trend, desc: "세계 시장의 큰 흐름을 따라가 보는 전략이에요.", keywords: ["세계 시장 흐름", "상품 확인"], directness: "상품 확인 후 가능", bucket: "작은 비중으로 기회를 보는 투자", accountApplication: "연금계좌에서 살 수 있는 여러 자산을 담은 펀드가 있을 때만 살펴봐요.", howItWorks: "주식·채권·원자재 등 세계 시장의 큰 흐름을 규칙에 따라 살펴봐요. 연금계좌에 맞는 상품이 확인될 때만 작은 비중으로 활용해요.", easyWords: [{ word: "추세추종", meaning: "오르거나 내리는 큰 흐름을 따라가 보는 방법이에요." }, { word: "글로벌 매크로", meaning: "세계의 금리·물가·경기 같은 큰 흐름을 보는 방법이에요." }, { word: "멀티에셋", meaning: "주식·채권처럼 여러 종류의 자산을 함께 담는다는 뜻이에요." }] },
];
