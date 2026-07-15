"""Deterministic ranked search over the curated vault (stdlib only).

Shared by the `/find-project-knowledge` workflow and the UserPromptSubmit hook
(per-prompt relevant-doc injection). Keyword-scored, title-weighted — it finds
candidates; ranking meaning is left to an agent.
"""

from __future__ import annotations

import re
from pathlib import Path

from hub_lib import frontmatter, paths

_TITLE_WEIGHT = 5
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "into",
    "you",
    "your",
    "are",
    "was",
    "were",
    "can",
    "could",
    "should",
    "would",
    "will",
    "have",
    "has",
    "how",
    "what",
    "when",
    "where",
    "why",
    "who",
    "which",
    "please",
    "run",
    "add",
    "use",
    "using",
    "get",
    "set",
    "let",
    "new",
    "all",
    "any",
    "not",
    "but",
    "our",
}


def extract_terms(prompt: str, limit: int = 8) -> list[str]:
    """Meaningful lowercase tokens from a prompt (drops stopwords and <3 chars)."""
    terms: list[str] = []
    for tok in re.findall(r"[a-z0-9]+", (prompt or "").lower()):
        if len(tok) >= 3 and tok not in _STOPWORDS and tok not in terms:
            terms.append(tok)
    return terms[:limit]


def score(terms: list[str], title: str, body: str) -> int:
    title_l, body_l = title.lower(), body.lower()
    return sum(_TITLE_WEIGHT * title_l.count(t) + body_l.count(t) for t in terms)


def snippet(terms: list[str], body: str) -> str:
    for line in body.splitlines():
        low = line.lower()
        if line.strip() and any(t in low for t in terms):
            return line.strip()[:120]
    return ""


def search(
    hub_root: Path,
    terms: list[str],
    type_filter: str | None = None,
    limit: int | None = None,
) -> list[tuple[int, str, str, str]]:
    """Return ``(score, relpath, title, snippet)`` for matching docs, best first."""
    if not terms:
        return []
    results = []
    for doc in paths.iter_curated_docs(hub_root):
        meta, body = frontmatter.load(doc)
        if type_filter and meta.get("type") != type_filter:
            continue
        title = meta.get("title", doc.stem)
        s = score(terms, title, body)
        if s:
            results.append(
                (s, doc.relative_to(hub_root).as_posix(), title, snippet(terms, body))
            )
    results.sort(reverse=True)
    return results[:limit] if limit else results
