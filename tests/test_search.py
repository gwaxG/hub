import pytest

from hub_lib import paths, search


@pytest.fixture
def vault(tmp_path):
    for m in paths._ROOT_MARKERS:
        (tmp_path / m).write_text("", encoding="utf-8") if "." in m else (
            tmp_path / m
        ).mkdir()
    docs = tmp_path / "docs"
    (docs / "domain").mkdir(parents=True)
    (docs / "workflows").mkdir(parents=True)
    (docs / "domain" / "players.md").write_text(
        "---\ntitle: Player entity\ntype: domain\nstatus: current\n---\n\n"
        "A player has a status and a lifecycle.\n",
        encoding="utf-8",
    )
    (docs / "workflows" / "match.md").write_text(
        "---\ntitle: Match creation\ntype: workflow\nstatus: current\n---\n\n"
        "The match creation pipeline has ordered stages.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_extract_terms_drops_stopwords_and_short():
    assert search.extract_terms("How do I add the player status") == [
        "player",
        "status",
    ]


def test_search_ranks_title_match_first(vault):
    hits = search.search(vault, ["player"])
    assert hits[0][1] == "docs/domain/players.md"


def test_search_matches_body(vault):
    hits = search.search(vault, ["pipeline"])
    assert [h[1] for h in hits] == ["docs/workflows/match.md"]


def test_search_type_filter(vault):
    assert search.search(vault, ["status"], type_filter="workflow") == []
    assert search.search(vault, ["status"], type_filter="domain")


def test_search_empty_terms_returns_nothing(vault):
    assert search.search(vault, []) == []
