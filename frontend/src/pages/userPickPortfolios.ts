export type UserPickFeasibility = "direct" | "product" | null;

export interface UserPickPortfolioPresentation {
  id: string;
  sector: string;
  period: string;
  returnLabel: string;
  returnColor: string;
  amount: string;
  allocations: {
    domestic: number;
    global: number;
    bond: number;
    cash: number;
  };
  strategyName: string | null;
  strategyDetail: string | null;
  feasibility: UserPickFeasibility;
}

export const USER_PICK_PORTFOLIOS: UserPickPortfolioPresentation[] = [
  {
    id: "꾸준한거북이",
    sector: "2차전지 종사자",
    period: "운용 3년 8개월",
    returnLabel: "+18.2%",
    returnColor: "#166f39",
    amount: "2,860만원",
    allocations: { domestic: 38, global: 27, bond: 20, cash: 15 },
    strategyName: "테마",
    strategyDetail: "테마 선정·교체 규칙 일부 정의, 모델 비중 미정",
    feasibility: "direct",
  },
  {
    id: "배당모으미",
    sector: "금융업 종사자",
    period: "운용 2년 6개월",
    returnLabel: "+9.6%",
    returnColor: "#166f39",
    amount: "5,120만원",
    allocations: { domestic: 34, global: 30, bond: 22, cash: 14 },
    strategyName: "팩터",
    strategyDetail: "가치·퀄리티·모멘텀 비중 미정",
    feasibility: "direct",
  },
  {
    id: "느긋한바벨러",
    sector: "자산운용 종사자",
    period: "운용 5년 2개월",
    returnLabel: "+6.1%",
    returnColor: "#166f39",
    amount: "8,430만원",
    allocations: { domestic: 30, global: 20, bond: 34, cash: 16 },
    strategyName: "바벨",
    strategyDetail: "성장·안전자산 구성 비중을 연령별로만 일부 정의",
    feasibility: "direct",
  },
  {
    id: "중립러버",
    sector: "IT업 종사자",
    period: "운용 1년 2개월",
    returnLabel: "+3.8%",
    returnColor: "#166f39",
    amount: "3,270만원",
    allocations: { domestic: 26, global: 24, bond: 28, cash: 22 },
    strategyName: "롱숏·시장중립",
    strategyDetail: "계좌 적격 상품과 실제 성과 데이터 없음",
    feasibility: "product",
  },
  {
    id: "초보투자자",
    sector: "학생",
    period: "운용 5개월",
    returnLabel: "-2.4%",
    returnColor: "#2e7ce0",
    amount: "540만원",
    allocations: { domestic: 62, global: 12, bond: 8, cash: 18 },
    strategyName: null,
    strategyDetail: null,
    feasibility: null,
  },
];
