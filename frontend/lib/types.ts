export type Band = "excellent" | "good" | "moderate" | "low";
export type Eligibility = "eligible" | "partially_eligible" | "not_eligible";
export type ApplicationStatus =
  | "interested"
  | "applied"
  | "assessment"
  | "interview"
  | "rejected"
  | "offer";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  alert_enabled: boolean;
  alert_min_match: number;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Job {
  id: string;
  source: string;
  title: string;
  company: string;
  description: string;
  required_skills: string[];
  preferred_skills: string[];
  all_skills: string[];
  education_requirement: Record<string, unknown>;
  experience_min_years: number | null;
  experience_max_years: number | null;
  experience_level: string;
  location_raw: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  is_remote: boolean;
  work_mode: string;
  job_type: string;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  salary_raw: string | null;
  posted_at: string | null;
  deadline_at: string | null;
  apply_url: string;
  also_seen_on: string[];
  first_seen_at: string;
}

export interface CategoryScore {
  raw: number;
  weight: number;
  configured_weight?: number;
  contribution: number;
  label: string;
}

export interface MatchSummary {
  score: number;
  band: Band;
  eligibility_status: Eligibility;
  eligibility_multiplier: number;
  matched_skills: string[];
  missing_skills: string[];
  missing_mandatory_skills: string[];
  category_scores: Record<string, CategoryScore>;
  computed_at: string;
}

export interface JobWithMatch {
  job: Job;
  match: MatchSummary | null;
  is_saved: boolean;
  application_status: ApplicationStatus | null;
}

export interface CalculationStep {
  category: string;
  label: string;
  subscore: number;
  weight: number;
  configured_weight?: number;
  contribution_points: number;
}

export interface Calculation {
  formula: string;
  weighted_sum: number;
  weight_total: number;
  eligibility_multiplier: number;
  pre_gate_percentage: number;
  final_percentage: number;
  steps: CalculationStep[];
  gate_adjustments: { reason: string; multiplier: number | null }[];
  semantic_cosine_raw: number;
  level_fit_detail: Record<string, unknown>;
  job_skills_parsed?: number;
  skill_confidence?: number;
  weight_adjustments?: {
    category: string;
    configured_weight: number;
    effective_weight: number;
    reason: string;
  }[];
}

export interface MatchedSkill {
  skill: string;
  kind: string;
  via: string;
  credit: number;
  candidate_skill?: string;
}

export interface MissingSkill {
  skill: string;
  kind: string;
  category?: string;
}

export interface Blocker {
  type: string;
  severity: string;
  message: string;
  skills?: string[];
  multiplier_applied?: number;
}

export interface MatchAnalysis {
  job: Job;
  score: number;
  band: Band;
  band_label: string;
  eligibility_status: Eligibility;
  eligibility_multiplier: number;
  semantic_similarity: number;
  category_scores: Record<string, CategoryScore>;
  calculation: Calculation;
  eligibility_checks: { check: string; passed: boolean; detail: string }[];
  eligibility_warnings: { type: string; message: string }[];
  matched_skills: MatchedSkill[];
  missing_skills: MissingSkill[];
  missing_mandatory_skills: string[];
  extra_skills: string[];
  relevant_projects: RelevantItem[];
  relevant_experience: RelevantItem[];
  reasons: string[];
  blockers: Blocker[];
  recommendations: string[];
  explanation: string | null;
  explanation_source: string;
  weights: Record<string, number>;
  category_descriptions: Record<string, string>;
  computed_at: string;
}

export interface RelevantItem {
  name: string;
  relevance: number;
  weighted_relevance: number;
  semantic: number;
  shared_technologies: string[];
  duration_months: number | null;
  kind: string | null;
  company: string | null;
}

export interface Facet {
  value: string;
  count: number;
}

export interface JobList {
  items: JobWithMatch[];
  total: number;
  page: number;
  page_size: number;
  facets: {
    sources: Facet[];
    work_modes: Facet[];
    job_types: Facet[];
    experience_levels: Facet[];
    cities: Facet[];
    countries: Facet[];
    companies: Facet[];
    skills: Facet[];
  };
}

