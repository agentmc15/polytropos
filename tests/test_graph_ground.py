"""Code-graph context is fresh, bounded, and relevant to the task (step 21).

WHAT WAS MEASURED before `bin/graph_ground.py` existed: a synthetic graph naming a deleted
file briefed normally through `graph_brief.py` with no word about freshness in its output;
the only exclusion was a hard-coded `tests/` prefix; hubs were whole-graph centrality; and
there was no path from "the graph does not cover this" to reading the code.

These tests pin the replacement with synthetic trees and graphs in temp dirs and a canned
git callable through the module's injectable seam. Real git is used in exactly one class,
against a temp repository this test creates, to prove the seam matches what git says.
graphify is never installed or run; the module's source is checked for that.
"""

import contextlib
import importlib.util
import inspect
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_ground_test", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gg = _load("graph_ground")


def _node(node_id, label, source_file, loc="L1"):
    return {"id": node_id, "label": label, "source_file": source_file, "source_location": loc}


def _link(s, t, relation="calls", confidence="EXTRACTED"):
    return {"source": s, "target": t, "relation": relation, "confidence": confidence}


class _Tree:
    """A temp tree with a small package, a spec dir, a graph, and a canned git."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="graph_ground_test_"))
        (self.tmp / "app").mkdir()
        (self.tmp / "spec").mkdir()
        self.write("app/main.py", "def run():\n    return helper()\n")
        self.write("app/utils.py", "def helper():\n    return 1\n")
        self.write("app/gone.py", "def old():\n    return 0\n")
        self.write("spec/test_main.py", "def test_run():\n    assert run()\n")
        self.graph = {
            "version": "fixture-0.1", "directed": True,
            "nodes": [
                _node("app.main.run", "run", "app/main.py"),
                _node("app.utils.helper", "helper", "app/utils.py"),
                _node("app.gone.old", "old", "app/gone.py"),
                _node("spec.test_main.test_run", "test_run", "spec/test_main.py"),
            ],
            "links": [
                _link("app.main.run", "app.utils.helper"),
                _link("spec.test_main.test_run", "app.main.run"),
                _link("app.gone.old", "app.utils.helper", confidence="INFERRED"),
            ],
        }
        self.graph_path = self.tmp / "graphify-out" / "graph.json"
        self.graph_path.parent.mkdir()
        self.save_graph()
        self.head = "aaaaaaaaaaaa1111"
        self.dirty, self.untracked = [], []

    def write(self, rel, text):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def save_graph(self):
        self.graph_path.write_text(json.dumps(self.graph))

    def git(self, args):
        verb = args[0]
        if verb == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(self.tmp) + "\n"
        if verb == "rev-parse":
            return 0, self.head + "\n"
        if verb == "status":
            entries = [f" M {p}" for p in self.dirty] + [f"?? {p}" for p in self.untracked]
            return 0, "\0".join(entries) + ("\0" if entries else "")
        if verb == "config":
            return 0, "https://someone:s3cret@example.invalid/org/repo.git\n"
        if verb == "ls-files":
            files = sorted(str(p.relative_to(self.tmp).as_posix()) for p in self.tmp.rglob("*")
                           if p.is_file())
            return 0, "\0".join(files) + "\0"
        return 1, ""

    def no_git(self, args):
        return 128, ""

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class _Case(unittest.TestCase):
    def setUp(self):
        self.t = _Tree()

    def tearDown(self):
        self.t.cleanup()


# ---- 1. the stamp records what is available and invents nothing ----------------------------------

class StampTests(_Case):
    def test_the_sidecar_carries_revision_fingerprints_and_a_credential_free_remote(self):
        t = self.t
        side = gg.stamp(t.tmp, t.graph_path, extraction="working-tree", git=t.git,
                        now=datetime(2026, 9, 13, tzinfo=timezone.utc))
        self.assertEqual(side["v"], gg.SIDECAR_VERSION)
        self.assertEqual(side["stamped_at"], "2026-09-13T00:00:00Z")
        self.assertEqual(side["revision"]["head"], t.head)
        self.assertEqual(side["repository"]["remote"], "https://example.invalid/org/repo.git")
        self.assertNotIn("s3cret", json.dumps(side))
        self.assertEqual(sorted(side["fingerprints"]),
                         ["app/gone.py", "app/main.py", "app/utils.py", "spec/test_main.py"])
        self.assertEqual(side["extraction"], "working-tree")
        self.assertEqual(side["extractor"]["version"], "fixture-0.1")
        self.assertEqual(side["extractor"]["source"], "graph.json metadata")
        self.assertEqual(side["relationship_provenance"]["relations"], {"calls": 3})
        self.assertEqual(side["relationship_provenance"]["confidence"],
                         {"EXTRACTED": 2, "INFERRED": 1})
        self.assertIn("mtime_note", side["graph"])
        written = json.loads((t.graph_path.parent / gg.SIDECAR_NAME).read_text())
        self.assertEqual(written["graph"]["sha256"], side["graph"]["sha256"])
        mode = (t.graph_path.parent / gg.SIDECAR_NAME).stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_no_metadata_means_extractor_unknown_not_guessed(self):
        t = self.t
        t.graph.pop("version")
        t.save_graph()
        side = gg.stamp(t.tmp, t.graph_path, git=t.git, write=False)
        self.assertEqual(side["extractor"], {"name": "graphify", "source": "unknown"})
        self.assertEqual(side["extraction"], "unknown")
        self.assertFalse((t.graph_path.parent / gg.SIDECAR_NAME).exists())

    def test_an_unknown_extraction_label_is_refused(self):
        with self.assertRaises(gg.GroundingError):
            gg.stamp(self.t.tmp, self.t.graph_path, extraction="fresh", git=self.t.git)

    def test_excluded_and_absent_and_rejected_paths_are_recorded_not_fingerprinted(self):
        t = self.t
        t.graph["nodes"] += [_node("x", "x", "/etc/passwd"), _node("y", "y", "../up.py"),
                             _node("z", "z", "app/never.py")]
        t.save_graph()
        side = gg.stamp(t.tmp, t.graph_path, excludes=("spec/",), git=t.git, write=False)
        self.assertEqual(side["coverage"]["files_excluded"], ["spec/test_main.py"])
        self.assertEqual(side["coverage"]["files_unfingerprinted"], {"app/never.py": "absent"})
        self.assertEqual(set(side["coverage"]["paths_rejected"]), {"/etc/passwd", "../up.py"})
        self.assertNotIn("spec/test_main.py", side["fingerprints"])
        self.assertIn("dynamic imports", " ".join(side["coverage"]["limits"]))

    def test_git_unavailable_is_recorded_as_such(self):
        t = self.t
        side = gg.stamp(t.tmp, t.graph_path, git=t.no_git, write=False)
        self.assertFalse(side["repository"]["git_available"])
        self.assertIsNone(side["revision"]["head"])
        self.assertIn("not a git repository", side["revision"]["note"])
        self.assertEqual(len(side["fingerprints"]), 4, "fingerprints need no git")

    def test_a_graph_past_the_byte_ceiling_is_refused_not_truncated(self):
        t = self.t
        with mock.patch.object(gg, "MAX_GRAPH_BYTES", 10):
            with self.assertRaisesRegex(gg.GroundingError, "ceiling"):
                gg.stamp(t.tmp, t.graph_path, git=t.git, write=False)


# ---- 2. freshness -----------------------------------------------------------------------------------

class FreshnessTests(_Case):
    def test_no_sidecar_is_unknown_and_still_names_deleted_files(self):
        t = self.t
        (t.tmp / "app" / "gone.py").unlink()
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "unknown")
        self.assertFalse(f["sidecar"])
        self.assertIn("no provenance sidecar", f["reasons"][0])
        self.assertEqual(f["deleted"], ["app/gone.py"])
        self.assertTrue(any("absent from the working tree" in r for r in f["reasons"]))
        self.assertEqual(f["files"]["app/gone.py"], "deleted")

    def test_stamped_and_untouched_is_fresh(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "fresh")
        self.assertEqual(f["changed"], [])
        self.assertFalse(f["revision"]["moved"])
        self.assertEqual(f["counts"]["fingerprinted"], 4)

    def test_a_changed_and_a_deleted_file_make_it_partial_and_name_both(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        t.write("app/main.py", "def run():\n    return helper() + 1\n")
        (t.tmp / "app" / "gone.py").unlink()
        t.dirty = ["app/main.py"]
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "partial")
        self.assertEqual(f["changed"], ["app/main.py"])
        self.assertEqual(f["deleted"], ["app/gone.py"])
        self.assertEqual(f["dirty_now"], ["app/main.py"])
        self.assertEqual(f["files"]["app/utils.py"], "unchanged")
        text = " ".join(f["reasons"])
        self.assertIn("app/main.py", text)
        self.assertIn("app/gone.py", text)

    def test_a_moved_revision_alone_does_not_make_a_graph_stale(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        t.head = "bbbbbbbbbbbb2222"
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "fresh")
        self.assertTrue(f["revision"]["moved"])
        self.assertTrue(any("revision moved" in r for r in f["reasons"]))

    def test_a_dirty_file_whose_content_the_stamp_saw_is_unchanged_but_flagged(self):
        t = self.t
        t.write("app/main.py", "def run():\n    return 2\n")
        t.dirty = ["app/main.py"]
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "fresh")
        self.assertEqual(f["files"]["app/main.py"], "unchanged")
        self.assertEqual(f["dirty_now"], ["app/main.py"])

    def test_every_covered_file_differing_is_stale(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        for rel in ("app/main.py", "app/utils.py", "app/gone.py", "spec/test_main.py"):
            t.write(rel, "# rewritten\n")
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "stale")

    def test_a_graph_rewritten_after_the_stamp_is_stale_whatever_the_tree_says(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        t.graph["nodes"].append(_node("new", "new", "app/main.py", "L9"))
        t.save_graph()
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "stale")
        self.assertTrue(any("not the file the sidecar describes" in r for r in f["reasons"]))

    def test_git_unavailable_is_unknown_with_the_reason_and_existence_still_checked(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        (t.tmp / "app" / "gone.py").unlink()
        f = gg.freshness(t.tmp, t.graph_path, git=t.no_git)
        self.assertEqual(f["verdict"], "unknown")
        self.assertFalse(f["git_available"])
        self.assertTrue(any("no revision to compare" in r for r in f["reasons"]))
        self.assertEqual(f["deleted"], ["app/gone.py"])

    def test_a_malformed_sidecar_is_unknown_not_a_crash(self):
        t = self.t
        (t.graph_path.parent / gg.SIDECAR_NAME).write_text("{not json")
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "unknown")
        self.assertTrue(any("unreadable" in r for r in f["reasons"]))
        (t.graph_path.parent / gg.SIDECAR_NAME).write_text(json.dumps({"v": "other/9"}))
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "unknown")

    def test_missing_or_corrupt_graph_is_unknown(self):
        t = self.t
        self.assertEqual(gg.freshness(t.tmp, t.tmp / "nope.json", git=t.git)["verdict"],
                         "unknown")
        t.graph_path.write_text("{oops")
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["verdict"], "unknown")
        self.assertIn("could not parse", f["reasons"][0])

    def test_rejected_paths_are_never_read_and_are_named(self):
        t = self.t
        t.graph["nodes"].append(_node("x", "x", "../../etc/hosts"))
        t.save_graph()
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertIn("../../etc/hosts", f["paths_rejected"])
        self.assertNotIn("../../etc/hosts", f["files"])

    def test_uncovered_changed_files_are_listed_for_the_task(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        t.write("app/new_module.py", "x = 1\n")
        t.untracked = ["app/new_module.py"]
        f = gg.freshness(t.tmp, t.graph_path, git=t.git)
        self.assertEqual(f["uncovered_changed"], ["app/new_module.py"])


# ---- 3. bounded impact -----------------------------------------------------------------------------

class ImpactTests(unittest.TestCase):
    def _chain(self, n, extra_hub=False):
        nodes = [_node(f"n{i}", f"n{i}", f"pkg/m{i}.py") for i in range(n)]
        links = [_link(f"n{i}", f"n{i + 1}") for i in range(n - 1)]
        if extra_hub:
            nodes.append(_node("hub", "hub", "pkg/hub.py"))
            nodes += [_node(f"leaf{i}", f"leaf{i}", "pkg/leaves.py") for i in range(30)]
            links.append(_link("n1", "hub"))
            links += [_link("hub", f"leaf{i}") for i in range(30)]
        return {"nodes": nodes, "links": links}

    def test_seeds_match_ids_labels_and_files_and_unmatched_are_named(self):
        data = self._chain(3)
        imp = gg.impact(data, ["n0", "n1", "pkg/m2.py", "ghost"])
        self.assertEqual(imp["seeds"]["n0"], ["n0"])
        self.assertEqual(imp["seeds"]["pkg/m2.py"], ["n2"])
        self.assertEqual(imp["unmatched"], ["ghost"])

    def test_depth_bounds_the_walk(self):
        data = self._chain(6)
        one = gg.impact(data, ["n0"], depth=1)
        self.assertEqual([n["id"] for n in one["neighbors"]], ["n1"])
        two = gg.impact(data, ["n0"], depth=2)
        self.assertEqual([n["id"] for n in two["neighbors"]], ["n1", "n2"])
        self.assertEqual(two["neighbors"][1]["path"], ["n0", "n1", "n2"])
        self.assertEqual(two["neighbors"][1]["via"]["relation"], "calls")

    def test_the_node_limit_truncates_and_says_so(self):
        data = self._chain(10)
        imp = gg.impact(data, ["n0"], depth=9, limit=3)
        self.assertEqual(len(imp["neighbors"]), 3)
        self.assertTrue(imp["truncated"])

    def test_a_hub_is_listed_with_its_degree_and_never_expanded_through(self):
        data = self._chain(3, extra_hub=True)
        imp = gg.impact(data, ["n0"], depth=3, limit=100, hub_degree=5)
        ids = [n["id"] for n in imp["neighbors"]]
        self.assertIn("hub", ids)
        hub = next(n for n in imp["neighbors"] if n["id"] == "hub")
        self.assertTrue(hub["hub"])
        self.assertEqual(hub["degree"], 31)
        self.assertFalse(any(i.startswith("leaf") for i in ids), "leaves are behind the hub")
        self.assertEqual(imp["hubs_not_expanded"], ["hub"])

    def test_a_seed_that_is_itself_a_hub_is_expanded(self):
        data = self._chain(3, extra_hub=True)
        imp = gg.impact(data, ["hub"], depth=1, limit=100, hub_degree=5)
        self.assertTrue(any(n["id"].startswith("leaf") for n in imp["neighbors"]))

    def test_excludes_are_configurable_prefixes_not_a_tests_assumption(self):
        data = {"nodes": [_node("a", "a", "src/a.py"), _node("b", "b", "spec/b.py"),
                          _node("c", "c", "tests/c.py")],
                "links": [_link("a", "b"), _link("a", "c")]}
        none = gg.impact(data, ["a"])
        self.assertEqual({n["id"] for n in none["neighbors"]}, {"b", "c"})
        spec = gg.impact(data, ["a"], excludes=("spec/",))
        self.assertEqual({n["id"] for n in spec["neighbors"]}, {"c"})
        self.assertEqual(spec["excluded"], 1)

    def test_file_states_ride_along_and_labels_are_bounded(self):
        data = {"nodes": [_node("a", "a", "src/a.py"), _node("b", "x" * 500, "src/b.py")],
                "links": [_link("a", "b")]}
        imp = gg.impact(data, ["a"], file_states={"src/b.py": "changed"})
        self.assertEqual(imp["neighbors"][0]["file_state"], "changed")
        self.assertEqual(len(imp["neighbors"][0]["label"]), gg.LABEL_CHARS)

    def test_both_edge_directions_are_walked(self):
        data = {"nodes": [_node("a", "a", "s/a.py"), _node("b", "b", "s/b.py")],
                "links": [_link("b", "a")]}
        imp = gg.impact(data, ["a"])
        self.assertEqual(imp["neighbors"][0]["id"], "b")
        self.assertEqual(imp["neighbors"][0]["via"]["direction"], "in")


# ---- 4. the search fallback and the shared result --------------------------------------------------

class SearchAndGroundingTests(_Case):
    def test_search_is_bounded_and_skips_binaries_and_excludes(self):
        t = self.t
        (t.tmp / "app" / "blob.bin").write_bytes(b"helper\0\x00\x01")
        s = gg.search(t.tmp, ["helper"], git=t.git)
        paths = {h["path"] for h in s["hits"]}
        self.assertIn("app/main.py", paths)
        self.assertIn("app/utils.py", paths)
        self.assertNotIn("app/blob.bin", paths)
        s = gg.search(t.tmp, ["helper"], excludes=("app/",), git=t.git)
        self.assertEqual(s["hits"], [])
        s = gg.search(t.tmp, ["def"], max_hits=2, git=t.git)
        self.assertEqual(len(s["hits"]), 2)
        self.assertTrue(s["truncated"])
        self.assertEqual(gg.search(t.tmp, [], git=t.git)["hits"], [])

    def test_no_graph_means_provider_none_and_a_search_fallback(self):
        t = self.t
        g = gg.grounding(t.tmp, t.tmp / "absent" / "graph.json", seeds=["helper"], git=t.git)
        self.assertEqual(g["v"], gg.CONTRACT_VERSION)
        self.assertEqual(g["provider"], "none")
        self.assertEqual(g["graph_role"], "none")
        self.assertIsNone(g["freshness"])
        self.assertTrue(g["fallback"]["used"])
        self.assertIn("no graph.json", g["fallback"]["reasons"][0])
        self.assertTrue(g["fallback"]["search"]["hits"])
        self.assertIn("dynamic imports", " ".join(g["limits"]))
        self.assertIn("grants no permission", g["advisory"])

    def test_a_fresh_graph_is_evidence_and_needs_no_fallback(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        g = gg.grounding(t.tmp, t.graph_path, seeds=["app/main.py"], git=t.git)
        self.assertEqual(g["graph_role"], "evidence")
        self.assertFalse(g["fallback"]["used"])
        self.assertEqual([n["id"] for n in g["impact"]["neighbors"]][:1], ["app.utils.helper"])

    def test_a_stale_or_unknown_graph_is_hints_plus_a_search(self):
        t = self.t
        g = gg.grounding(t.tmp, t.graph_path, seeds=["helper"], git=t.git)
        self.assertEqual(g["freshness"]["verdict"], "unknown")
        self.assertEqual(g["graph_role"], "hints")
        self.assertTrue(g["fallback"]["used"])
        self.assertTrue(any("navigation hints" in r for r in g["fallback"]["reasons"]))
        self.assertTrue(g["impact"]["neighbors"], "the graph is still walked, as hints")
        paths = {h["path"] for h in g["fallback"]["search"]["hits"]}
        self.assertNotIn("graphify-out/graph.json", paths, "the graph never searches itself")

    def test_changed_seeds_the_walk_with_the_dirty_tree(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        t.dirty = ["app/main.py"]
        g = gg.grounding(t.tmp, t.graph_path, changed=True, git=t.git)
        self.assertEqual(g["seeds"], ["app/main.py"])
        self.assertEqual(g["impact"]["seeds"], {"app/main.py": ["app.main.run"]})

    def test_an_uncovered_seed_falls_back_to_search_for_that_seed_only(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        t.write("app/orphan.py", "def lonely():\n    return 3\n")
        g = gg.grounding(t.tmp, t.graph_path, seeds=["app/main.py", "lonely"], git=t.git)
        self.assertEqual(g["impact"]["unmatched"], ["lonely"])
        self.assertTrue(g["fallback"]["used"])
        self.assertEqual(g["fallback"]["search"]["terms"], ["lonely"])
        self.assertEqual({h["path"] for h in g["fallback"]["search"]["hits"]}, {"app/orphan.py"})

    def test_weak_coverage_adds_the_dynamic_import_warning_and_a_search(self):
        t = self.t
        t.graph = {"nodes": [_node("a", "a", "app/main.py"), _node("b", "b", "app/main.py")],
                   "links": [_link("a", "b")]}
        t.save_graph()
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        g = gg.grounding(t.tmp, t.graph_path, seeds=["a"], git=t.git)
        self.assertTrue(g["fallback"]["used"])
        self.assertTrue(any(r.startswith("weak coverage") for r in g["fallback"]["reasons"]))
        self.assertTrue(any("LOW CROSS-FILE" in lim for lim in g["limits"]))

    def test_render_is_bounded_and_says_where_it_cut(self):
        t = self.t
        gg.stamp(t.tmp, t.graph_path, git=t.git)
        g = gg.grounding(t.tmp, t.graph_path, seeds=["app/main.py"], git=t.git)
        full = gg.render_grounding(g, max_chars=100000)
        self.assertIn("grounding (polytropos.grounding/1)", full)
        self.assertIn("freshness: fresh", full)
        self.assertIn("advisory:", full)
        cut = gg.render_grounding(g, max_chars=300)
        self.assertLessEqual(len(cut), 300)
        self.assertIn("truncated to 300 chars", cut)
        self.assertIn("tokens est.", cut)


# ---- 5. the real git seam, once ---------------------------------------------------------------------

@unittest.skipUnless(shutil.which("git"), "git is not installed")
class RealGitTests(unittest.TestCase):
    def test_repo_state_matches_git_on_a_temp_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x")
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True, env=env)
            (root / "a.py").write_text("x = 1\n")
            subprocess.run(["git", "add", "a.py"], cwd=tmp, check=True, env=env)
            subprocess.run(["git", "commit", "-q", "-m", "one"], cwd=tmp, check=True, env=env)
            (root / "a.py").write_text("x = 2\n")
            (root / "b.py").write_text("y = 1\n")
            state = gg.repo_state(root)
            self.assertTrue(state["available"])
            self.assertEqual(len(state["head"]), 40)
            self.assertEqual(state["dirty"], ["a.py"])
            self.assertEqual(state["untracked"], ["b.py"])
            self.assertEqual(Path(state["root"]).resolve(), root.resolve())
            with tempfile.TemporaryDirectory() as plain:
                self.assertFalse(gg.repo_state(plain)["available"])


# ---- 6. hygiene: no graphify invocation, no subprocess of its own -----------------------------------

class SourceHygieneTests(unittest.TestCase):
    def test_the_module_never_invokes_graphify_or_spawns_on_its_own(self):
        source = inspect.getsource(gg)
        self.assertNotIn("subprocess", source)
        for banned in ("os.system", "os.popen", "exec(", "eval(", "Path.home", "expanduser",
                       "urllib", "urlopen"):
            self.assertNotIn(banned, source)
        self.assertIn("graphify", source)
        self.assertNotIn("[\"graphify\"", source)
        self.assertNotIn("'graphify',", source)

    def test_only_read_only_git_verbs_are_allowed(self):
        self.assertEqual(set(gg.GIT_READ_VERBS), {"rev-parse", "status", "ls-files", "config"})
        with self.assertRaises(gg.GroundingError):
            gg._git(".", "commit", git=lambda a: (0, ""))

    def test_remote_credentials_are_scrubbed(self):
        self.assertEqual(gg.scrub_remote("https://u:p@h/o/r.git"), "https://h/o/r.git")
        self.assertEqual(gg.scrub_remote("git@h:o/r.git"), "git@h:o/r.git")
        self.assertIsNone(gg.scrub_remote(""))

    def test_demo_runs_in_a_temp_tree_with_canned_git_and_spends_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gg.main(["demo"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("verdict=unknown", text)
        self.assertIn("verdict=fresh", text)
        self.assertIn("verdict=partial", text)
        self.assertIn("HUB(degree 31, not expanded)", text)
        self.assertIn("provider=none", text)
        self.assertNotIn("graph.json:1:", text, "the fallback never searches the graph itself")


class CommandLineTests(_Case):
    def _main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = gg.main(argv)
            except SystemExit as exc:  # argparse refuses a bad choice before main returns
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_freshness_exit_codes_follow_the_verdict(self):
        t = self.t
        real_repo_state = gg.repo_state
        with mock.patch.object(gg, "repo_state",
                                        lambda repo, git=None: real_repo_state(repo, git=t.git)):
            code, out, _ = self._main(["freshness", "--repo", str(t.tmp), "--graph",
                                       str(t.graph_path)])
            self.assertEqual(code, 3)
            self.assertIn("freshness: unknown", out)
            code, out, _ = self._main(["stamp", "--repo", str(t.tmp), "--graph",
                                       str(t.graph_path), "--extraction", "commit-only"])
            self.assertEqual(code, 0)
            self.assertIn("extraction=commit-only", out)
            code, out, _ = self._main(["freshness", "--repo", str(t.tmp), "--graph",
                                       str(t.graph_path), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["verdict"], "fresh")
            code, out, _ = self._main(["ground", "--repo", str(t.tmp), "--graph",
                                       str(t.graph_path), "--seed", "app/main.py", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["v"], gg.CONTRACT_VERSION)
            code, out, _ = self._main(["search", "--repo", str(t.tmp), "--term", "helper"])
            self.assertEqual(code, 0)
            self.assertIn("app/utils.py:1:", out)

    def test_a_bad_extraction_label_exits_2(self):
        code, _, err = self._main(["stamp", "--repo", str(self.t.tmp), "--graph",
                                   str(self.t.graph_path), "--extraction", "guess"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
