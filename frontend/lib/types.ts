/**
 * Wire types mirroring the FastAPI response schemas.
 *
 * Kept hand-written rather than generated so the frontend has one obvious
 * place to look, and so a backend change that breaks the contract shows up as
 * a TypeScript error rather than a runtime undefined.
 */

export type RemoteStatus = "remote" | "hybrid" | "onsite" | "unspecified";

export type RecommendedAction =
  | "STRONGLY_PURSUE"
  | "PURSUE"
  | "WORTH_A_CALL"
  | "MAYBE"
  | "LOW_PRIORITY"
  | "REJECT";

export type DecisionType =
  | "pursue"
  | "maybe"
  | "reject"
  | "ignore"
  | "responded"
  | "interviewed"
  | "offer"
  | "declined_offer"
  | "accepted_offer";

export type MessageStatus =
  | "new"
  | "analyzed"
  | "draft_generated"
  | "approved"
  | "edited"
  | "rejected"
  | "ignored";

export type DraftTone = "professional" | "warm" | "direct" | "humorous";

export type ProofabilityTier = "already_demonstrated" | "proofable" | "hard_gate";

export interface ScoreReason {
  text: string;
  impact: number;
  kind: "positive" | "negative" | "neutral" | "missing";
}

export interface DimensionScore {
  name: string;
  score: number;
  reasons: ScoreReason[];
  details: Record<string, unknown>;
}

export interface Gap {
  requirement: string;
  tier: ProofabilityTier;
  detail: string;
  proofability: number;
  suggested_project: string | null;
  interview_readiness: string | null;
  learning_difficulty: string | null;
}

export interface ProveItAnalysis {
  already_demonstrated: { skill: string; category: string; required: boolean }[];
  learnable: {
    requirement: string;
    learning_difficulty: string | null;
    suggested_project: string | null;
    interview_readiness: string | null;
    how_to_demonstrate: string;
    proofability: number;
  }[];
  hard_gates: { requirement: string; detail: string; why_hard: string }[];
  summary: string;
}

export interface Explanation {
  headline: string[];
  dimensions: Record<string, DimensionScore>;
  weights: Record<string, number>;
  overall_capped_by_hard_gate: boolean;
  prove_it: ProveItAnalysis;
}

export interface OpportunityScore {
  id: string;
  opportunity_id: string;
  candidate_id: string;
  fit_score: number;
  career_capital_score: number;
  proofability_score: number;
  compensation_score: number;
  lifestyle_score: number;
  upside_score: number;
  risk_score: number;
  overall_score: number;
  recommended_action: RecommendedAction;
  explanation: Explanation;
  missing_requirements: Gap[];
  matched_strengths: string[];
  hard_gates: Gap[];
  proofable_gaps: Gap[];
  weights_used: Record<string, number>;
  generated_at: string;
}

export interface JobOpportunity {
  id: string;
  company: string | null;
  title: string | null;
  location: string | null;
  remote_status: RemoteStatus;
  employment_type: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  bonus: string | null;
  commission_ote: number | null;
  equity: boolean | null;
  equity_percent_min: number | null;
  equity_percent_max: number | null;
  equity_notes: string | null;
  hours: number | null;
  travel: number | null;
  relocation_required: boolean | null;
  on_call: boolean | null;
  nights_weekends: boolean | null;
  shift_work: boolean | null;
  security_clearance: string;
  polygraph_requirement: string;
  citizenship_requirement: string | null;
  required_skills: string[];
  preferred_skills: string[];
  required_years_experience: number | null;
  preferred_years_experience: number | null;
  education_requirements: string[];
  certifications: string[];
  management_responsibility: boolean | null;
  company_stage: string | null;
  estimated_company_size: string | null;
  industry: string | null;
  customer_type: string | null;
  government_or_commercial: string | null;
  revenue_responsibility: boolean | null;
  customer_facing_intensity: string | null;
  technical_depth: string | null;
  research_intensity: string | null;
  ownership_level: string | null;
  job_family: string | null;
  job_description: string | null;
  source_url: string | null;
  recruiter_name: string | null;
  recruiter_contact: string | null;
  source_type: string;
  extracted_at: string;
  confidence: Record<string, string>;
  extraction_method: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  /** slug -> display label, supplied by the backend ontology. */
  skill_labels: Record<string, string>;
}

/** One curated demo scenario from data/samples. */
export interface ExampleCase {
  id: string;
  title: string;
  channel: string;
  /** What this case is here to show. */
  demonstrates: string;
  /** The outcome the system is expected to reach. */
  expect: string;
  raw_text: string;
}

