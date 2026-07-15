#!/usr/bin/env python3
"""PostToolUse hook — record workspace edits into the reconciliation queue.

Cheap and deterministic: when a workspace/ file is edited, append one record to
docs/memory/pending-updates.jsonl (with candidate docs if a source map exists).
No LLM, no doc rewrites — the semantic update happens later in /update-project-docs.
"""

from __future__ import annotations

import json

from _common import HUB_ROOT, read_event  # noqa: E402


def _source_map_entries():
    from hub_lib import paths

    path = paths.generated_dir(HUB_ROOT) / "source-map.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (json.JSONDecodeError, OSError):
        return []


def record_edit(tool_name: str, file_path: str) -> bool:
    from pathlib import Path

    from hub_lib import paths, queue

    if not file_path or not paths.is_workspace_path(file_path, HUB_ROOT):
        return False
    try:
        rel = Path(file_path).resolve().relative_to(HUB_ROOT).as_posix()
    except ValueError:
        rel = Path(file_path).as_posix()

    candidates = paths.map_source_to_docs(rel, _source_map_entries())
    queue.append_record(
        paths.memory_dir(HUB_ROOT), queue.make_record(rel, tool_name, candidates)
    )
    return True


def main() -> int:
    event = read_event()
    try:
        tool_input = event.get("tool_input", {}) or {}
        record_edit(event.get("tool_name", ""), tool_input.get("file_path", ""))
    except Exception:  # never disturb the observed tool
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
