import type {
  AggregationEvaluation,
  AggregationInput,
  PensionAccountSnapshot,
  RiskProfile,
  UserPensionPortfolio,
} from "./api/types";

export interface PensionPlannerAccountOption {
  id: string;
  name: string;
  type: PensionAccountSnapshot["account_type"] | null;
  balance: string;
  combined: boolean;
}

export interface PensionPlannerFrameState {
  accounts: PensionPlannerAccountOption[];
  accountId: string;
  age: number;
  endAge: number;
  monthly: number;
  strategyId: string | null;
  selectedRiskProfile: RiskProfile;
}

export function toAggregationInput(
  portfolio: UserPensionPortfolio,
): AggregationInput {
  return {
    accounts: portfolio.accounts.map((account) => ({
      account_id: account.account_id,
      account_type: account.account_type,
      holdings: account.holdings.map((holding) => ({
        holding_id: holding.holding_id,
        instrument_name: holding.instrument_name,
        asset_class: holding.asset_class,
        amount_krw: holding.amount_krw,
        risk_treatment: holding.risk_treatment,
        statutory_exception: holding.statutory_exception,
      })),
    })),
  };
}

export function plannerAccountOptions(
  portfolio: UserPensionPortfolio,
  aggregation: AggregationEvaluation,
): PensionPlannerAccountOption[] {
  return [
    {
      id: "all",
      name: "전체 계좌",
      type: null,
      balance: aggregation.total_amount_krw,
      combined: true,
    },
    ...portfolio.accounts.map((account) => ({
      id: account.account_id,
      name: account.account_name,
      type: account.account_type,
      balance: account.market_value_krw,
      combined: false,
    })),
  ];
}

export function latestPortfolioDate(
  portfolio: UserPensionPortfolio,
): string | null {
  return portfolio.accounts.reduce<string | null>(
    (latest, account) => (
      latest === null || account.as_of_date > latest
        ? account.as_of_date
        : latest
    ),
    null,
  );
}

export function portfolioBoundaryLabel(
  boundary: UserPensionPortfolio["data_boundary"],
): string {
  return {
    real: "실계좌 데이터",
    mock: "교육용 목데이터",
    mixed: "실·목 혼합 데이터",
    unavailable: "계좌 미연결",
  }[boundary];
}
