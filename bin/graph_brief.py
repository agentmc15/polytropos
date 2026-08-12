#!/usr/bin/env python3
"""Read a graphify graph.json and print an architect-grounding brief.

This engine only ever READS a `graph.json` file that a human already produced by
running the external `graphify` CLI (https://github.com/Graphify-Labs/graphify, the
`graphifyy` uv tool). It never invokes the `graphify` binary itself — graphify is an
external, user-installed tool that this repo never vendors, installs, or shells out to.
Every code path here is a pure, offline JSON reader.

graphifyy is a v0.9 tool, so the shape of graph.json is treated as MEASURED-not-promised:
every key access goes through `.get(...)`, a top-level `edges` list is accepted as an
alias for `links` when `links` is absent, and nodes/links missing expected keys degrade
into `(none)` buckets rather than raising.
"""

import argparse
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

DEFAULT_GRAPH_PATH = "graphify-out/graph.json"

HUBS_EXCL_TESTS_LABEL = (
    "hubs excluding tests/ (test fixtures can dominate raw degree -- on the repo this "
    "tool was calibrated against, tests/ held 54% of node mass and topped the "
    "all-files hub list)"
)

LOW_CROSS_FILE_WARNING = (
    "LOW CROSS-FILE VISIBILITY -- dynamic loaders (importlib, plugin registries) are "
    "invisible to AST extraction; this graph under-represents cross-module coupling. "
    "Verify dependencies by reading the code, not by absence of edges."
)

LOW_CROSS_FILE_RATIO_THRESHOLD = 0.05


# --------------------------------------------------------------------------- loading