export interface ExampleCasesResponse {
  examples: ExampleCase[];
  note: string;
}

export interface MissingField {
  field: string;
  label: string;
  priority: number;
  question: string;
  rationale: string;
}

export interface Draft {
  intent: string;
  tone: DraftTone;
  subject: string;
  body: string;
  questions_asked: string[];
  generated_by: string;
  message_id: string | null;
  missing_information: MissingField[];
}

export interface ResumeMatchEntry {
  resume_id: string;
  title: string;
  score: number;
  matched_skills: string[];
  missing_keywords: string[];
  highlight: string[];
  de_emphasize: string[];
  rationale: string[];
  summary: string;
}

export interface ResumeMatchResult {
  best: ResumeMatchEntry | null;
  ranked: ResumeMatchEntry[];
  semantic_enabled: boolean;
}

export interface AnalyzeResponse {
  opportunity: JobOpportunity;
  score: OpportunityScore;
  missing_information: MissingField[];
  draft: Draft | null;
  resume_match: ResumeMatchResult | null;
  prove_it: ProveItAnalysis;
  saved: boolean;
}

export interface DashboardRow {
  opportunity_id: string;
  company: string | null;
  title: string | null;
  location: string | null;
  remote_status: RemoteStatus;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  job_family: string | null;
  overall_score: number;
  fit_score: number;
  career_capital_score: number;
  proofability_score: number;
  compensation_score: number;
  lifestyle_score: number;
  upside_score: number;
  risk_score: number;
  recommended_action: RecommendedAction;
  hard_gate_count: number;
  decision: DecisionType | null;
  message_status: MessageStatus | null;
  scored_at: string | null;
  created_at: string;
}

export interface CandidateProfile {
  id: string;
  name: string;
  summary: string | null;
  current_location: string | null;
  citizenship: string | null;
  work_authorization: string | null;
  clearance_level: string;
  polygraph_type: string;
  languages: string[];
  education: string[];
  certifications: string[];
  technical_skills: string[];
  domain_skills: string[];
  years_experience_by_skill: Record<string, number>;
  target_roles: string[];
  preferred_locations: string[];
  remote_preference: string;
  willingness_to_travel: number;
  minimum_salary: number | null;
  target_salary: number | null;
  desired_equity: string | null;
  preferred_weekly_hours: number | null;
  lifestyle_preferences: Record<string, unknown>;
  industries_of_interest: string[];
  industries_to_avoid: string[];
  career_goals: string[];
  risk_tolerance: string;
  notes: string | null;
  scoring_config: Record<string, unknown>;
  proofable_skills: string[];
  created_at: string;
  updated_at: string;
}

export interface DashboardResponse {
  rows: DashboardRow[];
  total: number;
  candidate: CandidateProfile | null;
  stats: {
    count: number;
    by_action: Record<string, number>;
    average_overall: number;
    hard_gated: number;
    median_salary_max: number | null;
  };
}

export interface RecruiterMessage {
  id: string;
  opportunity_id: string;
  raw_text: string;
  channel: string;
  sender: string | null;
  timestamp: string;
  extracted_missing_information: MissingField[];
  response_draft: string | null;
  approved_response: string | null;
  status: MessageStatus;
}

export interface UserDecisionRecord {
  id: string;
  decision: DecisionType;
  reason: string | null;
  edited_response: string | null;
  outcome_metadata: Record<string, unknown>;
  timestamp: string;
}

export interface JobDetail {
  opportunity: JobOpportunity;
  score: OpportunityScore | null;
  messages: RecruiterMessage[];
  decisions: UserDecisionRecord[];
  missing_information: MissingField[];
}

export interface ResumeDocument {
  id: string;
  candidate_id: string;
  title: string;
  raw_text: string;
  parsed_sections: Record<string, unknown>;
  skills: string[];
  target_families: string[];
  active: boolean;
  created_at: string;
  has_embedding: boolean;
}

export interface EquityScenario {
  exit_valuation: number;
  gross_value: number;
  net_value: number;
  label: string;
}

export interface EquityAnalysis {
  equity_percent: number;
  dilution_percent: number;
  post_dilution_percent: number;
  strike_price: number | null;
  shares: number | null;
  current_valuation: number | null;
  current_paper_value: number | null;
  scenarios: EquityScenario[];
  disclaimer: string;
}

export interface ClearanceJobsKeywords {
  keywords: string;
  source: string;
}

export interface ClearanceJobsImportResult {
  saved: number;
  below_threshold: number;
  duplicates_skipped: number;
  total_results: number;
}
