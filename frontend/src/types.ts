export interface Notebook {
  id: string
  title: string
  updatedAt: string
  sourceCount: number
}

export interface Source {
  id: string
  type: 'pdf' | 'docx' | 'image' | 'url' | 'text'
  name: string
}

export interface NotebookDetail {
  id: string
  title: string
  updatedAt: string
  sources: Source[]
  documentation: string | null
  summary: string | null
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
}

export interface EvidenceItem {
  source_type: 'patient_document' | 'rag_knowledge_base' | 'pubmed' | 'clinical_guideline'
  source_id: string
  evidence_grade: 'systematic_review' | 'rct' | 'cohort_study' | 'case_control' | 'case_report' | 'expert_consensus' | 'patient_reported'
  finding: string
}

export interface PossibleCondition {
  name: string
  icd11_code: string
  epidemiological_prior: string
  posterior_likelihood: 'high' | 'medium' | 'low' | 'very_low'
  likelihood_rationale: string
  supporting_evidence: EvidenceItem[]
  refuting_evidence: EvidenceItem[]
  unconfirmed_hallmark_symptoms: string[]
}

export interface RedFlag {
  symptom: string
  associated_condition: string
  clinical_decision_rule?: string
  action: string
}

export interface RecommendedTest {
  test: string
  diagnostic_value: string
  targets_condition: string
  priority: 'stat' | 'urgent' | 'routine'
}

export interface PubMedResult {
  id: string
  title: string
  source: string
  pub_date: string
  abstract: string
}

export interface ClinicalAnalysis {
  keywords: string[]
  pubmed_results: PubMedResult[]
  symptom_analysis: {
    possible_conditions: PossibleCondition[]
    next_best_discriminator: string
    red_flags: RedFlag[]
    recommended_tests: RecommendedTest[]
  }
  query_response: string
  confidence: number
}

export interface AddSourceData {
  type: 'file' | 'url' | 'text'
  files?: File[]
  urls?: string
  text?: string
  anonymize?: boolean
}

export interface DrugMention {
  name_as_mentioned: string
  generic_name: string
  drug_class: string
  dosage: string
  duration: string
  candidate_names: string[]
  rxcui?: string
}

export interface PICOResult {
  population: string | null
  intervention: string | null
  comparison: string | null
  outcome: string | null
  evidence_quality: string
  key_findings: string | null
  supporting_pmids: string[]
}

export interface DrugInteraction {
  drug1: string
  drug2: string
  drug1_rxcui: string | null
  drug2_rxcui: string | null
  interaction_found: boolean
  severity: string
  rxnorm_description: string | null
  rxnorm_source: string | null
  openfda_warnings: string | null
  openfda_boxed_warning: string | null
  adverse_event_count: number | null
  pico: PICOResult | null
  pubmed_abstracts: PubMedResult[]
}

export interface InteractionSource {
  label: string
  url: string
  type: string
  pmid?: string
}

// ── ICD-11 ───────────────────────────────────────────────────────────────────

export interface ICD11TreeNode {
  entity_id: string
  code: string
  title: string
  has_children: boolean
  ancestors?: { entity_id: string; code: string; title: string }[]
  children: ICD11TreeNode[]
  browser_url?: string
}

export interface ICD11Match {
  code: string
  title: string
  tree?: ICD11TreeNode | null
}

export interface ICD11Result {
  keywords: string[]
  search_terms: string[]
  icd11_results: ICD11Match[]
}

export interface DrugInteractionResult {
  drugs_extracted: { drugs_mentioned: DrugMention[] }
  brand_molecule_map: Record<string, string>
  pseudoscience_flags: unknown[]
  verified_drugs: DrugMention[]
  interaction_results: DrugInteraction[]
  all_sources: InteractionSource[]
  query_response: string
  confidence: number
}

// ── Literature Review ─────────────────────────────────────────────────────────

export interface GradedArticle {
  id: string
  title: string
  source: string
  pub_date: string
  abstract: string
  pub_types: string[]
  authors: string[]
  study_type: string
  evidence_level: string
  grade: 'A' | 'B' | 'C' | 'D'
  sample_size: number | null
  bias_flags: string[]
  summary: string
}

