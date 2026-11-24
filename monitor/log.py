from datetime import UTC, datetime
from pathlib import Path

from monitor.verdict import Verdict

LOG_NAME = "monitor-log.md"


def append_tick(
    folder: Path, tick: int, when: datetime, verdict: Verdict, summary: str
) -> None:
    line = f"- {_stamp(when)} tick {tick} {verdict}: {_one_line(summary)}\n"
    with (folder / LOG_NAME).open("a") as log:
        log.write(line)


def _stamp(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def _one_line(text: str) -> str:
    return " ".join(text.split())
