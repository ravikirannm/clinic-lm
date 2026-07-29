"""Diff the deterministic posteriors against the LLM's self-reported ones — design doc
§9 migration step 3: "Run it in parallel with the existing LLM posteriors and diff
them... this validates the arithmetic and surfaces where the LLM was guessing."

Condition matching is exact string equality by construction: compute_posterior is run
using the LLM's own condition names as the Prior.condition key (see
services/evidence_extraction.py and clinical_analyzer.py), not a separate fixed
vocabulary — so there is no fuzzy name-matching problem to solve here.
"""

from services.bayesian import PosteriorChain

# These cutoffs are an arbitrary display convention I chose to make computed_posterior
# (a number) comparable to the LLM's self-reported high/medium/low/very_low (a label
# with no numeric definition anywhere in the system) — they are NOT a clinical or
# statistical standard, and nothing sourced them. computed_posterior is always present
# in the output alongside the bucket specifically so this convention can be ignored
# in favor of the exact number.
_BUCKET_THRESHOLDS = (  # (floor, label) — first match wins, checked high to low
    (0.5, "high"),
    (0.2, "medium"),
    (0.05, "low"),
)


def bucket_from_probability(p: float) -> str:
    for floor, label in _BUCKET_THRESHOLDS:
        if p >= floor:
            return label
    return "very_low"


def build_diff(chains: list[PosteriorChain], symptom_analysis: dict) -> list[dict]:
    llm_by_name = {c.get("name"): c for c in symptom_analysis.get("possible_conditions", [])}
    diff = []
    for chain in chains:
        computed_bucket = bucket_from_probability(chain.posterior)
        match = llm_by_name.get(chain.condition)
        if match is None:
            diff.append({
                "condition": chain.condition,
                "computed_posterior": chain.posterior,
                "computed_bucket": computed_bucket,
                "llm_bucket": None,
                "agree": None,
                "note": "condition not present in the LLM differential for this run",
            })
            continue
        llm_bucket = match.get("posterior_likelihood")
        diff.append({
            "condition": chain.condition,
            "computed_posterior": chain.posterior,
            "computed_bucket": computed_bucket,
            "llm_bucket": llm_bucket,
            "agree": computed_bucket == llm_bucket,
        })
    return diff