def load_graph(path):
    """Load a graph.json file at `path` (str or Path).

    Returns (data, error) where exactly one is None. `error` is a one-line string
    naming what was expected, suitable for printing directly -- never a traceback.
    """
    p = Path(path)
    try:
        raw = p.read_text()
    except OSError:
        return None, "missing"
    except UnicodeDecodeError as exc:
        return None, (
            f"{path} is not valid UTF-8 ({exc}) -- expected a graphify graph.json "
            "(graphify can embed non-UTF-8 source snippets in link 'context' fields "
            "when extracting from latin-1 or other non-UTF-8 source files)"
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"could not parse {path} as JSON: {exc}"

    if not isinstance(data, dict):
        return None, f"expected a JSON object at the top level of {path}, got {type(data).__name__}"

    has_nodes = "nodes" in data
    has_links = "links" in data or "edges" in data
    if not has_nodes and not has_links:
        return None, (
            f"{path} is missing both 'nodes' and 'links'/'edges' -- expected a graphify "
            "graph.json (networkx node-link JSON)"
        )

    return data, None


def _links_of(data):
    links = data.get("links")
    if links is None:
        links = data.get("edges")
    if not isinstance(links, list):
        return []
    return links


def _nodes_of(data):
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return []
    return nodes


# --------------------------------------------------------------------------- brief sections

def compute_counts(nodes, links):
    communities = {n.get("community") for n in nodes if n.get("community") is not None}
    files = {n.get("source_file") for n in nodes if n.get("source_file") is not None}
    return {
        "nodes": len(nodes),
        "links": len(links),
        "communities": len(communities),
        "files": len(files),
    }


def compute_relation_mix(links):
    counts = Counter()
    for link in links:
        relation = link.get("relation") or "(none)"
        counts[relation] += 1
    return counts.most_common()


def compute_directory_mass(nodes):
    counts = Counter()
    for node in nodes:
        source_file = node.get("source_file")
        if not source_file:
            counts["(none)"] += 1
            continue
        # top-level directory of a relative path; a bare filename has no directory
        parts = str(source_file).replace("\\", "/").split("/")
        top_dir = parts[0] if len(parts) > 1 else "(none)"
        counts[top_dir] += 1
    return counts.most_common()


def _node_index(nodes):
    """Map node id -> node dict, tolerating nodes without an 'id' key."""
    index = {}
    for node in nodes:
        node_id = node.get("id")
        if node_id is not None:
            index[node_id] = node
    return index


def _degrees(nodes, links):
    """Return {node_id: degree} counted over `links` for every node in `nodes`."""
    degree = Counter()
    for node in nodes:
        node_id = node.get("id")
        if node_id is not None:
            degree[node_id] += 0  # ensure every node is present, even degree-0
    for link in links:
        source = link.get("source")
        target = link.get("target")
        if source is not None:
            degree[source] += 1
        if target is not None:
            degree[target] += 1
    return degree


def compute_hubs(nodes, links, top_n, exclude_tests=False):
    index = _node_index(nodes)
    if exclude_tests:
        keep_ids = {
            node_id
            for node_id, node in index.items()
            if not str(node.get("source_file") or "").startswith("tests/")
        }
        filtered_nodes = [n for n in nodes if n.get("id") in keep_ids]
        filtered_links = [
            link
            for link in links
            if link.get("source") in keep_ids and link.get("target") in keep_ids
        ]
    else:
        filtered_nodes = nodes
        filtered_links = links

    degree = _degrees(filtered_nodes, filtered_links)
    ranked = sorted(degree.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    hubs = []
    for node_id, deg in ranked:
        node = index.get(node_id, {})
        hubs.append({
            "id": node_id,
            "label": node.get("label") or node.get("norm_label") or str(node_id),
            "degree": deg,
            "source_file": node.get("source_file"),
            "source_location": node.get("source_location"),
        })
    return hubs


def compute_confidence_mix(links):
    counts = Counter()
    for link in links:
        confidence = link.get("confidence") or "(none)"
        counts[confidence] += 1
    return counts.most_common()


def compute_cross_file_ratio(nodes, links):
    """Return (ratio, cross_file_count, total_call_count_with_both_source_files)."""
    index = _node_index(nodes)
    total = 0
    cross = 0
    for link in links:
        if link.get("relation") != "calls":
            continue
        source_node = index.get(link.get("source"))
        target_node = index.get(link.get("target"))
        if source_node is None or target_node is None:
            continue
        source_file = source_node.get("source_file")
        target_file = target_node.get("source_file")
        if not source_file or not target_file:
            continue
        total += 1
        if source_file != target_file:
            cross += 1
    ratio = (cross / total) if total else 0.0
    return ratio, cross, total


def build_brief(data, top_n):
    # a negative --top is a slice artifact, not a request to drop hubs off the end --
    # normalize it to 0 (renders the same "(none)" empty-hub form as an explicit 0).
    top_n = max(top_n, 0)
    nodes = _nodes_of(data)
    links = _links_of(data)

    counts = compute_counts(nodes, links)
    relation_mix = compute_relation_mix(links)
    directory_mass = compute_directory_mass(nodes)
    hubs_all = compute_hubs(nodes, links, top_n, exclude_tests=False)
    hubs_excl_tests = compute_hubs(nodes, links, top_n, exclude_tests=True)
    confidence_mix = compute_confidence_mix(links)
    cross_file_ratio, cross_file_count, cross_file_total = compute_cross_file_ratio(nodes, links)
    low_cross_file_warning = (
        cross_file_total == 0 or cross_file_ratio < LOW_CROSS_FILE_RATIO_THRESHOLD
    )

    return {
        "counts": counts,
        "relation_mix": relation_mix,
        "directory_mass": directory_mass,
        "hubs_all": hubs_all,
        "hubs_excl_tests": hubs_excl_tests,
        "hubs_excl_tests_label": HUBS_EXCL_TESTS_LABEL,
        "confidence_mix": confidence_mix,
        "cross_file_call_ratio": cross_file_ratio,
        "cross_file_call_count": cross_file_count,
        "cross_file_call_total": cross_file_total,
        "low_cross_file_warning": low_cross_file_warning,
        "low_cross_file_warning_text": LOW_CROSS_FILE_WARNING if low_cross_file_warning else None,
    }


# --------------------------------------------------------------------------- rendering

def _format_hub_line(hub):
    source_file = hub.get("source_file") or "(none)"
    source_location = hub.get("source_location") or "(none)"
    return f"  {hub['label']}  degree={hub['degree']}  {source_file}:{source_location}"


def render_brief(brief):
    lines = []
    counts = brief["counts"]
    lines.append(
        f"nodes={counts['nodes']} links={counts['links']} "
        f"communities={counts['communities']} files={counts['files']}"
    )

    lines.append("")
    lines.append("relation mix:")
    if brief["relation_mix"]:
        for relation, count in brief["relation_mix"]:
            lines.append(f"  {relation}: {count}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("per-directory mass:")
    if brief["directory_mass"]:
        for directory, count in brief["directory_mass"]:
            lines.append(f"  {directory}: {count}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("hubs (all files):")
    if brief["hubs_all"]:
        for hub in brief["hubs_all"]:
            lines.append(_format_hub_line(hub))
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"{brief['hubs_excl_tests_label']}:")
    if brief["hubs_excl_tests"]:
        for hub in brief["hubs_excl_tests"]:
            lines.append(_format_hub_line(hub))
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("confidence mix:")
    if brief["confidence_mix"]:
        for confidence, count in brief["confidence_mix"]:
            lines.append(f"  {confidence}: {count}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append(
        f"cross-file call ratio: {brief['cross_file_call_count']}/"
        f"{brief['cross_file_call_total']} = {brief['cross_file_call_ratio']:.3f}"
    )
    if brief["low_cross_file_warning"]:
        lines.append("")
        lines.append(brief["low_cross_file_warning_text"])

    return "\n".join(lines)


# --------------------------------------------------------------------------- subcommands

def cmd_brief(args):
    data, error = load_graph(args.graph)
    if error == "missing":
        print(
            f"no graph at {args.graph} -- run `graphify update <repo>` first "
            "(graphify is an external, user-installed tool; this repo never installs "
            "or invokes it)"
        )
        return 0
    if error is not None:
        print(error)
        return 2

    brief = build_brief(data, args.top)
    if args.json:
        print(json.dumps(brief, indent=2, sort_keys=True))
    else:
        print(render_brief(brief))
    return 0


# --------------------------------------------------------------------------- demo data

def _demo_normal_graph():
    """A small, illustrative graph.json with healthy cross-file call visibility.

    Synthetic -- not derived from any real graphify output. Exists only so `demo` has
    something to brief without ever touching a real file or the real `graphify` binary.
    """
    nodes = [
        {"id": "app.main.run", "label": "run", "norm_label": "run",
         "source_file": "app/main.py", "source_location": "L10", "community": 0},
        {"id": "app.utils.helper", "label": "helper", "norm_label": "helper",
         "source_file": "app/utils.py", "source_location": "L4", "community": 0},
        {"id": "app.utils.other_helper", "label": "other_helper", "norm_label": "other_helper",
         "source_file": "app/utils.py", "source_location": "L12", "community": 0},
        {"id": "tests.test_main.test_run", "label": "test_run", "norm_label": "test_run",
         "source_file": "tests/test_main.py", "source_location": "L3", "community": 1},
    ]
    links = [
        {"source": "app.main.run", "target": "app.utils.helper", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "app/main.py", "source_location": "L10"},
        {"source": "app.utils.helper", "target": "app.utils.other_helper", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "app/utils.py", "source_location": "L4"},
        {"source": "tests.test_main.test_run", "target": "app.main.run", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "tests/test_main.py", "source_location": "L3"},
        {"source": "app.main.run", "target": "app.utils.other_helper", "relation": "contains",
         "confidence": "EXTRACTED"},
    ]
    return {"nodes": nodes, "links": links, "directed": True}


def _demo_low_ratio_graph():
    """A small graph.json seeded so almost every call is same-file -- demonstrates the
    low-cross-file-visibility warning without needing a real graphify run."""
    nodes = [
        {"id": "pkg.mod.a", "label": "a", "norm_label": "a",
         "source_file": "pkg/mod.py", "source_location": "L1", "community": 0},
        {"id": "pkg.mod.b", "label": "b", "norm_label": "b",
         "source_file": "pkg/mod.py", "source_location": "L5", "community": 0},
        {"id": "pkg.mod.c", "label": "c", "norm_label": "c",
         "source_file": "pkg/mod.py", "source_location": "L9", "community": 0},
    ]
    links = [
        {"source": "pkg.mod.a", "target": "pkg.mod.b", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "pkg/mod.py", "source_location": "L1"},
        {"source": "pkg.mod.b", "target": "pkg.mod.c", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "pkg/mod.py", "source_location": "L5"},
    ]
    return {"nodes": nodes, "links": links, "directed": True}


def cmd_demo(args):
    """Synthetic smoke: build two throwaway graph.json files in a tempfile.mkdtemp
    tree, brief both, print both cards, and always exit 0.

    No real graph.json is ever read here -- the demo subparser accepts no `--graph`
    (or any other path argument), so this command cannot resolve into the real cwd
    repo by construction. The temp tree is removed in a `finally` regardless of
    success or failure.
    """
    tmpdir = tempfile.mkdtemp(prefix="graph_brief_demo_")
    try:
        normal_path = Path(tmpdir) / "demo_graph.json"
        normal_path.write_text(json.dumps(_demo_normal_graph()))
        normal_data, normal_error = load_graph(normal_path)
        print("=== graph_brief demo: normal repo shape (synthetic, no graphify run) ===")
        if normal_error is not None:
            print(normal_error)
        else:
            print(render_brief(build_brief(normal_data, 8)))

        print()

        low_path = Path(tmpdir) / "demo_graph_low_ratio.json"
        low_path.write_text(json.dumps(_demo_low_ratio_graph()))
        low_data, low_error = load_graph(low_path)
        print("=== graph_brief demo: seeded low cross-file visibility (synthetic) ===")
        if low_error is not None:
            print(low_error)
        else:
            print(render_brief(build_brief(low_data, 8)))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return 0


# --------------------------------------------------------------------------- CLI

def build_parser():
    ap = argparse.ArgumentParser(
        prog="graph_brief.py",
        description=(
            "Read a graphify graph.json (READ-ONLY) and print an architect-grounding "
            "brief. Never invokes the graphify binary -- graphify is an external, "
            "user-installed tool this repo never vendors."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_brief = sub.add_parser("brief", help="render a repo-shape brief from a graph.json")
    p_brief.add_argument(
        "--graph", default=DEFAULT_GRAPH_PATH,
        help=f"path to graph.json (default: {DEFAULT_GRAPH_PATH}, relative to cwd)",
    )
    p_brief.add_argument(
        "--top", type=int, default=8, help="how many hubs to list per hub section (default: 8)",
    )
    p_brief.add_argument("--json", action="store_true", help="machine-readable output")
    p_brief.set_defaults(func=cmd_brief)

    p_demo = sub.add_parser(
        "demo",
        help=(
            "synthetic smoke: build two throwaway graph.json files in a tempfile.mkdtemp "
            "tree, brief both, and exit 0 -- no real files, no graphify binary"
        ),
    )
    p_demo.set_defaults(func=cmd_demo)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
