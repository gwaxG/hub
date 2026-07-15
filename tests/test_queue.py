from hub_lib import queue


def test_append_and_read_roundtrip(tmp_path):
    rec = queue.make_record(
        "workspace/a/x.py",
        "Edit",
        ["docs/workflows/a.md"],
        ts="2026-01-01T00:00:00+00:00",
    )
    queue.append_record(tmp_path, rec)
    queue.append_record(
        tmp_path,
        queue.make_record("workspace/a/y.py", "Write", ts="2026-01-01T00:00:01+00:00"),
    )
    records = queue.read_records(tmp_path)
    assert len(records) == 2
    assert records[0]["source_path"] == "workspace/a/x.py"
    assert records[0]["resolved"] is False


def test_read_missing_file_is_empty(tmp_path):
    assert queue.read_records(tmp_path) == []


def test_read_skips_malformed_lines(tmp_path):
    path = tmp_path / queue.QUEUE_FILENAME
    path.write_text('{"source_path": "workspace/a"}\nnot json\n\n', encoding="utf-8")
    records = queue.read_records(tmp_path)
    assert len(records) == 1


def test_dedup_unions_candidate_docs(tmp_path):
    records = [
        queue.make_record("workspace/a/x.py", "Edit", ["docs/one.md"]),
        queue.make_record("workspace/a/x.py", "Edit", ["docs/two.md"]),
    ]
    deduped = queue.dedup(records)
    assert len(deduped) == 1
    assert deduped[0]["candidate_docs"] == ["docs/one.md", "docs/two.md"]


def test_unresolved_filters_resolved():
    records = [
        {"source_path": "a", "resolved": True},
        {"source_path": "b", "resolved": False},
        {"source_path": "c"},
    ]
    assert {r["source_path"] for r in queue.unresolved(records)} == {"b", "c"}


def test_resolve_removes_matching_records(tmp_path):
    for name in ("x", "y", "z"):
        queue.append_record(
            tmp_path, queue.make_record(f"workspace/a/{name}.py", "Edit")
        )
    removed = queue.resolve(tmp_path, {"workspace/a/x.py", "workspace/a/z.py"})
    assert removed == 2
    remaining = queue.read_records(tmp_path)
    assert [r["source_path"] for r in remaining] == ["workspace/a/y.py"]


def test_pending_count(tmp_path):
    queue.append_record(tmp_path, queue.make_record("workspace/a/x.py", "Edit"))
    assert queue.pending_count(tmp_path) == 1
