from datetime import UTC, datetime
from pathlib import Path

from monitor.log import append_tick


def test_append_tick_writes_one_line_per_tick(tmp_path: Path):
    when = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)

    append_tick(tmp_path, 3, when, "GREEN", "0 issues, 12 errors (baseline 11)")
    append_tick(tmp_path, 4, when, "YELLOW", "1 new issue")

    lines = (tmp_path / "monitor-log.md").read_text().splitlines()
    assert lines == [
        "- 2026-11-24T10:00Z tick 3 GREEN: 0 issues, 12 errors (baseline 11)",
        "- 2026-11-24T10:00Z tick 4 YELLOW: 1 new issue",
    ]
