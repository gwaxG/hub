# /// script
# requires-python = ">=3.11"
# ///
"""Stop hook: once per session, ask Claude to record learnings in docs/ if it did work but wrote none."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parents[2]
MARKERS = HUB / "tmp" / "docs-nudge"
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
WORK_COMMANDS = ("git commit", "git push", "merge_requests")
REASON = (
    "Before finishing: did this session uncover durable knowledge (how something works, a root cause, "
    "a rollout rule, an MR's design)? If yes, add or update a note in the hub docs/ lake per CLAUDE.md "
    "(frontmatter, MEMORY.md line, `uv run workflows/lint_docs.py`). If not, reply 'nothing for docs' and stop."
)


class Transcript:
    def __init__(self, path: Path) -> None:
        self.tool_uses = list(self._tool_uses(path))

    @staticmethod
    def _tool_uses(path: Path):
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            content = (entry.get("message") or {}).get("content")
            if entry.get("type") == "assistant" and isinstance(content, list):
                yield from (c for c in content if c.get("type") == "tool_use")

    def wrote_docs(self) -> bool:
        return any(
            self._is_docs_path(u["input"].get("file_path", "")) for u in self._writes()
        )

    def did_work(self) -> bool:
        code_writes = any(
            not self._is_docs_path(u["input"].get("file_path", ""))
            for u in self._writes()
        )
        commands = (
            u["input"].get("command", "") for u in self.tool_uses if u["name"] == "Bash"
        )
        mr_calls = any("merge_request" in u["name"] for u in self.tool_uses)
        return (
            code_writes
            or mr_calls
            or any(w in c for c in commands for w in WORK_COMMANDS)
        )

    def _writes(self):
        return (u for u in self.tool_uses if u["name"] in WRITE_TOOLS)

    @staticmethod
    def _is_docs_path(path: str) -> bool:
        hub_docs = "/docs/" in path and "/workspace/" not in path
        return hub_docs or path.endswith("MEMORY.md")


def should_nudge(event: dict, marker: Path) -> bool:
    if event.get("stop_hook_active") or marker.exists():
        return False
    transcript = Transcript(Path(event["transcript_path"]))
    return transcript.did_work() and not transcript.wrote_docs()


def main() -> None:
    event = json.load(sys.stdin)
    marker = MARKERS / event["session_id"]
    if should_nudge(event, marker):
        MARKERS.mkdir(parents=True, exist_ok=True)
        marker.touch()
        print(json.dumps({"decision": "block", "reason": REASON}))


if __name__ == "__main__":
    main()
