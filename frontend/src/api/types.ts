/**
 * FastAPI REST 계약 타입 (backend/app/api/*, backend/app/engine/models.py 동기화).
 *
 * 주의: 백엔드의 Decimal 필드는 JSON에서 전부 "문자열"로 직렬화된다.
 * 금액(_krw)·비율(_percent) 타입이 string인 것은 실수가 아니라 계약이다.
 */

export type AccountType = "dc" | "irp" | "pension_savings";

/**
 * Account-link screen display code. `db` is presentation metadata only and
 * must not be passed to the engine's AccountType-based APIs.
 */
export type AccountLinkOptionCode = AccountType | "db";

export interface AccountLinkOption {
  code: AccountLinkOptionCode;
  display_name: string;
  category_label: string;
  diagnosable: boolean;
  description: string | null;
}

export interface AccountLinkOptionsResponse {
  options: AccountLinkOption[];
  notice: string;
  data_boundary: "mock";
}

export interface PensionHoldingSnapshot {
  holding_id: string;
  product_id: string | null;
  instrument_name: string;
  etf_isu_code: string | null;
  asset_class: AssetClass;
  amount_krw: string;
  risk_treatment: RiskTreatment;
  statutory_exception: StatutoryException | null;
}

export interface PensionAccountSnapshot {
  account_id: string;
  account_type: AccountType;
  account_name: string;
  data_kind: "real" | "mock";
  origin: "user_input" | "provider_import" | "synthetic";
  snapshot_id: string;
  as_of_date: string;
  contributed_principal_krw: string | null;
  market_value_krw: string;
  holdings: PensionHoldingSnapshot[];
}

export interface UserPensionPortfolio {
  owner_id: string;
  data_boundary: "real" | "mock" | "mixed" | "unavailable";
  accounts: PensionAccountSnapshot[];
}
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

export interface RebalancingReminderState {
  profile_required: boolean;
  enabled: boolean;
  review_available: boolean;
  risk_profile: RiskProfile | null;
  cadence: { review_interval_months: number; drift_threshold_percent_points: string; rationale: string } | null;
  last_reviewed_at: string | null;
  next_review_at: string | null;
  is_due: boolean;
}
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
export type IsaTransferEligibilityStatus = "none" | "eligible" | "unknown";
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

export interface StrategyPlanningReturnComponent {
  cma_bucket: string;
  target_percent: string;
  cma_percent: string;
}

export interface StrategyPlanningReturnEvaluation {
  strategy_id: string;
  cma_weighted_return_percent: string;
  uncertainty_discount_percent: string;
  net_planning_return_percent: string;
  components: StrategyPlanningReturnComponent[];
  cma_policy_id: string;
  policy_version: string;
  sources: SourceChip[];
  annual_review_required: boolean;
  is_forecast: boolean;
  warnings: string[];
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
  selected_values: string[];
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
  answers: Array<{
    question_code: string;
    selected_value: string;
    selected_label: string;
    selected_score: number;
  }>;
  evidence: SourceChip[];
}

export interface InvestmentProfileSubmission {
  survey: ProfileSurveyInput;
  investment_advice_desired: boolean;
  investor_information_provided: boolean;
}

export interface InvestmentProfileAssessment {
  assessed_at: string;
  total_score: number;
  min_score: number;
  max_score: number;
  score_percent: string;
  risk_profile: RiskProfile;
  engine_name: string;
  engine_version: string;
  rule_version: string;
  provisional: boolean;
  answers: Array<{
    question_code: string;
    selected_value: string;
    selected_label: string;
    selected_score: number;
  }>;
  assessed_on: string;
  valid_until: string;
  is_expired: boolean;
  validity_policy_version: string;
}

