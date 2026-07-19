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
export type IncomeBasis =
  | "gross_salary"
  | "comprehensive_income"
  | "unknown";
export type WithdrawalReason = "general" | "unavoidable" | "unknown";
export type IrpDeferredIncomeStatus = "none" | "known" | "unknown";

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
  loss_tolerance_percent: string;
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

// ── /engine/pension-tax* ──
export interface PensionAccountTaxInput {
  balance_krw: string;
  current_year_contribution_krw: string;
  prior_year_non_deducted_principal_krw?: string | null;
}

export interface PensionTaxCreditInput {
  tax_year: 2026;
  income_basis: IncomeBasis;
  income_amount_krw?: string | null;
  pension_savings_contribution_krw: string;
  irp_contribution_krw: string;
}

export interface NonPensionWithdrawalInput {
  tax_year: 2026;
  pension_savings?: PensionAccountTaxInput | null;
  irp?: PensionAccountTaxInput | null;
  withdrawal_reason: WithdrawalReason;
  irp_deferred_income_status: IrpDeferredIncomeStatus;
  irp_deferred_retirement_income_krw?: string | null;
}

export interface PensionTaxScenarioInput {
  tax_year: 2026;
  income_basis: IncomeBasis;
  income_amount_krw?: string | null;
  pension_savings: PensionAccountTaxInput;
  irp: PensionAccountTaxInput;
  withdrawal_reason: WithdrawalReason;
  irp_deferred_income_status: IrpDeferredIncomeStatus;
  irp_deferred_retirement_income_krw?: string | null;
}

export interface TaxCreditRateScenario {
  label: string;
  income_tax_rate_percent: string;
  local_inclusive_display_rate_percent: string;
  estimated_tax_credit_krw: string;
}

export interface PensionTaxCreditEvaluation {
  engine_name: string;
  engine_version: string;
  rule_version: string;
  tax_year: number;
  pension_savings_contribution_krw: string;
  irp_contribution_krw: string;
  pension_savings_eligible_contribution_krw: string;
  irp_eligible_contribution_krw: string;
  total_eligible_contribution_krw: string;
  unused_combined_limit_krw: string;
  rate_determined: boolean;
  rate_scenarios: TaxCreditRateScenario[];
  assumption_notice: string;
  evidence: SourceChip[];
}

export interface WithdrawalAccountBreakdown {
  account_type: AccountType;
  balance_krw: string;
  current_year_contribution_excluded_krw: string;
  prior_year_non_deducted_principal_excluded_krw: string;
  deferred_retirement_income_excluded_krw: string;
  assumed_other_income_tax_base_krw: string;
}

export interface NonPensionWithdrawalEvaluation {
  engine_name: string;
  engine_version: string;
  rule_version: string;
  tax_year: number;
  status: "estimated" | "requires_review";
  calculation_mode:
    | "source_aware_estimate"
    | "simplified_max_other_income_estimate"
    | null;
  total_balance_krw: string | null;
  total_current_year_contribution_excluded_krw: string;
  total_prior_year_non_deducted_principal_excluded_krw: string;
  total_deferred_retirement_income_excluded_krw: string;
  assumed_other_income_tax_base_krw: string | null;
  other_income_rate_percent: string | null;
  estimated_max_other_income_withholding_krw: string | null;
  account_breakdowns: WithdrawalAccountBreakdown[];
  assumptions: string[];
  limitations: string[];
  evidence: SourceChip[];
}

export interface PensionTaxToolResult {
  tax_credit?: PensionTaxCreditEvaluation | null;
  withdrawal?: NonPensionWithdrawalEvaluation | null;
}

// ── /engine/mock-scenario ──
export interface AssetAllocation {
  asset_class_code: string;
  amount_krw: string;
  allocation_percent: string;
  account_count: number;
}

