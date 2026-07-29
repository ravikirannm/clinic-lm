from pydantic import BaseModel, Field
from typing import List, Literal, Optional

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

class EvidenceItem(BaseModel):
    source_type: Literal["patient_document", "rag_knowledge_base", "pubmed", "clinical_guideline"]
    source_id: str = Field(description="PMID, RAG chunk id, or document identifier — never freeform")
    evidence_grade: Literal[
        "systematic_review", "rct", "cohort_study", "case_control",
        "case_report", "expert_consensus", "patient_reported"
    ]
    finding: str = Field(description="The specific claim this source supports, in plain language")


class DifferentialCondition(BaseModel):
    name: str
    icd11_code: str = Field(description="Best-matching ICD-11 code. Append '(approximate)' if not certain")
    epidemiological_prior: str = Field(
        description="Baseline prevalence reasoning for this patient's demographic, stated BEFORE symptom matching. "
                    "If demographics are unknown, say so explicitly and use general population base rate."
    )
    posterior_likelihood: Literal["high", "medium", "low", "very_low"]
    likelihood_rationale: str = Field(
        description="Name which specific reported symptoms raised probability, which lowered it, "
                    "and how the prior moved to this posterior. This is the Bayesian update step — show the work."
    )
    supporting_evidence: List[EvidenceItem]
    refuting_evidence: List[EvidenceItem] = Field(
        description="Evidence AGAINST this condition. If genuinely none exists in the provided sources, "
                    "include one EvidenceItem with finding='no disconfirming evidence identified in available sources'. "
                    "Never omit this field — an empty list is not the same as an explicit absence statement."
    )
    unconfirmed_hallmark_symptoms: List[str]


class RedFlag(BaseModel):
    symptom: str
    associated_condition: str
    clinical_decision_rule: Optional[str] = Field(
        default=None, description="Named validated score if one applies, e.g. 'CURB-65', 'Wells Score', 'NEWS2'"
    )
    action: str


class RecommendedTest(BaseModel):
    test: str
    targets_condition: str
    diagnostic_value: str = Field(
        description="What a positive vs. negative result does to the probability of the targeted condition — "
                    "not just 'confirms' or 'rules out'"
    )
    priority: Literal["stat", "urgent", "routine"]


class FindingVocabularyProposal(BaseModel):
    """LLM output: canonical finding ids relevant to THIS patient's presentation,
    proposed fresh per request — not a fixed domain list. See services/finding_vocabulary.py."""
    finding_ids: List[str] = []
    confidence: float = _CONF_FIELD


class Finding(BaseModel):
    """A single discrete observation extracted from free text. The LLM maps text to a
    Finding.name drawn from a controlled vocabulary and does not assign probabilities —
    see services/finding_vocabulary.py and docs/clinical_analyzer_refactor.md §4.2."""
    name: str = Field(description="Canonical finding id from the supplied controlled vocabulary — never freeform")
    status: Literal["present", "absent", "not_reported"]
    grade: str | None = Field(default=None, description="Optional severity/graded value, e.g. 'mild', '7/10'")
    source_span: str = Field(description="Verbatim text this finding was extracted from")
    extractor_version: str = Field(default="", description="Filled in by the caller after parsing, not by the model")


class FindingExtractionResult(BaseModel):
    """LLM output wrapper for the finding-extraction stage."""
    findings: List[Finding] = []
    confidence: float = _CONF_FIELD


_EVIDENCE_GRADE = Literal[
    "systematic_review", "rct", "cohort_study", "case_control",
    "case_report", "expert_consensus", "patient_reported"
]


class ExtractedPrior(BaseModel):
    """LLM output: a baseline prevalence claim found VERBATIM in a retrieved source
    document — never the model's own unsourced estimate. See services/evidence_extraction.py."""
    condition: str = Field(description="Must exactly match one of the candidate condition names provided")
    probability: float = Field(ge=0.0, le=1.0)
    stratum: str = Field(min_length=1, description="The population/stratum the source describes, "
                                                     "e.g. 'ED patients with chest pain' — required, not optional")
    source_id: str = Field(description="The exact id shown in the SOURCE DOCUMENTS list — never invented")
    quote: str = Field(description="Verbatim sentence from that source containing the number")
    grade: _EVIDENCE_GRADE = Field(description="What kind of study this source is — classify honestly from its "
                                                "title/abstract, do not default to the same grade for every source")


class ExtractedLR(BaseModel):
    """LLM output: a likelihood ratio claim found VERBATIM in a retrieved source document."""
    finding: str = Field(description="Must exactly match one of the controlled vocabulary finding ids provided")
    condition: str = Field(description="Must exactly match one of the candidate condition names provided")
    lr_present: float | None = Field(default=None, description="LR+ if stated; omit if not found")
    lr_absent: float | None = Field(default=None, description="LR- if stated; omit if not found")
    source_id: str = Field(description="The exact id shown in the SOURCE DOCUMENTS list — never invented")
    quote: str = Field(description="Verbatim sentence from that source containing the number(s)")
    grade: _EVIDENCE_GRADE = Field(description="What kind of study this source is — classify honestly from its "
                                                "title/abstract, do not default to the same grade for every source")


class EvidenceExtractionResult(BaseModel):
    """LLM output wrapper for the evidence-extraction stage. Empty lists are the
    expected/correct output when the retrieved documents contain no explicit
    prevalence or likelihood-ratio statement — the model must not fill gaps with
    outside knowledge."""
    priors: List[ExtractedPrior] = []
    lr_entries: List[ExtractedLR] = []
    confidence: float = _CONF_FIELD


class ClinicalAssessment(BaseModel):
    possible_conditions: List[DifferentialCondition]
    next_best_discriminator: str = Field(
        description="The single highest-yield question or test that would most reduce uncertainty between "
                    "the top two differentials, and why it outperforms the alternatives"
    )
    red_flags: List[RedFlag]
    recommended_tests: List[RecommendedTest]
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in THIS ASSESSMENT given evidence completeness — not diagnostic certainty about the patient"
    )


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