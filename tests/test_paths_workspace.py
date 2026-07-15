import pytest

from hub_lib import paths


@pytest.fixture
def hub(tmp_path):
    for m in paths._ROOT_MARKERS:
        (tmp_path / m).write_text("", encoding="utf-8") if "." in m else (
            tmp_path / m
        ).mkdir()
    (tmp_path / "docs" / "graph" / "repositories").mkdir(parents=True)
    (tmp_path / "workspace" / "grp").mkdir(parents=True)
    return tmp_path


def _make_repo(hub, name):
    repo = hub / "workspace" / "grp" / name
    (repo / ".git").mkdir(parents=True)
    return repo


def test_iter_workspace_repos_finds_git_dirs(hub):
    _make_repo(hub, "wilson")
    _make_repo(hub, "football")
    names = sorted(p.name for p in paths.iter_workspace_repos(hub))
    assert names == ["football", "wilson"]


def test_iter_workspace_repos_does_not_descend_into_repo(hub):
    repo = _make_repo(hub, "wilson")
    (repo / "sub").mkdir()
    (repo / "sub" / ".git").mkdir()  # nested repo must be ignored, not double-counted
    names = [p.name for p in paths.iter_workspace_repos(hub)]
    assert names == ["wilson"]


def test_un_ingested_repos_tracks_graph_nodes(hub):
    _make_repo(hub, "wilson")
    _make_repo(hub, "football")
    assert paths.un_ingested_repos(hub) == ["football", "wilson"]
    paths.graph_node_for_repo(hub, "wilson").write_text(
        "---\ntitle: wilson\ntype: graph\nstatus: current\n---\n", encoding="utf-8"
    )
    assert paths.un_ingested_repos(hub) == ["football"]
