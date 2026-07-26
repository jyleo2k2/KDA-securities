// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const submitPrompt = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const resetStream = vi.hoisted(() => vi.fn());
const setMessages = vi.hoisted(() => vi.fn());

vi.mock("../api/client", () => ({
  ApiError: class ApiError extends Error {},
  apiErrorMessage: vi.fn(),
  completeRebalancingReview: vi.fn(),
  deleteAllChatSessions: vi.fn(),
  deleteChatSession: vi.fn(),
  getChatCards: vi.fn().mockResolvedValue({ cards: [] }),
  getChatSessions: vi.fn().mockResolvedValue([]),
  getMyPensionAccounts: vi.fn(),
  getRebalancingProfile: vi.fn(),
  getRebalancingReminder: vi.fn(),
  getScenarios: vi.fn().mockResolvedValue([]),
  getStoredChatMessages: vi.fn().mockResolvedValue([]),
  updateRebalancingReminder: vi.fn(),
  withoutDemoNameMarker: (name: string) => name,
}));

vi.mock("../hooks/useChatStream", () => ({
  useChatStream: () => ({
    isSending: false,
    messages: [],
    resetStream,
    sendingStage: null,
    setMessages,
    streamingAnswer: "",
    streamingAnswerIsNarration: false,
    submitPrompt,
  }),
}));

import {
  getMyPensionAccounts,
  getRebalancingProfile,
  getRebalancingReminder,
} from "../api/client";
import type { SupabaseAuthState } from "../auth/useSupabaseAuth";
import { GuidePage } from "./GuidePage";

const auth = {
  session: { access_token: "access-token", user: { id: "user-1", email: "owner@example.com" } },
  loading: false,
  configured: true,
  error: null,
  signIn: vi.fn(),
  signOut: vi.fn(),
} as unknown as SupabaseAuthState;

beforeEach(() => {
  vi.mocked(getRebalancingReminder).mockResolvedValue({
    profile_required: false,
    enabled: true,
    risk_profile: "active",
    cadence: {
      review_interval_months: 1,
      drift_threshold_percent_points: "3",
      rationale: "목표 비중 이탈 여부를 점검해요.",
    },
    last_reviewed_at: null,
    next_review_at: null,
    is_due: false,
  });
  vi.mocked(getRebalancingProfile).mockResolvedValue({
    account_type: "irp",
    account_types: ["irp"],
    current_age: 35,
    retirement_start_age: 60,
    risk_profile: "active",
    loss_tolerance_percent: "30",
  });
  vi.mocked(getMyPensionAccounts).mockResolvedValue({
    owner_id: "user-1",
    data_boundary: "mock",
    accounts: [{
      account_id: "irp-1",
      account_type: "irp",
      account_name: "개인형 IRP",
      data_kind: "mock",
      origin: "synthetic",
      snapshot_id: "snapshot-1",
      as_of_date: "2026-07-16",
      contributed_principal_krw: "10000000",
      market_value_krw: "10000000",
      holdings: [{
        holding_id: "holding-1",
        product_id: "product-1",
        instrument_name: "KODEX 200",
        etf_isu_code: "069500",
        asset_class: "domestic_equity",
        amount_krw: "10000000",
        risk_treatment: "general_risky",
        statutory_exception: null,
      }],
    }],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("actual rebalancing review", () => {
  it("restores the saved profile before submitting current holdings for review", async () => {
    render(
      <GuidePage
        auth={auth}
        onSignOut={vi.fn().mockResolvedValue(undefined)}
        surveyProfile={null}
        userContext={null}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "챗봇에 점검 요청" }));

    await waitFor(() => {
      expect(getRebalancingProfile).toHaveBeenCalledWith("access-token");
      expect(getMyPensionAccounts).toHaveBeenCalledWith("access-token");
      expect(submitPrompt).toHaveBeenCalledWith(
        "개인형 IRP의 실제 보유 비중을 목표 비중과 비교하고 이탈폭을 점검해줘.",
        expect.objectContaining({
          account_type: "irp",
          age: 35,
          retirement_start_age: 60,
          loss_tolerance_percent: "30",
          current_holdings: [expect.objectContaining({
            isu_code: "069500",
            amount_krw: "10000000",
          })],
        }),
      );
    });
  });
});
