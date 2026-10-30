# /// script
# requires-python = ">=3.11"
# ///
"""Stop hook: ask Claude to record learnings in docs/ after costly work that wrote no note."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

HUB = Path(__file__).resolve().parents[2]
MARKERS = HUB / "tmp" / "docs-nudge"
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
SUBAGENT_TOOLS = {"Agent", "Task"}
WORK_COMMANDS = ("git commit", "git push", "merge_requests")
SHELL_WRITES = (" > ", ">>", "sed -i", "cp ", "mv ", "tee ")
MIN_TOOL_CALLS = 25
MIN_DURATION = timedelta(minutes=20)
REASON = (
    "Before finishing: this stretch of work was costly. Check MEMORY.md, then record anything not "
    "already covered: a workflow or runbook, how a system or architecture works, a root cause, a "
    "rollout rule, an MR's design, or any finding that took real time or tokens to reach. Add or update "
    "a note in the hub docs/ lake per CLAUDE.md (frontmatter, MEMORY.md line, "
    "`uv run workflows/lint_docs.py`). If nothing qualifies, reply 'nothing for docs' and stop."
)


@dataclass
class ToolUse:
    name: str
    input: dict
    at: datetime | None


class Transcript:
    def __init__(self, path: Path, start: int = 0) -> None:
        self.tool_uses = list(self._tool_uses(path))[start:]

    @staticmethod
    def _tool_uses(path: Path):
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            content = (entry.get("message") or {}).get("content")
            if entry.get("type") != "assistant" or not isinstance(content, list):
                continue
            stamp = entry.get("timestamp")
            at = datetime.fromisoformat(stamp) if stamp else None
            for c in content:
                if c.get("type") == "tool_use":
                    yield ToolUse(c["name"], c.get("input") or {}, at)

    def wrote_docs(self) -> bool:
        edits = any(
            self._is_docs_path(u.input.get("file_path", "")) for u in self._writes()
        )
        shell = any(
            "docs/" in cmd and any(w in cmd for w in SHELL_WRITES)
            for cmd in self._commands()
        )
        return edits or shell

    def shipped_work(self) -> bool:
        code_writes = any(
            not self._is_docs_path(u.input.get("file_path", "")) for u in self._writes()
        )
        mr_calls = any("merge_request" in u.name for u in self.tool_uses)
        commits = any(w in c for c in self._commands() for w in WORK_COMMANDS)
        return code_writes or mr_calls or commits

    def investigated(self) -> bool:
        times = [u.at for u in self.tool_uses if u.at]
        long_running = bool(times) and max(times) - min(times) >= MIN_DURATION
        subagents = any(u.name in SUBAGENT_TOOLS for u in self.tool_uses)
        return len(self.tool_uses) >= MIN_TOOL_CALLS or subagents or long_running

    def _writes(self):
        return (u for u in self.tool_uses if u.name in WRITE_TOOLS)

    def _commands(self):
        return (u.input.get("command", "") for u in self.tool_uses if u.name == "Bash")

    @staticmethod
    def _is_docs_path(path: str) -> bool:
        hub_docs = "/docs/" in path and "/workspace/" not in path
        return hub_docs or path.endswith("MEMORY.md")


class NudgeMarker:
    """Tool-call count at the session's last nudge; only work after it counts."""

    def __init__(self, session_id: str) -> None:
        self.path = MARKERS / session_id

    def offset(self) -> int:
        return int(self.path.read_text() or 0) if self.path.exists() else 0

    def save(self, offset: int) -> None:
        MARKERS.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(offset))


def main() -> None:
    event = json.load(sys.stdin)
    if event.get("stop_hook_active"):
        return
    marker = NudgeMarker(event["session_id"])
    window = Transcript(Path(event["transcript_path"]), marker.offset())
    costly = window.shipped_work() or window.investigated()
    if costly and not window.wrote_docs():
        marker.save(marker.offset() + len(window.tool_uses))
        print(json.dumps({"decision": "block", "reason": REASON}))


if __name__ == "__main__":
    main()
