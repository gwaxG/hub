"""Deterministic keyword classifier for prompts (UserPromptSubmit hook).

Cheap and dumb on purpose: map a prompt to a likely task category, then point at
the curated ``docs/`` folders worth consulting. No LLM, no repo scan.
"""

from __future__ import annotations

import re

# Ordered: first category whose pattern matches wins. Keep specific before broad.
_RULES: list[tuple[str, str]] = [
    ("documentation_only", r"\b(docs?|document\w*|readme|changelog|comment\w*)\b"),
    ("architecture_change", r"\b(architect\w*|topology|boundary|decision|adr)\b"),
    (
        "interface_change",
        r"\b(apis?|endpoint\w*|schema\w*|contract\w*|event\w*|queue\w*|topic\w*|payload\w*|graphql)\b",
    ),
    (
        "workflow_change",
        r"\b(pipeline\w*|workflow\w*|ingest\w*|publish\w*|deliver\w*|reprocess\w*|state machine|sfn|step function)\b",
    ),
    (
        "domain_change",
        r"\b(domain\w*|business rule|invariant\w*|entit(y|ies)|glossary|lifecycle)\b",
    ),
    (
        "operations_change",
        r"\b(deploy\w*|infra\w*|pulumi|terraform|dashboard\w*|alert\w*|runbook\w*|rollback|ecs|lambda)\b",
    ),
    ("bugfix", r"\b(bugs?|fix\w*|broken|regression|error|crash\w*|failing)\b"),
    (
        "refactor",
        r"\b(refactor\w*|rename\w*|clean ?up|extract\w*|simplif\w*|restructure\w*)\b",
    ),
]

# Which vault folders each category should consult.
_POINTERS: dict[str, list[str]] = {
    "architecture_change": [
        "docs/architecture/",
        "docs/architecture/decisions/",
        "docs/graph/",
    ],
    "interface_change": ["docs/interfaces/", "docs/graph/"],
    "workflow_change": ["docs/workflows/", "docs/runbooks/"],
    "domain_change": ["docs/domain/"],
    "operations_change": ["docs/operations/", "docs/runbooks/"],
    "bugfix": ["docs/runbooks/", "docs/workflows/"],
    "refactor": ["docs/architecture/", "docs/development/"],
    "documentation_only": ["docs/"],
    "unknown": [],
}


def classify(prompt: str) -> str:
    text = (prompt or "").lower()
    for category, pattern in _RULES:
        if re.search(pattern, text):
            return category
    return "unknown"


def doc_pointers(category: str) -> list[str]:
    return _POINTERS.get(category, [])