export interface DiscoveryRun {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "partial";
  progress: number;
  sources_attempted: string[];
  sources_succeeded: string[];
  sources_failed: { source: string; error: string }[];
  queries: string[];
  jobs_fetched: number;
  jobs_new: number;
  jobs_duplicate: number;
  matches_computed: number;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface DashboardSummary {
  total_jobs: number;
  excellent: number;
  good: number;
  moderate: number;
  low: number;
  saved: number;
  tracked: number;
  eligible: number;
  partially_eligible: number;
  not_eligible: number;
  sources_live: string[];
  sources_unavailable: string[];
  last_discovery: DiscoveryRun | null;
  unread_notifications: number;
  has_profile: boolean;
  top_matches: JobWithMatch[];
}

export interface SourceInfo {
  key: string;
  display_name: string;
  kind: "public_api" | "licensed_api" | "gated";
  requires_credentials: boolean;
  credential_env_vars: string[];
  available: boolean;
  reason: string;
  missing_env: string[];
  notes: string;
  is_enabled: boolean;
  last_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  jobs_last_run: number;
}

export interface EducationEntry {
  degree?: string | null;
  level?: number | null;
  level_label?: string | null;
  field?: string | null;
  institution?: string | null;
  start?: string | null;
  end?: string | null;
  ongoing?: boolean;
  score?: string | null;
}

export interface ProjectEntry {
  name?: string;
  description?: string;
  tech?: string[];
  highlights?: string[];
  links?: string[];
}

export interface ExperienceEntry {
  role?: string;
  company?: string | null;
  kind?: string;
  start?: string | null;
  end?: string | null;
  months?: number;
  description?: string;
  tech?: string[];
}

export interface CertificationEntry {
  name?: string;
  issuer?: string | null;
  year?: string | null;
}

export interface ParsedPayload {
  contact: {
    name: string | null;
    email: string | null;
    phone: string | null;
    location: string | null;
    links: string[];
  };
  education: EducationEntry[];
  skills: {
    technical: string[];
    soft: string[];
    raw?: string[];
    unrecognised?: string[];
  };
  languages: string[];
  frameworks: string[];
  tools: string[];
  projects: ProjectEntry[];
  experience: ExperienceEntry[];
  certifications: CertificationEntry[];
  achievements: string[];
}

export interface SeniorityInfo {
  seniority: string;
  label: string;
  signals: { signal: string; detail: string }[];
  total_experience_months: number;
  internship_months: number;
  graduation_year: number | null;
  highest_degree_level: number;
  field_of_study: string | null;
  all_labels: Record<string, string>;
}

export interface ParsedResume {
  resume_id: string;
  status: string;
  structuring_mode: string;
  payload: ParsedPayload;
  field_confidence: Record<string, number>;
  warnings: string[];
  derived: {
    total_experience_months: number;
    internship_months: number;
    highest_degree_level: number;
    field_of_study: string | null;
    graduation_year: number | null;
    seniority: string;
    seniority_signals: { signal: string; detail: string }[];
  };
  edited_by_user: boolean;
}

export interface Profile {
  id: string;
  resume_id: string | null;
  revision: number;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  links: string[];
  education: EducationEntry[];
  skills: string[];
  programming_languages: string[];
  frameworks: string[];
  tools: string[];
  projects: ProjectEntry[];
  experience: ExperienceEntry[];
  certifications: CertificationEntry[];
  achievements: string[];
  total_experience_months: number;
  internship_months: number;
  highest_degree_level: number;
  field_of_study: string | null;
  graduation_year: number | null;
  seniority: string;
  seniority_signals: { signal: string; detail: string }[];
  embedding_model: string | null;
  created_at: string;
  updated_at: string;
}

export interface SavedJob {
  id: string;
  collection: string;
  notes: string | null;
  created_at: string;
  job: Job;
  match: MatchSummary | null;
}

export interface ApplicationEvent {
  id: string;
  from_status: string | null;
  to_status: string;
  note: string | null;
  created_at: string;
}

export interface Application {
  id: string;
  status: ApplicationStatus;
  notes: string | null;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
  job: Job;
  match: MatchSummary | null;
  events: ApplicationEvent[];
}

export interface ApplicationBoard {
  columns: Record<ApplicationStatus, Application[]>;
  counts: Record<ApplicationStatus, number>;
  statuses: ApplicationStatus[];
}

export interface SkillGapItem {
  skill: string;
  category: string;
  jobs_requiring: number;
  jobs_requiring_as_mandatory: number;
  demand_percentage: number;
  mandatory_ratio: number;
  estimated_score_lift: number;
  priority_score: number;
  example_jobs: { job_id: string; title: string; company: string; score: number }[];
  builds_on: string[];
}

export interface SkillGap {
  total_jobs_analysed: number;
  gaps: SkillGapItem[];
  learn_first: {
    rank: number;
    skill: string;
    reason: string;
    estimated_score_lift: number;
  }[];
  strengths: {
    skill: string;
    jobs_requiring: number;
    demand_percentage: number;
    category: string;
  }[];
  message: string | null;
}

export interface AlternativeRole {
  role_key: string;
  title: string;
  family: string;
  fit: number;
  blurb: string;
  matched_skills: string[];
  transferable_skills: { required: string; via: string }[];
  missing_core_skills: string[];
  missing_supporting_skills: string[];
  search_terms: string[];
  levels: string[];
  why: string;
  skills_to_add: string[];
  sample_jobs: {
    job_id: string;
    title: string;
    company: string;
    source: string;
    score: number;
    band: Band;
  }[];
  open_job_count: number;
}

export interface ResumeFeedback {
  score: number;
  suggestions: {
    section: string;
    severity: "high" | "medium" | "low";
    title: string;
    detail: string;
  }[];
  missing_keywords: {
    keyword: string;
    job_count: number;
    frequency_percentage: number;
    mandatory_count: number;
  }[];
  section_coverage: Record<string, boolean>;
  rewrites: {
    available: boolean;
    reason: string | null;
    rewrites: {
      name: string;
      original: string;
      bullets: string[];
      note: string;
    }[];
  } | null;
}

export interface Notification {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  payload: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
}

export interface Weights {
  weights: Record<string, number>;
  defaults: Record<string, number>;
  labels: Record<string, string>;
  descriptions: Record<string, string>;
  hash: string;
}

export interface Health {
  status: string;
  database: string;
  embedding_backend: string;
  llm_provider: string;
  task_backend: string;
  sources_live: string[];
  sources_unavailable: string[];
  jobs_indexed: number;
}
