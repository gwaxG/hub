import json

import pytest

from hub_lib import generate, paths


@pytest.fixture
def vault(tmp_path):
    for m in paths._ROOT_MARKERS:
        (tmp_path / m).write_text("", encoding="utf-8") if "." in m else (
            tmp_path / m
        ).mkdir()
    docs = tmp_path / "docs"
    (docs / "graph" / "repositories").mkdir(parents=True)
    (docs / "workflows").mkdir(parents=True)
    (docs / "graph" / "repositories" / "wilson.md").write_text(
        "---\ntitle: wilson\ntype: graph\nstatus: current\n"
        "related:\n  - ../../workflows/match.md\n---\n\nThe monolith.\n",
        encoding="utf-8",
    )
    (docs / "workflows" / "match.md").write_text(
        "---\ntitle: Match creation\ntype: workflow\nstatus: current\n"
        "source_paths:\n  - workspace/wilson/src/matches/\n---\n\nStages.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_build_graph_nodes_edges_and_banner(vault):
    nodes, edges, target = generate.build_graph(vault)
    assert [n["id"] for n in nodes] == ["graph/repositories/wilson.md"]
    assert edges == [
        {"from": "graph/repositories/wilson.md", "to": "../../workflows/match.md"}
    ]
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["generated_by"] == "workflows/refresh_graph.py"


def test_build_source_map_collects_source_paths(vault):
    entries, target = generate.build_source_map(vault)
    assert entries == [
        {
            "doc": "docs/workflows/match.md",
            "title": "Match creation",
            "type": "workflow",
            "source_paths": ["workspace/wilson/src/matches/"],
        }
    ]
    assert (
        json.loads(target.read_text(encoding="utf-8"))["generated_by"]
        == "workflows/source_map.py"
    )
