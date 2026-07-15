#!/usr/bin/env python3
"""Stop hook — cheap validation + unresolved-impact reminder.

Runs the shared front-matter/link scan, persists a snapshot, and prints a concise
reminder when something needs attention. Never blocks (a Stop does not prove the
feature is done) and never rewrites docs — no recursion.
"""

from __future__ import annotations

import sys

from _common import HUB_ROOT, read_event  # noqa: E402


def check() -> tuple[list[str], int]:
    from hub_lib import paths, queue, validate

    memory = paths.memory_dir(HUB_ROOT)
    errors = validate.scan_docs(HUB_ROOT)
    pending = queue.pending_count(memory)
    validate.write_report(memory, errors, pending)
    return errors, pending


def main() -> int:
    event = read_event()
    if event.get("stop_hook_active"):  # already looping — do nothing
        return 0
    try:
        errors, pending = check()
    except Exception:
        return 0
    notes = []
    if errors:
        notes.append(f"{len(errors)} doc validation issue(s) — run /hub-validate-docs")
    if pending:
        notes.append(
            f"{pending} unresolved doc-impact record(s) — run /hub-update-project-docs"
        )
    if notes:
        print("Docs: " + "; ".join(notes) + ".", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
