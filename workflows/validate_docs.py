# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""validate_docs.py — full curated-vault validation.

Strict YAML front matter, internal links, required metadata, duplicate titles,
generated-file markers, source-path existence (staleness), and unresolved-queue
summary. Writes docs/memory/{stale-docs,last-validation}.json and exits non-zero
when hard errors are present.

    uv run workflows/validate_docs.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import paths, queue, validate  # noqa: E402


def split_front_matter(text: str) -> tuple[str | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :])
    return None, text


def validate_doc(
    doc: Path, hub_root: Path, errors: list[str], stale: list[dict]
) -> str | None:
    rel = doc.relative_to(hub_root).as_posix()
    raw, body = split_front_matter(doc.read_text(encoding="utf-8"))
    if raw is None:
        errors.append(f"{rel}: missing YAML front matter")
        return None
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        errors.append(f"{rel}: invalid YAML front matter ({exc.__class__.__name__})")
        return None
    errors += [f"{rel}: {e}" for e in validate.check_frontmatter(meta)]
    errors += [f"{rel}: {e}" for e in validate.check_internal_links(doc, body)]
    for reason in validate.check_source_paths_exist(meta, hub_root):
        stale.append({"doc": rel, "reason": reason})
    if meta.get("status") == "deprecated":
        stale.append({"doc": rel, "reason": "status is deprecated"})
    return meta.get("title")


def check_duplicate_titles(titles: dict[str, list[str]], errors: list[str]) -> None:
    for title, docs in titles.items():
        if title and len(docs) > 1:
            errors.append(f"duplicate title {title!r} in: {', '.join(docs)}")


def check_generated_markers(hub_root: Path, errors: list[str]) -> None:
    gen = paths.generated_dir(hub_root)
    for f in sorted(gen.rglob("*")) if gen.exists() else []:
        if not f.is_file() or f.name == "README.md":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if f.suffix == ".json" and '"generated_by"' not in text:
            errors.append(
                f"{f.relative_to(hub_root)}: generated JSON missing 'generated_by'"
            )
        elif f.suffix == ".md" and not validate.has_generated_banner(text):
            errors.append(
                f"{f.relative_to(hub_root)}: generated Markdown missing banner"
            )


def main() -> int:
    hub_root = paths.find_hub_root(Path.cwd())
    errors: list[str] = []
    stale: list[dict] = []
    titles: dict[str, list[str]] = {}

    for doc in paths.iter_curated_docs(hub_root):
        title = validate_doc(doc, hub_root, errors, stale)
        titles.setdefault(title or "", []).append(doc.relative_to(hub_root).as_posix())

    check_duplicate_titles(titles, errors)
    check_generated_markers(hub_root, errors)

    memory = paths.memory_dir(hub_root)
    pending = queue.pending_count(memory)
    _write_stale(memory, stale)
    validate.write_report(memory, errors, pending)

    print(
        f"validated {sum(1 for _ in paths.iter_curated_docs(hub_root))} curated doc(s)"
    )
    print(
        f"  errors: {len(errors)} | stale: {len(stale)} | unresolved queue: {pending}"
    )
    for e in errors:
        print(f"  ✗ {e}")
    for s in stale:
        print(f"  ~ {s['doc']}: {s['reason']}")
    return 1 if errors else 0


def _write_stale(memory: Path, stale: list[dict]) -> None:
    memory.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stale": stale,
    }
    (memory / "stale-docs.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
