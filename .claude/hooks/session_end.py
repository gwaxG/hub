#!/usr/bin/env python3
"""SessionEnd hook — persist bookkeeping and cleanup.

Writes a final validation snapshot so the next SessionStart can surface stale/
unresolved state. Does not duplicate the episodic history claude-mem already keeps.
"""

from __future__ import annotations

from _common import HUB_ROOT, read_event  # noqa: E402


def persist() -> None:
    from hub_lib import paths, queue, validate

    memory = paths.memory_dir(HUB_ROOT)
    if not paths.docs_dir(HUB_ROOT).exists():
        return
    errors = validate.scan_docs(HUB_ROOT)
    pending = queue.pending_count(memory)
    validate.write_report(memory, errors, pending)


def main() -> int:
    read_event()
    try:
        persist()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