export interface LiteratureReviewResult {
  keywords: string[]
  search_queries: { pubmed: { primary_query: string; fallback_query: string; filters: string[] } }
  articles: GradedArticle[]
}

// ── Risk Analysis ─────────────────────────────────────────────────────────────

export interface RiskCriterion {
  criterion: string
  points_possible: number | null
  points_awarded: number | null
  status: string
  evidence: string | null
}

export interface ScoreResult {
  score: number | null
  max_score: number
  risk_level: string
  criteria: RiskCriterion[]
  missing_parameters: string[]
  // score-specific
  probability?: string
  recommendation?: string
  annual_stroke_risk?: string
  interpretation?: string
  '3_month_mortality'?: string
  meld_na?: number
}

export interface RiskAnalysisResult {
  keywords: string[]
  scores: {
    wells_dvt: ScoreResult
    cha2ds2_vasc: ScoreResult
    qsofa: ScoreResult
    meld: ScoreResult
  }
}

// ── Rare Disease ──────────────────────────────────────────────────────────────

export interface MappedSymptom {
  symptom: string
  hpo_id: string | null
  hpo_name: string | null
}

export interface MatchedSymptom {
  symptom: string
  hpo_id: string
  hpo_name: string
}

export interface RareDisease {
  orpha_code: string
  name: string
  matched_hpo_count: number
  total_queried: number
  match_score: number
  matched_symptoms: MatchedSymptom[]
}

export interface RareDiseaseResult {
  symptoms_mapped: MappedSymptom[]
  diseases: RareDisease[]
  hpo_totals?: Record<string, number>
}

// ── Guidelines Conformance ────────────────────────────────────────────────────

export interface GuidelineFinding {
  area: string
  guideline_recommendation: string
  current_practice: string
  status: 'conforming' | 'deviation' | 'partial' | 'not_assessed'
  severity: 'major' | 'minor' | 'informational'
  action: string
  pmid: string | null
  guideline_title: string | null
}

// ── Contradiction Detector ────────────────────────────────────────────────────

export interface ContradictionItem {
  topic: string
  type: 'source_vs_source' | 'intra_document'  // injected by backend, not from LLM
  claim_a: string
  source_a: string
  claim_b: string
  source_b: string
  severity: 'high' | 'medium' | 'low'
  explanation: string
  resolution: string
}

export interface ContradictionResult {
  keywords: string[]
  sources_analysed: string[]
  contradictions: ContradictionItem[]      // intra_document + source_vs_source merged
  source_vs_source: ContradictionItem[]
  intra_document: ContradictionItem[]
  severity_counts: { high: number; medium: number; low: number }
  overall_assessment: string
  confidence: number
}

// ── Document Drafter ─────────────────────────────────────────────────────────

export interface DraftItem {
  document_type: string
  document_type_label: string
  content: string
  generated_at: string
}

export type DraftResult = Record<string, DraftItem>

// ── Guidelines Conformance ────────────────────────────────────────────────────

export interface GuidelinesConformanceResult {
  keywords: string[]
  guidelines_fetched: number
  confidence: number
  sources?: { pubmed: number; bookshelf: number; medlineplus: number; nlm_catalog: number }
  findings: GuidelineFinding[]
  deviations: GuidelineFinding[]
  conforming: GuidelineFinding[]
  not_assessed: GuidelineFinding[]
  overall_summary: string
}

// ── Users & Roles ─────────────────────────────────────────────────────────────

export const ROLES = {
  1: { id: 1, name: 'free', label: 'Free User' },
  2: { id: 2, name: 'premium', label: 'Premium User' },
  3: { id: 3, name: 'admin', label: 'Admin User' },
} as const

export type RoleId = keyof typeof ROLES

export interface User {
  user_id: string
  name: string
  email: string
  role_id: RoleId
}

export interface UserRecord extends User {
  is_verified: boolean
  created_at: string | null
}
