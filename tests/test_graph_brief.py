"""Stdlib unittest regression suite for bin/graph_brief.py.

bin/ is not a package; graph_brief.py is loaded via importlib by absolute path computed
from this file's own location, per the tests/test_harness_select.py convention.

SAFETY: this engine only ever READS a graph.json file. Every test here builds a synthetic
graph.json in a `tempfile.TemporaryDirectory()` -- nothing here reads a real graphify
output, and the real `graphify` binary is never invoked (it isn't even referenced except
inside message/docstring strings, which the introspection test below double-checks).
"""

import contextlib
import importlib.util
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gb = _load("graph_brief")


# --------------------------------------------------------------------------- fixtures

def _node(node_id, label, source_file=None, source_location=None, community=None,
          **extra):
    node = {"id": node_id, "label": label, "norm_label": label.lower()}
    if source_file is not None:
        node["source_file"] = source_file
    if source_location is not None:
        node["source_location"] = source_location
    if community is not None:
        node["community"] = community
    node.update(extra)
    return node


def _link(source, target, relation="calls", confidence="EXTRACTED", **extra):
    link = {"source": source, "target": target, "relation": relation,
            "confidence": confidence}
    link.update(extra)
    return link


def _build_graph():
    """A synthetic graph.json covering >=2 directories, tests/-dominated hubs, a
    cross-file call, and a same-file call.

    Layout:
      - bin/foo.py: foo_helper (community 0)
      - bin/bar.py: bar_main (community 0) -- calls foo_helper (cross-file)
      - bin/bar.py: bar_util (community 0) -- calls bar_main (same-file)
      - tests/test_foo.py: assert_helper (community 1) -- 6 distinct bin/bar.py leaf
        nodes each reference it once, so its degree (6) dominates bar_main's degree
        (3) from the base call/contains/extends links -- fixture dominance, measured.
      - tests/test_foo.py: fixture_helper (community 1) -- same pattern, another 6
        distinct leaves, so BOTH top-2 all-files hubs are tests/ nodes.
      - bin/bar.py: 12 single-degree "leaf" nodes, each with exactly one reference
        edge into assert_helper or fixture_helper -- they exist purely to give those
        two tests/ nodes high degree via many distinct callers (not one repeated
        caller, which would just inflate the caller's own degree instead).
    """
    nodes = [
        _node("bin.foo.foo_helper", "foo_helper", "bin/foo.py", "L10", community=0),
        _node("bin.bar.bar_main", "bar_main", "bin/bar.py", "L5", community=0),
        _node("bin.bar.bar_util", "bar_util", "bin/bar.py", "L20", community=0),
        _node("tests.test_foo.assert_helper", "assert_helper", "tests/test_foo.py",
              "L3", community=1),
        _node("tests.test_foo.fixture_helper", "fixture_helper", "tests/test_foo.py",
              "L8", community=1),
    ]

    links = [
        # cross-file call: bin/bar.py -> bin/foo.py
        _link("bin.bar.bar_main", "bin.foo.foo_helper", relation="calls",
              source_file="bin/bar.py", source_location="L5"),
        # same-file call: bin/bar.py -> bin/bar.py
        _link("bin.bar.bar_util", "bin.bar.bar_main", relation="calls",
              source_file="bin/bar.py", source_location="L20"),
        # contains / extends / references to exercise relation mix
        _link("bin.bar.bar_main", "bin.bar.bar_util", relation="contains"),
        _link("bin.foo.foo_helper", "bin.bar.bar_main", relation="extends"),
    ]

    # 6 distinct single-degree leaves referencing assert_helper, 6 more referencing
    # fixture_helper -- none of them "calls" links, so the cross-file ratio (which
    # only counts "calls") is unaffected.
    for i in range(6):
        leaf_id = f"bin.bar.leaf_assert_{i}"
        nodes.append(_node(leaf_id, f"leaf_assert_{i}", "bin/bar.py", "L1", community=0))
        links.append(_link(leaf_id, "tests.test_foo.assert_helper", relation="references",
                            source_file="bin/bar.py", source_location="L1"))
    for i in range(6):
        leaf_id = f"bin.bar.leaf_fixture_{i}"
        nodes.append(_node(leaf_id, f"leaf_fixture_{i}", "bin/bar.py", "L1", community=0))
        links.append(_link(leaf_id, "tests.test_foo.fixture_helper", relation="references",
                            source_file="bin/bar.py", source_location="L1"))

    return {"nodes": nodes, "links": links, "directed": True}


