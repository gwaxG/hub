"""Minimal YAML-front-matter reader (stdlib only).

Handles exactly the subset the vault uses: a leading ``---`` fenced block of
``key: scalar`` pairs, block lists (``key:`` then ``  - item`` lines) and inline
lists (``key: [a, b]``). Not a general YAML parser — hooks need something fast
with no dependency. Workflows that write front-matter use PyYAML instead.
"""

from __future__ import annotations

from pathlib import Path

_FENCE = "---"


def parse(text: str) -> tuple[dict, str]:
    """Split *text* into ``(metadata, body)``. No front-matter → ``({}, text)``."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _FENCE:
        return {}, text
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == _FENCE)
    except StopIteration:
        return {}, text
    meta = _parse_block(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    return meta, body


def load(path: Path | str) -> tuple[dict, str]:
    return parse(Path(path).read_text(encoding="utf-8"))


def _parse_block(lines: list[str]) -> dict:
    meta: dict = {}
    key: str | None = None
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")) and raw.lstrip().startswith("- "):
            if key is not None:  # continuation of a block list
                meta.setdefault(key, [])
                if isinstance(meta[key], list):
                    meta[key].append(_scalar(raw.lstrip()[2:]))
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key, value = key.strip(), value.strip()
        meta[key] = _value(value) if value else []
    return meta


def _value(value: str):
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_scalar(v) for v in inner.split(",")] if inner else []
    return _scalar(value)


def _scalar(value: str):
    value = value.strip().strip("'\"")
    return value
