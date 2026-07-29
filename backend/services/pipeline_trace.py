"""Versioning + replay records — design doc §6.

Each analyze() call produces a list of StageRecords. LLM-generated stages are
snapshotted (their output is reproduced by storage, since generation is not
guaranteed reproducible even at temperature 0). Deterministic stages are recomputed
by construction — the record here is what to feed compute_posterior / rank_falsifiers
again to reproduce the same result, not a substitute for re-running them.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


def content_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class StageRecord:
    stage: str
    kind: str                      # "llm_snapshot" | "deterministic"
    versions: dict[str, str]       # e.g. {"model": "qwen2.5:7b", "prompt_hash": "...", "kb_version": "..."}
    output_hash: str
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def make_stage_record(stage: str, kind: str, versions: dict[str, str], output) -> StageRecord:
    return StageRecord(stage=stage, kind=kind, versions=versions, output_hash=content_hash(output))


def trace_to_dicts(records: list[StageRecord]) -> list[dict]:
    return [
        {
            "stage": r.stage,
            "kind": r.kind,
            "versions": r.versions,
            "output_hash": r.output_hash,
            "computed_at": r.computed_at,
        }
        for r in records
    ]
