"""Pure validation predicates for curated docs (stdlib only).

Shared by the cheap ``Stop``-hook check and the full ``/hub-validate-docs`` workflow.
Every function is side-effect free and returns a list of human-readable errors
(empty == valid), so callers can aggregate and report.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_FIELDS = ("title", "type", "status")
VALID_TYPES = {
    "graph",
    "architecture",
    "decision",
    "domain",
    "workflow",
    "runbook",
    "interface",
    "operations",
    "development",
}
VALID_STATUS = {"draft", "current", "deprecated"}
GENERATED_MARKER = "<!-- generated:"

# Markdown links to a local .md file, e.g. [x](../domain/y.md#anchor).
_LINK_RE = re.compile(r"\]\((?!https?://|mailto:)([^)\s]+\.md)(?:#[^)]*)?\)")


def check_frontmatter(meta: dict) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if not meta.get(field):
            errors.append(f"missing required front-matter field: {field}")
    kind = meta.get("type")
    if kind and kind not in VALID_TYPES:
        errors.append(f"invalid type: {kind}")
    status = meta.get("status")
    if status and status not in VALID_STATUS:
        errors.append(f"invalid status: {status}")
    return errors


def extract_internal_links(body: str) -> list[str]:
    return _LINK_RE.findall(body)


def check_internal_links(doc_path: Path | str, body: str) -> list[str]:
    """Every relative ``.md`` link must resolve to an existing file."""
    base = Path(doc_path).resolve().parent
    errors: list[str] = []
    for link in extract_internal_links(body):
        target = (base / link).resolve()
        if not target.exists():
            errors.append(f"dead link: {link}")
    return errors


def has_generated_banner(text: str) -> bool:
    return GENERATED_MARKER in text


def check_source_paths_exist(meta: dict, hub_root: Path | str) -> list[str]:
    """Declared ``source_paths`` should still exist on disk (else the doc is stale)."""
    root = Path(hub_root)
    errors: list[str] = []
    for sp in meta.get("source_paths", []) or []:
        if not (root / sp).exists():
            errors.append(f"source path no longer exists: {sp}")
    return errors


def scan_docs(hub_root: Path | str) -> list[str]:
    """Cheap front-matter + internal-link check over every curated doc.

    Returns ``"<relpath>: <error>"`` strings. Used by the Stop hook and the full
    /hub-validate-docs workflow (which layers extra checks on top).
    """
    from hub_lib import frontmatter, paths

    root = Path(hub_root)
    errors: list[str] = []
    for doc in paths.iter_curated_docs(root):
        rel = doc.relative_to(root)
        try:
            meta, body = frontmatter.load(doc)
        except OSError:
            errors.append(f"{rel}: unreadable")
            continue
        errors += [f"{rel}: {e}" for e in check_frontmatter(meta)]
        errors += [f"{rel}: {e}" for e in check_internal_links(doc, body)]
    return errors


def write_report(memory_dir: Path | str, errors: list[str], pending: int) -> Path:
    """Persist a validation snapshot to ``memory/last-validation.json``."""
    memory = Path(memory_dir)
    memory.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error_count": len(errors),
        "pending": pending,
        "errors": errors,
    }
    target = memory / "last-validation.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return target
