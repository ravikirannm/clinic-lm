"""Deterministic Bayesian layer — see docs/clinical_analyzer_refactor.md §4.

Everything here is pure computation over already-extracted Finding[] and Prior/LREntry
objects. No LLM calls, no hardcoded clinical values — Prior and LREntry instances are
produced per-request by services/evidence_extraction.py from live PubMed/RAG retrieval,
not from a static table. Same findings + same kb_version -> identical output, by
construction.

Deviation from the design doc's pseudocode: LREntry.lr_present / lr_absent are Optional.
Real literature curation is incremental — a source often reports LR+ without LR-, or
vice versa. Modeling that as Optional lets compute_posterior record a missing half of a
pair as a gap (same spirit as a missing (finding, condition) row entirely), rather than
forcing a fabricated placeholder number into a required field.
"""

import math
from dataclasses import dataclass, field

from services.data_model import Finding


@dataclass(frozen=True)
class Prior:
    condition: str
    probability: float          # base-rate for the stated stratum
    source_id: str
    stratum: str                # e.g. "ed_chest_pain_presentation" — NOT necessarily general population
    kb_version: str
    grade: str                  # evidence grade of the source, e.g. "systematic_review", "cohort_study"


@dataclass(frozen=True)
class LREntry:
    finding: str                 # matches Finding.name
    condition: str
    lr_present: float | None     # LR+ when finding is present; None = not sourced yet
    lr_absent: float | None      # LR- when finding is confirmed absent; None = not sourced yet
    source_id: str                # PMID or guideline id — never freeform
    grade: str                    # evidence grade, e.g. "systematic_review", "cohort_study"
    kb_version: str


@dataclass(frozen=True)
class ChainStep:
    kind: str                     # "prior" | "update" | "gap"
    running_probability: float
    finding: str | None = None
    status: str | None = None
    lr: float | None = None
    source_id: str | None = None
    grade: str | None = None
    stratum: str | None = None    # populated for the "prior" step only
    note: str | None = None       # populated for "gap" steps


@dataclass(frozen=True)
class PosteriorChain:
    condition: str
    posterior: float
    steps: list[ChainStep]
    kb_version: str


