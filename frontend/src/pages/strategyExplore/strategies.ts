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
}

export const STRATEGIES: StrategyExploreItem[] = [
  { id: "market-beta", name: "시장 베타 전략", accent: "#4FB6E6", role: "공무원", img: marketBeta, desc: "시장 전체 흐름을 그대로 따라가는 안정적인 전략이에요.", keywords: ["시장 전체 흐름", "안정적"] },
  { id: "factor", name: "팩터 전략", accent: "#24386E", role: "회계사", img: factor, desc: "성과에 영향을 주는 핵심 팩터를 골라 담는 전략이에요.", keywords: ["핵심 팩터"] },
  { id: "theme", name: "테마 전략", accent: "#F5871F", role: "스타트업 창업가", img: theme, desc: "성장 테마를 발굴해 기회를 노리는 전략이에요.", keywords: ["성장 테마"] },
  { id: "topdown", name: "탑다운 전략", accent: "#3B4148", role: "거시경제 애널리스트", img: topdown, desc: "거시 흐름부터 짚어 유망 자산으로 좁혀가는 전략이에요.", keywords: ["거시 흐름", "유망 자산"] },
  { id: "bottomup", name: "바텀업 전략", accent: "#1E9E5D", role: "기업실사 담당자", img: bottomup, desc: "개별 기업을 실사하듯 꼼꼼히 뜯어보는 전략이에요.", keywords: ["개별 기업", "실사"] },
  { id: "target", name: "타깃 전략", accent: "#333333", role: "프리랜서 겸 공무원 부업러", img: target, desc: "목표 시점·목표 수익에 맞춰 자산을 조정해가는 전략이에요.", keywords: ["목표 시점", "목표 수익"] },
  { id: "volatility", name: "변동성 관리 전략", accent: "#9CA7AE", role: "리스크 매니저", img: volatility, desc: "위험을 조절해 변동성을 다스리는 전략이에요.", keywords: ["위험", "변동성"] },
  { id: "longshort", name: "롱숏·시장중립 전략", accent: "#7B4FC0", role: "헤지펀드 매니저", img: longshort, desc: "매수와 매도를 함께 써 시장 방향에 덜 흔들리는 전략이에요.", keywords: ["매수와 매도", "시장 방향"] },
  { id: "eventdriven", name: "이벤트드리븐 전략", accent: "#F5C518", role: "M&A 전문 변호사·자문역", img: eventdriven, desc: "인수합병 등 특정 이벤트에서 기회를 찾는 전략이에요.", keywords: ["인수합병", "이벤트"] },
  { id: "trend", name: "추세추종·글로벌 매크로 전략", accent: "#2F6FE0", role: "국제 정세 담당 애널리스트", img: trend, desc: "글로벌 추세와 거시 흐름에 올라타는 전략이에요.", keywords: ["글로벌 추세", "거시 흐름"] },
];
