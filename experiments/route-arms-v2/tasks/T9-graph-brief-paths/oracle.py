import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "bin"
SCRATCH_ROOT = ROOT / ".route_oracle_tmp"


def _load():
    spec = importlib.util.spec_from_file_location(
        "route_oracle_graph_brief", BIN_DIR / "graph_brief.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gb = _load()


def _node(node_id, label=None, **extra):
    node = {"id": node_id, "label": label if label is not None else node_id}
    node.update(extra)
    return node


def _link(source, target, relation="calls", **extra):
    link = {"source": source, "target": target, "relation": relation}
    link.update(extra)
    return link


class GraphFixture:
    def __init__(self, graph, filename="graph.json"):
        self.graph = graph
        self.filename = filename
        self.tmp = None
        self.path = None

    def __enter__(self):
        SCRATCH_ROOT.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="graph_paths_", dir=SCRATCH_ROOT)
        self.path = Path(self.tmp.name) / self.filename
        self.path.write_text(json.dumps(self.graph), encoding="utf-8")
        return self.path

    def __exit__(self, exc_type, exc, tb):
        self.tmp.cleanup()
        try:
            SCRATCH_ROOT.rmdir()
        except OSError:
            pass
        return False


def _run(argv):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = gb.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def _base_graph():
    nodes = [
        _node("A", "start"),
        _node("B", "bee"),
        _node("C", "see"),
        _node("D", "finish"),
        _node("E", "elsewhere"),
        _node("Z", "isolated"),
    ]
    links = [
        _link("A", "B"),
        _link("A", "C"),
        _link("B", "D"),
        _link("C", "D"),
        _link("D", "E"),
        _link("C", "A"),  # cycle back toward A; shortest paths must stay simple
        _link("missing", "D"),
        {"source": "A"},
        {"target": "B"},
    ]
    return {"nodes": nodes, "links": links, "directed": False}


def _payload_from_json(out):
    return json.loads(out)


class PathsCliSuccessTests(unittest.TestCase):
    def test_forward_text_lists_all_shortest_paths_in_lexicographic_order(self):
        with GraphFixture(_base_graph()) as path:
            code, out, err = _run(["paths", "A", "D", "--graph", str(path)])
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out,
            "shortest paths from A to D (hops=2, count=2, direction=forward):\n"
            "  1. A -> B -> D\n"
            "  2. A -> C -> D\n",
        )

    def test_label_lookup_works_when_id_does_not_match(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "start", "finish", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("shortest paths from A to D", out)

    def test_exact_id_wins_over_label_match_elsewhere(self):
        graph = {
            "nodes": [_node("target", "not-it"), _node("X", "target"), _node("Y", "end")],
            "links": [_link("target", "Y"), _link("X", "target")],
        }
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "target", "Y", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("  1. target -> Y\n", out)
        self.assertNotIn("X -> target", out)

    def test_success_json_has_exact_keys_and_node_summaries(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "A", "D", "--graph", str(path), "--json"])
        self.assertEqual(code, 0)
        payload = _payload_from_json(out)
        self.assertEqual(
            list(payload.keys()),
            ["direction", "end", "hops", "max_hops", "path_count", "paths", "shown_path_count", "start", "truncated"],
        )
        self.assertEqual(payload["start"], {"id": "A", "label": "start"})
        self.assertEqual(payload["end"], {"id": "D", "label": "finish"})
        self.assertEqual(payload["paths"], [["A", "B", "D"], ["A", "C", "D"]])
        self.assertFalse(payload["truncated"])

    def test_top_level_edges_alias_is_used_for_paths(self):
        graph = _base_graph()
        graph["edges"] = graph.pop("links")
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "A", "D", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("count=2", out)

    def test_stringified_numeric_ids_are_supported(self):
        graph = {"nodes": [_node(1, "one"), _node(2, "two")], "links": [_link(1, 2)]}
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "1", "2", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("shortest paths from 1 to 2", out)


