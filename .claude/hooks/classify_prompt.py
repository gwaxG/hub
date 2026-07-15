#!/usr/bin/env python3
"""UserPromptSubmit hook — deterministic task classification.

Cheap keyword match → task category → pointers to the relevant docs/ folders.
No repo-wide analysis, no LLM. Stays silent when the category is unknown.
"""

from __future__ import annotations

from _common import emit_context, read_event  # noqa: E402


def build_context(prompt: str) -> str:
    from hub_lib import classify

    category = classify.classify(prompt)
    pointers = classify.doc_pointers(category)
    if category == "unknown" or not pointers:
        return ""
    return (
        f"Prompt looks like: {category}. Relevant curated docs to consult and keep "
        f"current: {', '.join(pointers)}."
    )


def main() -> int:
    event = read_event()
    try:
        emit_context("UserPromptSubmit", build_context(event.get("prompt", "")))
    except Exception:  # never block a prompt
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