def _write_graph(tmp_dir, graph, filename="graph.json"):
    path = Path(tmp_dir) / filename
    path.write_text(json.dumps(graph))
    return path


def _run_brief(argv):
    """Run gb.main(argv) capturing stdout; return (exit_code, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = gb.main(argv)
    return code, buf.getvalue()


def _run_brief_both(argv):
    """Run gb.main(argv) capturing stdout AND stderr; return (code, stdout, stderr)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code = gb.main(argv)
    return code, out_buf.getvalue(), err_buf.getvalue()


# --------------------------------------------------------------------------- card sections

class BriefCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.graph = _build_graph()
        self.path = _write_graph(self.tmp.name, self.graph)

    def test_counts_section(self):
        data, error = gb.load_graph(self.path)
        self.assertIsNone(error)
        nodes = gb._nodes_of(data)
        links = gb._links_of(data)
        counts = gb.compute_counts(nodes, links)
        self.assertEqual(counts["nodes"], 5 + 12)  # base 5 + 12 single-degree leaves
        self.assertEqual(counts["links"], 4 + 6 + 6)
        self.assertEqual(counts["communities"], 2)
        self.assertEqual(counts["files"], 3)  # bin/foo.py, bin/bar.py, tests/test_foo.py

    def test_relation_mix_descending(self):
        data, _ = gb.load_graph(self.path)
        nodes, links = gb._nodes_of(data), gb._links_of(data)
        mix = gb.compute_relation_mix(links)
        mix_dict = dict(mix)
        self.assertEqual(mix_dict["references"], 12)
        self.assertEqual(mix_dict["calls"], 2)
        self.assertEqual(mix_dict["contains"], 1)
        self.assertEqual(mix_dict["extends"], 1)
        # descending order
        counts_in_order = [c for _, c in mix]
        self.assertEqual(counts_in_order, sorted(counts_in_order, reverse=True))

    def test_per_directory_mass(self):
        data, _ = gb.load_graph(self.path)
        nodes = gb._nodes_of(data)
        mass = dict(gb.compute_directory_mass(nodes))
        self.assertEqual(mass["bin"], 3 + 12)  # foo/bar/util + 12 leaf nodes
        self.assertEqual(mass["tests"], 2)

    def test_per_directory_mass_none_bucket(self):
        nodes = [gb._nodes_of({"nodes": [{"id": "x", "label": "x"}]})[0]]
        mass = dict(gb.compute_directory_mass(nodes))
        self.assertEqual(mass["(none)"], 1)

    def test_hubs_all_files_dominated_by_tests(self):
        data, _ = gb.load_graph(self.path)
        nodes, links = gb._nodes_of(data), gb._links_of(data)
        hubs = gb.compute_hubs(nodes, links, top_n=8, exclude_tests=False)
        top_label = hubs[0]["label"]
        self.assertIn(top_label, ("assert_helper", "fixture_helper"))
        # hub line carries label, degree, source_file:source_location
        self.assertIn("degree", hubs[0])
        self.assertEqual(hubs[0]["source_file"], "tests/test_foo.py")

    def test_hubs_excluding_tests_changes_the_ranking(self):
        data, _ = gb.load_graph(self.path)
        nodes, links = gb._nodes_of(data), gb._links_of(data)
        hubs_all = gb.compute_hubs(nodes, links, top_n=8, exclude_tests=False)
        hubs_excl = gb.compute_hubs(nodes, links, top_n=8, exclude_tests=True)
        all_ids = [h["id"] for h in hubs_all]
        excl_ids = [h["id"] for h in hubs_excl]
        self.assertNotEqual(all_ids, excl_ids)
        # no tests/ node should appear in the excluded list
        for hub in hubs_excl:
            self.assertNotEqual((hub["source_file"] or ""), "tests/test_foo.py")
            self.assertFalse((hub["source_file"] or "").startswith("tests/"))

    def test_negative_top_normalizes_to_zero_hubs_not_a_slice_artifact(self):
        # review N8: --top -1 used to hit the Python slice `[:-1]` and silently drop the
        # last hub instead of rendering "no hubs" -- any negative --top must normalize
        # to 0 (same empty-hub form as an explicit --top 0), never trim from the end.
        data, _ = gb.load_graph(self.path)
        brief_negative = gb.build_brief(data, top_n=-1)
        brief_zero = gb.build_brief(data, top_n=0)
        self.assertEqual(brief_negative["hubs_all"], [])
        self.assertEqual(brief_negative["hubs_excl_tests"], [])
        self.assertEqual(brief_negative["hubs_all"], brief_zero["hubs_all"])
        self.assertEqual(brief_negative["hubs_excl_tests"], brief_zero["hubs_excl_tests"])

    def test_negative_top_via_cli_renders_none_hubs(self):
        code, out = _run_brief(["brief", "--graph", str(self.path), "--top", "-1"])
        self.assertEqual(code, 0)
        # hub sections render the "(none)" empty form, not a truncated hub list
        lines = out.splitlines()
        all_hubs_idx = lines.index("hubs (all files):")
        self.assertEqual(lines[all_hubs_idx + 1].strip(), "(none)")

    def test_confidence_mix(self):
        data, _ = gb.load_graph(self.path)
        links = gb._links_of(data)
        mix = dict(gb.compute_confidence_mix(links))
        self.assertEqual(mix["EXTRACTED"], len(links))

    def test_cross_file_call_ratio_computed_over_calls_only(self):
        data, _ = gb.load_graph(self.path)
        nodes, links = gb._nodes_of(data), gb._links_of(data)
        ratio, cross, total = gb.compute_cross_file_ratio(nodes, links)
        # exactly 2 "calls" links with both endpoints carrying source_file: one
        # cross-file (bar_main -> foo_helper), one same-file (bar_util -> bar_main)
        self.assertEqual(total, 2)
        self.assertEqual(cross, 1)
        self.assertAlmostEqual(ratio, 0.5)

    def test_render_brief_includes_all_sections(self):
        data, _ = gb.load_graph(self.path)
        brief = gb.build_brief(data, top_n=8)
        text = gb.render_brief(brief)
        self.assertIn("nodes=17", text)
        self.assertIn("relation mix:", text)
        self.assertIn("per-directory mass:", text)
        self.assertIn("hubs (all files):", text)
        self.assertIn(gb.HUBS_EXCL_TESTS_LABEL, text)
        self.assertIn("confidence mix:", text)
        self.assertIn("cross-file call ratio:", text)


