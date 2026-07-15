"""Shared helpers for the hub's stdlib-only hooks.

Hooks run via ``uv run --no-project`` (no dependency resolution). Importing this
module puts the hub root on ``sys.path`` so ``hub_lib`` is available. Every hook
stays defensive: a hook must never crash the tool it observes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# .claude/hooks/_common.py → hub root is two levels up from the hooks dir.
HUB_ROOT = Path(__file__).resolve().parents[2]
if str(HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(HUB_ROOT))


def read_event() -> dict:
    """Parse the hook event JSON from stdin; tolerate empty/garbage input."""
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def emit_context(event_name: str, text: str) -> None:
    """Inject additional context (SessionStart / UserPromptSubmit / PostToolUse)."""
    if not text:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event_name,
                    "additionalContext": text,
                }
            }
        )
    )


def deny(reason: str) -> None:
    """Emit a PreToolUse denial for the observed tool call."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
