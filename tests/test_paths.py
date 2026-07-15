import pytest

from hub_lib import paths


@pytest.fixture
def hub_root(tmp_path):
    for marker in paths._ROOT_MARKERS:
        target = tmp_path / marker
        if "." in marker:
            target.write_text("", encoding="utf-8")
        else:
            target.mkdir()
    (tmp_path / "docs" / "generated").mkdir(parents=True)
    (tmp_path / "workspace" / "grp" / "repo").mkdir(parents=True)
    return tmp_path


def test_find_hub_root_from_nested(hub_root):
    nested = hub_root / "workspace" / "grp" / "repo"
    assert paths.find_hub_root(nested) == hub_root


def test_find_hub_root_raises_when_absent(tmp_path):
    with pytest.raises(FileNotFoundError):
        paths.find_hub_root(tmp_path)


def test_is_workspace_path(hub_root):
    assert paths.is_workspace_path(
        hub_root / "workspace" / "grp" / "repo" / "a.py", hub_root
    )
    assert not paths.is_workspace_path(hub_root / "docs" / "x.md", hub_root)


def test_is_generated_doc(hub_root):
    assert paths.is_generated_doc(
        hub_root / "docs" / "generated" / "index.md", hub_root
    )
    assert not paths.is_generated_doc(hub_root / "docs" / "domain" / "x.md", hub_root)


def test_is_worktree_path():
    assert paths.is_worktree_path("/home/u/dev/hub/.claude/worktrees/foo/x.py")
    assert not paths.is_worktree_path("/home/u/dev/hub/workspace/grp/repo/x.py")


def test_map_source_to_docs_prefix_match():
    entries = [
        {
            "doc": "docs/workflows/match.md",
            "source_paths": ["workspace/wilson/src/matches/"],
        },
        {
            "doc": "docs/domain/player.md",
            "source_paths": ["workspace/wilson/src/players/"],
        },
    ]
    hits = paths.map_source_to_docs("workspace/wilson/src/matches/create.py", entries)
    assert hits == ["docs/workflows/match.md"]


def test_map_source_to_docs_no_false_prefix():
    entries = [{"doc": "docs/x.md", "source_paths": ["workspace/wilson/src/match"]}]
    # "match" must not match "matches" as a directory prefix
    assert paths.map_source_to_docs("workspace/wilson/src/matches/x.py", entries) == []
