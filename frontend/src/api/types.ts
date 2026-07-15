/**
 * FastAPI REST 계약 타입 (backend/app/api/*, backend/app/engine/models.py 동기화).
 *
 * 주의: 백엔드의 Decimal 필드는 JSON에서 전부 "문자열"로 직렬화된다.
 * 금액(_krw)·비율(_percent) 타입이 string인 것은 실수가 아니라 계약이다.
 */

export type AccountType = "dc" | "irp" | "pension_savings";
export type RiskTreatment =
  | "capital_preservation"
  | "general_risky"
  | "statutory_exception";
export type StatutoryException = "eligible_tdf" | "default_option";
export type RuleStatus = "pass" | "fail" | "not_applicable";
export type AssetClass =
  | "cash"
  | "deposit"
  | "bond"
  | "domestic_equity"
  | "global_equity"
  | "alternative"
  | "eligible_tdf"
  | "default_option";
export type RiskProfile =
  | "stable"
  | "stable_seeking"
  | "risk_neutral"
  | "active"
  | "aggressive";
export type AgeBand =
  | "age_20s"
  | "age_30s"
  | "age_40s"
  | "age_50_54"
  | "at_or_above_55";
export type AssumptionScenario = "low" | "base" | "high";

export interface HealthResponse {
  status: string;
}

export interface SourceChip {
  label: string;
  reference: string;
  as_of: string;
}

export interface AllocationWeights {
  growth_percent: string;
  safe_percent: string;
  cash_percent: string;
}

export interface AssetClassWeight {
  asset_class: AssetClass;
  amount_krw: string;
  weight_percent: string;
}

// ── /engine/risk-cap ──
export interface HoldingInput {
  holding_id: string;
  amount_krw: string;
  risk_treatment: RiskTreatment;
  statutory_exception?: StatutoryException | null;
}

export interface PortfolioInput {
  account_type: AccountType;
  holdings: HoldingInput[];
}

export interface RiskCapEvidence {
  rule_code: string;
  rule_version: string;
  source: SourceChip;
  numerator_general_risky_krw: string;
  denominator_total_krw: string;
  statutory_exception_krw: string;
  limit_percent: string | null;
}

export interface RiskCapEvaluation {
  engine_name: string;
  engine_version: string;
  evaluated_input: PortfolioInput;
  total_amount_krw: string;
  capital_preservation_amount_krw: string;
  general_risky_amount_krw: string;
  statutory_exception_amount_krw: string;
  general_risky_ratio_percent: string;
  limit_percent: string | null;
  excess_general_risky_amount_krw: string | null;
  within_limit: boolean | null;
  status: RuleStatus;
  evidence: RiskCapEvidence[];
}

// ── /engine/profile ──
export interface SurveyAnswer {
  question_code: string;
  selected_score: number;
}

export interface ProfileSurveyInput {
  answers: SurveyAnswer[];
}

export interface ProfileEvaluation {
  engine_name: string;
  engine_version: string;
  rule_version: string;
  provisional: boolean;
  total_score: number;
  min_score: number;
  max_score: number;
  score_percent: string;
  risk_profile: RiskProfile;
  band_upper_bounds_percent: Record<RiskProfile, string | null>;
  evidence: SourceChip[];
}

// ── /engine/diagnostics ──
export interface AccountHolding extends HoldingInput {
  instrument_name: string;
  asset_class: AssetClass;
}

export interface AccountInput {
  account_id: string;
  account_type: AccountType;
  holdings: AccountHolding[];
}

export interface DiagnosticFinding {
  check_code: string;
  status: RuleStatus;
  measured_percent: string;
  threshold_percent: string | null;
  subject_asset_class?: AssetClass | null;
  message: string;
  source: SourceChip;
}

export interface AccountDiagnosticsEvaluation {
  engine_name: string;
  engine_version: string;
  account_id: string;
  account_type: AccountType;
  total_amount_krw: string;
  asset_class_weights: AssetClassWeight[];
  findings: DiagnosticFinding[];
  risk_cap: RiskCapEvaluation;
}