class DirectionAndLimitTests(unittest.TestCase):
    def test_forward_direction_does_not_walk_edges_backwards(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "D", "A", "--graph", str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "no path from D to A within 8 hops (direction=forward)\n")

    def test_reverse_direction_walks_edges_backwards(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "D", "A", "--direction", "reverse", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("direction=reverse", out)
        self.assertIn("D -> B -> A", out)
        self.assertIn("D -> C -> A", out)

    def test_both_direction_allows_backward_single_hop(self):
        graph = {"nodes": [_node("A"), _node("B")], "links": [_link("A", "B")]}
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "B", "A", "--direction", "both", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[1], "  1. B -> A")

    def test_top_level_directed_flag_is_ignored(self):
        graph = {"nodes": [_node("A"), _node("B")], "links": [_link("A", "B")], "directed": False}
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "B", "A", "--graph", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("direction=forward", out)

    def test_max_hops_blocks_longer_existing_path(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "A", "D", "--max-hops", "1", "--graph", str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "no path from A to D within 1 hops (direction=forward)\n")

    def test_zero_hop_same_endpoint_succeeds(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "A", "A", "--max-hops", "0", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(out, "shortest paths from A to A (hops=0, count=1, direction=forward):\n  1. A\n")

    def test_zero_hop_different_endpoint_fails(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "A", "B", "--max-hops", "0", "--graph", str(path)])
        self.assertEqual(code, 1)
        self.assertIn("within 0 hops", out)

    def test_invalid_negative_max_hops_uses_argparse_status_two(self):
        with GraphFixture(_base_graph()) as path:
            code, _out, err = _run(["paths", "A", "B", "--max-hops", "-1", "--graph", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("--max-hops", err)

    def test_invalid_zero_max_paths_uses_argparse_status_two(self):
        with GraphFixture(_base_graph()) as path:
            code, _out, err = _run(["paths", "A", "B", "--max-paths", "0", "--graph", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("--max-paths", err)


class ErrorOutputTests(unittest.TestCase):
    def test_not_found_text_status_two(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "missing-node", "D", "--graph", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "node not found for query 'missing-node' (lookup checks exact id first, then exact label)\n")

    def test_not_found_json_status_two(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "missing-node", "D", "--graph", str(path), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(
            _payload_from_json(out),
            {
                "error": "node-not-found",
                "message": "node not found for query 'missing-node' (lookup checks exact id first, then exact label)",
                "query": "missing-node",
            },
        )

    def test_duplicate_id_is_ambiguous_with_sorted_candidates(self):
        graph = {"nodes": [_node("dup", "a"), _node("dup", "b"), _node("end")], "links": []}
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "dup", "end", "--graph", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "ambiguous node query 'dup' matched 2 ids:\n  dup\n  dup\n")

    def test_duplicate_label_is_ambiguous_with_ids_sorted(self):
        graph = {"nodes": [_node("z.node", "shared"), _node("a.node", "shared"), _node("end")], "links": []}
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "shared", "end", "--graph", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "ambiguous node query 'shared' matched 2 labels:\n  a.node\n  z.node\n")

    def test_ambiguous_json_includes_candidates(self):
        graph = {"nodes": [_node("z.node", "shared"), _node("a.node", "shared"), _node("end")], "links": []}
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "shared", "end", "--graph", str(path), "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(_payload_from_json(out)["candidates"], ["a.node", "z.node"])
        self.assertEqual(_payload_from_json(out)["error"], "ambiguous-node")

    def test_node_without_id_is_not_a_label_candidate(self):
        graph = {"nodes": [{"label": "ghost"}, _node("end")], "links": []}
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "ghost", "end", "--graph", str(path)])
        self.assertEqual(code, 2)
        self.assertIn("node not found", out)

    def test_no_path_json_payload_is_exact(self):
        with GraphFixture(_base_graph()) as path:
            code, out, _ = _run(["paths", "A", "Z", "--graph", str(path), "--json"])
        self.assertEqual(code, 1)
        self.assertEqual(
            _payload_from_json(out),
            {
                "direction": "forward",
                "end": "Z",
                "error": "no-path",
                "max_hops": 8,
                "message": "no path from A to Z within 8 hops (direction=forward)",
                "start": "A",
            },
        )


class ShortestPathAlgorithmTests(unittest.TestCase):
    def test_cycle_does_not_repeat_nodes_or_choose_longer_cycle_path(self):
        graph = {
            "nodes": [_node("A"), _node("B"), _node("C"), _node("D")],
            "links": [_link("A", "B"), _link("B", "A"), _link("B", "C"), _link("C", "D"), _link("A", "D")],
        }
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "A", "D", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(out, "shortest paths from A to D (hops=1, count=1, direction=forward):\n  1. A -> D\n")

    def test_all_shortest_paths_are_collected_not_just_first_bfs_parent(self):
        graph = {
            "nodes": [_node("A"), _node("B"), _node("C"), _node("D"), _node("E")],
            "links": [_link("A", "B"), _link("A", "C"), _link("A", "E"), _link("B", "D"), _link("C", "D"), _link("E", "D")],
        }
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "A", "D", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("count=3", out)
        self.assertIn("  3. A -> E -> D\n", out)

    def test_lexicographic_tie_order_uses_full_path_tuple(self):
        graph = {
            "nodes": [_node("A"), _node("b"), _node("B"), _node("D")],
            "links": [_link("A", "b"), _link("A", "B"), _link("b", "D"), _link("B", "D")],
        }
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "A", "D", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertLess(out.index("A -> B -> D"), out.index("A -> b -> D"))

    def test_max_paths_truncates_after_sorting_in_text(self):
        graph = {
            "nodes": [_node("A"), _node("B"), _node("C"), _node("E"), _node("D")],
            "links": [_link("A", "C"), _link("A", "B"), _link("A", "E"), _link("C", "D"), _link("B", "D"), _link("E", "D")],
        }
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "A", "D", "--max-paths", "2", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("count=3", out)
        self.assertIn("  1. A -> B -> D\n  2. A -> C -> D\n", out)
        self.assertIn("  ... 1 more shortest path(s) not shown (increase --max-paths)\n", out)
        self.assertNotIn("A -> E -> D", out)

    def test_max_paths_truncates_json_counts_without_losing_total_count(self):
        graph = {
            "nodes": [_node("A"), _node("B"), _node("C"), _node("E"), _node("D")],
            "links": [_link("A", "B"), _link("A", "C"), _link("A", "E"), _link("B", "D"), _link("C", "D"), _link("E", "D")],
        }
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "A", "D", "--max-paths", "2", "--graph", str(path), "--json"])
        self.assertEqual(code, 0)
        payload = _payload_from_json(out)
        self.assertEqual(payload["path_count"], 3)
        self.assertEqual(payload["shown_path_count"], 2)
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["paths"], [["A", "B", "D"], ["A", "C", "D"]])

    def test_malformed_links_and_unknown_endpoints_are_ignored(self):
        graph = {
            "nodes": [_node("A"), _node("B"), _node("D")],
            "links": [_link("A", "missing"), {"source": "A"}, {"target": "B"}, _link("A", "B"), _link("B", "D")],
        }
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "A", "D", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[1], "  1. A -> B -> D")

    def test_longer_path_not_reported_when_shorter_exists(self):
        graph = {
            "nodes": [_node("A"), _node("B"), _node("C"), _node("D")],
            "links": [_link("A", "D"), _link("A", "B"), _link("B", "C"), _link("C", "D")],
        }
        with GraphFixture(graph) as path:
            code, out, _ = _run(["paths", "A", "D", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("hops=1, count=1", out)
        self.assertNotIn("A -> B -> C -> D", out)


class ExistingBehaviourTests(unittest.TestCase):
    def test_brief_still_renders_existing_sections(self):
        graph = _base_graph()
        with GraphFixture(graph) as path:
            code, out, _ = _run(["brief", "--graph", str(path), "--top", "2"])
        self.assertEqual(code, 0)
        self.assertIn("nodes=6", out)
        self.assertIn("relation mix:", out)
        self.assertIn("hubs (all files):", out)
        self.assertIn("cross-file call ratio:", out)

    def test_missing_graph_keeps_existing_zero_exit_message(self):
        SCRATCH_ROOT.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="missing_graph_", dir=SCRATCH_ROOT) as td:
                missing = Path(td) / "nope" / "graph.json"
                code, out, _ = _run(["paths", "A", "B", "--graph", str(missing)])
        finally:
            try:
                SCRATCH_ROOT.rmdir()
            except OSError:
                pass
        self.assertEqual(code, 0)
        self.assertIn(f"no graph at {missing}", out)
        self.assertIn("external, user-installed tool", out)

    def test_corrupt_graph_exits_two_without_traceback(self):
        SCRATCH_ROOT.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="bad_graph_", dir=SCRATCH_ROOT) as td:
                bad = Path(td) / "graph.json"
                bad.write_text("{not json", encoding="utf-8")
                code, out, err = _run(["paths", "A", "B", "--graph", str(bad)])
        finally:
            try:
                SCRATCH_ROOT.rmdir()
            except OSError:
                pass
        self.assertEqual(code, 2)
        self.assertIn("could not parse", out)
        self.assertNotIn("Traceback", out + err)


if __name__ == "__main__":
    unittest.main()
