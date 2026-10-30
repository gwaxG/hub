# /// script
# requires-python = ">=3.11"
# ///
"""Lint the docs/ file lake: frontmatter, MEMORY.md index links, orphans, stale notes."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent
DOCS = HUB / "docs"
INDEX = HUB / "MEMORY.md"
REQUIRED_KEYS = ("repo", "verified_at")
NON_NOTES = {"README.md"}
LINK = re.compile(r"\]\(([^)#\s]+)")
CODE_SPAN = re.compile(r"`[^`\n]*`")


@dataclass
class Note:
    path: Path
    meta: dict[str, str] | None
    body: str

    @classmethod
    def load(cls, path: Path) -> Note:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            return cls(path, None, text)
        head, body = text[4:].split("\n---\n", 1)
        pairs = (line.split(":", 1) for line in head.splitlines() if ":" in line)
        return cls(path, {k.strip(): v.strip() for k, v in pairs}, body)

    @property
    def verified_at(self) -> date | None:
        try:
            return date.fromisoformat((self.meta or {}).get("verified_at", ""))
        except ValueError:
            return None


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def print(self) -> None:
        for label, items in (("ERROR", self.errors), ("WARN", self.warnings)):
            for item in items:
                print(f"{label}  {item}")
        print(f"\n{len(self.errors)} error(s), {len(self.warnings)} warning(s)")


class DocsLinter:
    def __init__(self, stale_days: int) -> None:
        self.stale_before = date.today() - timedelta(days=stale_days)
        self.report = Report()

    def run(self) -> Report:
        notes = [
            Note.load(p) for p in sorted(DOCS.glob("*.md")) if p.name not in NON_NOTES
        ]
        for note in notes:
            self._check_frontmatter(note)
            self._check_links(note.path, note.body)
        self._check_index({p.name for p in DOCS.iterdir() if p.name not in NON_NOTES})
        return self.report

    def _check_frontmatter(self, note: Note) -> None:
        name = note.path.name
        if note.meta is None:
            self.report.errors.append(f"{name}: no frontmatter")
            return
        missing = [k for k in REQUIRED_KEYS if not note.meta.get(k, "").strip("[] ")]
        if missing:
            self.report.errors.append(f"{name}: missing {', '.join(missing)}")
        elif note.verified_at is None:
            self.report.errors.append(f"{name}: verified_at is not YYYY-MM-DD")
        elif note.verified_at < self.stale_before:
            self.report.warnings.append(
                f"{name}: stale, verified_at {note.verified_at}"
            )

    def _check_links(self, path: Path, text: str) -> None:
        for target in LINK.findall(CODE_SPAN.sub("", text)):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).exists():
                self.report.errors.append(
                    f"{path.relative_to(HUB)}: dead link {target}"
                )

    def _check_index(self, files: set[str]) -> None:
        text = INDEX.read_text(encoding="utf-8")
        self._check_links(INDEX, text)
        indexed = {Path(t).name for t in LINK.findall(text) if t.startswith("docs/")}
        for orphan in sorted(files - indexed):
            self.report.errors.append(f"{orphan}: not listed in MEMORY.md")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stale-days", type=int, default=90)
    report = DocsLinter(parser.parse_args().stale_days).run()
    report.print()
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
