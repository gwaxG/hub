from hub_lib import frontmatter

DOC = """---
title: Match creation workflow
type: workflow
status: current
owners:
  - backend
systems: [wilson, orion]
source_paths:
  - workspace/backend/wilson/src/matches/
related: []
last_verified: 2026-07-15
---

# Body starts here

Some prose.
"""


def test_parse_scalars_and_lists():
    meta, body = frontmatter.parse(DOC)
    assert meta["title"] == "Match creation workflow"
    assert meta["type"] == "workflow"
    assert meta["owners"] == ["backend"]
    assert meta["systems"] == ["wilson", "orion"]
    assert meta["source_paths"] == ["workspace/backend/wilson/src/matches/"]
    assert meta["related"] == []
    assert body.startswith("\n# Body starts here")


def test_no_frontmatter_returns_empty_meta():
    meta, body = frontmatter.parse("# Just a heading\n")
    assert meta == {}
    assert body == "# Just a heading\n"


def test_unterminated_fence_is_not_frontmatter():
    meta, body = frontmatter.parse("---\ntitle: x\nno closing fence\n")
    assert meta == {}


def test_load_from_file(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(DOC, encoding="utf-8")
    meta, _ = frontmatter.load(p)
    assert meta["status"] == "current"
