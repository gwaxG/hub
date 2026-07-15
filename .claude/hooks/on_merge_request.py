#!/usr/bin/env python3
"""PostToolUse hook — documentation gate when a merge request is opened.

Fires after the GitLab ``create_merge_request`` MCP tool. Does the deterministic
work directly (refresh the generated graph + source map, no LLM), then injects a
directive telling Claude to reconcile docs for this MR and to record an ADR only
if the change is a genuine architectural decision.
"""

from __future__ import annotations

from _common import HUB_ROOT, emit_context, read_event  # noqa: E402


def build_context() -> str:
    from hub_lib import generate, paths, queue

    if not paths.docs_dir(HUB_ROOT).exists():
        return ""

    generate.build_graph(HUB_ROOT)
    generate.build_source_map(HUB_ROOT)
    pending = queue.pending_count(paths.memory_dir(HUB_ROOT))

    return "\n".join(
        [
            "Merge request opened — documentation gate:",
            "  1. Project graph + source map were refreshed automatically.",
            f"  2. Run /hub-update-project-docs to reconcile the vault against this MR's diff "
            f"before it merges ({pending} record(s) currently queued).",
            "  3. If this MR embodies an architectural decision (real alternatives / "
            "lasting consequences), run /hub-create-adr — otherwise skip it.",
        ]
    )


def main() -> int:
    read_event()
    try:
        emit_context("PostToolUse", build_context())
    except Exception:  # never disturb the tool that just ran
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
