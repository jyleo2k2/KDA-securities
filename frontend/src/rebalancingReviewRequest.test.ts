import { describe, expect, it } from "vitest";

import type { CompletedSurveyProfile, UserPensionPortfolio } from "./api/types";
import { buildActualRebalancingReviewRequest } from "./rebalancingReviewRequest";

const profile: CompletedSurveyProfile = {
  account_type: "irp",
  current_age: 35,
  retirement_start_age: 60,
  risk_profile: "risk_neutral",
  loss_tolerance_percent: "20",
};

const portfolio: UserPensionPortfolio = {
  owner_id: "user-1",
  data_boundary: "mock",
  accounts: [{
    account_id: "irp-1",
    account_type: "irp",
    account_name: "내 IRP",
    data_kind: "mock",
    origin: "synthetic",
    snapshot_id: "snapshot-1",
    as_of_date: "2026-07-24",
    contributed_principal_krw: null,
    market_value_krw: "10000000",
    holdings: [
      {
        holding_id: "etf-1",
        product_id: "product-1",
        instrument_name: "국내 주식 ETF",
        etf_isu_code: "069500",
        asset_class: "domestic_equity",
        amount_krw: "6000000",
        risk_treatment: "general_risky",
        statutory_exception: null,
      },
      {
        holding_id: "cash-1",
        product_id: null,
        instrument_name: "예수금",
        etf_isu_code: null,
        asset_class: "cash",
        amount_krw: "4000000",
        risk_treatment: "capital_preservation",
        statutory_exception: null,
      },
    ],
  }],
};

describe("buildActualRebalancingReviewRequest", () => {
  it("uses the saved account snapshot, including cash in the actual allocation", () => {
    const result = buildActualRebalancingReviewRequest(profile, portfolio);

    expect(result).toMatchObject({
      status: "ready",
      accountName: "내 IRP",
      input: {
        account_type: "irp",
        current_holdings: [
          { isu_code: "069500", amount_krw: "6000000", asset_class: "domestic_equity" },
          { isu_code: "snapshot:cash-1", amount_krw: "4000000", asset_class: "cash" },
        ],
      },
    });
  });

  it("does not silently use a different account type", () => {
    const result = buildActualRebalancingReviewRequest(
      profile,
      { ...portfolio, accounts: [{ ...portfolio.accounts[0], account_type: "dc" }] },
    );

    expect(result).toEqual({ status: "account_not_found" });
  });
});
