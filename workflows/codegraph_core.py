"""codegraph_core.py — shared analysis engine for the code-graph workflows.

Not a script: imported by `workflows/code_graph.py` (whole-repo report) and
`workflows/mr_graph.py` (feature-integration report). Both run under `uv run`
with the same PEP 723 dependency set, and Python puts the script's own
directory on `sys.path`, so a plain `import codegraph_core` resolves — no
packaging, no install (the hub stays `package = false`).

Everything here is read-only with respect to the analysed repository: grimp's
on-disk cache is disabled, and a historical revision is materialised with
`git archive` into `hub/tmp` rather than by checking anything out.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tarfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import grimp
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze as raw_analyze

# ---------------------------------------------------------------------------
# Hardcoded config
# ---------------------------------------------------------------------------
HUB_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = HUB_ROOT / "workflows" / "templates"
OUT_ROOT = (
    HUB_ROOT / "tmp" / "code-graph"
)  # hub/tmp holds generated artefacts (gitignored)

# Directories never treated as an analysable top-level package.
IGNORED_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    "build",
    "dist",
    "docs",
    "static",
    "templates",
}
# Module-name substrings dropped from the graph (generated / non-design code).
DEFAULT_EXCLUDES = ["migrations", "alembic.versions", "node_modules"]

# Above this many modules the report collapses to package nodes unless told otherwise.
AUTO_PACKAGE_THRESHOLD = 150
MODULE_LAYER_DEPTH = 2  # at module level, a node's layer is its first 2 dotted segments
DEFAULT_SINCE = "1 year ago"
HOTSPOT_LIMIT = 40


@dataclass
class FileMetrics:
    """Structural + complexity metrics for one source file."""

    loc: int = 0
    cc_max: int = 0
    cc_total: int = 0
    mi: float = 100.0
    classes: int = 0
    abstract: int = 0


@dataclass
class FileChurn:
    """Git history for one source file over the requested window."""

    shas: set[str] = field(default_factory=set)
    added: int = 0
    deleted: int = 0
    authors: set[str] = field(default_factory=set)
    last: int = 0


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def packages_in(base: Path) -> list[str]:
    """Names of the importable packages directly under `base`."""
    if not base.is_dir():
        return []
    return [
        child.name
        for child in sorted(base.iterdir())
        if child.is_dir()
        and not child.name.startswith(".")
        and child.name not in IGNORED_DIRS
        and (child / "__init__.py").is_file()
    ]


def discover_packages(root: Path) -> tuple[Path, list[str]]:
    """Find the sys.path root and the packages under it — (base, names).

    Three layouts are recognised:
      src      `<repo>/src/<pkg>/`          -> base = src
      flat     `<repo>/<pkg>/`              -> base = repo
      Django   `<repo>/<proj>/manage.py`    -> base = <proj>, packages = its apps

    The Django case matters: `<proj>` has an `__init__.py` so it looks like the
    package, but `manage.py` puts `<proj>` itself on sys.path — so the code
    imports `api.models`, not `<proj>.api.models`. Analysing `<proj>` as the
    package resolves every intra-project import as external and silently yields
    an almost edgeless graph. Override with `--root` when the guess is wrong.
    """
    for base in (root / "src", root):
        names = packages_in(base)
        if not names:
            continue
        django = [n for n in names if (base / n / "manage.py").is_file()]
        if len(django) == 1:
            inner = packages_in(base / django[0])
            if inner:
                return base / django[0], inner
        return base, names
    return root, []


def module_file(name: str, base: Path) -> Path | None:
    """Resolve a dotted module name to its file, or None if it has no source."""
    rel = Path(*name.split("."))
    for candidate in (base / rel.with_suffix(".py"), base / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Import graph
# ---------------------------------------------------------------------------
def build_import_graph(
    base: Path, names: list[str], excludes: list[str]
) -> tuple[list[str], list[tuple[str, str]]]:
    """Return (modules, edges) for the given packages, minus excluded modules.

    `cache_dir=None` keeps grimp from writing a cache into the analysed repo.
    """
    sys.path.insert(0, str(base))
    try:
        graph = grimp.build_graph(
            *names, include_external_packages=False, cache_dir=None
        )
    finally:
        sys.path.remove(str(base))  # two snapshots may share package names
    keep = sorted(m for m in graph.modules if not any(x in m for x in excludes))
    kept = set(keep)
    edges = [
        (src, dst)
        for src in keep
        for dst in graph.find_modules_directly_imported_by(src)
        if dst in kept
    ]
    return keep, edges


def node_id(module: str, level: str, depth: int) -> str:
    """Map a module to its node id — itself, or its package truncated to `depth`."""
    if level == "module":
        return module
    return ".".join(module.split(".")[:depth])


def layer_depth_for(level: str, depth: int) -> int:
    """How many segments a layer name keeps — always one coarser than a node.

    Otherwise layers and nodes coincide and the layer-coupling matrix carries no
    information beyond the node graph (which is exactly the case that matters:
    a big repo analysed at package level).
    """
    return MODULE_LAYER_DEPTH if level == "module" else max(1, depth - 1)


def layer_of(node: str, depth: int) -> str:
    """A node's layer — its id truncated to `depth` dotted segments."""
    return ".".join(node.split(".")[:depth])


