#!/usr/bin/env python3
"""SessionStart hook — inject *compact* authoritative hub context.

Deliberately small: the documentation policy, a one-line vault index and any
outstanding warnings. Never dumps the vault and never duplicates claude-mem
(which injects its own episodic context).
"""

from __future__ import annotations

import json

from _common import HUB_ROOT, emit_context, read_event  # noqa: E402


def _stale_count() -> int:
    from hub_lib import paths

    path = paths.memory_dir(HUB_ROOT) / "stale-docs.json"
    if not path.exists():
        return 0
    try:
        return len(json.loads(path.read_text(encoding="utf-8")).get("stale", []))
    except (json.JSONDecodeError, OSError):
        return 0


def _new_repo_line() -> str | None:
    from hub_lib import paths

    new = paths.un_ingested_repos(HUB_ROOT)
    if not new:
        return None
    shown = ", ".join(new[:15]) + (f" (+{len(new) - 15} more)" if len(new) > 15 else "")
    return (
        f"🆕 {len(new)} workspace repo(s) with no graph node yet: {shown}. "
        "Run /hub-ingest-repository <path> to add them to the vault."
    )


def build_context() -> str:
    from hub_lib import paths, queue

    if not paths.docs_dir(HUB_ROOT).exists():
        return ""

    note_count = sum(1 for _ in paths.iter_curated_docs(HUB_ROOT))
    pending = queue.pending_count(paths.memory_dir(HUB_ROOT))
    stale = _stale_count()

    lines = [
        "Hub docs policy: docs/ is the authoritative Layer-2 knowledge vault. "
        "Verify against source before trusting it; capture durable knowledge there, "
        "not routine edits. claude-mem covers episodic history separately.",
        f"Vault: {note_count} curated note(s) across "
        "graph/architecture/domain/workflows/runbooks/interfaces/operations/development.",
    ]
    if pending:
        lines.append(
            f"⚠ {pending} unresolved doc-impact record(s) in the queue — run /hub-update-project-docs."
        )
    if stale:
        lines.append(
            f"⚠ {stale} doc(s) flagged stale — see docs/memory/stale-docs.json."
        )
    new_repos = _new_repo_line()
    if new_repos:
        lines.append(new_repos)
    return "\n".join(lines)


def main() -> int:
    read_event()
    try:
        emit_context("SessionStart", build_context())
    except Exception:  # a hook must never break session startup
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
