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
}

// 각 전략의 정성 설명은 docs/team/주식 전략을 활용한 연금 포트폴리오 운용안.md 근거다.
// 전략별 자산배분 %·수익률 등 수치는 문서에 근거가 없어 화면에 넣지 않는다(수치 환각 금지 규칙).
export const STRATEGIES: StrategyExploreItem[] = [
  { id: "market-beta", name: "시장 베타 전략", accent: "#4FB6E6", role: "공무원", img: marketBeta, desc: "시장 전체 흐름을 그대로 따라가는 안정적인 전략이에요.", keywords: ["시장 전체 흐름", "안정적"], directness: "직접 구현 가능", bucket: "코어 베타", accountApplication: "국내·글로벌 광범위 지수 ETF·펀드로 담아요.", howItWorks: "시장 전체를 넓게 담아 장기 시장수익을 확보하는 코어 영역이에요. 단기 전망에 따라 전량 매도하지 않고 오래 보유합니다." },
  { id: "factor", name: "팩터 전략", accent: "#24386E", role: "회계사", img: factor, desc: "성과에 영향을 주는 핵심 팩터를 골라 담는 전략이에요.", keywords: ["핵심 팩터"], directness: "직접 구현 가능", bucket: "코어 베타", accountApplication: "가치·퀄리티·모멘텀·최소변동성 팩터 ETF로 담아요.", howItWorks: "성과에 영향을 주는 팩터를 규칙 기반으로 골라 담아요. 퀄리티·가치 팩터는 장기 코어로, 모멘텀은 회전율·반전 위험을 함께 관리합니다." },
  { id: "theme", name: "테마 전략", accent: "#F5871F", role: "스타트업 창업가", img: theme, desc: "성장 테마를 발굴해 기회를 노리는 전략이에요.", keywords: ["성장 테마"], directness: "직접 구현 가능", bucket: "전술 알파", accountApplication: "AI·반도체·바이오·인프라 등 분산형 테마 ETF로 담아요.", howItWorks: "구조적 성장 근거·최근 상대성과·거래량과 분산·밸류에이션 과열 미발생을 모두 통과한 테마만 후보로 편입해요. 단일 테마는 총계좌의 5~10%, 전술 버킷의 30% 이내로 제한합니다." },
  { id: "topdown", name: "탑다운 전략", accent: "#3B4148", role: "거시경제 애널리스트", img: topdown, desc: "거시 흐름부터 짚어 유망 자산으로 좁혀가는 전략이에요.", keywords: ["거시 흐름", "유망 자산"], directness: "직접 구현 가능", bucket: "전술 알파", accountApplication: "국가·지역·산업·채권만기 비중을 조절해 담아요.", howItWorks: "금리·물가·경기 같은 거시 흐름부터 짚은 뒤 국가·산업·채권 만기 비중을 좁혀가는 전술 영역이에요." },
  { id: "bottomup", name: "바텀업 전략", accent: "#1E9E5D", role: "기업실사 담당자", img: bottomup, desc: "개별 기업을 실사하듯 꼼꼼히 뜯어보는 전략이에요.", keywords: ["개별 기업", "실사"], directness: "직접 구현 가능", bucket: "전술 알파", accountApplication: "액티브 주식형·퀄리티·GARP 펀드로 담아요.", howItWorks: "개별 기업을 실사하듯 뜯어보는 액티브·퀄리티·GARP 접근이에요. 전술 알파 버킷 안에서만 움직입니다." },
  { id: "target", name: "타깃 전략", accent: "#333333", role: "프리랜서 겸 공무원 부업러", img: target, desc: "목표 시점·목표 수익에 맞춰 자산을 조정해가는 전략이에요.", keywords: ["목표 시점", "목표 수익"], directness: "직접 구현 가능", bucket: "안정화 버킷 연동", accountApplication: "목표 시점(은퇴 시기)에 맞춰 위험자산과 안정화 버킷 비중을 조정해요.", howItWorks: "만 55세 최소목표와 현재 자산 사이 여유를 반영해 위험 비중을 조정하고, 목표 시점이 가까워질수록 안정화 버킷 비중을 확대해요." },
  { id: "volatility", name: "변동성 관리 전략", accent: "#9CA7AE", role: "리스크 매니저", img: volatility, desc: "위험을 조절해 변동성을 다스리는 전략이에요.", keywords: ["위험", "변동성"], directness: "직접 구현 가능", bucket: "안정화 버킷 연동", accountApplication: "저변동 ETF와 현금·채권 간 비중을 조절해 담아요.", howItWorks: "실현변동성이 연령별 목표의 1.25배를 넘으면 전술 비중을 비례해 줄여요. 변동성이 큰 구간에서 주식 노출을 낮추고 현금·채권을 늘려 경로를 완만하게 만듭니다." },
  { id: "longshort", name: "롱숏·시장중립 전략", accent: "#7B4FC0", role: "헤지펀드 매니저", img: longshort, desc: "매수와 매도를 함께 써 시장 방향에 덜 흔들리는 전략이에요.", keywords: ["매수와 매도", "시장 방향"], directness: "상품 확인 후 가능", bucket: "전술 알파", accountApplication: "적격 시장중립·절대수익형 공모펀드가 있을 때만 담아요.", howItWorks: "매수와 매도를 함께 써 시장 방향 노출을 줄여요. 계좌에서 매수할 상품이 없으면 그 비중은 퀄리티·최소변동성 또는 안정화 버킷으로 옮깁니다." },
  { id: "eventdriven", name: "이벤트드리븐 전략", accent: "#F5C518", role: "M&A 전문 변호사·자문역", img: eventdriven, desc: "인수합병 등 특정 이벤트에서 기회를 찾는 전략이에요.", keywords: ["인수합병", "이벤트"], directness: "상품 확인 후 가능", bucket: "전술 알파", accountApplication: "적격 합병차익·기업행동·스페셜시추에이션 펀드가 있을 때만 담아요.", howItWorks: "합병·분할·자사주·지배구조 개편처럼 이미 공시된 기업행동의 가격 변화를 이용해요. 적격 공모펀드가 없으면 종목 추천 신호로 쓰지 않고 교육 정보로만 제공합니다." },
  { id: "trend", name: "추세추종·글로벌 매크로 전략", accent: "#2F6FE0", role: "국제 정세 담당 애널리스트", img: trend, desc: "글로벌 추세와 거시 흐름에 올라타는 전략이에요.", keywords: ["글로벌 추세", "거시 흐름"], directness: "상품 확인 후 가능", bucket: "전술 알파", accountApplication: "적격 멀티에셋·글로벌 매크로 펀드가 있을 때만 담아요.", howItWorks: "글로벌 추세와 거시 흐름에 규칙 기반으로 올라타는 전술 영역이에요. 적격 상품이 확인될 때만 편입합니다." },
];