# --------------------------------------------------------------------------- low ratio warning

class LowCrossFileWarningTests(unittest.TestCase):
    def test_warning_absent_when_ratio_high(self):
        # Build a graph with many cross-file calls so the ratio clears 0.05.
        nodes = [
            _node("a", "a", "bin/a.py"),
            _node("b", "b", "bin/b.py"),
        ]
        links = [_link("a", "b", relation="calls", source_file="bin/a.py")
                 for _ in range(10)]
        data = {"nodes": nodes, "links": links}
        brief = gb.build_brief(data, top_n=8)
        self.assertFalse(brief["low_cross_file_warning"])
        text = gb.render_brief(brief)
        self.assertNotIn("LOW CROSS-FILE VISIBILITY", text)

    def test_warning_present_when_ratio_low(self):
        # 100 same-file calls, 1 cross-file call -> ratio well under 0.05.
        nodes = [
            _node("a", "a", "bin/a.py"),
            _node("b", "b", "bin/a.py"),
            _node("c", "c", "bin/c.py"),
        ]
        links = [_link("a", "b", relation="calls", source_file="bin/a.py")
                 for _ in range(100)]
        links.append(_link("a", "c", relation="calls", source_file="bin/a.py"))
        data = {"nodes": nodes, "links": links}
        brief = gb.build_brief(data, top_n=8)
        self.assertTrue(brief["low_cross_file_warning"])
        text = gb.render_brief(brief)
        self.assertIn(gb.LOW_CROSS_FILE_WARNING, text)

    def test_warning_present_when_zero_cross_file_calls(self):
        nodes = [_node("a", "a", "bin/a.py"), _node("b", "b", "bin/a.py")]
        links = [_link("a", "b", relation="calls", source_file="bin/a.py")]
        data = {"nodes": nodes, "links": links}
        brief = gb.build_brief(data, top_n=8)
        self.assertTrue(brief["low_cross_file_warning"])
        self.assertEqual(brief["cross_file_call_total"], 1)
        self.assertEqual(brief["cross_file_call_count"], 0)

    def test_warning_does_not_change_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            nodes = [_node("a", "a", "bin/a.py"), _node("b", "b", "bin/a.py")]
            links = [_link("a", "b", relation="calls", source_file="bin/a.py")]
            path = _write_graph(tmp, {"nodes": nodes, "links": links})
            code, out = _run_brief(["brief", "--graph", str(path)])
            self.assertEqual(code, 0)
            self.assertIn("LOW CROSS-FILE VISIBILITY", out)