export interface ScenarioEvaluation {
  engine_name: string;
  engine_version: string;
  scenario_code: string;
  data_boundary: string;
  total_amount_krw: string;
  account_evaluations: RiskCapEvaluation[];
  asset_allocations: AssetAllocation[];
  duplicated_asset_classes: string[];
  source: SourceChip;
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

// ── /chat/demo* (backend/app/api/chat.py) ──
export type ChatIntent =
  | "account_rule"
  | "mock_portfolio"
  | "provider_disclosure"
  | "news"
  | "pension_tax"
  | "etf_theme"
  | "educational_portfolio"
  | "out_of_scope";

export type DataBoundary =
  | "verified_knowledge"
  | "official_disclosure"
  | "news_metadata"
  | "news_summary"
  | "mock"
  | "engine"
  | "user_input"
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

export type AnswerBlockKind = "callout" | "paragraph" | "bullets" | "table" | "formula";

export interface AnswerBlock {
  kind: AnswerBlockKind;
  title?: string | null;
  text?: string | null;
  items: string[];
  headers: string[];
  rows: string[][];
}

export interface AnswerSection {
  kind: "fact" | "external_opinion" | "service_explanation" | "limitation";
  title: string;
  content: string;
  evidence_ids: string[];
  blocks?: AnswerBlock[];
}

export interface ChatNewsItem {
  evidence_id: string;
  title: string;
  publisher?: string | null;
  description?: string | null;
  summary_lines?: string[];
  original_url: string;
  published_at?: string | null;
}

export interface BenchmarkDistribution {
  code: string;
  count: number;
}

export interface BenchmarkAccountTypeStat {
  account_type: string;
  account_count: number;
  mean_balance_krw: string;
  mean_monthly_contribution_krw: string;
  mean_risky_asset_ratio_percent: string;
}

export interface BenchmarkSummary {
  data_boundary: "mock";
  source_label: string;
  notice: string;
  user_count: number;
  account_count: number;
  holding_count: number;
  age_groups: BenchmarkDistribution[];
  risk_profiles: BenchmarkDistribution[];
  account_type_stats: BenchmarkAccountTypeStat[];
}

export type VisualizationKind = "asset_allocation" | "risk_cap" | "tax_summary";
export type VisualizationDatumRole = "segment" | "current" | "limit" | "value";

export interface VisualizationDatum {
  label: string;
  value: string | number;
  unit: string;
  role: VisualizationDatumRole;
}

export interface ChatVisualization {
  kind: VisualizationKind;
  title: string;
  description: string;
  data_boundary: DataBoundary;
  evidence_ids: string[];
  items: VisualizationDatum[];
}

export interface CompletedSurveyProfile {
  account_type: AccountType;
  account_types?: AccountType[];
  current_age: number;
  retirement_start_age: number;
  risk_profile: RiskProfile;
  loss_tolerance_percent: string | number;
}

export interface ConversationContext {
  account_type?: AccountType | null;
  scenario_code?: string | null;
  last_intent?: ChatIntent | null;
  survey_profile?: CompletedSurveyProfile | null;
  selected_risk_profile?: RiskProfile | null;
  news?: NewsConversationContext | null;
}

export interface NewsConversationContext {
  news_item_ids: string[];
  focus_news_item_id?: string | null;
  market_region: "all" | "kr" | "us";
  shown_at: string;
}

export interface ChatResponse {
  intent: ChatIntent;
  answer: string;
  data_mode: string;
  narration_mode: string;
  model_name?: string | null;
  /** Claude 내레이터의 검토 과정 요약(새 숫자 감지 시 서버가 생략). */
  narration_reasoning?: string | null;
  salutation?: string | null;
  sections: AnswerSection[];
  news_items: ChatNewsItem[];
  visualizations: ChatVisualization[];
  sources: SourceEvidence[];
  numeric_evidence: NumericEvidence[];
  engine_results: unknown[];
  scenario_evaluation?: ScenarioEvaluation | null;
  pension_tax_result?: PensionTaxToolResult | null;
  educational_portfolio_evaluation?: unknown | null;
  educational_portfolio_evaluations?: unknown[];
  limitations: string[];
  conversation_context?: ConversationContext | null;
}

export interface ScenarioSummary {
  code: string;
  name: string;
  description: string;
  age_band: string;
  risk_profile: string;
  investment_horizon_years: number;
}

export interface ChatCapabilities {
  supported: string[];
  conditional: string[];
  unsupported: string[];
  scenario_codes: string[];
}

// ── authenticated /chat* history ──
export interface DemoUserFinancialContext {
  auth_user_id: string;
  nickname: string;
  representative_age: number;
  customer_context: string;
  scenario_code: string;
  scenario_name: string;
  age_band: string;
  risk_profile: string;
  investment_horizon_years: number;
  tax_year: number;
  income_basis: IncomeBasis;
  income_amount_krw: string;
  dc_balance_krw: string;
  irp_balance_krw: string;
  pension_savings_balance_krw: string;
  total_pension_balance_krw: string;
  irp_contribution_krw: string;
  pension_savings_contribution_krw: string;
  as_of_date: string;
  data_kind: "mock";
  defaulted_fields: string[];
}

export interface PersistedChatResponse {
  persisted: boolean;
  session_id: string | null;
  user_message_id: string | null;
  assistant_message_id: string | null;
  response: ChatResponse;
}

export interface ChatSessionSummary {
  session_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface StoredMessageEvidence {
  document_id: string | null;
  chunk_id: number | null;
  news_item_id: string | null;
  source_locator: string;
  quote_text: string | null;
  rank: number | null;
}

export interface StoredChatMessage {
  message_id: string;
  question_message_id: string | null;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  response: ChatResponse | null;
  model_name: string | null;
  created_at: string;
  evidence: StoredMessageEvidence[];
}
