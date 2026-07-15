"""The reconciliation queue: ``docs/memory/pending-updates.jsonl``.

The buffer between cheap deterministic *detection* (a PostToolUse hook appends a
record when a ``workspace/`` file is edited) and deliberate semantic *update*
(the ``/hub-update-project-docs`` skill consumes, reconciles, then resolves).

Append-only JSONL: crash-safe, greppable, trivial for a fast hook to produce.
Malformed lines are skipped rather than fatal.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

QUEUE_FILENAME = "pending-updates.jsonl"


def _queue_path(memory_dir: Path) -> Path:
    return Path(memory_dir) / QUEUE_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_record(
    source_path: str,
    tool: str,
    candidate_docs: list[str] | None = None,
    *,
    event: str = "source_edit",
    ts: str | None = None,
) -> dict:
    return {
        "ts": ts or _now(),
        "event": event,
        "source_path": source_path,
        "tool": tool,
        "candidate_docs": candidate_docs or [],
        "resolved": False,
    }


def append_record(memory_dir: Path, record: dict) -> None:
    path = _queue_path(memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_records(memory_dir: Path) -> list[dict]:
    path = _queue_path(memory_dir)
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate corruption, never crash a hook
    return records


def unresolved(records: list[dict]) -> list[dict]:
    return [r for r in records if not r.get("resolved")]


def dedup(records: list[dict]) -> list[dict]:
    """One record per source_path (latest wins), unioning candidate_docs."""
    merged: dict[str, dict] = {}
    for rec in records:
        key = rec.get("source_path", "")
        if key in merged:
            docs = {
                *merged[key].get("candidate_docs", []),
                *rec.get("candidate_docs", []),
            }
            rec = {**rec, "candidate_docs": sorted(docs)}
        merged[key] = rec
    return list(merged.values())


def pending_count(memory_dir: Path) -> int:
    return len(unresolved(read_records(memory_dir)))


def resolve(memory_dir: Path, source_paths: set[str]) -> int:
    """Drop records whose source_path is in *source_paths*. Returns count removed."""
    records = read_records(memory_dir)
    kept = [r for r in records if r.get("source_path") not in source_paths]
    removed = len(records) - len(kept)
    path = _queue_path(memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in kept:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return removed