# --------------------------------------------------------------------------- failure honesty

class FailureHonestyTests(unittest.TestCase):
    def test_absent_graph_exits_zero_with_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = str(Path(tmp) / "does-not-exist" / "graph.json")
            code, out = _run_brief(["brief", "--graph", missing_path])
            self.assertEqual(code, 0)
            self.assertIn(f"no graph at {missing_path}", out)
            self.assertIn("graphify update", out)
            self.assertIn("external, user-installed tool", out)

    def test_corrupt_json_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text("{not valid json")
            code, out = _run_brief(["brief", "--graph", str(path)])
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", out)

    def test_non_utf8_graph_exits_two_without_traceback(self):
        # graphify embeds source snippets in link 'context' fields, so extraction over a
        # latin-1 (or otherwise non-UTF-8) source file can produce a graph.json with an
        # invalid UTF-8 byte -- this must degrade to a one-line message, never a
        # traceback (review finding F1).
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_bytes(b'{"nodes": [], "links": [{"context": "caf\xe9"}]}')
            code, out, err = _run_brief_both(["brief", "--graph", str(path)])
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", out)
            self.assertNotIn("Traceback", err)
            self.assertIn("not valid UTF-8", out)
            # exactly one line of output -- not a multi-line traceback dump
            self.assertEqual(len(out.rstrip("\n").splitlines()), 1)

    def test_parseable_but_missing_both_nodes_and_links_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            path.write_text(json.dumps({"directed": False, "graph": {}}))
            code, out = _run_brief(["brief", "--graph", str(path)])
            self.assertEqual(code, 2)
            self.assertIn("nodes", out)
            self.assertIn("links", out)

    def test_edges_alias_for_links_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = _build_graph()
            graph["edges"] = graph.pop("links")
            path = _write_graph(tmp, graph)
            data, error = gb.load_graph(path)
            self.assertIsNone(error)
            links = gb._links_of(data)
            self.assertEqual(len(links), 16)


# --------------------------------------------------------------------------- --json round-trip

class JsonRoundTripTests(unittest.TestCase):
    def test_json_output_matches_human_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_graph(tmp, _build_graph())
            code_human, out_human = _run_brief(["brief", "--graph", str(path)])
            code_json, out_json = _run_brief(["brief", "--graph", str(path), "--json"])
            self.assertEqual(code_human, 0)
            self.assertEqual(code_json, 0)
            parsed = json.loads(out_json)
            self.assertEqual(parsed["counts"]["nodes"], 17)
            self.assertEqual(parsed["counts"]["links"], 16)
            self.assertIn("nodes=17", out_human)
            self.assertEqual(parsed["counts"]["communities"], 2)
            self.assertEqual(parsed["counts"]["files"], 3)


# --------------------------------------------------------------------------- demo subcommand

