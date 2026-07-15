#!/usr/bin/env python3
"""UserPromptSubmit hook — deterministic task classification + knowledge surfacing.

Cheap and LLM-free: (1) keyword-classify the prompt and point at the relevant
docs/ folders, and (2) search the vault for the prompt's terms and inject the top
matching docs so existing knowledge is surfaced before Claude answers.
"""

from __future__ import annotations

from _common import HUB_ROOT, emit_context, read_event  # noqa: E402

_MAX_HITS = 3


def _classification_line(prompt: str) -> str | None:
    from hub_lib import classify

    category = classify.classify(prompt)
    pointers = classify.doc_pointers(category)
    if category == "unknown" or not pointers:
        return None
    return (
        f"Prompt looks like: {category}. Relevant curated docs to consult and keep "
        f"current: {', '.join(pointers)}."
    )


def _knowledge_lines(prompt: str) -> list[str]:
    from hub_lib import paths, search

    if not paths.docs_dir(HUB_ROOT).exists():
        return []
    terms = search.extract_terms(prompt)
    hits = search.search(HUB_ROOT, terms, limit=_MAX_HITS)
    if not hits:
        return []
    lines = ["Possibly relevant vault knowledge (verify against source):"]
    lines += [f"  - {rel} — {title}" for _score, rel, title, _snip in hits]
    return lines


def build_context(prompt: str) -> str:
    parts = []
    classification = _classification_line(prompt)
    if classification:
        parts.append(classification)
    parts += _knowledge_lines(prompt)
    return "\n".join(parts)


def main() -> int:
    event = read_event()
    try:
        emit_context("UserPromptSubmit", build_context(event.get("prompt", "")))
    except Exception:  # never block a prompt
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