def _odds(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return p / (1 - p)


def _prob(odds: float) -> float:
    return odds / (1 + odds)


def compute_posterior(prior: Prior, findings: list[Finding],
                       lr_table: dict[tuple[str, str], LREntry]) -> PosteriorChain:
    """prior x LRs -> posterior, in odds space. No LLM involved. Recomputable: same
    inputs + same kb_version always produce the identical chain."""
    odds = _odds(prior.probability)
    steps: list[ChainStep] = [
        ChainStep(kind="prior", running_probability=prior.probability, source_id=prior.source_id,
                   grade=prior.grade, stratum=prior.stratum)
    ]

    for f in findings:
        if f.status == "not_reported":
            continue  # explicitly non-discriminating — does not update, prevents anchoring on absent data

        entry = lr_table.get((f.name, prior.condition))
        if entry is None:
            steps.append(ChainStep(
                kind="gap", running_probability=_prob(odds), finding=f.name, status=f.status,
                note=f"no LR entry for ({f.name!r}, {prior.condition!r}) in kb_version={prior.kb_version}",
            ))
            continue

        lr = entry.lr_present if f.status == "present" else entry.lr_absent
        if lr is None:
            steps.append(ChainStep(
                kind="gap", running_probability=_prob(odds), finding=f.name, status=f.status,
                note=f"LR entry exists for ({f.name!r}, {prior.condition!r}) but "
                     f"{'lr_present' if f.status == 'present' else 'lr_absent'} not yet sourced",
            ))
            continue

        odds *= lr
        steps.append(ChainStep(
            kind="update", running_probability=_prob(odds), finding=f.name, status=f.status,
            lr=lr, source_id=entry.source_id, grade=entry.grade,
        ))

    return PosteriorChain(condition=prior.condition, posterior=_prob(odds), steps=steps,
                           kb_version=prior.kb_version)


def render_chain(chain: PosteriorChain) -> str:
    """Human-readable rendering of a posterior chain — see design doc §4.4."""
    prior_step = chain.steps[0]
    prior_desc = f"({prior_step.stratum}, {prior_step.grade}, {prior_step.source_id})" \
        if prior_step.stratum else f"({prior_step.source_id})"
    parts = [f"Prior {prior_step.running_probability:.3f} {prior_desc}"]
    for step in chain.steps[1:]:
        if step.kind == "update":
            parts.append(f"{step.finding} {step.status}, LR {step.lr:.2f} ({step.source_id}) "
                         f"-> {step.running_probability:.3f}")
        elif step.kind == "gap":
            parts.append(f"[gap: {step.note}]")
    parts.append(f"posterior {chain.posterior:.3f}")
    return " -> ".join(parts)


# ── Confidence from posterior separation — design doc §7 ───────────────────────────

def confidence_from_separation(chains: list[PosteriorChain]) -> float:
    """How far the leading hypothesis sits from the runner-up. A margin of 0.51
    (0.62 vs 0.11) reads as high confidence; a margin of 0.02 (0.31 vs 0.29) reads as
    low — matching the design doc's worked example. Revisit this formula once it has
    been validated against real cases; it is a first-pass, not a settled metric."""
    if not chains:
        return 0.0
    ranked = sorted((c.posterior for c in chains), reverse=True)
    if len(ranked) == 1:
        return round(ranked[0], 3)
    margin = ranked[0] - ranked[1]
    return round(min(max(margin, 0.0), 1.0), 3)


# ── Information-gain ranking of candidate falsifiers — design doc §5 ───────────────

def binary_entropy(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def _invert_lr_to_sens_spec(lr_pos: float, lr_neg: float) -> tuple[float, float] | None:
    """Recover (sensitivity, specificity) from LR+ and LR- alone — these are intrinsic
    test properties, independent of prevalence, so no other input is needed:
        LR+ = Se / (1 - Sp)
        LR- = (1 - Se) / Sp
    Returns None for a degenerate/non-informative pair (LR+ == LR-, or values outside
    the range solvable to Se, Sp in [0, 1])."""
    if lr_pos == lr_neg or lr_pos <= 0 or lr_neg <= 0:
        return None
    sp = (1 - lr_pos) / (lr_neg - lr_pos)
    se = lr_pos * (1 - sp)
    if not (0.0 <= sp <= 1.0 and 0.0 <= se <= 1.0):
        return None
    return se, sp


@dataclass(frozen=True)
class FalsifierCandidate:
    finding: str
    expected_information_gain: float | None   # None = no sourced LR evidence for this finding at all (a gap)
    conditions_with_evidence: list[str] = field(default_factory=list)


def expected_information_gain(finding_name: str, chains: list[PosteriorChain],
                               lr_table: dict[tuple[str, str], LREntry]) -> FalsifierCandidate:
    """Expected reduction in summed binary entropy across the hypothesis set if
    `finding_name` were resolved to present/absent. Higher = better discriminator.
    Hypotheses with no LR entry for this finding keep their current posterior in both
    outcome branches — they contribute zero marginal information, which is correct:
    we have no sourced basis to claim this finding would move that hypothesis."""
    current_entropy = sum(binary_entropy(c.posterior) for c in chains)
    expected_entropy = 0.0
    conditions_with_evidence: list[str] = []

    for chain in chains:
        entry = lr_table.get((finding_name, chain.condition))
        if entry is None or entry.lr_present is None or entry.lr_absent is None:
            expected_entropy += binary_entropy(chain.posterior)
            continue

        inverted = _invert_lr_to_sens_spec(entry.lr_present, entry.lr_absent)
        if inverted is None:
            expected_entropy += binary_entropy(chain.posterior)
            continue
        se, sp = inverted
        conditions_with_evidence.append(chain.condition)

        p = chain.posterior  # current probability this hypothesis is true
        p_finding_present = p * se + (1 - p) * (1 - sp)
        p_finding_absent = 1 - p_finding_present

        odds_present = _odds(p) * entry.lr_present
        odds_absent = _odds(p) * entry.lr_absent
        h_present = binary_entropy(_prob(odds_present))
        h_absent = binary_entropy(_prob(odds_absent))

        expected_entropy += p_finding_present * h_present + p_finding_absent * h_absent

    if not conditions_with_evidence:
        return FalsifierCandidate(finding=finding_name, expected_information_gain=None)

    gain = current_entropy - expected_entropy
    return FalsifierCandidate(finding=finding_name, expected_information_gain=round(gain, 4),
                               conditions_with_evidence=conditions_with_evidence)


def rank_falsifiers(candidate_findings: list[str], chains: list[PosteriorChain],
                     lr_table: dict[tuple[str, str], LREntry]) -> list[FalsifierCandidate]:
    """Rank candidate findings (not yet reported) by expected information gain.
    Gaps (no sourced LR evidence at all) sort last, not first — an unranked finding is
    not a good discriminator by default, it is simply unscored."""
    scored = [expected_information_gain(f, chains, lr_table) for f in candidate_findings]
    return sorted(scored, key=lambda c: (c.expected_information_gain is None,
                                          -(c.expected_information_gain or 0.0)))
