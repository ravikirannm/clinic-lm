from pydantic import BaseModel, Field
from typing import List

_CONF_FIELD = Field(
    default=0.8,
    description=(
        "Your confidence in this output (0.0–1.0). "
        "1.0=high certainty, unambiguous data, multiple concordant sources. "
        "0.7=good confidence, minor gaps. "
        "0.5=moderate, limited info or some ambiguity. "
        "0.3=low, significant missing data. "
        "0.0=very low, insufficient basis for reliable output."
    ),
)

# ── Shared ────────────────────────────────────────────────────────────────────

class PubMedSearchQuery(BaseModel):
    primary_query: str
    fallback_query: str
    filters: list[str] = []


# ── Clinical Analysis ─────────────────────────────────────────────────────────

class PubMedSearchRequest(BaseModel):
    """LLM output wrapper: instructs the model to produce a PubMed search config."""
    pubmed: PubMedSearchQuery
    confidence: float = _CONF_FIELD

class DifferentialDiagnosis(BaseModel):
    name: str
    likelihood: str
    reasoning: str
    supporting_evidence: str
    unconfirmed_hallmark_symptoms: list[str]


class ClinicalRedFlag(BaseModel):
    symptom: str
    associated_condition: str
    action: str


class DiagnosticTest(BaseModel):
    test: str
    reason: str
    targets_condition: str


class ClinicalAssessment(BaseModel):
    possible_conditions: list[DifferentialDiagnosis]
    red_flags: list[ClinicalRedFlag]
    recommended_tests: list[DiagnosticTest]
    confidence: float = _CONF_FIELD


# ── Drug Interaction ──────────────────────────────────────────────────────────

class DrugNameList(BaseModel):
    """Step A LLM output: raw drug name strings extracted from text."""
    items: list[str] = []
    confidence: float = _CONF_FIELD


class DrugMention(BaseModel):
    name_as_mentioned: str = ""
    generic_name: str = ""
    drug_class: str = ""
    dosage: str = "unspecified"
    duration: str = "unspecified"
    candidate_names: list[str] = []


class DrugExtractionResult(BaseModel):
    drugs_mentioned: list[DrugMention] = []
    confidence: float = _CONF_FIELD


class PICOEvidence(BaseModel):
    population: str | None = None
    intervention: str | None = None
    comparison: str | None = None
    outcome: str | None = None
    evidence_quality: str = "insufficient"
    key_findings: str | None = None
    supporting_pmids: list[str] = []

# ICD-11 Tree ──────────────────────────────────────────────────────────

class ICD11SearchRequest(BaseModel):
    search_terms: List[str]


# Literature Review ────────────────────────────────────────────────────

class ArticleGrading(BaseModel):
    sample_size: int | None = None
    bias_flags: list[str] = []
    summary: str = ""


# Risk Analysis ────────────────────────────────────────────────────────

class ExtractedParameter(BaseModel):
    parameter: str
    status_found: str | None = None
    value_found: str | None = None
    unit: str | None = None
    evidence_quote: str | None = None

class RiskScoreExtraction(BaseModel):
    scoring_system: str
    parameters_extracted: list[ExtractedParameter]
    missing_parameters: list[str] = []


# Rare Disease ─────────────────────────────────────────────────────────

class SymptomList(BaseModel):
    symptoms: list[str]


# Guidelines Conformance ───────────────────────────────────────────────

class GuidelineDeviation(BaseModel):
    area: str                        # clinical area, e.g. "Antihypertensive therapy"
    guideline_recommendation: str    # what the guideline says to do
    current_practice: str            # what is currently done for this patient
    status: str                      # "conforming" | "deviation" | "partial" | "not_assessed"
    severity: str                    # "major" | "minor" | "informational"
    action: str                      # what should be done / corrected
    pmid: str | None = None
    guideline_title: str | None = None

class ConformanceAnalysis(BaseModel):
    findings: list[GuidelineDeviation]
    overall_summary: str
    confidence: float = _CONF_FIELD


# Contradiction Detector ───────────────────────────────────────────────

class ContradictionItem(BaseModel):
    topic: str        # brief label, e.g. "Laterality Mismatch"
    claim_a: str      # first contradicting statement (quote or paraphrase)
    source_a: str     # exact document name from the uploaded list
    claim_b: str      # second contradicting statement
    source_b: str     # exact document name from the uploaded list
    severity: str     # "high" | "medium" | "low"
    explanation: str  # why these two statements contradict
    resolution: str   # action needed to resolve the contradiction

class ContradictionReport(BaseModel):
    intra_document: list[ContradictionItem] = []     # contradictions within ONE document
    source_vs_source: list[ContradictionItem] = []  # contradictions ACROSS documents
    overall_assessment: str = ""
    confidence: float = _CONF_FIELD


# Chat ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    messages: list[dict]   # conversation history [{role, content}, ...]
    query: str


class SaveHistoryBody(BaseModel):
    messages: list[dict]


# Document Drafter ──────────────────────────────────────────────────────────────

class DraftDocumentRequest(BaseModel):
    document_type: str  # "referral_letter" | "discharge_summary" | "case_writeup"