// ── /engine/aggregation ──
export interface AggregationInput {
  accounts: AccountInput[];
}

export interface AccountContribution {
  account_id: string;
  account_type: AccountType;
  amount_krw: string;
  weight_percent: string;
}

export interface OverlapFinding {
  asset_class: AssetClass;
  account_ids: string[];
  combined_amount_krw: string;
  combined_weight_percent: string;
}

export interface AggregationEvaluation {
  engine_name: string;
  engine_version: string;
  total_amount_krw: string;
  asset_class_totals: AssetClassWeight[];
  per_account: AccountContribution[];
  overlaps: OverlapFinding[];
  notice: string;
  evidence: SourceChip[];
}

// ── /engine/simulation ──
export interface SimulationInput {
  current_age: number;
  risk_profile: RiskProfile;
  current_balance_krw: string;
  monthly_contribution_krw: string;
  inflation_percent?: string;
}

export interface BandSegment {
  age_band: AgeBand;
  months: number;
  weights: AllocationWeights;
  net_annual_return_percent_by_scenario: Record<AssumptionScenario, string>;
}

export interface ScenarioProjection {
  scenario: AssumptionScenario;
  nominal_value_at_55_krw: string;
  real_value_at_55_krw: string;
  investment_gain_krw: string;
}

export interface SimulationEvaluation {
  engine_name: string;
  engine_version: string;
  assumption_version: string;
  current_age: number;
  target_age: number;
  years_to_55: number;
  months_to_55: number;
  inflation_percent: string;
  total_principal_krw: string;
  projections: ScenarioProjection[];
  band_segments: BandSegment[];
  assumption_notice: string;
  evidence: SourceChip[];
}

// ── /engine/allocation-example ──
export interface AllocationExampleInput {
  current_age: number;
  risk_profile: RiskProfile;
  account_type: AccountType;
}

export interface AllocationExampleEvaluation {
  engine_name: string;
  engine_version: string;
  assumption_version: string;
  account_type: AccountType;
  risk_profile: RiskProfile;
  age_band: AgeBand;
  weights: AllocationWeights | null;
  display_net_return_percent_by_scenario: Partial<
    Record<AssumptionScenario, string>
  >;
  dc_irp_cap_applied: boolean;
  market_shock_percent: string | null;
  educational_notice: string;
  evidence: SourceChip[];
}

// ── /retrieval/* ──
export interface KnowledgeMatch {
  chunk_id: number;
  document_id: string;
  title: string;
  source_url: string;
  content: string;
  text_rank: number;
}

export interface KnowledgeSearchResponse {
  query: string;
  source_label: string;
  results: KnowledgeMatch[];
}

export interface NewsItem {
  item_id: string;
  title: string;
  description: string | null;
  original_url: string;
  portal_url: string | null;
  published_at: string | null;
}

export interface NewsListResponse {
  search_query: string;
  source_label: string;
  results: NewsItem[];
}

// ── /disclosures/* ──
export interface PensionSavingsStat {
  year: number;
  quarter: number;
  area_name_raw: string;
  company_name_raw: string;
  reserve_krw: string | null;
  earn_rate_1y: string | null;
  avg_earn_rate_3y: string | null;
  fee_rate_1y: string | null;
  quality_flags: string[];
  observed_at: string;
}

export interface PensionSavingsDisclosureResponse {
  source_label: string;
  year: number | null;
  quarter: number | null;
  results: PensionSavingsStat[];
}

export interface RetirementStat {
  year: number;
  quarter: number;
  scheme: "db" | "dc" | "irp";
  area_name_raw: string;
  company_name_raw: string;
  reserve_krw: string | null;
  earn_rate_current: string | null;
  avg_earn_rate_3y: string | null;
  avg_earn_rate_5y: string | null;
  quality_flags: string[];
  observed_at: string;
}

export interface RetirementDisclosureResponse {
  source_label: string;
  scheme: "db" | "dc" | "irp" | null;
  year: number | null;
  quarter: number | null;
  results: RetirementStat[];
}
