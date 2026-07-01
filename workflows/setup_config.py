# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""setup_config.py — write and validate config/hub.config.yaml.

The ONE config file for the hub. The `/setup-config` skill collects answers
interactively, then calls this script with them as JSON on stdin. Everything
project-specific lives in the file this produces; nothing is hardcoded elsewhere.

Usage:
    echo '<answers-json>' | uv run workflows/setup_config.py write
    uv run workflows/setup_config.py validate      # check the existing file

Answers JSON shape (all fields optional; sensible defaults applied):
    {
      "project_name": "My Project",
      "connectors": {
        "sentry": {"enabled": true, "org": "my-org", "projects": ["backend"]},
        "gitlab": {"enabled": true, "group": "my-group", "flag_stale_mrs_days": 3},
        "notion": {"enabled": false, "watch_pages": []},
        "slack":  {"enabled": false, "channels": []}
      }
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "hub.config.yaml"

# Non-secret selectors only. Auth lives in the Claude app / MCP connectors.
DEFAULTS = {
    "project_name": "CHANGEME",
    "connectors": {
        "sentry": {"enabled": False, "org": "", "projects": []},
        "gitlab": {"enabled": False, "group": "", "flag_stale_mrs_days": 3},
        "notion": {"enabled": False, "workspace": "", "watch_pages": []},
        "slack": {"enabled": False, "channels": []},
    },
    "output_dir": "./data",
}

HEADER = (
    "# Claude Ops Hub — the ONE project-specific file (git-ignored).\n"
    "# Written by the /setup-config skill. Connector AUTH lives in the Claude\n"
    "# app / MCP connectors, never here — only non-secret selectors below.\n"
)


def _merge(base: dict, override: dict) -> dict:
    """Deep-merge override into a copy of base (dicts only)."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def build_config(answers: dict) -> dict:
    """Merge interactive answers onto defaults, producing the full config dict."""
    return _merge(DEFAULTS, answers or {})


def validate(cfg: dict) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a config dict."""
    errors: list[str] = []
    warnings: list[str] = []

    name = cfg.get("project_name", "")
    if not name or name == "CHANGEME":
        errors.append("project_name is unset (still 'CHANGEME').")

    connectors = cfg.get("connectors", {}) or {}
    enabled = {k: v for k, v in connectors.items() if (v or {}).get("enabled")}
    if not enabled:
        errors.append("No connectors enabled — the hub would have nothing to read.")

    required = {"sentry": "org", "gitlab": "group"}
    for conn, field in required.items():
        c = connectors.get(conn, {}) or {}
        if c.get("enabled") and not c.get(field):
            errors.append(f"connectors.{conn}.enabled but '{field}' is empty.")

    slack = connectors.get("slack", {}) or {}
    if slack.get("enabled") and not (slack.get("channels") or []):
        warnings.append("connectors.slack.enabled but no channels listed.")

    warnings.append(
        "Connector auth lives in the Claude app / MCP — present in cloud routines, "
        "but local runs may lack it and return empty findings."
    )
    return errors, warnings


def write_config(cfg: dict) -> Path:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    CONFIG_PATH.write_text(HEADER + "\n" + body)
    return CONFIG_PATH


def _report(errors: list[str], warnings: list[str]) -> int:
    for w in warnings:
        print(f"  warn:  {w}")
    for e in errors:
        print(f"  ERROR: {e}")
    if errors:
        print(f"\n{len(errors)} error(s) — fix config/hub.config.yaml.")
        return 1
    print("\nConfig looks good.")
    return 0


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "validate"

    if cmd == "write":
        answers = json.loads(sys.stdin.read() or "{}")
        cfg = build_config(answers)
        path = write_config(cfg)
        print(f"Wrote {path}")
        errors, warnings = validate(cfg)
        return _report(errors, warnings)

    if cmd == "validate":
        if not CONFIG_PATH.exists():
            print(f"{CONFIG_PATH} not found — run /setup-config first.", file=sys.stderr)
            return 2
        cfg = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        errors, warnings = validate(cfg)
        return _report(errors, warnings)

    print(f"unknown command: {cmd} (use: write | validate)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
