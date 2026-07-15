from hub_lib import validate


def test_check_frontmatter_valid():
    meta = {"title": "X", "type": "workflow", "status": "current"}
    assert validate.check_frontmatter(meta) == []


def test_check_frontmatter_missing_and_invalid():
    errors = validate.check_frontmatter({"type": "nonsense", "status": "weird"})
    assert any("title" in e for e in errors)
    assert any("invalid type" in e for e in errors)
    assert any("invalid status" in e for e in errors)


def test_extract_internal_links_ignores_external():
    body = "See [a](../domain/x.md) and [ext](https://e.com/y.md) and [anchor](z.md#h)."
    assert validate.extract_internal_links(body) == ["../domain/x.md", "z.md"]


def test_check_internal_links_flags_dead(tmp_path):
    (tmp_path / "domain").mkdir()
    (tmp_path / "domain" / "real.md").write_text("ok", encoding="utf-8")
    doc = tmp_path / "workflows" / "w.md"
    doc.parent.mkdir()
    doc.write_text("x", encoding="utf-8")
    body = "[live](../domain/real.md) [dead](../domain/missing.md)"
    errors = validate.check_internal_links(doc, body)
    assert errors == ["dead link: ../domain/missing.md"]


def test_has_generated_banner():
    assert validate.has_generated_banner("<!-- generated: refresh_graph.py -->\n# x")
    assert not validate.has_generated_banner("# hand written")


def test_check_source_paths_exist(tmp_path):
    (tmp_path / "workspace" / "repo").mkdir(parents=True)
    meta = {"source_paths": ["workspace/repo", "workspace/gone"]}
    errors = validate.check_source_paths_exist(meta, tmp_path)
    assert errors == ["source path no longer exists: workspace/gone"]
