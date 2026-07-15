import pytest

from hub_lib import classify


@pytest.mark.parametrize(
    "prompt, expected",
    [
        ("Fix the failing login bug", "bugfix"),
        ("Add a new REST endpoint for players", "interface_change"),
        ("Document the deployment topology", "documentation_only"),
        ("Change the match creation pipeline", "workflow_change"),
        ("Update the pulumi infrastructure and alerts", "operations_change"),
        ("Clarify the domain invariant for player status", "domain_change"),
        ("Write an ADR about the new architecture boundary", "architecture_change"),
        ("Rename this variable and extract a helper", "refactor"),
        ("What time is it", "unknown"),
    ],
)
def test_classify(prompt, expected):
    assert classify.classify(prompt) == expected


def test_doc_pointers_known_and_unknown():
    assert "docs/interfaces/" in classify.doc_pointers("interface_change")
    assert classify.doc_pointers("unknown") == []
