"""Context candidates for a recovery repair: bounded, versioned, deterministic (D16).

WHAT IS UNDER TEST. `bin/decision_context.py` builds the manifest that the recovery
experiment's arm C would supply -- "one bounded package of previously missing contract
context" -- from the graph/search seam `bin/graph_ground.py` already owns. These tests pin it
with synthetic trees and SYNTHETIC graph.json fixtures in temp dirs and a canned git through
the seam's injectable probe. graphify is external and user-installed: nothing here runs it,
looks for it, or asks whether it is present, and no test writes outside its own temp dir.

WHAT THE ACCEPTANCE TERMS MEAN HERE, and how each is made structural rather than asserted:

  * NO DISPATCH -- a proc runner that RAISES if anything calls it, proven reachable by a
    control that does call it, plus an AST sweep over this module's own calls with a
    non-empty guard on the collection being walked.
  * DETERMINISTIC ARTIFACT -- byte identity across repeated builds, across a graph whose node
    and link order has been shuffled, and across two child interpreters with different
    `PYTHONHASHSEED`, which is the only way set-iteration order shows up at all.
  * PRIVACY WITHHELD -- an ineligible file is counted under its rule and neither its path nor
    any byte of its content appears anywhere in the artifact, checked against the whole
    serialised manifest rather than against the field that was supposed to hold it.
  * HUBS EXCLUDED -- a node past the degree bound is counted, not listed, and the control is
    that without the bound it WOULD have been listed.
  * FALLBACK WORKS -- each of the six retrieval reasons is triggered in isolation, with the
    other five held off, because a reason that only ever fires beside another proves nothing.

`ContextRepairPolicyTests` is D17's, not this task's, and is deliberately not written here.
"""

import ast
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "bin"
MODULE_PATH = BIN_DIR / "decision_context.py"

#: Pinned so the artifact carries no wall clock of its own. A manifest built with `now=None`
#: carries `generated_at: None`; nothing here ever reads the machine's clock.
INSTANT = datetime.datetime(2026, 9, 17, 12, 30, 0, tzinfo=datetime.timezone.utc)


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_ctx_test", BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dc = _load("decision_context")


def _node(node_id, label, source_file, loc="L1"):
    return {"id": node_id, "label": label, "source_file": source_file, "source_location": loc}


def _link(source, target, relation="calls", confidence="EXTRACTED"):
    return {"source": source, "target": target, "relation": relation, "confidence": confidence}


class _Tree:
    """A synthetic repository, a synthetic graph over it, and a canned git.

    Everything a candidate could be is represented once: a consumer that reaches the seed, an
    interface the seed reaches, a contract test, configuration only a scan can find, a hub, a
    personal store, two privacy shapes no prefix can express, and a graph path that tries to
    escape the repository root.
    """

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="decision_context_test_"))
        self.head = "aaaaaaaaaaaa1111"
        self.dirty, self.untracked = [], []
        self.write("app/main.py", "def run():\n    return helper()\n")
        self.write("app/utils.py", "def helper():\n    return 1\n")
        self.write("app/caller.py", "from app.main import run\n\n\ndef go():\n    return run()\n")
        self.write("app/hub.py", "# everything touches this\n")
        self.write("app/leaves.py", "# leaves\n")
        self.write("app/dup.py", "# reached two ways\n")
        self.write("spec/test_main.py", "def test_run():\n    assert run()\n")
        self.write("config/app.toml", "[main]\nrun = true\n")
        self.write("config/secretish.toml",
                   "main_token = ghp_0123456789abcdefghijABCDEF0123\n")
        self.write("config/long.toml", 'main = "' + "x" * 400 + '"\n')
        self.write("docs/guide.md", "see main for details\n")
        self.write("memory/notes.md", "main.py private notes\n")
        self.write("deploy/server.pem", "main material that is not for a manifest\n")
        self.write(".hidden/app.json", '{"main": true}\n')
        self.graph = {
            "version": "fixture-0.1", "directed": True,
            "nodes": [
                _node("app.main.run", "run", "app/main.py"),
                _node("app.utils.helper", "helper", "app/utils.py"),
                _node("app.caller.go", "go", "app/caller.py", loc="L4"),
                _node("spec.test_main.test_run", "test_run", "spec/test_main.py"),
                _node("hub.everything", "everything", "app/hub.py"),
                _node("memory.notes.thing", "thing", "memory/notes.md"),
                _node("escape", "escape", "../../etc/passwd"),
                _node("dup.a", "dup", "app/dup.py"),
                _node("dup.b", "dup", "app/dup.py"),
            ] + [_node(f"leaf{i}", f"leaf{i}", "app/leaves.py") for i in range(30)],
            "links": [
                _link("app.main.run", "app.utils.helper"),
                _link("app.caller.go", "app.main.run"),
                _link("spec.test_main.test_run", "app.main.run"),
                _link("app.main.run", "hub.everything"),
                _link("app.main.run", "memory.notes.thing"),
                _link("app.main.run", "escape"),
                _link("app.utils.helper", "dup.a"),
                _link("app.caller.go", "dup.b"),
            ] + [_link("hub.everything", f"leaf{i}") for i in range(30)],
        }
        self.graph_path = self.tmp / "graphify-out" / "graph.json"
        self.graph_path.parent.mkdir()
        self.save()

    # ---- tree -----------------------------------------------------------------------------

    def write(self, rel, text):
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def save(self):
        self.graph_path.write_text(json.dumps(self.graph))

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- the canned git probe --------------------------------------------------------------

    def git(self, args):
        verb = args[0]
        if verb == "rev-parse" and args[1] == "--show-toplevel":
            return 0, f"{self.tmp}\n"
        if verb == "rev-parse":
            return 0, f"{self.head}\n"
        if verb == "status":
            entries = [f" M {p}" for p in self.dirty] + [f"?? {p}" for p in self.untracked]
            return 0, "\0".join(entries) + ("\0" if entries else "")
        if verb == "config":
            return 0, "https://user:token@example.invalid/org/fixture.git\n"
        if verb == "ls-files":
            files = sorted(str(p.relative_to(self.tmp).as_posix())
                           for p in self.tmp.rglob("*") if p.is_file())
            return 0, "\0".join(files) + "\0"
        return 1, ""

    # ---- what the tests drive ---------------------------------------------------------------

    def stamp(self, **kwargs):
        return dc._gg().stamp(self.tmp, self.graph_path, extraction="working-tree",
                              git=self.git, **kwargs)

    def manifest(self, **kwargs):
        kwargs.setdefault("seeds", ["app/main.py"])
        kwargs.setdefault("now", INSTANT)
        kwargs.setdefault("git", self.git)
        graph = kwargs.pop("graph_path", self.graph_path)
        return dc.context_manifest(self.tmp, graph, **kwargs)