# ---------------------------------------------------------------------------
# Per-file metrics
# ---------------------------------------------------------------------------
def abstractness(tree: ast.Module) -> tuple[int, int]:
    """Count (classes, abstract classes) — ABC/Protocol bases or @abstractmethod."""
    classes = abstract = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        classes += 1
        bases = {ast.unparse(b).split(".")[-1] for b in node.bases}
        has_abstract_method = any(
            ast.unparse(d).split(".")[-1] in {"abstractmethod", "abstractproperty"}
            for child in node.body
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            for d in child.decorator_list
        )
        if bases & {"ABC", "ABCMeta", "Protocol"} or has_abstract_method:
            abstract += 1
    return classes, abstract


def file_metrics(path: Path) -> FileMetrics:
    """Measure one source file; an unparsable file yields zeroed metrics."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return FileMetrics()
    blocks = cc_visit(source)
    classes, abstract = abstractness(tree)
    return FileMetrics(
        loc=raw_analyze(source).sloc,
        cc_max=max((b.complexity for b in blocks), default=0),
        cc_total=sum(b.complexity for b in blocks),
        mi=round(mi_visit(source, True), 1),
        classes=classes,
        abstract=abstract,
    )


# ---------------------------------------------------------------------------
# Git history
# ---------------------------------------------------------------------------
def git(root: Path, *args: str) -> str:
    """Run a read-only git command in `root`, returning stdout ('' on failure)."""
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return done.stdout if done.returncode == 0 else ""


def git_churn(root: Path, since: str, rev: str | None = None) -> dict[str, FileChurn]:
    """Per-file commit/author/line churn over the window, keyed by repo-relative path.

    `rev` limits history to that commit's ancestry, so a base snapshot is scored
    on the history it actually had — not on the feature commits that follow it.
    """
    log = git(
        root,
        "log",
        "--no-merges",
        f"--since={since}",
        "--numstat",
        "--format=__C__%H\t%an\t%at",
        *([rev] if rev else []),
    )
    churn: dict[str, FileChurn] = defaultdict(FileChurn)
    sha = author = ""
    stamp = 0
    for line in log.splitlines():
        if line.startswith("__C__"):
            sha, author, raw_stamp = line[5:].split("\t")
            stamp = int(raw_stamp)
            continue
        parts = line.split("\t")
        if len(parts) != 3 or not parts[2].endswith(".py"):
            continue
        added, deleted, path = parts
        path = path.split(" => ")[-1].rstrip("}")  # renames: a/{old => new}/b.py
        entry = churn[path]
        entry.shas.add(sha)
        entry.added += int(added) if added.isdigit() else 0
        entry.deleted += int(deleted) if deleted.isdigit() else 0
        entry.authors.add(author)
        entry.last = max(entry.last, stamp)
    return churn


# ---------------------------------------------------------------------------
# Graph analysis
# ---------------------------------------------------------------------------
def tarjan_sccs(adj: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one member, largest first.

    Iterative Tarjan — a recursive one blows the stack on a repo the size of wilson.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    found: list[list[str]] = []

    for root, children in adj.items():
        if root in index:
            continue
        work: list[tuple[str, list[str]]] = [(root, sorted(children))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, pending = work[-1]
            if pending:
                child = pending.pop()
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, sorted(adj.get(child, ()))))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1:
                    found.append(sorted(component))
    return sorted(found, key=len, reverse=True)


def topological_order(
    records: list[dict], edge_weights: Counter[tuple[str, str]], cycles: list[list[str]]
) -> list[int]:
    """Order nodes so imports run one way — importers first, imported last.

    Cycles are condensed into one unit (they have no internal order), so in the
    resulting dependency matrix every ordinary import lands above the diagonal
    and anything *below* it is a genuine back-edge. Without this the triangle a
    cell falls in would just reflect alphabetical luck.
    """
    component: dict[str, tuple[str, object]] = {}
    for i, group in enumerate(cycles):
        for member in group:
            component[member] = ("scc", i)
    names = [r["id"] for r in records]
    for name in names:
        component.setdefault(name, ("node", name))

    successors: dict[tuple, set[tuple]] = defaultdict(set)
    indegree: dict[tuple, int] = {c: 0 for c in component.values()}
    for src, dst in edge_weights:
        tail, head = component[src], component[dst]
        if tail == head or head in successors[tail]:
            continue
        successors[tail].add(head)
        indegree[head] += 1

    ready = sorted((c for c, d in indegree.items() if d == 0), key=str)
    order: list[tuple] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for nxt in sorted(successors[current], key=str):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=str)
    placed = set(order)
    order += sorted((c for c in indegree if c not in placed), key=str)

    members: dict[tuple, list[str]] = defaultdict(list)
    for name in names:
        members[component[name]].append(name)
    position = {r["id"]: i for i, r in enumerate(records)}
    return [position[name] for c in order for name in sorted(members[c])]


# ---------------------------------------------------------------------------
# Payload assembly
# ---------------------------------------------------------------------------
def collect_nodes(
    modules: list[str],
    base: Path,
    root: Path,
    churn: dict[str, FileChurn],
    level: str,
    depth: int,
) -> tuple[dict[str, dict], list[dict]]:
    """Fold per-file metrics into node records, and rank per-file hotspots.

    Returns (nodes by id, hotspot rows) — hotspots stay per-file because
    churn x complexity is only meaningful at file granularity.
    """
    nodes: dict[str, dict] = {}
    files: list[dict] = []
    for module in modules:
        path = module_file(module, base)
        if path is None:
            continue
        metrics = file_metrics(path)
        rel = path.relative_to(root).as_posix()
        history = churn.get(rel, FileChurn())
        files.append(
            {
                "path": rel,
                "loc": metrics.loc,
                "cc_max": metrics.cc_max,
                "mi": metrics.mi,
                "commits": len(history.shas),
                "churn": history.added + history.deleted,
                "authors": len(history.authors),
            }
        )
        node = nodes.setdefault(
            node_id(module, level, depth),
            {
                "loc": 0,
                "files": 0,
                "paths": [],
                "cc_max": 0,
                "cc_total": 0,
                "mi": [],
                "classes": 0,
                "abstract": 0,
                "shas": set(),
                "churn": 0,
                "authors": set(),
                "last": 0,
            },
        )
        node["loc"] += metrics.loc
        node["files"] += 1
        node["paths"].append(rel)
        node["cc_max"] = max(node["cc_max"], metrics.cc_max)
        node["cc_total"] += metrics.cc_total
        node["mi"].append(metrics.mi)
        node["classes"] += metrics.classes
        node["abstract"] += metrics.abstract
        node["shas"] |= history.shas
        node["churn"] += history.added + history.deleted
        node["authors"] |= history.authors
        node["last"] = max(node["last"], history.last)
    return nodes, rank_hotspots(files)


def rank_hotspots(files: list[dict]) -> list[dict]:
    """Score files by normalised churn x complexity, worst first."""
    max_churn = max((f["churn"] for f in files), default=0) or 1
    max_cc = max((f["cc_max"] for f in files), default=0) or 1
    for f in files:
        f["score"] = round((f["churn"] / max_churn) * (f["cc_max"] / max_cc), 4)
    ranked = sorted(files, key=lambda f: f["score"], reverse=True)
    return [f for f in ranked if f["score"] > 0][:HOTSPOT_LIMIT]


def finalise_nodes(
    nodes: dict[str, dict],
    edge_weights: Counter[tuple[str, str]],
    layer_depth: int,
) -> list[dict]:
    """Turn the accumulators into ordered node records with the coupling metrics."""
    fan_out: Counter[str] = Counter()
    fan_in: Counter[str] = Counter()
    for (src, dst), weight in edge_weights.items():
        fan_out[src] += weight
        fan_in[dst] += weight

    records = []
    for node_key, acc in sorted(nodes.items()):
        ca, ce = fan_in[node_key], fan_out[node_key]
        instability = round(ce / (ca + ce), 3) if ca + ce else 0.0
        abstract_ratio = (
            round(acc["abstract"] / acc["classes"], 3) if acc["classes"] else 0.0
        )
        records.append(
            {
                "id": node_key,
                "layer": layer_of(node_key, layer_depth),
                "paths": sorted(acc["paths"]),
                "files": acc["files"],
                "loc": acc["loc"],
                "ca": ca,
                "ce": ce,
                "i": instability,
                "a": abstract_ratio,
                "dist": round(abs(abstract_ratio + instability - 1), 3),
                "cc_max": acc["cc_max"],
                "cc_total": acc["cc_total"],
                "mi": round(sum(acc["mi"]) / len(acc["mi"]), 1) if acc["mi"] else 100.0,
                "commits": len(acc["shas"]),
                "churn": acc["churn"],
                "authors": len(acc["authors"]),
                "last": acc["last"],
            }
        )
    return records


def layer_matrix(records: list[dict], edge_weights: Counter[tuple[str, str]]) -> dict:
    """Aggregate edges into a layer-by-layer coupling matrix."""
    layers = sorted({r["layer"] for r in records})
    position = {name: i for i, name in enumerate(layers)}
    matrix = [[0] * len(layers) for _ in layers]
    node_layer = {r["id"]: r["layer"] for r in records}
    for (src, dst), weight in edge_weights.items():
        matrix[position[node_layer[src]]][position[node_layer[dst]]] += weight
    return {"layers": layers, "matrix": matrix}


# ---------------------------------------------------------------------------
# Analysis entry point
# ---------------------------------------------------------------------------
@dataclass
class Options:
    """One analysis request.

    `tree_root` is where the source files live and `git_root` is where history
    is read from — they differ when analysing a historical revision, whose tree
    is extracted into `hub/tmp` but whose churn comes from the real repository.
    """

    tree_root: Path
    git_root: Path
    rev: str | None = None  # limit churn history to this commit's ancestry
    root: Path | None = None  # explicit sys.path dir; None = auto-detect
    packages: list[str] = field(default_factory=list)
    level: str = "auto"
    depth: int = 2
    since: str = DEFAULT_SINCE
    excludes: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    label: str = ""  # prefix on progress lines, e.g. "base" / "head"
    quiet: bool = False


def resolve_packages(opts: Options) -> tuple[Path, list[str]]:
    """Settle the sys.path root and the package list for an analysis."""
    base, names = discover_packages(opts.tree_root)
    if opts.root:
        base = opts.root if opts.root.is_absolute() else opts.tree_root / opts.root
        names = packages_in(base)
    packages = opts.packages or names
    if not packages:
        raise SystemExit(f"ERROR: no importable package found under {base}")
    return base, packages


def analyse(opts: Options) -> dict:
    """Analyse one source tree and return the full JSON payload for a template."""
    tag = f"[{opts.label}] " if opts.label else ""

    def say(message: str) -> None:
        if not opts.quiet:
            print(f"  {tag}{message}", flush=True)

    base, packages = resolve_packages(opts)
    say(f"root       : {base}")
    say(f"packages   : {', '.join(packages)}")

    modules, edges = build_import_graph(base, packages, opts.excludes)
    if modules and len(edges) < len(modules) / 4:
        print(
            f"  {tag}WARNING    : only {len(edges)} imports across {len(modules)} modules —"
            " the sys.path root is probably wrong, so intra-project imports resolve"
            f" as external. Try --root <dir> (currently {base.name}/).",
            file=sys.stderr,
        )

    level = opts.level
    if level == "auto":
        level = "package" if len(modules) > AUTO_PACKAGE_THRESHOLD else "module"
    say(f"modules    : {len(modules)} ({len(edges)} imports) -> level={level}")

    churn = git_churn(opts.git_root, opts.since, opts.rev)
    say("measuring  : complexity + coupling ...")
    nodes, hotspots = collect_nodes(
        modules, base, opts.tree_root, churn, level, opts.depth
    )

    edge_weights = Counter(
        (node_id(src, level, opts.depth), node_id(dst, level, opts.depth))
        for src, dst in edges
    )
    for src, dst in list(edge_weights):
        if src == dst or src not in nodes or dst not in nodes:
            del edge_weights[(src, dst)]

    records = finalise_nodes(nodes, edge_weights, layer_depth_for(level, opts.depth))
    order = {r["id"]: i for i, r in enumerate(records)}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for src, dst in edge_weights:
        adjacency[src].add(dst)
    cycles = tarjan_sccs({r["id"]: adjacency[r["id"]] for r in records})
    say(f"nodes      : {len(records)}, cycles: {len(cycles)}")

    rev = opts.rev or "HEAD"
    return {
        "meta": {
            "repo": opts.git_root.name,
            "path": str(opts.git_root),
            "root": str(base),
            "packages": packages,
            "level": level,
            "depth": opts.depth,
            "since": opts.since,
            "excluded": opts.excludes,
            "modules": len(modules),
            "imports": len(edges),
            "rev": rev,
            "branch": git(opts.git_root, "rev-parse", "--abbrev-ref", rev).strip(),
            "commit": git(opts.git_root, "rev-parse", "--short", rev).strip(),
            "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        },
        "nodes": records,
        "edges": [
            {"s": order[src], "t": order[dst], "w": weight}
            for (src, dst), weight in sorted(edge_weights.items())
        ],
        "cycles": cycles,
        "dsm_order": topological_order(records, edge_weights, cycles),
        "hotspots": hotspots,
        **layer_matrix(records, edge_weights),
    }


def snapshot(repo: Path, rev: str, dest: Path) -> Path:
    """Materialise a revision's tree under `dest` via `git archive`.

    Deliberately not `git worktree` / `git checkout`: archiving touches neither
    the mirror's working tree nor its `.git` metadata, so a repo being analysed
    cannot be left dirty or half-switched if this is interrupted.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for stale in dest.iterdir():
        if stale.is_dir():
            shutil.rmtree(stale)
        else:
            stale.unlink()
    archive = dest.parent / f"{dest.name}.tar"
    with archive.open("wb") as handle:
        done = subprocess.run(
            ["git", "-C", str(repo), "archive", "--format=tar", rev],
            stdout=handle,
            stderr=subprocess.PIPE,
            check=False,
        )
    if done.returncode != 0:
        archive.unlink(missing_ok=True)
        raise SystemExit(
            f"ERROR: git archive {rev} failed — {done.stderr.decode().strip()}"
        )
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="data")
    archive.unlink()
    return dest


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(
    payload: dict, template: Path, out_dir: Path, name: str, tokens: dict
) -> Path:
    """Fill a report template and write `<out_dir>/<name>.{html,json}`.

    `STYLE`, `HELPERS` and `PAYLOAD` are supplied here so every template shares
    one stylesheet and one set of browser helpers; the caller adds the rest.
    """
    filled = {
        "STYLE": (TEMPLATES / "_shared.css").read_text(encoding="utf-8"),
        "HELPERS": (TEMPLATES / "_shared.js").read_text(encoding="utf-8"),
        "PAYLOAD": json.dumps(payload, separators=(",", ":")),
        **tokens,
    }
    html = template.read_text(encoding="utf-8")
    for key, value in filled.items():
        html = html.replace("{{" + key + "}}", value)
    if "{{" in html:
        leftover = html[html.index("{{") : html.index("{{") + 40]
        raise SystemExit(f"ERROR: unfilled template token near {leftover!r}")

    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / f"{name}.html"
    report.write_text(html, encoding="utf-8")
    (out_dir / f"{name}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    return report
