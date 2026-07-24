import type {
  CompletedSurveyProfile,
  EducationalPortfolioInput,
  PensionAccountSnapshot,
  UserPensionPortfolio,
} from "./api/types";

export type ActualRebalancingReviewRequest =
  | {
    status: "ready";
    accountName: string;
    asOfDate: string;
    input: EducationalPortfolioInput;
  }
  | {
    status: "account_not_found" | "holdings_not_available";
  };

function positiveAmount(value: string): boolean {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return false;
  const [whole, fraction = ""] = normalized.split(".");
  return BigInt(whole) > 0n || /[1-9]/.test(fraction);
}

function accountForReview(
  profile: CompletedSurveyProfile,
  portfolio: UserPensionPortfolio,
): PensionAccountSnapshot | undefined {
  return portfolio.accounts.find(
    (account) => account.account_type === profile.account_type,
  );
}

/**
 * Converts the saved account snapshot into the engine's single-account review
 * input. Product classifications win for ETFs; asset classes let cash and
 * bonds remain part of the actual-account denominator.
 */
export function buildActualRebalancingReviewRequest(
  profile: CompletedSurveyProfile,
  portfolio: UserPensionPortfolio,
): ActualRebalancingReviewRequest {
  const account = accountForReview(profile, portfolio);
  if (!account) return { status: "account_not_found" };

  const currentHoldings = account.holdings
    .filter((holding) => positiveAmount(holding.amount_krw))
    .map((holding) => ({
      isu_code: holding.etf_isu_code?.trim() || `snapshot:${holding.holding_id}`,
      amount_krw: holding.amount_krw,
      asset_class: holding.asset_class,
    }));
  if (currentHoldings.length === 0) return { status: "holdings_not_available" };

  return {
    status: "ready",
    accountName: account.account_name,
    asOfDate: account.as_of_date,
    input: {
      account_type: account.account_type,
      age: profile.current_age,
      retirement_start_age: profile.retirement_start_age,
      risk_profile: profile.risk_profile,
      loss_tolerance_percent: profile.loss_tolerance_percent,
      max_etfs: 7,
      current_holdings: currentHoldings,
      new_contribution_krw: "0",
    },
  };
}