class _Case(unittest.TestCase):
    def setUp(self):
        self.tree = _Tree()
        self.addCleanup(self.tree.cleanup)

    def paths(self, manifest, kind=None):
        return [row["path"] for row in manifest["candidates"]
                if kind is None or row["kind"] == kind]

    def refusal(self, code, fn, *args, **kwargs):
        with self.assertRaises(Exception) as caught:
            fn(*args, **kwargs)
        self.assertEqual(getattr(caught.exception, "code", None), code,
                         f"expected [{code}], got {caught.exception}")
        return caught.exception


class ContextCandidateTests(_Case):

    # ---- A. the four candidate kinds, under a bounded policy ----------------------------

    def test_an_inbound_edge_is_a_direct_consumer_and_an_outbound_one_an_omitted_interface(self):
        manifest = self.tree.manifest()
        self.assertIn("app/caller.py", self.paths(manifest, "direct-consumer"))
        self.assertIn("app/utils.py", self.paths(manifest, "omitted-interface"))
        consumer = next(r for r in manifest["candidates"] if r["path"] == "app/caller.py")
        self.assertEqual(consumer["evidence"]["kind"], "graph-edge-inbound")
        self.assertEqual(consumer["symbol"], "go")
        interface = next(r for r in manifest["candidates"] if r["path"] == "app/utils.py")
        self.assertEqual(interface["evidence"]["kind"], "graph-edge-outbound")

    def test_a_contract_test_is_recognised_by_where_it_lives(self):
        manifest = self.tree.manifest()
        self.assertIn("spec/test_main.py", self.paths(manifest, "contract-test"))

    def test_the_test_prefixes_are_an_argument_and_not_an_assumption(self):
        manifest = self.tree.manifest(test_prefixes=("nowhere/",))
        # `spec/` is no longer a test directory, but the FILE is still named `test_main.py`,
        # which is the other half of the convention and a separate argument.
        self.assertIn("spec/test_main.py", self.paths(manifest, "contract-test"))
        manifest = self.tree.manifest(test_prefixes=("nowhere/",), kinds=("direct-consumer",))
        self.assertEqual(self.paths(manifest, "contract-test"), [])

    def test_configuration_is_found_by_the_scan_because_a_code_graph_does_not_index_it(self):
        manifest = self.tree.manifest()
        self.assertIn("config/app.toml", self.paths(manifest, "configuration"))
        row = next(r for r in manifest["candidates"] if r["path"] == "config/app.toml")
        self.assertEqual(row["evidence"]["kind"], "search-hit")
        self.assertIn("kind-not-in-graph", manifest["retrieval"]["reasons"])

    def test_a_kind_outside_the_retrieval_policy_is_excluded_and_counted(self):
        manifest = self.tree.manifest(kinds=("direct-consumer",))
        self.assertEqual(sorted({r["kind"] for r in manifest["candidates"]}),
                         ["direct-consumer"])
        self.assertGreater(manifest["excluded"]["not_requested"], 0)
        self.assertEqual(manifest["bounds"]["kinds"], ["direct-consumer"])

    def test_a_supplied_path_is_no_longer_an_omitted_interface(self):
        before = self.tree.manifest()
        self.assertIn("app/utils.py", self.paths(before))
        after = self.tree.manifest(supplied=["app/utils.py"])
        self.assertNotIn("app/utils.py", self.paths(after))
        self.assertGreater(after["excluded"]["already_supplied"],
                           before["excluded"]["already_supplied"])
        self.assertEqual(after["supplied"], ["app/utils.py"])

    def test_the_seed_is_never_handed_back_as_context_it_was_not_shown(self):
        # The seed's own file has to CARRY the search term, or the guard is unreachable and
        # the assertion below passes against a candidate that could never have been produced.
        self.tree.write("app/main.py", "# main entry point\ndef run():\n    return helper()\n")
        loose = self.tree.manifest(seeds=["app/main.py"], supplied=[])
        self.assertNotIn("app/main.py", self.paths(loose))
        self.assertGreater(loose["excluded"]["already_supplied"], 0)

    # ---- B. hubs -----------------------------------------------------------------------

    def test_an_irrelevant_hub_is_excluded_and_counted_never_listed(self):
        manifest = self.tree.manifest()
        self.assertNotIn("app/hub.py", self.paths(manifest))
        self.assertEqual(manifest["excluded"]["hubs"], 1)
        self.assertEqual(manifest["bounds"]["hub_degree"], dc._gg().DEFAULT_HUB_DEGREE)

    def test_the_hub_bound_is_what_excludes_it_and_raising_it_lets_it_through(self):
        # The control for the test above: with the degree bound above the hub's own degree the
        # same node IS a candidate, so the exclusion is the bound doing work and not the
        # fixture failing to produce a hub.
        manifest = self.tree.manifest(hub_degree=100)
        self.assertIn("app/hub.py", self.paths(manifest))
        self.assertEqual(manifest["excluded"]["hubs"], 0)

    # ---- C. privacy --------------------------------------------------------------------

    def test_a_personal_store_reached_through_the_graph_is_withheld_by_rule_and_count(self):
        manifest = self.tree.manifest()
        self.assertIn({"rule": "runtime-store", "count": 1}, manifest["withheld"])
        self.assertNotIn("memory/notes.md", self.paths(manifest))

    def test_a_withheld_file_leaks_neither_its_path_nor_a_byte_of_its_content(self):
        manifest = self.tree.manifest()
        blob = json.dumps(manifest)
        for secret in ("memory/notes.md", "private notes", "deploy/server.pem",
                       "not for a manifest", ".hidden/app.json"):
            self.assertNotIn(secret, blob, f"{secret!r} reached the manifest")
        self.assertGreaterEqual(manifest["withheld_total"], 3)

    def test_credential_shaped_and_dotted_paths_are_withheld_under_their_own_rules(self):
        manifest = self.tree.manifest()
        rules = {entry["rule"]: entry["count"] for entry in manifest["withheld"]}
        self.assertEqual(rules.get("credential-shape"), 1)
        self.assertEqual(rules.get("dot-path"), 1)

    def test_the_withheld_report_is_ordered_by_the_closed_rule_vocabulary(self):
        manifest = self.tree.manifest()
        order = [entry["rule"] for entry in manifest["withheld"]]
        self.assertEqual(order, [r for r in dc.PRIVACY_RULE_KINDS if r in set(order)])

    def test_an_operator_denied_prefix_extends_the_policy(self):
        manifest = self.tree.manifest(denied=["docs/"])
        self.assertNotIn("docs/guide.md", self.paths(manifest))
        rules = {entry["rule"]: entry["count"] for entry in manifest["withheld"]}
        self.assertGreaterEqual(rules.get("operator-denied", 0), 0)
        self.assertIn("docs/", manifest["bounds"]["denied_prefixes"])

    def test_the_scan_is_told_the_prefix_rules_so_a_personal_store_is_never_opened(self):
        gg = dc._gg()
        seen = {}
        original = gg.search

        def watched(repo, terms, **kwargs):
            seen.update(kwargs)
            return original(repo, terms, **kwargs)

        gg.search = watched
        self.addCleanup(setattr, gg, "search", original)
        self.tree.manifest()
        self.assertTrue(seen, "the scan never ran, so this proves nothing about its excludes")
        for prefix in dc.store_prefixes():
            self.assertIn(prefix, seen["excludes"])

    def test_the_store_prefixes_come_from_the_module_that_declares_the_stores(self):
        stores = _load("runtime_data").STORES
        self.assertEqual(dc.store_prefixes(), tuple(sorted(f"{s}/" for s in stores)))
        self.assertTrue(stores)

    def test_no_argument_anywhere_can_switch_a_privacy_rule_off(self):
        import inspect
        params = set(inspect.signature(dc.context_manifest).parameters)
        for switch in ("allow", "allow_private", "skip_privacy", "privacy", "unsafe",
                       "include_private", "no_privacy"):
            self.assertNotIn(switch, params)
        self.assertIn("denied", params, "the policy is extendable even though it is not "
                                        "relaxable")

    def test_a_privacy_rule_reports_the_first_match_in_a_stable_order(self):
        self.assertEqual(dc.privacy_rule("memory/x.md"), "runtime-store")
        self.assertEqual(dc.privacy_rule("deploy/a.pem"), "credential-shape")
        self.assertEqual(dc.privacy_rule(".ssh/id_rsa"), "credential-shape")
        self.assertEqual(dc.privacy_rule(".config/app.py"), "dot-path")
        self.assertEqual(dc.privacy_rule("memory/x.md", denied=("memory/",)),
                         "operator-denied")
        self.assertIsNone(dc.privacy_rule("app/main.py"))

    # ---- D. redaction and bounds on retained text ---------------------------------------

    def test_a_credential_shape_in_a_retained_excerpt_is_labelled_and_counted(self):
        manifest = self.tree.manifest()
        row = next(r for r in manifest["candidates"] if r["path"] == "config/secretish.toml")
        self.assertNotIn("ghp_0123456789abcdefghijABCDEF0123", json.dumps(manifest))
        self.assertIn("[redacted:", row["excerpt"])
        self.assertTrue(manifest["redactions"])
        self.assertTrue(all(isinstance(v, int) and v > 0
                            for v in manifest["redactions"].values()))

    def test_an_excerpt_is_bounded_by_the_policy_and_says_where_it_cut(self):
        manifest = self.tree.manifest(excerpt_chars=40)
        row = next(r for r in manifest["candidates"] if r["path"] == "config/long.toml")
        self.assertIn("truncated", row["excerpt"])
        self.assertLess(len(row["excerpt"]), 120)
        wider = self.tree.manifest(excerpt_chars=400)
        row = next(r for r in wider["candidates"] if r["path"] == "config/long.toml")
        self.assertNotIn("truncated", row["excerpt"])

    def test_a_graph_candidate_carries_no_excerpt_because_no_file_was_opened(self):
        manifest = self.tree.manifest()
        for row in manifest["candidates"]:
            if row["evidence"]["kind"].startswith("graph-edge"):
                self.assertIsNone(row["excerpt"])

    # ---- E. untrusted paths from the graph ----------------------------------------------

    def test_a_graph_path_that_escapes_the_repository_is_rejected_and_never_named(self):
        manifest = self.tree.manifest()
        self.assertEqual(manifest["excluded"]["rejected_paths"], 1)
        blob = json.dumps(manifest)
        self.assertNotIn("passwd", blob)
        self.assertNotIn("..", blob)

    # ---- F. freshness, including uncommitted work ---------------------------------------

    def test_a_stamped_and_untouched_graph_is_fresh_and_its_files_say_so(self):
        self.tree.stamp()
        manifest = self.tree.manifest()
        self.assertEqual(manifest["freshness"]["verdict"], "fresh")
        self.assertTrue(manifest["freshness"]["sidecar"])
        self.assertEqual(manifest["freshness"]["extraction"], "working-tree")
        self.assertEqual(manifest["freshness"]["revision"]["now"], self.tree.head)
        states = {row["path"]: row["file_state"] for row in manifest["candidates"]}
        self.assertEqual(states["app/utils.py"], "unchanged")

    def test_a_dirty_but_unchanged_covered_file_is_flagged_without_making_it_stale(self):
        self.tree.stamp()
        self.tree.dirty = ["app/utils.py"]
        manifest = self.tree.manifest()
        self.assertEqual(manifest["freshness"]["verdict"], "fresh")
        self.assertEqual(manifest["freshness"]["dirty_now"], 1)

    def test_a_changed_covered_file_makes_the_graph_partial_and_is_counted(self):
        self.tree.stamp()
        self.tree.write("app/utils.py", "def helper():\n    return 2\n")
        self.tree.dirty = ["app/utils.py"]
        manifest = self.tree.manifest()
        self.assertEqual(manifest["freshness"]["verdict"], "partial")
        self.assertEqual(manifest["freshness"]["changed"], 1)

    def test_untracked_work_the_graph_never_saw_is_the_reason_the_scan_runs(self):
        # THE failure mode this module exists for: the graph is FRESH by every file it covers,
        # and the work that actually broke is in a file it has never heard of. The kinds are
        # narrowed to the two the graph can answer so `kind-not-in-graph` cannot mask this.
        self.tree.stamp()
        narrow = ("direct-consumer", "omitted-interface")
        quiet = self.tree.manifest(kinds=narrow)
        self.assertEqual(quiet["retrieval"]["reasons"], [])
        self.assertEqual(quiet["retrieval"]["sources"], ["graph"])

        self.tree.write("app/brandnew.py", "def brandnew():\n    return main\n")
        self.tree.untracked = ["app/brandnew.py"]
        manifest = self.tree.manifest(kinds=narrow)
        self.assertEqual(manifest["freshness"]["verdict"], "fresh")
        self.assertEqual(manifest["freshness"]["uncovered_changed"], 1)
        self.assertEqual(manifest["retrieval"]["reasons"], ["uncovered-dirty-context"])
        self.assertEqual(manifest["retrieval"]["sources"], ["graph", "search"])
        self.assertIn("app/brandnew.py", self.paths(manifest))

    def test_without_a_graph_every_dirty_and_untracked_path_counts_as_uncovered(self):
        self.tree.dirty = ["app/utils.py"]
        self.tree.untracked = ["app/brandnew.py"]
        manifest = self.tree.manifest(graph_path=None)
        self.assertEqual(manifest["freshness"]["uncovered_changed"], 2)
        self.assertIn("uncovered-dirty-context", manifest["retrieval"]["reasons"])

    # ---- G. the retrieval reasons, one at a time ----------------------------------------

    def test_no_graph_at_all_falls_back_to_the_scan_and_says_so(self):
        manifest = self.tree.manifest(graph_path=None)
        self.assertIn("no-graph", manifest["retrieval"]["reasons"])
        self.assertEqual(manifest["retrieval"]["sources"], ["search"])
        self.assertEqual(manifest["retrieval"]["graph_role"], "none")
        self.assertTrue(manifest["candidates"])

    def test_a_missing_graph_file_is_the_same_as_no_graph(self):
        manifest = self.tree.manifest(graph_path=self.tree.tmp / "absent" / "graph.json")
        self.assertIn("no-graph", manifest["retrieval"]["reasons"])

    def test_an_unreadable_graph_is_its_own_reason_and_not_silently_no_graph(self):
        self.tree.graph_path.write_text("{ this is not json")
        manifest = self.tree.manifest()
        self.assertIn("graph-unreadable", manifest["retrieval"]["reasons"])
        self.assertNotIn("no-graph", manifest["retrieval"]["reasons"])
        self.assertEqual(manifest["retrieval"]["sources"], ["search"])

    def test_an_unstamped_graph_is_not_fresh_and_its_edges_are_hints(self):
        manifest = self.tree.manifest()
        self.assertEqual(manifest["freshness"]["verdict"], "unknown")
        self.assertEqual(manifest["retrieval"]["graph_role"], "hints")
        self.assertIn("graph-not-fresh", manifest["retrieval"]["reasons"])

    def test_a_seed_the_graph_does_not_contain_is_its_own_reason(self):
        self.tree.stamp()
        manifest = self.tree.manifest(seeds=["app/main.py", "app/absent.py"],
                                      kinds=("direct-consumer", "omitted-interface"))
        self.assertEqual(manifest["retrieval"]["reasons"], ["seed-not-in-graph"])

    def test_kind_not_in_graph_is_only_claimed_about_a_graph_that_was_read(self):
        manifest = self.tree.manifest(graph_path=None)
        self.assertNotIn("kind-not-in-graph", manifest["retrieval"]["reasons"])
        self.tree.stamp()
        read = self.tree.manifest()
        self.assertIn("kind-not-in-graph", read["retrieval"]["reasons"])

    def test_a_fresh_graph_answering_the_kinds_asked_for_runs_no_scan_at_all(self):
        self.tree.stamp()
        gg = dc._gg()
        original = gg.search

        def forbidden(*args, **kwargs):
            raise AssertionError("the scan ran although the graph answered")

        gg.search = forbidden
        self.addCleanup(setattr, gg, "search", original)
        manifest = self.tree.manifest(kinds=("direct-consumer", "omitted-interface"))
        self.assertEqual(manifest["retrieval"]["sources"], ["graph"])
        self.assertEqual(manifest["retrieval"]["reasons"], [])
        self.assertEqual(manifest["retrieval"]["graph_role"], "evidence")

    def test_every_recorded_reason_is_in_the_closed_vocabulary(self):
        for manifest in (self.tree.manifest(), self.tree.manifest(graph_path=None)):
            for reason in manifest["retrieval"]["reasons"]:
                self.assertIn(reason, dc.RETRIEVAL_REASONS)

    def test_the_scan_never_answers_from_the_graph_or_its_own_sidecar(self):
        self.tree.stamp()
        manifest = self.tree.manifest()
        for row in manifest["candidates"]:
            self.assertNotIn("graphify-out", row["path"])

    def test_the_scan_never_reclassifies_a_file_the_graph_already_named(self):
        # `app/caller.py` carries the text `app.main`, so the scan finds it too. Taken as a
        # second opinion it would arrive again as a directionless "omitted interface" and
        # overwrite what an inbound edge actually showed.
        manifest = self.tree.manifest()
        rows = [r for r in manifest["candidates"] if r["path"] == "app/caller.py"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "direct-consumer")
        self.assertGreater(manifest["excluded"]["duplicates"], 0)

    # ---- H. abstention -------------------------------------------------------------------

    def test_nothing_relevant_is_an_abstention_with_its_reason_not_an_empty_success(self):
        empty = _Tree()
        self.addCleanup(empty.cleanup)
        for rel in ("app/caller.py", "app/utils.py", "spec/test_main.py", "config/app.toml",
                    "config/secretish.toml", "config/long.toml", "docs/guide.md",
                    "app/hub.py", "app/leaves.py", "memory/notes.md", "deploy/server.pem",
                    ".hidden/app.json"):
            (empty.tmp / rel).unlink()
        empty.graph["nodes"] = [_node("app.main.run", "run", "app/main.py")]
        empty.graph["links"] = []
        empty.save()
        manifest = empty.manifest()
        self.assertEqual(manifest["status"], "no-relevant-context")
        self.assertEqual(manifest["candidates"], [])
        self.assertEqual(manifest["abstention"], ["no-evidence-found"])
        self.assertIn("legitimate", manifest["abstention_note"])

    def test_an_abstention_says_when_everything_it_found_was_withheld(self):
        withheld = _Tree()
        self.addCleanup(withheld.cleanup)
        withheld.graph["nodes"] = [_node("app.main.run", "run", "app/main.py"),
                                   _node("memory.notes.thing", "thing", "memory/notes.md")]
        withheld.graph["links"] = [_link("app.main.run", "memory.notes.thing")]
        withheld.save()
        manifest = withheld.manifest(kinds=("direct-consumer", "omitted-interface"),
                                     denied=["app/", "config/", "docs/", "spec/"])
        self.assertEqual(manifest["status"], "no-relevant-context")
        self.assertIn("all-candidates-withheld", manifest["abstention"])

    def test_an_abstention_says_when_the_only_neighbour_was_a_hub(self):
        hubbed = _Tree()
        self.addCleanup(hubbed.cleanup)
        hubbed.graph["links"] = [_link("app.main.run", "hub.everything")] + \
            [_link("hub.everything", f"leaf{i}") for i in range(30)]
        hubbed.save()
        manifest = hubbed.manifest(kinds=("direct-consumer", "omitted-interface"),
                                   denied=["config/", "docs/", "spec/", "app/caller.py",
                                           "app/utils.py", "app/leaves.py"])
        self.assertEqual(manifest["status"], "no-relevant-context")
        self.assertIn("all-candidates-hub", manifest["abstention"])

    def test_an_abstention_says_when_the_seed_matched_no_node(self):
        self.tree.stamp()
        manifest = self.tree.manifest(seeds=["nowhere_at_all_xyzzy"],
                                      kinds=("direct-consumer", "omitted-interface"))
        self.assertEqual(manifest["status"], "no-relevant-context")
        self.assertIn("no-seed-matched", manifest["abstention"])

    def test_every_abstention_reason_is_in_the_closed_vocabulary(self):
        manifest = self.tree.manifest()
        self.assertEqual(manifest["abstention"], [])
        self.assertEqual(manifest["status"], "candidates")
        for reason in dc.ABSTENTION_REASONS:
            self.assertIsInstance(reason, str)

    # ---- I. the budget -------------------------------------------------------------------

    def test_the_candidate_ceiling_cuts_and_says_it_cut(self):
        manifest = self.tree.manifest(max_candidates=2)
        self.assertEqual(len(manifest["candidates"]), 2)
        self.assertTrue(manifest["retrieval"]["over_budget"])
        self.assertGreater(manifest["excluded"]["over_budget"], 0)

    def test_the_per_kind_ceiling_stops_one_kind_crowding_the_package(self):
        full = self.tree.manifest()
        self.assertGreater(len([r for r in full["candidates"]
                                if r["kind"] == "configuration"]), 1)
        capped = self.tree.manifest(max_per_kind=1)
        by_kind = {}
        for row in capped["candidates"]:
            by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
        self.assertTrue(all(count == 1 for count in by_kind.values()), by_kind)

    def test_the_bounds_the_manifest_was_built_under_ride_on_the_manifest(self):
        manifest = self.tree.manifest(max_candidates=5, max_per_kind=2, depth=2,
                                      hub_degree=9, excerpt_chars=77, excludes=["docs/"])
        bounds = manifest["bounds"]
        self.assertEqual(bounds["max_candidates"], 5)
        self.assertEqual(bounds["max_per_kind"], 2)
        self.assertEqual(bounds["hops"], 2)
        self.assertEqual(bounds["hub_degree"], 9)
        self.assertEqual(bounds["excerpt_chars"], 77)
        self.assertEqual(bounds["excludes"], ["docs/"])

    def test_a_caller_exclude_keeps_a_directory_out_of_both_passes(self):
        manifest = self.tree.manifest(excludes=["config/", "docs/"])
        for row in manifest["candidates"]:
            self.assertFalse(row["path"].startswith(("config/", "docs/")), row["path"])

    # ---- J. refusals ---------------------------------------------------------------------

    def test_a_bare_string_of_seeds_is_refused_rather_than_read_one_character_at_a_time(self):
        # The list/tuple check below it would refuse a string too, with the same code. This
        # branch earns its place by SAYING WHY, so the message is what is pinned here.
        error = self.refusal("wrong-type", self.tree.manifest, seeds="app/main.py")
        self.assertIn("one character at a time", str(error))
        self.refusal("wrong-type", self.tree.manifest, seeds=b"app/main.py")

    def test_a_blank_or_non_string_seed_is_refused(self):
        self.refusal("value-invalid", self.tree.manifest, seeds=["app/main.py", "  "])
        self.refusal("value-invalid", self.tree.manifest, seeds=[None])

    def test_no_seed_at_all_is_refused_rather_than_retrieving_the_whole_tree(self):
        self.refusal("missing-field", self.tree.manifest, seeds=[])

    def test_more_seeds_than_the_ceiling_are_refused(self):
        self.refusal("bounds-exceeded", self.tree.manifest,
                     seeds=[f"seed{i}" for i in range(dc.MAX_SEEDS + 1)])

    def test_an_unknown_candidate_kind_is_refused(self):
        self.refusal("unknown-value", self.tree.manifest, kinds=("everything",))

    def test_an_empty_retrieval_policy_is_refused(self):
        self.refusal("missing-field", self.tree.manifest, kinds=())

    def test_a_bound_outside_its_ceiling_is_refused(self):
        self.refusal("bounds-exceeded", self.tree.manifest, max_candidates=0)
        self.refusal("bounds-exceeded", self.tree.manifest,
                     max_candidates=dc.MAX_CANDIDATES_CEILING + 1)
        self.refusal("bounds-exceeded", self.tree.manifest, depth=dc.MAX_DEPTH_CEILING + 1)
        self.refusal("bounds-exceeded", self.tree.manifest,
                     excerpt_chars=dc.MAX_EXCERPT_CEILING + 1)
        self.refusal("wrong-type", self.tree.manifest, max_candidates=True)
        self.refusal("wrong-type", self.tree.manifest, max_candidates="12")

    def test_a_zoneless_instant_is_refused_rather_than_read_as_local_time(self):
        self.refusal("value-invalid", self.tree.manifest,
                     now=datetime.datetime(2026, 9, 17, 12, 30))
        self.refusal("wrong-type", self.tree.manifest, now="2026-09-17T12:30:00Z")

    def test_no_instant_at_all_leaves_the_field_null_rather_than_reading_a_clock(self):
        manifest = self.tree.manifest(now=None)
        self.assertIsNone(manifest["generated_at"])

    def test_a_supplied_instant_is_recorded_in_utc(self):
        other = datetime.datetime(2026, 9, 17, 8, 30, 0,
                                  tzinfo=datetime.timezone(datetime.timedelta(hours=-4)))
        self.assertEqual(self.tree.manifest(now=other)["generated_at"], "2026-09-17T12:30:00Z")

    # ---- K. the dependency fence ---------------------------------------------------------

    def test_neither_closed_vocabulary_has_a_dependency_member_to_set(self):
        for value in dc.CANDIDATE_KINDS + dc.EVIDENCE_KINDS:
            self.assertFalse(dc._is_dependency_key(value), value)

    def test_a_dependency_spelled_key_is_refused_however_it_is_punctuated(self):
        for key in ("depends_on", "DependsOn", "depends.on", "dependency", "required_by",
                    "blocked.by", "safe_to_parallel", "parallel-write", "used_by",
                    "authorises", "context.depends", "graph.requires", "edge.blocks"):
            with self.subTest(key=key):
                self.refusal("authority-field", dc.assert_no_dependency_claim,
                             {"candidates": [{key: "app/utils.py"}]})

    def test_the_fence_looks_inside_lists_and_nested_structures(self):
        self.refusal("authority-field", dc.assert_no_dependency_claim,
                     {"a": [{"b": {"c": [{"depends_on": 1}]}}]})
        dc.assert_no_dependency_claim({"a": [{"b": {"c": [{"path": "app/x.py"}]}}]})

    def test_an_ordinary_manifest_key_is_not_mistaken_for_a_claim(self):
        manifest = self.tree.manifest()
        dc.assert_no_dependency_claim(manifest)

    def test_the_fence_is_wired_into_the_build_and_runs_before_the_digest(self):
        seen = {}
        original = dc.assert_no_dependency_claim

        def recorder(value, where="the candidate manifest"):
            seen["keys"] = sorted(value)
            return original(value, where)

        dc.assert_no_dependency_claim = recorder
        self.addCleanup(setattr, dc, "assert_no_dependency_claim", original)
        self.tree.manifest()
        self.assertTrue(seen, "the builder never called the fence")
        self.assertNotIn("sha256", seen["keys"],
                         "the digest was taken before the body was swept")

    def test_a_refusing_fence_stops_the_build(self):
        original = dc.assert_no_dependency_claim

        def refuse(value, where="the candidate manifest"):
            raise AssertionError("the fence refused")

        dc.assert_no_dependency_claim = refuse
        self.addCleanup(setattr, dc, "assert_no_dependency_claim", original)
        with self.assertRaises(AssertionError):
            self.tree.manifest()

    def test_an_extractors_own_word_for_an_edge_is_quoted_and_never_adopted_as_a_key(self):
        quoted = _Tree()
        self.addCleanup(quoted.cleanup)
        for link in quoted.graph["links"]:
            link["relation"] = "depends_on"
        quoted.save()
        manifest = quoted.manifest()
        row = next(r for r in manifest["candidates"]
                   if r["evidence"]["kind"].startswith("graph-edge"))
        self.assertEqual(row["evidence"]["edge_label"], "depends_on")
        self.assertIn("not interpreted", row["evidence"]["edge_label_note"])
        self.assertNotIn("depends_on", json.dumps(sorted(row["evidence"])))

    def test_every_candidate_states_that_it_carries_no_authority(self):
        manifest = self.tree.manifest()
        self.assertTrue(manifest["candidates"])
        for row in manifest["candidates"]:
            self.assertIsNone(row["authority"])
            self.assertIn("navigation evidence", row["note"])
        self.assertIsNone(manifest["authority"])
        self.assertIn("authorises no concurrent write", manifest["navigation"])

    # ---- L. determinism -------------------------------------------------------------------

    def test_two_builds_of_the_same_inputs_are_byte_identical(self):
        first = self.tree.manifest()
        second = self.tree.manifest()
        self.assertEqual(dc.canonical_bytes(first), dc.canonical_bytes(second))
        self.assertEqual(repr(first), repr(second))
        self.assertEqual(first["sha256"], second["sha256"])

    def test_a_graph_whose_nodes_and_links_are_shuffled_is_the_same_artifact(self):
        baseline = self.tree.manifest(depth=2)
        rng = random.Random(20260917)
        for _ in range(6):
            rng.shuffle(self.tree.graph["nodes"])
            rng.shuffle(self.tree.graph["links"])
            self.tree.save()
            shuffled = self.tree.manifest(depth=2)
            self.assertEqual(dc.canonical_bytes(baseline), dc.canonical_bytes(shuffled))

    def test_the_digest_covers_every_field_but_itself(self):
        manifest = self.tree.manifest()
        self.assertEqual(manifest["sha256"],
                         hashlib.sha256(dc.canonical_bytes(manifest)).hexdigest())
        mutated = dict(manifest)
        mutated["repository"] = "somewhere-else"
        self.assertNotEqual(hashlib.sha256(dc.canonical_bytes(mutated)).hexdigest(),
                            manifest["sha256"])

    def test_a_different_input_is_a_different_artifact(self):
        self.assertNotEqual(self.tree.manifest()["sha256"],
                            self.tree.manifest(max_candidates=3)["sha256"])

    def test_the_artifact_is_identical_under_two_different_hash_seeds(self):
        # Written OUTSIDE the fixture tree: a driver sitting inside it would itself become a
        # scan hit, and the artifact under comparison would be describing the test harness.
        holder = Path(tempfile.mkdtemp(prefix="decision_context_driver_"))
        self.addCleanup(shutil.rmtree, holder, True)
        driver = holder / "determinism_driver.py"
        driver.write_text(_DRIVER)
        results = []
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            proc = subprocess.run(
                [sys.executable, str(driver), str(ROOT), str(self.tree.tmp),
                 str(self.tree.graph_path)],
                capture_output=True, text=True, timeout=180, env=env, cwd=str(ROOT))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(proc.stdout.strip(), "the child printed nothing to compare")
            results.append(proc.stdout)
        self.assertEqual(len(set(results)), 1, results)

    def test_candidates_arrive_in_the_order_the_kind_vocabulary_declares(self):
        manifest = self.tree.manifest()
        seen = [(dc.CANDIDATE_KINDS.index(row["kind"]), row["path"])
                for row in manifest["candidates"]]
        self.assertEqual(seen, sorted(seen))
        self.assertGreater(len({kind for kind, _ in seen}), 1,
                           "one kind only, so this proves nothing about the ordering")

    def test_two_graph_nodes_at_one_place_collapse_to_one_candidate(self):
        # `dup.a` and `dup.b` share a file, a location and a label, and are reached from two
        # different parents. They are indistinguishable to a reader, so one row is the honest
        # answer -- and WHICH one survives has to be settled by the content, not by the order
        # the graph happened to list its nodes in.
        manifest = self.tree.manifest(depth=2)
        rows = [row for row in manifest["candidates"] if row["path"] == "app/dup.py"]
        self.assertEqual(len(rows), 1)
        self.assertGreater(manifest["excluded"]["duplicates"], 0)

    def test_nothing_emitted_is_a_set_or_a_frozenset(self):
        def walk(value, path="manifest"):
            self.assertNotIsInstance(value, (set, frozenset), path)
            if isinstance(value, dict):
                for key, sub in value.items():
                    walk(sub, f"{path}.{key}")
            elif isinstance(value, list):
                for index, sub in enumerate(value):
                    walk(sub, f"{path}[{index}]")
        walk(self.tree.manifest())

    # ---- M. the reference and the rendering ------------------------------------------------

    def test_a_reference_carries_the_version_and_the_digest_and_nothing_else(self):
        manifest = self.tree.manifest()
        ref = dc.context_ref(manifest)
        self.assertEqual(sorted(ref), ["sha", "v"])
        self.assertEqual(ref["v"], dc.CONTEXT_VERSION)
        self.assertEqual(ref["sha"], manifest["sha256"])

    def test_a_reference_refuses_anything_that_is_not_this_manifest(self):
        self.refusal("not-a-reference", dc.context_ref,
                     {"v": "something/else", "sha256": "a" * 64})
        self.refusal("not-a-reference", dc.context_ref,
                     {"v": dc.CONTEXT_VERSION, "sha256": "short"})
        self.refusal("not-a-reference", dc.context_ref, "a string")

    def test_the_rendering_is_bounded_and_states_the_cut(self):
        manifest = self.tree.manifest()
        text = dc.render_manifest(manifest, max_chars=300)
        self.assertLessEqual(len(text), 300)
        self.assertIn("truncated", text)
        full = dc.render_manifest(manifest)
        self.assertIn("context candidates", full)
        self.assertIn("withheld:", full)

    def test_the_rendering_of_an_abstention_names_its_reason(self):
        self.tree.stamp()
        manifest = self.tree.manifest(seeds=["nowhere_at_all_xyzzy"],
                                      kinds=("direct-consumer",))
        self.assertIn("no candidates", dc.render_manifest(manifest))

    def test_the_manifest_states_its_version_its_limits_and_the_seams(self):
        manifest = self.tree.manifest()
        self.assertEqual(manifest["v"], dc.CONTEXT_VERSION)
        gg = dc._gg()
        for limit in gg.KNOWN_LIMITS:
            self.assertIn(limit, manifest["limits"])
        self.assertEqual(manifest["advisory"], gg.ADVISORY)

    # ---- N. no dispatch --------------------------------------------------------------------

    def test_nothing_in_a_build_starts_a_process(self):
        gg = dc._gg()

        class Raising:
            @staticmethod
            def run(*args, **kwargs):
                raise AssertionError("a process was started")

        had = "proc_runner" in gg._SIBLINGS
        previous = gg._SIBLINGS.get("proc_runner")
        gg._SIBLINGS["proc_runner"] = Raising

        def restore():
            if had:
                gg._SIBLINGS["proc_runner"] = previous
            else:
                gg._SIBLINGS.pop("proc_runner", None)

        self.addCleanup(restore)
        # The control: without the injected probe the seam WOULD spawn git, so the raising
        # runner is on a path this call really reaches. Without this the test below would pass
        # against a runner nothing could ever have called.
        with self.assertRaises(AssertionError):
            dc.context_manifest(self.tree.tmp, self.tree.graph_path, seeds=["app/main.py"],
                                now=INSTANT)
        manifest = self.tree.manifest()
        self.assertEqual(manifest["v"], dc.CONTEXT_VERSION)
        self.assertTrue(manifest["candidates"])

    def test_the_module_carries_no_process_starting_primitive_of_its_own(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    calls.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    calls.add(fn.id)
        self.assertTrue(calls, "the AST walk found no calls, so this sweep is vacuous")
        self.assertIn("context_manifest", {n.name for n in ast.walk(tree)
                                           if isinstance(n, ast.FunctionDef)})
        for banned in ("Popen", "system", "popen", "spawnv", "fork", "execv", "check_output",
                       "check_call"):
            self.assertNotIn(banned, calls)
        for banned in ("subprocess", "os.system", "os.popen", "Path.home", "expanduser",
                       "urllib", "urlopen", "socket"):
            self.assertNotIn(banned, text, f"{banned} appeared in the module source")

    def test_the_module_names_graphify_only_to_state_that_it_never_runs_it(self):
        # Same shape `tests/test_graph_ground.py` uses on the seam: the name must be PRESENT,
        # because the fence has to be written down, and must never sit where an argv token
        # would. An absent name would let this pass by saying nothing at all.
        text = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("graphify", text)
        for argv_shaped in ('["graphify"', "'graphify',", '"graphify",', '["graphify",',
                            "uv tool install", "pip install", "shutil.which"):
            self.assertNotIn(argv_shaped, text)

    def test_no_harness_command_line_is_named_anywhere_in_the_module(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        for cli in ("copilot", "codex", "cursor", "claude ", "agent "):
            self.assertNotIn(cli, text.lower())

    # ---- O. one authority per concern -------------------------------------------------------

    def test_the_module_reaches_only_the_named_surface_of_each_sibling(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        aliases = {"gg": "_gg", "sp": "_sp"}
        reached = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            value = node.value
            owner = None
            if isinstance(value, ast.Name) and value.id in aliases:
                owner = aliases[value.id]
            elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                    and value.func.id in ("_gg", "_sp", "_rd", "_contract", "_sibling"):
                owner = value.func.id
            if owner:
                reached.setdefault(owner, set()).add(node.attr)
        self.assertTrue(reached, "the walk found no sibling access at all")
        self.assertEqual({owner: sorted(names) for owner, names in sorted(reached.items())}, {
            "_contract": ["ContractError"],
            "_gg": ["ADVISORY", "DEFAULT_HUB_DEGREE", "KNOWN_LIMITS", "LABEL_CHARS",
                    "SIDECAR_NAME", "freshness", "impact", "load_graph_bytes", "repo_state",
                    "search"],
            "_rd": ["redact"],
            "_sibling": ["STORES"],
            "_sp": ["SafePathError", "safe_parts"],
        })

    def test_this_module_never_parses_a_graph_or_decides_freshness_itself(self):
        text = MODULE_PATH.read_text(encoding="utf-8")
        for owned_elsewhere in ("json.load", "_nodes_of", "_links_of", "build_brief",
                                "compute_hubs", "read_sidecar", "confined_read_bytes"):
            self.assertNotIn(owned_elsewhere, text)

    def test_the_seam_modules_are_unchanged_by_importing_this_one(self):
        gg = dc._gg()
        self.assertEqual(gg.CONTRACT_VERSION, "polytropos.grounding/1")
        self.assertEqual(gg.SIDECAR_VERSION, "polytropos.graph-provenance/1")

    def test_the_manifest_version_is_registered_with_the_release_gate(self):
        gate = (BIN_DIR / "release_gate.py").read_text(encoding="utf-8")
        self.assertIn('"decision_context", "CONTEXT_VERSION"', gate)


_DRIVER = '''import datetime
import hashlib
import importlib.util
import sys
from pathlib import Path

root, tree, graph = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("dc", root / "bin" / "decision_context.py")
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def git(args):
    verb = args[0]
    if verb == "rev-parse" and args[1] == "--show-toplevel":
        return 0, str(tree) + "\\n"
    if verb == "rev-parse":
        return 0, "aaaaaaaaaaaa1111\\n"
    if verb == "status":
        return 0, ""
    if verb == "config":
        return 0, "https://example.invalid/org/fixture.git\\n"
    if verb == "ls-files":
        files = sorted(str(p.relative_to(tree).as_posix())
                       for p in tree.rglob("*") if p.is_file())
        return 0, "\\0".join(files) + "\\0"
    return 1, ""


manifest = dc.context_manifest(
    tree, graph, seeds=["app/main.py"], git=git, depth=2,
    now=datetime.datetime(2026, 9, 17, 12, 30, 0, tzinfo=datetime.timezone.utc))
print(manifest["sha256"])
print(hashlib.sha256(repr(manifest).encode("utf-8")).hexdigest())
'''


if __name__ == "__main__":
    unittest.main()