export interface InvestmentProfileResponse {
  assessment: InvestmentProfileAssessment | null;
  preferences: {
    investment_advice_desired: boolean;
    investor_information_provided: boolean;
    confirmed_at: string;
    policy_version: string;
  } | null;
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

// ── /engine/pension-calculator ──
export interface PensionCalculatorInput {
  current_age: number;
  contribution_end_age: number;
  monthly_contribution_krw: string;
  current_balance_krw?: string;
  account_type: AccountType;
  risk_profile: RiskProfile;
  strategy_id?: string | null;
  payout_years?: number;
  scenario?: AssumptionScenario;
}

export interface PensionCalculatorCombinedInput {
  current_age: number;
  contribution_end_age: number;
  accounts: Array<{
    account_id: string;
    account_name: string;
    account_type: AccountType;
    current_balance_krw: string;
  }>;
  risk_profile: RiskProfile;
  strategy_id?: string | null;
  payout_years?: number;
  scenario?: AssumptionScenario;
}

export interface PensionCalculatorHeadline {
  total_krw: string;
  total_principal_krw: string;
  total_gain_krw: string;
  monthly_payout_pretax_krw: string;
  monthly_payout_after_tax_krw: string;
  contribution_years: number;
}

export interface PensionCalculatorYear {
  year_index: number;
  age: number;
  cumulative_principal_krw: string;
  cumulative_gain_krw: string;
  balance_krw: string;
}

export interface StrategyPresentation {
  strategy_id: string;
  display_name: string;
  summary: string;
  risk_badge: string;
  character_key: string;
}

export interface PensionCalculatorStrategy {
  strategy_id: string;
  presentation: StrategyPresentation;
  risk_profile: RiskProfile;
  net_annual_return_percent: string;
  growth_percent: string;
  safe_percent: string;
  cash_percent: string;
  within_profile: boolean;
  default_visible: boolean;
}

export interface PensionCalculatorTax {
  withholding_rate_percent_by_year: string[];
  effective_rate_percent: string;
  annual_payout_krw: string;
  exceeds_annual_15m_threshold: boolean;
  deferred_severance_excluded: true;
}

export interface PensionCalculatorAssumption {
  version: string;
  scenario: AssumptionScenario;
  source: SourceChip;
  notice: string;
}

export interface PensionCalculatorEvaluation {
  headline: PensionCalculatorHeadline;
  yearly: PensionCalculatorYear[];
  strategies: PensionCalculatorStrategy[];
  tax: PensionCalculatorTax;
  assumption: PensionCalculatorAssumption;
  warnings: string[];
}

export interface PensionCalculatorPortfolioCmaRequest {
  calculator: PensionCalculatorInput;
  current_holdings: Array<{
    isu_code: string;
    amount_krw: string;
  }>;
}

export interface PensionCalculatorPortfolioCmaEvaluation {
  calculator: PensionCalculatorEvaluation;
  planning_return: PortfolioPlanningEvaluation;
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
  dc_employee_additional_contribution_krw?: string;
  dc_employer_contribution_krw?: string;
  irp_deferred_retirement_income_contribution_krw?: string;
  pension_account_transfer_contribution_krw?: string;
  isa_maturity_transfer_krw?: string;
  isa_transfer_eligibility_status?: IsaTransferEligibilityStatus;
  isa_additional_limit_used_prior_tax_year_krw?: string;
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
  dc_employee_additional_contribution_krw?: string;
  dc_employer_contribution_krw?: string;
  irp_deferred_retirement_income_contribution_krw?: string;
  pension_account_transfer_contribution_krw?: string;
  isa_maturity_transfer_krw?: string;
  isa_transfer_eligibility_status?: IsaTransferEligibilityStatus;
  isa_additional_limit_used_prior_tax_year_krw?: string;
  withdrawal_reason: WithdrawalReason;
  irp_deferred_income_status: IrpDeferredIncomeStatus;
  irp_deferred_retirement_income_krw?: string | null;
}

export interface TaxCreditRateScenario {
  label: string;
  income_tax_rate_percent: string;
  local_inclusive_display_rate_percent: string;
  income_tax_credit_krw: string;
  estimated_total_tax_reduction_effect_krw: string;
  /** @deprecated Use estimated_total_tax_reduction_effect_krw. */
  estimated_tax_credit_krw: string;
}

export interface PensionTaxCreditEvaluation {
  engine_name: string;
  engine_version: string;
  rule_version: string;
  tax_year: number;
  pension_savings_contribution_krw: string;
  irp_contribution_krw: string;
  dc_employee_additional_contribution_krw: string;
  retirement_personal_contribution_krw: string;
  dc_employer_contribution_krw: string;
  irp_deferred_retirement_income_contribution_krw: string;
  pension_account_transfer_contribution_krw: string;
  total_excluded_contribution_krw: string;
  isa_maturity_transfer_krw: string;
  isa_transfer_eligibility_status: IsaTransferEligibilityStatus;
  isa_transfer_requires_review: boolean;
  isa_additional_limit_used_prior_tax_year_krw: string;
  isa_additional_credit_limit_krw: string;
  pension_savings_eligible_contribution_krw: string;
  irp_eligible_contribution_krw: string;
  dc_employee_eligible_contribution_krw: string;
  retirement_eligible_contribution_krw: string;
  regular_eligible_contribution_krw: string;
  total_eligible_contribution_krw: string;
  total_credit_limit_krw: string;
  unused_combined_limit_krw: string;
  unused_total_limit_krw: string;
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

export interface DemoHeroHolding extends HoldingInput {
  instrument_name: string;
  asset_class_code: AssetClass;
  etf_isu_code?: string | null;
}

export interface DemoHeroAccount {
  account_id: string;
  account_type: AccountType;
  label: string;
  holdings: DemoHeroHolding[];
}

export interface DemoHeroRiskSummary {
  dominant_asset_class: AssetClass;
  dominant_asset_percent: string;
  general_risky_asset_percent: string;
  stress_scenario_code: "equity_drawdown";
  estimated_stress_loss_percent: string;
  is_forecast: false;
  requires_rebalancing_review: boolean;
  policy_label: string;
}

export interface DemoHeroPastPerformance {
  metric_code: string;
  label: string;
  trailing_12m_return_pct: string;
  period_start: string;
  period_end: string;
  calculation_basis: string;
  source_label: string;
  data_kind: "MOCK";
  is_forecast: false;
  official_ranking_metric: false;
}

export interface DemoHeroLikeSummary {
  metric_code: string;
  label: string;
  count: number;
  as_of_date: string;
  data_kind: "MOCK";
  is_synthetic: true;
  performance_based: false;
}

export interface DemoHeroPortfolio {
  nickname: string;
  representative_age: number;
  customer_context: string;
  is_demo_login_candidate: boolean;
  scenario_code: string;
  scenario_name: string;
  age_band: string;
  risk_profile: string;
  investment_horizon_years: number;
  total_amount_krw: string;
  accounts: DemoHeroAccount[];
  asset_allocations: AssetAllocation[];
  duplicated_asset_classes: string[];
  risk_summary: DemoHeroRiskSummary;
  past_performance: DemoHeroPastPerformance;
  like_summary: DemoHeroLikeSummary;
  data_boundary: "mock";
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

// ── /chat (backend/app/api/chat.py) ──
export type ChatIntent =
  | "account_rule"
  | "mock_portfolio"
  | "provider_disclosure"
  | "news"
  | "pension_tax"
  | "etf_theme"
  | "etf_distribution"
  | "educational_portfolio"
  | "macro_evidence"
  | "out_of_scope";

export type DataBoundary =
  | "verified_knowledge"
  | "official_disclosure"
  | "official_statistics"
  | "news_metadata"
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

export interface RegimeHorizonOutcome {
  horizon_months: number;
  start_date: string;
  end_date: string;
  total_return_percent: string | number;
  maximum_drawdown_percent: string | number;
}

export interface RegimeOutcomeGap {
  horizon_months: number;
  reason: string;
}

export interface EtfPostRegimeOutcome {
  isu_code: string;
  isu_name: string;
  history_source?: string | null;
  source?: SourceChip | null;
  history_start?: string | null;
  history_end?: string | null;
  horizons: RegimeHorizonOutcome[];
  gaps: RegimeOutcomeGap[];
}

export interface MacroRegimeOutcomeGroup {
  regime_period: string;
  distance: string | number;
  etfs: EtfPostRegimeOutcome[];
}

export interface MacroRegimeEtfOutcomeEvaluation {
  engine_name: string;
  engine_version: string;
  policy_version: string;
  outcome_start_rule: string;
  boundary_lag_days: number;
  groups: MacroRegimeOutcomeGroup[];
  is_forecast: boolean;
  planning_return_input: boolean;
  allocation_weight_input: boolean;
  rebalancing_trigger_input: boolean;
  limitations: string[];
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
  description?: string | null;
  summary_lines?: string[];
  original_url: string;
  published_at?: string | null;
}

export type VisualizationKind = "asset_allocation" | "risk_cap" | "tax_summary" | "sleeve_allocation" | "stress_scenarios" | "disclosure_comparison" | "accumulation_projection";
export type VisualizationDatumRole = "segment" | "current" | "limit" | "value";

export interface VisualizationDatum {
  label: string;
  value: string | number;
  unit: string;
  role: VisualizationDatumRole;
}

export interface VisualizationPoint {
  position: number;
  label: string;
  value: string;
}

export interface VisualizationSeries {
  label: string;
  unit: string;
  points: VisualizationPoint[];
}

export interface ChatVisualization {
  kind: VisualizationKind;
  title: string;
  description: string;
  data_boundary: DataBoundary;
  evidence_ids: string[];
  items: VisualizationDatum[];
  series: VisualizationSeries[];
}

export interface SuggestedFollowUp {
  follow_up_id: string;
  label: string;
  message: string;
}

export type ChatCardCondition = "requires_scenario" | "requires_survey" | "requires_auth";

export interface ChatCard {
  card_id: string;
  title: string;
  message: string;
  intent: ChatIntent;
  conditions: ChatCardCondition[];
  priority: number;
  preview: string | null;
}

export interface ChatCardCatalog {
  cards: ChatCard[];
}

export interface CompletedSurveyProfile {
  account_type: AccountType;
  account_types?: AccountType[];
  current_age: number;
  retirement_start_age: number;
  risk_profile: RiskProfile;
  loss_tolerance_percent: string | number;
}

export interface CurrentHoldingInput {
  isu_code: string;
  amount_krw: string;
  asset_class?: AssetClass | null;
}

export interface EducationalPortfolioInput {
  account_type: AccountType;
  age: number;
  retirement_start_age: number;
  risk_profile: RiskProfile;
  loss_tolerance_percent: string | number;
  max_etfs?: number;
  current_holdings: CurrentHoldingInput[];
  new_contribution_krw: string;
}

export interface EducationalEtfCandidate {
  isu_code: string;
  isu_name: string;
  sleeve: string;
  target_percent: string;
  quality: Record<string, string>;
  region?: string | null;
  strategy?: string | null;
  max_correlation_with_selected: string | null;
  price_history_source: string;
  account_eligibility: Record<string, unknown>;
  reasons: string[];
}

export interface RebalancingSleeveGuidance {
  sleeve: string;
  target_percent: string;
  current_percent: string;
  projected_percent_after_contribution: string;
  drift_before_percent_points: string;
  drift_after_percent_points: string;
  contribution_example_krw: string;
  status: string;
}

export interface RebalancingGuidance {
  status: string;
  drift_threshold_percent_points: string;
  cadence: {
    review_interval_months: number;
    drift_threshold_percent_points: string;
    rationale: string;
  };
  current_total_krw: string;
  new_contribution_krw: string;
  projected_total_krw: string;
  unclassified_holding_amount_krw: string;
  contribution_first: boolean;
  sell_instruction_produced: boolean;
  sleeves: RebalancingSleeveGuidance[];
  warnings: string[];
}

export interface StressScenarioResult {
  scenario_code: string;
  estimated_loss_percent: string;
  sleeve_shocks_percent: Record<string, string>;
  is_forecast: boolean;
}

export type StressLossPolicyStatus = "not_evaluated" | "within_user_limit" | "review_required";

export interface PortfolioRiskEvaluation {
  engine_name: string;
  engine_version: string;
  policy_version: string;
  usage_label: string;
  status: string;
  observation_count: number;
  observation_start: string | null;
  observation_end: string | null;
  annualized_volatility_percent: string | null;
  annualized_downside_deviation_percent: string | null;
  maximum_drawdown_percent: string | null;
  historical_95pct_one_day_loss_percent: string | null;
  worst_daily_return_percent: string | null;
  historical_return_used_for_risk_only: boolean;
  is_return_forecast: boolean;
  stress_scenarios: StressScenarioResult[];
  stress_loss_limit_percent: string | null;
  worst_stress_loss_percent: string;
  stress_loss_policy_status: StressLossPolicyStatus;
  sources: Array<{
    label: string;
    reference: string;
    as_of: string;
  }>;
  warnings: string[];
}

export interface PortfolioPlanningComponent {
  isu_code: string;
  isu_name: string;
  sleeve: string;
  target_percent: string;
  cma_assumption_code: string;
  cma_percent: string;
  uncertainty_discount_percent: string;
  annual_cost_drag_percent: string;
  gross_planning_return_percent: string;
  net_planning_return_percent: string;
  proxy_used: boolean;
  warnings: string[];
}

export interface PortfolioPlanningEvaluation {
  engine_name: string;
  engine_version: string;
  policy_version: string;
  cma_policy_id: string;
  cma_policy_status: string;
  usage_label: string;
  retirement_start_age: number;
  portfolio_horizon_years: number;
  cma_source_horizon_min_years: number;
  cma_source_horizon_max_years: number;
  annual_review_required: boolean;
  coverage_weight_percent: string;
  gross_planning_return_percent: string | null;
  net_planning_return_percent: string | null;
  conservative_planning_return_percent: string | null;
  base_planning_return_percent: string | null;
  is_forecast: boolean;
  historical_performance_used: boolean;
  risk_adjustment_included: boolean;
  components: PortfolioPlanningComponent[];
  sources: SourceChip[];
  warnings: string[];
}

export interface EducationalPortfolioEvaluation {
  engine_name: string;
  engine_version: string;
  policy_version: string;
  usage_label: string;
  evaluated_input: EducationalPortfolioInput;
  strategy_label: string;
  retirement_start_age: number;
  planning_horizon_years: number;
  horizon_to_age_55_years: number;
  horizon_to_age_60_years: number;
  raw_risk_target_percent: string;
  final_general_risk_target_percent: string;
  account_risk_cap_percent: string | null;
  account_cap_binding: boolean;
  loss_tolerance_binding: boolean;
  stress_loss_proxy_percent: string;
  target_sleeves: Array<{
    sleeve: string;
    target_percent: string;
    risk_treatment: string;
    role: string;
  }>;
  candidates: EducationalEtfCandidate[];
  portfolio_risk: PortfolioRiskEvaluation;
  planning_return: PortfolioPlanningEvaluation;
  current_holdings_planning_return?: PortfolioPlanningEvaluation | null;
  rebalancing: RebalancingGuidance;
  sources: SourceEvidence[];
  warnings: string[];
}

export type MarketRegion = "all" | "kr" | "us";

export interface NewsConversationContext {
  news_item_ids: string[];
  focus_news_item_id?: string | null;
  market_region: MarketRegion;
  shown_at: string;
}

export interface ReferentItem {
  label: string;
  ref: string;
}

export interface ReferentList {
  intent: ChatIntent;
  topic?: string | null;
  items: ReferentItem[];
}

export interface ConversationContext {
  account_type?: AccountType | null;
  scenario_code?: string | null;
  last_intent?: ChatIntent | null;
  survey_profile?: CompletedSurveyProfile | null;
  selected_risk_profile?: RiskProfile | null;
  news?: NewsConversationContext | null;
  referents?: ReferentList | null;
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
  suggested_follow_ups: SuggestedFollowUp[];
  sources: SourceEvidence[];
  numeric_evidence: NumericEvidence[];
  engine_results: unknown[];
  scenario_evaluation?: ScenarioEvaluation | null;
  pension_tax_result?: PensionTaxToolResult | null;
  educational_portfolio_evaluation?: EducationalPortfolioEvaluation | null;
  educational_portfolio_evaluations?: EducationalPortfolioEvaluation[];
  macro_regime_etf_outcomes?: MacroRegimeEtfOutcomeEvaluation | null;
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
  asset_classes: string[];
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