class DemoCommandTests(unittest.TestCase):
    """`demo` is the CLAUDE.md run-line smoke: no real files, no graphify binary, always
    exits 0, and cannot resolve into the real cwd repo (no --graph on its subparser)."""

    def test_demo_exits_zero_and_prints_both_cards(self):
        code, out = _run_brief(["demo"])
        self.assertEqual(code, 0)
        self.assertIn("normal repo shape", out)
        self.assertIn("seeded low cross-file visibility", out)
        # both full brief cards render every section
        self.assertEqual(out.count("relation mix:"), 2)
        self.assertEqual(out.count("per-directory mass:"), 2)
        self.assertEqual(out.count("hubs (all files):"), 2)
        self.assertEqual(out.count(gb.HUBS_EXCL_TESTS_LABEL), 2)
        self.assertEqual(out.count("confidence mix:"), 2)
        self.assertEqual(out.count("cross-file call ratio:"), 2)

    def test_demo_seeds_the_low_cross_file_warning_exactly_once(self):
        code, out = _run_brief(["demo"])
        self.assertEqual(code, 0)
        self.assertEqual(out.count(gb.LOW_CROSS_FILE_WARNING), 1)

    def test_demo_subparser_rejects_a_graph_argument(self):
        # demo takes no path arguments by construction -- it cannot receive real files.
        with self.assertRaises(SystemExit):
            _run_brief(["demo", "--graph", "somewhere/graph.json"])

    def test_demo_source_never_references_args_graph_or_the_default_path(self):
        source = inspect.getsource(gb.cmd_demo)
        self.assertNotIn("args.graph", source)
        self.assertNotIn("DEFAULT_GRAPH_PATH", source)

    def test_demo_output_is_independent_of_cwd(self):
        cwd_before = os.getcwd()
        with tempfile.TemporaryDirectory() as other_cwd:
            os.chdir(other_cwd)
            try:
                code, out = _run_brief(["demo"])
            finally:
                os.chdir(cwd_before)
        self.assertEqual(code, 0)
        self.assertIn("normal repo shape", out)

    def test_demo_removes_its_temp_tree_in_a_finally(self):
        created = []
        original_mkdtemp = gb.tempfile.mkdtemp

        def _spy_mkdtemp(*args, **kwargs):
            path = original_mkdtemp(*args, **kwargs)
            created.append(path)
            return path

        with mock.patch.object(gb.tempfile, "mkdtemp", side_effect=_spy_mkdtemp):
            code, _out = _run_brief(["demo"])

        self.assertEqual(code, 0)
        self.assertEqual(len(created), 1)
        self.assertFalse(Path(created[0]).exists())


# --------------------------------------------------------------------------- drift tolerance

class DriftToleranceTests(unittest.TestCase):
    """graphifyy is v0.9 -- format drift is expected, not exceptional."""

    def test_edges_alias_parses_identically_through_full_pipeline(self):
        graph_links = _build_graph()
        graph_edges = _build_graph()
        graph_edges["edges"] = graph_edges.pop("links")
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            path_links = _write_graph(tmp1, graph_links)
            path_edges = _write_graph(tmp2, graph_edges)
            _, out_links = _run_brief(["brief", "--graph", str(path_links)])
            _, out_edges = _run_brief(["brief", "--graph", str(path_edges)])
        self.assertEqual(out_links, out_edges)

    def test_node_missing_label_degrades_to_id_in_hub_line(self):
        nodes = [{"id": "x", "source_file": "bin/x.py"}]  # no label, no norm_label
        data = {"nodes": nodes, "links": []}
        brief = gb.build_brief(data, top_n=8)
        self.assertEqual(brief["hubs_all"][0]["label"], "x")

    def test_node_missing_community_excluded_from_distinct_community_count(self):
        nodes = [
            {"id": "a", "source_file": "bin/a.py"},  # no community
            {"id": "b", "source_file": "bin/b.py", "community": 0},
        ]
        counts = gb.compute_counts(nodes, [])
        self.assertEqual(counts["communities"], 1)

    def test_node_missing_source_file_grouped_under_none_bucket_end_to_end(self):
        nodes = [{"id": "a", "label": "a"}]  # no source_file
        data = {"nodes": nodes, "links": []}
        brief = gb.build_brief(data, top_n=8)
        dir_mass = dict(brief["directory_mass"])
        self.assertEqual(dir_mass["(none)"], 1)
        self.assertIsNone(brief["hubs_all"][0]["source_file"])
        self.assertEqual(brief["counts"]["files"], 0)  # no source_file -> not counted

    def test_empty_nodes_list_renders_zeros_not_an_error(self):
        data = {"nodes": [], "links": []}
        brief = gb.build_brief(data, top_n=8)
        self.assertEqual(
            brief["counts"], {"nodes": 0, "links": 0, "communities": 0, "files": 0}
        )
        text = gb.render_brief(brief)
        self.assertIn("nodes=0 links=0 communities=0 files=0", text)
        self.assertIn("relation mix:", text)
        self.assertIn("per-directory mass:", text)
        self.assertIn("hubs (all files):", text)

    def test_empty_nodes_list_via_cli_exits_zero_not_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_graph(tmp, {"nodes": [], "links": []})
            code, out = _run_brief(["brief", "--graph", str(path)])
        self.assertEqual(code, 0)
        self.assertIn("nodes=0", out)


