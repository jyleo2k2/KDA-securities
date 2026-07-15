export type ChatIntent =
  | "account_rule"
  | "mock_portfolio"
  | "provider_disclosure"
  | "news"
  | "out_of_scope";

export type DataBoundary =
  | "verified_knowledge"
  | "official_disclosure"
  | "news_metadata"
  | "mock"
  | "engine"
  | "unavailable";

export interface SourceEvidence {
  evidence_id: string;
  label: string;
  locator: string;
  data_boundary: DataBoundary;
  publisher?: string | null;
  as_of?: string | null;
}

export interface NumericEvidence {
  label: string;
  value: string | number;
  unit: string;
  evidence_id: string;
  basis: string;
}

export interface AnswerSection {
  kind: "fact" | "external_opinion" | "service_explanation" | "limitation";
  title: string;
  content: string;
  evidence_ids: string[];
}

export interface ChatResponse {
  intent: ChatIntent;
  answer: string;
  data_mode: string;
  narration_mode: string;
  model_name?: string | null;
  sections: AnswerSection[];
  sources: SourceEvidence[];
  numeric_evidence: NumericEvidence[];
  engine_results: unknown[];
  scenario_evaluation?: unknown | null;
  limitations: string[];
}

export interface ScenarioSummary {
  code: string;
  name: string;
  description: string;
  risk_profile: string;
  investment_horizon_years: number;
}

export interface ChatCapabilities {
  supported: string[];
  conditional: string[];
  unsupported: string[];
  scenario_codes: string[];
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
  failedPrompt?: string;
  createdAt: Date;
}