# --------------------------------------------------------------------------- source introspection

class SourceIntrospectionTests(unittest.TestCase):
    """The tests/test_codex_setup.py idiom: assert the banned strings never appear in
    any function defined in this engine module, since this engine has no home-dir or
    network business whatsoever."""

    def test_no_home_dir_or_network_or_subprocess_primitives_in_any_function(self):
        banned = ("Path.home", "expanduser", "subprocess", "urllib", "urlopen")
        functions = inspect.getmembers(gb, inspect.isfunction)
        self.assertTrue(functions, "expected graph_brief.py to define functions")
        for name, func in functions:
            if func.__module__ != gb.__name__:
                continue  # skip anything imported rather than defined here
            source = inspect.getsource(func)
            for term in banned:
                self.assertNotIn(
                    term, source,
                    f"{name} must not reference {term!r} -- this engine has no "
                    "home-dir or network business",
                )

    def test_no_home_dir_or_network_primitives_in_whole_module_source(self):
        banned = ("Path.home", "expanduser", "subprocess", "urllib", "urlopen")
        source = inspect.getsource(gb)
        for term in banned:
            self.assertNotIn(term, source)

    def test_graphify_string_never_appears_in_an_exec_context(self):
        source = inspect.getsource(gb)
        self.assertIn("graphify", source)  # present in messages/docstrings
        self.assertNotIn("subprocess", source)
        for banned_call in ("os.system", "os.popen", "exec(", "eval("):
            self.assertNotIn(banned_call, source)


# --------------------------------------------------------------------------- literal pins

class HonestyStringLiteralPinTests(unittest.TestCase):
    """Pin the two honesty-feature constants to their FULL literal text, spelled out
    here as independent string literals (not derived from gb's own constants) -- copied
    byte-for-byte from bin/graph_brief.py. Every other test in this file pins these
    constants via `gb.HUBS_EXCL_TESTS_LABEL` / `gb.LOW_CROSS_FILE_WARNING`, which is
    self-referential: mutating the constant in the engine and its callers together would
    still pass those tests. This test compares against text fixed here, so silent
    softening of either string (e.g. dropping the 54% clause or the dynamic-loaders
    explanation) fails even if the engine and every other test were mutated in lockstep.
    """

    def test_hubs_excl_tests_label_full_text(self):
        expected = (
            "hubs excluding tests/ (test fixtures can dominate raw degree -- on the repo this "
            "tool was calibrated against, tests/ held 54% of node mass and topped the "
            "all-files hub list)"
        )
        self.assertEqual(gb.HUBS_EXCL_TESTS_LABEL, expected)

    def test_low_cross_file_warning_full_text(self):
        expected = (
            "LOW CROSS-FILE VISIBILITY -- dynamic loaders (importlib, plugin registries) are "
            "invisible to AST extraction; this graph under-represents cross-module coupling. "
            "Verify dependencies by reading the code, not by absence of edges."
        )
        self.assertEqual(gb.LOW_CROSS_FILE_WARNING, expected)


if __name__ == "__main__":
    unittest.main()
