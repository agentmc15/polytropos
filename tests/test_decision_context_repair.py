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

`ContextRepairPolicyTests` below is D17's and answers a different question against a different
module: whether ONE bounded context repair is admissible after a failure the ledger already
classified. It shares this file because it shares the subject, and it shares nothing else --
`bin/decision_policy.py` is what it exercises, every fixture it uses is its own, and it does not
touch a test, a helper or an assertion above it.
"""

import ast
import collections
import contextlib
import dataclasses
import datetime
import hashlib
import importlib.util
import inspect
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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

    def test_a_frozen_mapping_is_swept_rather_than_walked_past(self):
        """A walker that tests for the concrete `dict` sees nothing in a `MappingProxyType` and
        therefore certifies it. That is not hypothetical here: D17 freezes its repair plan into
        exactly that type, and sweeps BEFORE freezing only because this used to be the only
        order that worked."""
        frozen = types.MappingProxyType({"depends_on": "app/utils.py"})
        self.refusal("authority-field", dc.assert_no_dependency_claim, frozen)
        self.refusal("authority-field", dc.assert_no_dependency_claim, {"retry": frozen})
        self.refusal("authority-field", dc.assert_no_dependency_claim,
                     {"a": [{"retry": types.MappingProxyType({"safe_to_parallel": True})}]})
        # ... and a frozen mapping with nothing to hide still passes, so the refusals above are
        # about the KEY and not about the type.
        dc.assert_no_dependency_claim(types.MappingProxyType({"path": "app/utils.py"}))

    def test_a_shape_the_sweep_cannot_walk_is_refused_instead_of_certified(self):
        """The general form of the defect above: any container the walk does not descend into
        is a container it inspects nothing inside of. A namedtuple is the sharp case -- it IS a
        tuple, so descending it as a sequence walks its VALUES and never the field name where
        the claim lives -- so it is refused rather than unpacked."""
        pair = collections.namedtuple("_Claiming", ["depends_on"])("app/utils.py")
        instance = dataclasses.make_dataclass("_Claim", [("depends_on", str)])("app/utils.py")
        cases = {
            "namedtuple": pair,
            "namedtuple nested": {"retry": pair},
            "dataclass": instance,
            "dataclass nested": [instance],
            "items view": {"retry": {"depends_on": "app/utils.py"}.items()},
            "bytes": {"retry": b"{}"},
            "arbitrary object": {"retry": Path("/nowhere")},
        }
        for label, value in cases.items():
            with self.subTest(case=label):
                error = self.refusal("authority-field", dc.assert_no_dependency_claim, value)
                self.assertIn("cannot inspect", str(error))
                self.assertIn("cannot be certified free of a dependency claim", str(error))

    def test_a_generator_is_refused_without_being_consumed(self):
        """Descending one would be worse than passing it: it would empty the caller's own
        object and could not be repeated. So the refusal has to leave it untouched, which is
        what the second half of this test checks."""
        rows = [{"depends_on": "app/utils.py"}]
        stream = (row for row in rows)
        error = self.refusal("authority-field", dc.assert_no_dependency_claim,
                             {"candidates": stream})
        self.assertIn("cannot inspect", str(error))
        self.assertEqual(list(stream), rows, "the sweep consumed the caller's generator")

    def test_a_set_is_actually_descended_and_not_accepted_on_sight(self):
        """A set is walked rather than refused, because it CAN be walked exhaustively -- and
        this is the control proving that, since an un-sweepable member inside one is still
        caught. Nothing about the hardening is "refuse the unfamiliar"."""
        pair = collections.namedtuple("_Claiming", ["depends_on"])("app/utils.py")
        self.refusal("authority-field", dc.assert_no_dependency_claim, {pair})
        self.refusal("authority-field", dc.assert_no_dependency_claim,
                     {"seen": frozenset({pair})})

    def test_a_dependency_word_in_a_value_position_is_still_allowed_after_hardening(self):
        """The deliberate allowance, re-pinned because a fix aimed at "refuse more" is exactly
        what would quietly take it away: the fence sweeps KEYS. `relation` carries the
        extractor's own word, quoted under `EDGE_LABEL_NOTE` and never adopted, and refusing a
        VALUE would let a third-party extractor's vocabulary break a manifest.

        A set of pairs is the same allowance seen from the other side and is listed here rather
        than among the refusals above on purpose: a set cannot contain a mapping (no mapping is
        hashable), so `depends_on` inside one is a string VALUE and never a key."""
        dc.assert_no_dependency_claim({"relation": "depends_on", "edge_label": "depends_on"})
        dc.assert_no_dependency_claim({"evidence": [{"edge_label": "safe_to_parallel"}]})
        dc.assert_no_dependency_claim({("depends_on", "app/utils.py")})

    def test_the_hardened_sweep_still_accepts_everything_a_manifest_is_made_of(self):
        """The anti-vacuity control for the whole group: a refusal broad enough to pass those
        tests and fail every real caller would be no fix at all. The second shape is D17's plan
        as `bin/decision_policy.py` builds it -- frozen mappings, tuples and scalars."""
        dc.assert_no_dependency_claim({"v": dc.CONTEXT_VERSION, "candidates": [],
                                       "limits": list(dc.LIMITS), "authority": None,
                                       "withheld_total": 0, "bounds": {"depth": 1},
                                       "over_budget": False, "score": 0.5})
        dc.assert_no_dependency_claim({
            "failure": {"verify_rc": 1, "artifact": None},
            "retry": types.MappingProxyType({"model": "a-model", "assurance": ("reviewed",),
                                             "context_paths": ("app/utils.py",),
                                             "failed_attempt": types.MappingProxyType({})}),
            "ladder": ("a", "b"),
        }, "a context repair plan")

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


# ==============================================================================================
#  D17 -- ONE BOUNDED CONTEXT REPAIR, OFF UNTIL AN APPROVED BUNDLE SAYS OTHERWISE
# ==============================================================================================
# WHAT IS UNDER TEST. `bin/decision_policy.py`'s third half: `plan_context_repair`, which says
# whether ONE extra same-model retry carrying a bounded context package is admissible after a
# failure the attempt ledger already classified. D11 owns bundle resolution in that file and
# D13 owns selection; neither is touched here and both their test classes are elsewhere.
#
# WHAT THE ACCEPTANCE TERMS MEAN HERE, and how each is made structural rather than asserted:
#
#   * NO DEFAULT -- there is no argument that switches a repair on. The only thing that can is
#     a resolved `BundleResolution` carrying the contract's own allowlisted parameter as
#     literally `True`, and every cheaper way in is tested as a refusal: no bundle, a legacy
#     resolution, a bundle without the parameter, with it false, with it merely truthy, and a
#     bundle that never resolved because nobody approved it. A signature test additionally pins
#     that NO parameter of the function has a default value at all, so nothing is permissive by
#     omission either.
#   * NO LIVE TRIAL -- the module is pure and this class proves it the way the file's other two
#     classes do: an AST sweep over the module's own calls, plus the fact that every fixture
#     here is a dict built in this file. Nothing dispatches, retries, writes or activates, and
#     a sweep asserts nothing in `bin/` calls the planner at all.
#   * THE TRIGGER IS READ, NEVER GUESSED -- the failure class comes off the attempt projection
#     and every one of the ledger's other classes is tested as a refusal, in a loop over the
#     ledger's own `CLASSES` so a class added there cannot go unclassified here.
#   * CURRENT CAP ENFORCED -- the ceilings are `kit_contract`'s, the operation kind is its
#     `retry`, and a repair refuses both when a drawn ceiling is reached and when the run
#     declares no such ceiling at all.
#
# SAFETY CONTRACT. Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify`
# binary, reads a real home, opens a store, starts a process or touches the network. Model ids
# are synthetic and appear in no `data/pricing*.json`. One test builds a REAL manifest through
# the `_Tree` fixture above, which is a temp dir with a canned git probe.

dp = _load("decision_policy")
dpc = dp._contract()          # the SAME contract instance the module under test uses
al = dp._al()
kc = dp._kc()
ah = dp._ah()

#: The revision the failed attempt ran at, and the one the retry would run at.
HEAD = "aaaaaaaaaaaa1111"
MOVED_HEAD = "bbbbbbbbbbbb2222"

#: Synthetic and deliberately different from each other, so a plan that substituted the observed
#: model for the dispatched one would be visible rather than indistinguishable.
DISPATCHED = "fake-model-a"
OBSERVED = "fake-model-b"

PROJECT = "polytropos"
TASK_CLASS = "recovery-cross-module"
USE = "recovery-selection"
MANIFEST_V = "polytropos.synthetic-manifest/1"
APPROVAL_V = "polytropos.synthetic-approval/1"

FULL_ASSURANCE = ("deterministic-check", "independent-verification", "independent-review")


def _digest(seed):
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _ref(identity, version, sha=None):
    return al.make_ref(identity, sha=_digest(identity) if sha is None else sha, version=version)


def attempt_record(**over):
    """The failed attempt as `bin/attempt_history.py` projects it.

    Every field the planner reads carries a DISTINCTIVE value rather than a None, because a
    fixture whose fields are already absent makes a guard that refuses an absent field
    unfalsifiable -- the failure mode that left seven survivors in the task before this one.
    """
    record = ah.blank()
    record.update({
        "kit": "decision-improvement-v1", "run": "2026-09-17-d17a", "task": "D17",
        "attempt": "att-1", "source": "ledger", "harness": "fake-harness", "op": "initial",
        "role": "implementer", "ts": "2026-09-17T12:00:00Z", "result": "verify-failed",
        "failure_class": "verification", "verify_rc": 1,
        "verify_signature": "sig-abc", "verify_failures": 3, "artifact": "run.log",
        "requested_model": DISPATCHED, "dispatched_model": DISPATCHED,
        "observed_model": OBSERVED,
        "acceptance_ref": _ref("acc-D17", kc.CONTRACT_VERSION),
        "admission_ref": _ref("grant-initial-1", kc.CONTRACT_VERSION),
    })
    record.update(over)
    return record


def manifest_payload(**over):
    """A D16 manifest, carrying exactly the fields a repair plan reads.

    The digest is taken by `decision_context.canonical_bytes` -- the seam's own function -- so
    a synthetic manifest is referenceable on the same terms a real one is. One test below runs
    the planner against a REAL manifest built from the `_Tree` fixture, which is what keeps this
    shortcut honest.
    """
    payload = {
        "v": dc.CONTEXT_VERSION,
        "status": "candidates",
        "abstention": [],
        "candidates": [{"path": "app/caller.py"}, {"path": "app/utils.py"},
                       {"path": "spec/test_main.py"}],
        "freshness": {"revision": {"stamped": HEAD, "now": HEAD, "moved": False}},
    }
    payload.update(over)
    payload["sha256"] = hashlib.sha256(dc.canonical_bytes(payload)).hexdigest()
    return payload


def bundle_payload(**over):
    """A bundle whose data parameters put a context repair in force."""
    payload = {
        "v": dpc.BUNDLE_VERSION,
        "id": "bundle-context-repair-1",
        "parent": _ref("bundle-legacy-0", dpc.BUNDLE_VERSION),
        "scope": {"project": PROJECT, "task_classes": [TASK_CLASS], "intended_uses": [USE]},
        "components": {"decision_contract": dpc.CONTRACT_VERSION,
                       "task_contract": kc.CONTRACT_VERSION, "provider_contract": None},
        "parameters": {dp.REPAIR_PARAMETER: True, dp.REPAIR_FILES_PARAMETER: 4},
        "requirements": {"capabilities": [], "providers": [], "calibration": None},
        "fallback": {"kind": "legacy", "bundle_ref": None},
        "provenance": {"approval_ref": _ref("approval-1", APPROVAL_V),
                       "evaluation_ref": _ref("manifest-1", MANIFEST_V),
                       "rolled_back_from": None},
    }
    payload.update(over)
    return payload


class ContextRepairPolicyTests(unittest.TestCase):

    # ---- fixtures ----------------------------------------------------------------------------

    def setUp(self):
        self.grant = _ref("grant-repair-1", kc.CONTRACT_VERSION)

    def resolution(self, **over):
        """A resolution with a real, fully met bundle in force."""
        payload = bundle_payload(**over)
        facts = dp.runtime_facts(
            project=PROJECT, task_class=TASK_CLASS, intended_use=USE,
            components={"decision_contract": dpc.CONTRACT_VERSION,
                        "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})
        return dp.resolve_bundle(dp.bundle_ref(payload), [payload], facts)

    def in_force(self, **over):
        resolution = self.resolution(**over)
        self.assertEqual(resolution.source, "pinned",
                         "the positive fixture needs a bundle that actually resolved")
        return resolution

    def plan(self, **over):
        kwargs = {
            "attempt": attempt_record(), "manifest": manifest_payload(),
            "bundle": self.in_force(), "checkpoint": HEAD, "assurance": FULL_ASSURANCE,
            "admission_ref": self.grant,
            "plan_budget": {"max-dispatches": 5, "max-model-calls": 9},
            "used": {"max-dispatches": 2, "max-model-calls": 3},
            "ladder": [OBSERVED, "fake-model-c"], "repairs": [],
        }
        kwargs.update(over)
        return dp.plan_context_repair(
            kwargs.pop("attempt"), kwargs.pop("manifest"), kwargs.pop("bundle"), **kwargs)

    def refused(self, code, **over):
        """A plan that refuses for `code`, asserted to be admissible without the change.

        The control matters: without it every one of these would also pass against a planner
        that refused everything, which is the always-legacy hole D11 had to prove its way out
        of. `self.plan()` with no override is admissible, and every case below changes exactly
        one thing about it.
        """
        plan = self.plan(**over)
        self.assertFalse(plan.admissible, f"expected a refusal for {code}")
        self.assertIn(code, plan.reasons, f"reasons were {list(plan.reasons)}")
        self.assertIsNone(plan.retry)
        self.assertIsNone(plan.repair_id)
        self.assertIsNone(plan.operation)
        self.assertTrue(plan.refusal)
        return plan

    def refusal(self, code, callable_, *args, **kwargs):
        with self.assertRaises(Exception) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(getattr(caught.exception, "code", None), code, str(caught.exception))
        return caught.exception

    # ---- A. the vocabularies, and what they may not collide with -----------------------------

    def test_the_repair_vocabulary_is_a_third_one_and_collides_with_neither_other(self):
        """Resolution answers which parameters are in force, selection answers which action is
        taken, and this answers whether one extra bounded operation is admissible. A code
        meaning two of the three would make all three reports' tallies meaningless."""
        self.assertTrue(dp.REPAIR_REASONS and dp.SELECTION_REASONS and dp.RESOLUTION_REASONS)
        self.assertEqual(sorted(set(dp.REPAIR_REASONS) & set(dp.SELECTION_REASONS)), [])
        self.assertEqual(sorted(set(dp.REPAIR_REASONS) & set(dp.RESOLUTION_REASONS)), [])
        self.assertEqual(list(dp.REPAIR_REASONS), sorted(set(dp.REPAIR_REASONS)))
        self.assertIn(dp.REPAIR_ADMISSIBLE, dp.REPAIR_REASONS)

    def test_every_refusal_carries_the_sentence_its_refusal_is_printed_from(self):
        """A code with no sentence raises from inside the refusal path, which is the one place
        a raise helps least."""
        refusals = sorted(set(dp.REPAIR_REASONS) - {dp.REPAIR_ADMISSIBLE})
        self.assertTrue(refusals)
        self.assertEqual(sorted(dp._REPAIR_TEXT), refusals)
        for text in dp._REPAIR_TEXT.values():
            self.assertTrue(text and isinstance(text, str))

    def test_no_name_this_repair_defines_is_one_the_contract_bans(self):
        """A check OUTCOME must not be spelled like the grant either -- the rule that made D13's
        fourth coordinator check `budget_admission` rather than `budget`."""
        defined = set(dp.REPAIR_REASONS) | set(dp.REPAIRABLE_FAILURE_CLASSES)
        defined |= {f.name for f in dataclasses.fields(dp.ContextRepair)}
        defined |= set(inspect.signature(dp.plan_context_repair).parameters)
        defined |= set(dict(self.plan().retry))
        self.assertTrue(defined, "the name sets are what this test sweeps")
        self.assertTrue(dpc.BANNED_FIELDS, "an empty ban has nothing for this sweep to collide")
        self.assertEqual(sorted(name for name in defined if dpc._is_banned_key(name)), [])
        # And the ban still matches its own plain spellings, so this is not passing because the
        # comparison quietly stopped banning anything.
        self.assertTrue(dpc._is_banned_key("budget"))
        self.assertTrue(dpc._is_banned_key("approve"))

    def test_the_two_dials_are_the_contracts_own_allowlisted_parameters(self):
        """Not a dial this module invented: a parameter outside `DIFF_PARAMETERS` is refused on
        a bundle and in a proposal's diff alike, so a repair cannot be switched on by a key the
        contract would not have let through in the first place."""
        self.assertEqual(dpc.DIFF_PARAMETERS.get(dp.REPAIR_PARAMETER), "boolean")
        self.assertEqual(dpc.DIFF_PARAMETERS.get(dp.REPAIR_FILES_PARAMETER), "count")
        self.refusal("unknown-field", dpc.parse_bundle,
                     bundle_payload(parameters={"recovery.context_repair": True}))

    def test_a_repair_is_the_task_contracts_own_retry_and_draws_the_historic_dispatch_cap(self):
        """`max-dispatches` keeps exactly the meaning every recorded ledger already gave it: a
        repair spends inside the existing ceilings rather than defining a fifth kind beside
        them."""
        self.assertIn(dp.REPAIR_OPERATION, kc.OPERATION_CAPS)
        self.assertIn("max-dispatches", kc.OPERATION_CAPS[dp.REPAIR_OPERATION])
        self.assertEqual(self.plan().operation, dp.REPAIR_OPERATION)
        self.assertEqual(self.plan().retry["operation"], dp.REPAIR_OPERATION)

    def test_an_assurance_kind_a_new_role_brings_is_accepted_without_editing_this_module(self):
        """Derived by union from the task contract's own tables, like `denial_reasons()` is
        derived by subtraction from the router's. The safe direction is the automatic one."""
        self.assertNotIn("invented-assurance", dp.assurance_kinds())
        extended = dict(kc.ROLE_CONTRACTS)
        extended["invented-role"] = dict(kc.ROLE_CONTRACTS["verifier"],
                                         assurance="invented-assurance")
        with mock.patch.object(kc, "ROLE_CONTRACTS", extended):
            self.assertIn("invented-assurance", dp.assurance_kinds())
        for kind in kc.WORKFLOW_ASSURANCE["reviewed"]:
            self.assertIn(kind, dp.assurance_kinds())

    def test_every_declared_repair_reason_is_produced_and_none_is_invented(self):
        """Both directions, as D11 and D13 already pin their own vocabularies: a code nothing
        produces is a branch somebody removed, and a code nothing declared is one nobody can
        count."""
        tree = ast.parse((BIN_DIR / "decision_policy.py").read_text(encoding="utf-8"))
        produced, constants = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                constants.add(node.value)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append" and node.args
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "unmet"
                    and isinstance(node.args[0], ast.Constant)):
                produced.add(node.args[0].value)
        self.assertTrue(produced, "the walk found no repair reasons at all")
        self.assertEqual(sorted(produced),
                         sorted(set(dp.REPAIR_REASONS) - {dp.REPAIR_ADMISSIBLE}))
        self.assertEqual(sorted(set(dp.REPAIR_REASONS) - constants), [])

    # ---- B. off by default, and the only way out of it ---------------------------------------

    def test_no_parameter_of_the_plan_has_a_default_so_nothing_is_permissive_by_omission(self):
        """A flag defaulting to False is one copied call site away from on. There is no flag,
        and there is no default of any kind: a caller states every fact or the call fails."""
        signature = inspect.signature(dp.plan_context_repair)
        self.assertTrue(signature.parameters, "the walk found no parameters at all")
        for name, parameter in signature.parameters.items():
            with self.subTest(parameter=name):
                self.assertIs(parameter.default, inspect.Parameter.empty)
                self.assertIsNot(parameter.default, True)
        # And no parameter is spelled like a switch somebody could look for and flip.
        for switch in ("enabled", "enable", "allow", "force", "repair", "active", "on"):
            with self.subTest(switch=switch):
                self.assertNotIn(switch, signature.parameters)

    def test_with_no_bundle_there_is_no_repair_and_that_is_the_default_everywhere(self):
        plan = self.refused("repair-not-in-force", bundle=None)
        self.assertIsNone(plan.bundle_sha)
        self.assertIn("no resolved policy bundle", plan.refusal)

    def test_a_legacy_resolution_reads_exactly_like_no_bundle_at_all(self):
        """Take the bundle away and the behaviour is the behaviour that was there before any of
        this existed -- which for a repair means there is none."""
        facts = dp.runtime_facts(
            project=PROJECT, task_class=TASK_CLASS, intended_use=USE,
            components={"decision_contract": dpc.CONTRACT_VERSION,
                        "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})
        legacy = dp.resolve_bundle(None, [], facts)
        self.assertEqual(legacy.source, "legacy")
        plan = self.refused("repair-not-in-force", bundle=legacy)
        self.assertIsNone(plan.bundle_sha)

    def test_a_bundle_that_does_not_ask_for_a_repair_leaves_it_off(self):
        for parameters in ({dp.REPAIR_FILES_PARAMETER: 4},
                           {dp.REPAIR_PARAMETER: False, dp.REPAIR_FILES_PARAMETER: 4}):
            with self.subTest(parameters=sorted(parameters)):
                plan = self.refused("repair-not-in-force",
                                    bundle=self.in_force(parameters=parameters))
                # The bundle DID resolve -- its digest is on the plan -- so this is the
                # parameter refusing and not the resolution having fallen through to legacy.
                self.assertIsNotNone(plan.bundle_sha)

    def test_only_the_literal_true_switches_a_repair_on_and_a_truthy_value_does_not(self):
        """A repair that any truthy value could switch on is a repair switched on by accident.
        The contract already refuses a non-boolean here, so this is proven against a resolution
        hand-built to get past it -- the one way the value could ever arrive."""
        self.refusal("wrong-type", dpc.parse_bundle,
                     bundle_payload(parameters={dp.REPAIR_PARAMETER: 1,
                                                dp.REPAIR_FILES_PARAMETER: 4}))
        for value in (1, "yes", [1], 1.0):
            with self.subTest(value=value):
                faked = types.SimpleNamespace(
                    source="pinned",
                    bundle=types.SimpleNamespace(sha=lambda: "c" * 64),
                    parameters={dp.REPAIR_PARAMETER: value, dp.REPAIR_FILES_PARAMETER: 4})
                self.refused("repair-not-in-force", bundle=faked)
        # The control: the same hand-built resolution with the literal `True` IS in force, so
        # the loop above is the value being rejected rather than the fake being rejected.
        faked = types.SimpleNamespace(
            source="pinned", bundle=types.SimpleNamespace(sha=lambda: "c" * 64),
            parameters={dp.REPAIR_PARAMETER: True, dp.REPAIR_FILES_PARAMETER: 4})
        self.assertTrue(self.plan(bundle=faked).admissible)

    def test_a_bundle_nobody_approved_never_resolves_and_so_never_puts_a_repair_in_force(self):
        """Approval is upstream of this module and stays there: `resolve_bundle` refuses an
        unapproved bundle to legacy, and legacy cannot put a repair in force. Nothing here
        re-checks approval, which is what keeps the rule in one place."""
        unapproved = bundle_payload(
            provenance={"approval_ref": None, "evaluation_ref": _ref("manifest-1", MANIFEST_V),
                        "rolled_back_from": None})
        facts = dp.runtime_facts(
            project=PROJECT, task_class=TASK_CLASS, intended_use=USE,
            components={"decision_contract": dpc.CONTRACT_VERSION,
                        "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})
        resolution = dp.resolve_bundle(dp.bundle_ref(unapproved), [unapproved], facts)
        self.assertEqual(resolution.source, "legacy")
        self.assertIn("approval-absent", resolution.reasons)
        self.refused("repair-not-in-force", bundle=resolution)

    def test_a_bundle_out_of_scope_for_this_run_cannot_put_a_repair_in_force_either(self):
        facts = dp.runtime_facts(
            project=PROJECT, task_class="some-other-class", intended_use=USE,
            components={"decision_contract": dpc.CONTRACT_VERSION,
                        "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})
        payload = bundle_payload()
        resolution = dp.resolve_bundle(dp.bundle_ref(payload), [payload], facts)
        self.assertEqual(resolution.source, "legacy")
        self.assertIn("out-of-scope", resolution.reasons)
        self.refused("repair-not-in-force", bundle=resolution)

    # ---- C. the trigger, read from the trusted event and never guessed -----------------------

    def test_only_a_verification_failure_triggers_a_repair_and_every_other_class_refuses(self):
        """Looped over the LEDGER'S own class tuple, so a class added there cannot go
        unclassified here. Infrastructure, auth, config and permission are facts about the
        host; `model` is the model's own failure, whose remedy is the ladder's; `unknown` is a
        non-zero exit nobody attributed, and an unattributed failure is not a free retry."""
        self.assertTrue(al.CLASSES, "an empty class tuple would make this loop vacuous")
        self.assertEqual(tuple(dp.REPAIRABLE_FAILURE_CLASSES), ("verification",))
        for failure_class in al.CLASSES:
            with self.subTest(failure_class=failure_class):
                plan = self.plan(attempt=attempt_record(failure_class=failure_class))
                if failure_class in dp.REPAIRABLE_FAILURE_CLASSES:
                    self.assertTrue(plan.admissible)
                else:
                    self.assertFalse(plan.admissible)
                    self.assertIn("failure-class-excluded", plan.reasons)
        # The environment classes the plan names explicitly are the ones the shared PLAN says
        # must never trigger an escalation from a semantic guess.
        for deterministic in ("infrastructure", "auth", "config", "permission"):
            with self.subTest(deterministic=deterministic):
                self.assertIn(deterministic, al.CLASSES)
                self.assertNotIn(deterministic, dp.REPAIRABLE_FAILURE_CLASSES)

    def test_a_failure_nobody_classified_is_not_a_classified_one(self):
        """Its own code, not folded into the excluded one: "nobody looked" and "somebody looked
        and it was the host's" are different facts with different remedies."""
        plan = self.refused("failure-class-unestablished",
                            attempt=attempt_record(failure_class=None))
        self.assertNotIn("failure-class-excluded", plan.reasons)
        self.assertIsNone(plan.failure["failure_class_basis"])

    def test_the_deterministic_checks_own_exit_status_has_to_agree_with_the_class(self):
        """A record claiming a verification failure whose check exited 0 contradicts itself, and
        one that recorded no exit status never observed the failure at all. A boolean is not an
        exit status however willingly Python treats it as an integer."""
        for verify_rc in (0, None, True, "1"):
            with self.subTest(verify_rc=verify_rc):
                self.refused("failure-not-observed", attempt=attempt_record(verify_rc=verify_rc))
        self.assertTrue(self.plan(attempt=attempt_record(verify_rc=2)).admissible)

    def test_nothing_here_reads_output_text_to_decide_why_something_failed(self):
        """The class is the ledger's determination. This module never classifies, and the plan
        says where its own basis came from rather than asking a reader to take its word.

        Structural rather than textual, because the module NAMES the classifier in its own
        header to say where the class comes from -- the same shape as the graphify fence one
        module over, where the word appearing in prose is the fence and the word appearing in
        an argv position would be the breach."""
        text = (BIN_DIR / "decision_policy.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls, attributes = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    calls.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    calls.add(fn.id)
            if isinstance(node, ast.Attribute):
                attributes.add(node.attr)
        self.assertTrue(calls and attributes, "the walk found nothing, so the sweep is vacuous")
        self.assertIn("read_ref", calls, "the walk reaches the ledger access that matters")
        for classifier in ("classify_dispatch", "recovery_for", "normalize_output",
                           "failure_count", "observation", "retry_context"):
            with self.subTest(name=classifier):
                self.assertNotIn(classifier, calls)
                self.assertNotIn(classifier, attributes)
        self.assertIn("classify_dispatch", text,
                      "the module names where the class comes from rather than leaving it "
                      "implied; this is the fence written down")
        self.assertEqual(self.plan().failure["failure_class_basis"], "trusted-event")
        self.assertEqual(self.plan().failure["failure_class"], "verification")

    # ---- D. the five negative paths this task is required to hold ----------------------------

    def test_a_task_that_already_had_its_repair_does_not_get_a_second_one(self):
        """At most one approved context repair; the rest of the recovery path is the ladder's.
        Fed its OWN emitted identity, which is the shape a coordinator that recorded the first
        one would hand back."""
        first = self.plan()
        self.assertTrue(first.admissible)
        self.refused("repair-already-taken", repairs=[first.repair_id])
        # And a DIFFERENT repair counts too: "at most one" is about the task, not about this
        # particular package, so a second repair under a fresh identity is still a second one.
        self.refused("repair-already-taken", repairs=[_digest("some-other-repair")])
        # A placeholder is not a repair identity. The duplicate check cannot be satisfied with
        # a word, which is what stops it being satisfied by mistake.
        self.refusal("value-invalid", self.plan, repairs=["already-did-one"])

    def test_no_applicable_context_is_a_legitimate_abstention_and_not_a_repair(self):
        """The manifest's own answer, carried onto the plan with its reasons rather than
        flattened into "there was nothing"."""
        abstained = manifest_payload(status="no-relevant-context", candidates=[],
                                     abstention=["all-candidates-withheld", "no-evidence-found"])
        plan = self.refused("context-absent", manifest=abstained)
        self.assertEqual(plan.context["status"], "no-relevant-context")
        self.assertEqual(plan.context["abstention"],
                         ("all-candidates-withheld", "no-evidence-found"))
        self.assertEqual(plan.context["candidates"], 0)
        for reason in plan.context["abstention"]:
            with self.subTest(reason=reason):
                self.assertIn(reason, dc.ABSTENTION_REASONS)
        # A manifest claiming candidates while listing none is the same abstention, reached the
        # other way round, and is not a package either.
        self.refused("context-absent", manifest=manifest_payload(candidates=[]))

    def test_a_package_assembled_over_another_revision_is_not_this_checkpoints_context(self):
        """"Restore equivalent failing checkpoints" -- a package read from a tree that has since
        moved is not the context the failed attempt was missing."""
        plan = self.refused("checkpoint-moved", checkpoint=MOVED_HEAD)
        self.assertNotIn("checkpoint-unidentified", plan.reasons)
        self.refused("checkpoint-moved", manifest=manifest_payload(
            freshness={"revision": {"stamped": HEAD, "now": MOVED_HEAD, "moved": True}}))

    def test_a_checkpoint_nobody_could_establish_is_not_a_matching_one(self):
        """Its own code: git unavailable is a legitimate runtime state, and reporting it as
        "the revision moved" would be a diagnosis nobody made."""
        for case in ({"checkpoint": None},
                     {"manifest": manifest_payload(
                         freshness={"revision": {"stamped": None, "now": None,
                                                 "moved": False}})},
                     {"manifest": manifest_payload(freshness={})}):
            with self.subTest(case=sorted(case)):
                plan = self.refused("checkpoint-unidentified", **case)
                self.assertNotIn("checkpoint-moved", plan.reasons)

    def test_a_ceiling_already_reached_refuses_before_the_repair_spends(self):
        """The ceilings are `kit_contract`'s and so is the question: `blocking_cap` for the
        operation kind a repair IS. Each cap the operation draws down is tested on its own, so
        one reaching cannot be masked by the other."""
        for cap in kc.OPERATION_CAPS[dp.REPAIR_OPERATION]:
            with self.subTest(cap=cap):
                declared = {"max-dispatches": 5, "max-model-calls": 9}
                spent = {"max-dispatches": 2, "max-model-calls": 3}
                spent[cap] = declared[cap]
                self.refused("dispatch-cap-reached", plan_budget=declared, used=spent)
        # One below the ceiling is still inside it -- the control that keeps the check from
        # passing because it refuses everything.
        self.assertTrue(self.plan(plan_budget={"max-dispatches": 3, "max-model-calls": 9},
                                  used={"max-dispatches": 2, "max-model-calls": 3}).admissible)

    def test_an_extra_attempt_nobody_is_counting_is_the_unbounded_retry_this_refuses_to_be(self):
        """A run that declares no ceiling for a ceiling the operation draws down has not bounded
        the repair at all, and an empty budget is the most common way to have declared none."""
        for declared in ({}, {"max-dispatches": 5}, {"max-model-calls": 9}):
            with self.subTest(declared=sorted(declared)):
                plan = self.refused("dispatch-cap-undeclared", plan_budget=declared)
                # Not the reached code: a ceiling nobody declared has not been reached.
                self.assertNotIn("dispatch-cap-reached", plan.reasons)

    # ---- E. what the retry preserves ---------------------------------------------------------

    def test_the_retry_preserves_the_model_the_assurance_and_the_acceptance_exactly(self):
        """One bounded package before a SAME-MODEL retry: changing model and context at once is
        the one thing the experiment's design forbids, and dropping an independent check would
        make the retry a different operation from the one that failed."""
        plan = self.plan()
        self.assertTrue(plan.admissible)
        self.assertEqual(plan.retry["model"], DISPATCHED)
        self.assertEqual(plan.retry["assurance"], FULL_ASSURANCE)
        self.assertEqual(plan.retry["acceptance_ref"], _ref("acc-D17", kc.CONTRACT_VERSION))
        self.assertEqual(plan.retry["checkpoint"], HEAD)
        for mandatory in ("independent-verification", "independent-review"):
            with self.subTest(assurance=mandatory):
                self.assertIn(mandatory, plan.retry["assurance"])

    def test_the_observed_model_rides_beside_the_dispatched_one_and_never_stands_in_for_it(self):
        """What a harness reported running is not always what was asked for, and a repair
        preserves what was ASKED for. Unknown stays unknown rather than being filled in from
        the other slot."""
        plan = self.plan()
        self.assertNotEqual(DISPATCHED, OBSERVED)
        self.assertEqual(plan.failure["observed_model"], OBSERVED)
        self.assertEqual(plan.retry["model"], DISPATCHED)
        # The reverse: an attempt with only an observation recorded cannot be re-dispatched to
        # one, and nothing substitutes it.
        self.refused("model-unidentified", attempt=attempt_record(dispatched_model=None))
        plan = self.plan(attempt=attempt_record(observed_model=None))
        self.assertIsNone(plan.failure["observed_model"])
        self.assertEqual(plan.retry["model"], DISPATCHED)

    def test_what_a_repair_cannot_name_it_cannot_preserve(self):
        for code, over in (("model-unidentified", {"dispatched_model": None}),
                           ("model-unidentified", {"dispatched_model": "   "}),
                           ("acceptance-unidentified", {"acceptance_ref": None}),
                           ("acceptance-unidentified", {"acceptance_ref": "acc-D17"})):
            with self.subTest(code=code, over=sorted(over)):
                self.refused(code, attempt=attempt_record(**over))
        self.refused("assurance-undeclared", assurance=[])

    def test_the_original_failed_evidence_rides_in_the_retry_input(self):
        """A retry that cannot see the failure it is repairing is a fresh attempt. Every field
        asserted is checked against the record it came from rather than against a literal, so
        this cannot pass on a fixture whose values were already what was expected."""
        record = attempt_record()
        plan = self.plan(attempt=record)
        carried = plan.retry["failed_attempt"]
        for field in ("kit", "run", "task", "attempt", "ts", "result", "failure_class",
                      "verify_rc", "verify_signature", "verify_failures", "artifact",
                      "dispatched_model", "observed_model"):
            with self.subTest(field=field):
                self.assertIsNotNone(record[field], "the fixture must carry it to prove it")
                self.assertEqual(carried[field], record[field])
        self.assertEqual(carried["acceptance_ref"], record["acceptance_ref"])
        self.assertEqual(carried["admission_ref"], record["admission_ref"])
        self.assertEqual(plan.retry["context_ref"], dc.context_ref(manifest_payload()))
        self.assertEqual(plan.retry["context_paths"],
                         ("app/caller.py", "app/utils.py", "spec/test_main.py"))

    def test_the_failed_evidence_is_kept_on_a_refusing_plan_too(self):
        """A refusal that dropped the evidence would make the most audit-relevant outcome the
        least legible one."""
        plan = self.refused("checkpoint-moved", checkpoint=MOVED_HEAD)
        self.assertEqual(plan.failure["task"], "D17")
        self.assertEqual(plan.failure["verify_signature"], "sig-abc")
        self.assertEqual(plan.context["candidates"], 3)

    def test_the_remaining_ladder_is_carried_verbatim_and_never_climbed_or_consumed(self):
        """A repair is one retry on the same model; what happens after it is what the driver's
        own ladder already said. Order included -- a plan that sorted it would be proposing a
        different recovery path."""
        rungs = ["fake-model-z", "fake-model-c", "fake-model-b"]
        plan = self.plan(ladder=list(rungs))
        self.assertEqual(plan.ladder, tuple(rungs))
        self.assertEqual(plan.retry["ladder"], tuple(rungs))
        self.assertNotEqual(tuple(rungs), tuple(sorted(rungs)),
                            "a ladder already in sorted order could not show a sort")
        self.assertNotIn(plan.retry["model"], plan.ladder,
                         "the repair rung is not one the ladder was going to climb")
        # Carried on a refusal too, so the plan always says where the run goes next.
        self.assertEqual(self.refused("checkpoint-moved", checkpoint=MOVED_HEAD,
                                      ladder=list(rungs)).ladder, tuple(rungs))
        # An empty ladder is a legitimate state -- Cursor has no ladder at all -- and is not
        # itself a refusal.
        self.assertTrue(self.plan(ladder=[]).admissible)

    # ---- F. a separately identified operation, inside the bounds ------------------------------

    def test_a_repair_needs_its_own_grant_and_not_the_one_the_failed_attempt_already_spent(self):
        """The grant that funded the attempt is spent; a repair is a second operation and needs
        a second admission. The same refusal `select_action` makes about acting on the grant
        that admitted asking."""
        spent = _ref("grant-initial-1", kc.CONTRACT_VERSION)
        self.refused("admission-not-separate", admission_ref=spent)
        # A different digest under the same id is still the same grant: identity is the id.
        self.refused("admission-not-separate",
                     admission_ref=al.make_ref("grant-initial-1", sha="d" * 64,
                                               version=kc.CONTRACT_VERSION))

    def test_an_attempt_that_recorded_no_grant_cannot_show_the_repair_is_separate(self):
        """An attempt written before provenance references existed carries none, and an
        unestablished fact is not an established one. Conservative on purpose."""
        for value in (None, "grant-initial-1", {"sha": "d" * 64}):
            with self.subTest(value=value):
                plan = self.refused("admission-not-separate",
                                    attempt=attempt_record(admission_ref=value))
                self.assertIsNone(plan.failure["admission_ref"])

    def test_a_null_grant_is_refused_because_there_is_no_null_that_means_repairing_anyway(self):
        for value in (None, "grant-repair-1", {"id": ""}, 7):
            with self.subTest(value=value):
                self.refusal("not-a-reference", self.plan, admission_ref=value)

    def test_the_package_is_bounded_by_the_bundles_own_count(self):
        """"Bounded" that the retriever decides for itself is not bounded by the approved
        bundle. The dial is a `count` data parameter and a package larger than it refuses."""
        self.refused("context-over-bound",
                     bundle=self.in_force(parameters={dp.REPAIR_PARAMETER: True,
                                                      dp.REPAIR_FILES_PARAMETER: 2}))
        self.assertTrue(self.plan(bundle=self.in_force(
            parameters={dp.REPAIR_PARAMETER: True, dp.REPAIR_FILES_PARAMETER: 3})).admissible)
        self.assertEqual(self.plan().context["bound"], 4)

    def test_a_bundle_that_bounds_nothing_has_not_bounded_the_package(self):
        """On its own code rather than the over-bound one: an absent ceiling is not a ceiling
        that was exceeded, and telling them apart is what lets an operator fix the right thing."""
        plan = self.refused("context-bound-undeclared",
                            bundle=self.in_force(parameters={dp.REPAIR_PARAMETER: True}))
        self.assertNotIn("context-over-bound", plan.reasons)
        self.assertIsNone(plan.context["bound"])

    def test_the_repair_identity_is_content_addressed_and_changes_with_what_it_names(self):
        """"Separately identified" means the identity distinguishes this repair from another
        one. A digest identifies content; it protects against nothing, and nothing here treats
        it as though it did."""
        base = self.plan().repair_id
        self.assertEqual(len(base), 64)
        self.assertEqual(base, self.plan().repair_id, "the same repair has the same identity")
        variants = {
            "grant": {"admission_ref": _ref("grant-repair-2", kc.CONTRACT_VERSION)},
            "attempt": {"attempt": attempt_record(attempt="att-2")},
            "package": {"manifest": manifest_payload(
                candidates=[{"path": "app/caller.py"}, {"path": "app/utils.py"}])},
            "bundle": {"bundle": self.in_force(
                parameters={dp.REPAIR_PARAMETER: True, dp.REPAIR_FILES_PARAMETER: 3})},
        }
        for name, over in variants.items():
            with self.subTest(names=name):
                self.assertNotEqual(self.plan(**over).repair_id, base)

    # ---- G. caller defects refuse rather than degrade to a safe-looking answer ----------------

    def test_a_record_that_is_not_the_projection_is_refused_rather_than_read(self):
        """A shape assembled beside `attempt_history`'s projection is not the projection, and
        reading one would be exactly the "determined by a semantic guess" this forbids."""
        self.refusal("wrong-type", self.plan, attempt=["verify-failed"])
        self.refusal("wrong-type", self.plan, attempt="verify-failed")
        self.refusal("unknown-field", self.plan,
                     attempt=dict(attempt_record(), why="it looked wrong"))
        for missing in ("task", "failure_class", "verify_rc"):
            with self.subTest(missing=missing):
                record = attempt_record()
                record.pop(missing)
                self.refusal("missing-field", self.plan, attempt=record)
        self.assertTrue(set(ah.RECORD_FIELDS) >= set(attempt_record()),
                        "the fixture itself must be a record this projection could hold")

    def test_a_manifest_of_another_shape_or_status_is_refused(self):
        self.refusal("wrong-type", self.plan, manifest=[manifest_payload()])
        self.refusal("unknown-value", self.plan,
                     manifest=manifest_payload(v="polytropos.context-candidates/99"))
        self.refusal("unknown-value", self.plan, manifest=manifest_payload(status="fine"))
        self.refusal("wrong-type", self.plan, manifest=manifest_payload(candidates={}))

    def test_a_resolution_that_is_not_one_is_refused_rather_than_read_as_off(self):
        """Silently reading a malformed resolution as "no repair" would be the safe-looking
        answer that hides a caller's bug, which this module refuses to give anywhere else
        either."""
        self.refusal("wrong-type", self.plan, bundle=bundle_payload())
        self.refusal("wrong-type", self.plan,
                     bundle=types.SimpleNamespace(source="active"))
        self.refusal("wrong-type", self.plan, bundle=types.SimpleNamespace(
            source="pinned", bundle=types.SimpleNamespace(sha=lambda: "c" * 64)))

    def test_the_named_arguments_are_validated_before_they_are_copied(self):
        """The coercion defect this file has now produced twice, once in each of its other two
        halves: `list("fake-model-a")` is twelve letters and `dict(some_list)` raises a bare
        `ValueError`, and either answers the question before the contract can."""
        self.refusal("wrong-type", self.plan, assurance="deterministic-check")
        self.refusal("wrong-type", self.plan, ladder=OBSERVED)
        self.refusal("wrong-type", self.plan, repairs=_digest("x"))
        self.refusal("wrong-type", self.plan, plan_budget=[("max-dispatches", 5)])
        self.refusal("wrong-type", self.plan, used=[("max-dispatches", 2)])
        self.refusal("unknown-value", self.plan, assurance=["thorough-vibes"])
        # An entry that is not a name at all is refused as one, BEFORE the vocabulary check --
        # which is what isolates it: without this the empty string reads as an unknown kind and
        # the arrival check goes unnoticed, and a ladder rung of `None` is not checked at all.
        self.refusal("value-invalid", self.plan, assurance=["deterministic-check", ""])
        self.refusal("value-invalid", self.plan, assurance=[None])
        self.refusal("value-invalid", self.plan, ladder=[OBSERVED, "   "])
        self.refusal("value-invalid", self.plan, ladder=[None])
        self.refusal("unknown-field", self.plan, plan_budget={"max-vibes": 5})
        self.refusal("value-invalid", self.plan, used={"max-dispatches": -1})
        self.refusal("value-invalid", self.plan, used={"max-dispatches": True})
        self.refusal("value-invalid", self.plan, checkpoint="   ")
        self.refusal("bounds-exceeded", self.plan, ladder=[f"rung-{i}" for i in range(33)])

    def test_an_undeclared_reason_cannot_be_put_on_a_plan_at_all(self):
        """Closed at construction, like every other vocabulary in this file."""
        fields = {"admissible": False, "operation": None, "repair_id": None, "bundle_sha": None,
                  "failure": None, "context": None, "retry": None, "refusal": "because",
                  "ladder": ()}
        self.refusal("unknown-value", dp.ContextRepair, reasons=("looked-wrong",), **fields)
        self.refusal("bounds-exceeded", dp.ContextRepair, reasons=(), **fields)
        self.refusal("duplicate-entry", dp.ContextRepair,
                     reasons=("checkpoint-moved", "checkpoint-moved"), **fields)
        # A plan cannot claim a repair while naming a refusal, nor refuse while handing back a
        # retry to perform.
        self.refusal("value-invalid", dp.ContextRepair,
                     reasons=("checkpoint-moved",), **dict(fields, admissible=True))
        self.refusal("value-invalid", dp.ContextRepair,
                     reasons=(dp.REPAIR_ADMISSIBLE,), **dict(fields, admissible=True))

    # ---- H. what this module does not do ------------------------------------------------------

    def test_every_unmet_condition_is_collected_and_none_masks_another(self):
        """Not short-circuited, for the reason D11 gives: a test asserting one refusal cannot be
        satisfied by a different check refusing the same input first. Fourteen things wrong at
        once come back as fourteen reasons."""
        plan = self.plan(
            attempt=attempt_record(failure_class="auth", verify_rc=0, dispatched_model=None,
                                   acceptance_ref=None, admission_ref=None),
            manifest=manifest_payload(status="no-relevant-context", candidates=[],
                                      abstention=["no-evidence-found"],
                                      freshness={"revision": {"stamped": None, "now": None,
                                                              "moved": False}}),
            bundle=None, checkpoint=None, assurance=[], plan_budget={}, used={},
            repairs=[_digest("earlier-repair")])
        for code in ("repair-not-in-force", "failure-class-excluded", "failure-not-observed",
                     "model-unidentified", "acceptance-unidentified", "assurance-undeclared",
                     "admission-not-separate", "repair-already-taken",
                     "dispatch-cap-undeclared", "context-absent", "checkpoint-unidentified"):
            with self.subTest(code=code):
                self.assertIn(code, plan.reasons)
        self.assertFalse(plan.admissible)
        self.assertEqual(len(set(plan.reasons)), len(plan.reasons))

    def test_the_repair_plan_is_swept_for_a_dependency_claim_by_the_seams_own_guard(self):
        """D16 wrote that sweep saying its work was forward -- that D17 extends the seam and a
        `depends_on` on a candidate would turn navigation evidence into an authorisation. This
        is the wiring it was waiting for, proven by a recorder that sees the real structure and
        by a raiser that kills the plan."""
        seen = {}

        def recorder(value, where="the candidate manifest"):
            seen["value"] = value
            seen["where"] = where
            return value

        with mock.patch.object(dp._dx(), "assert_no_dependency_claim", recorder):
            plan = self.plan()
        self.assertTrue(plan.admissible)
        swept = seen["value"]
        # A mapping proxy is not a `dict`, so a sweep handed one would walk nothing at all and
        # pass on every input. What is handed over is the plain structure.
        self.assertIsInstance(swept, dict)
        self.assertEqual(sorted(swept), ["context", "failure", "ladder", "retry"])
        self.assertIsInstance(swept["retry"], dict)
        self.assertIsInstance(swept["failure"], dict)
        self.assertIn("a context repair plan", seen["where"])

        def raiser(value, where="the candidate manifest"):
            raise dp._dx()._contract().ContractError(
                "authority-field", "the plan carries 'depends_on'. it is navigation evidence")

        with mock.patch.object(dp._dx(), "assert_no_dependency_claim", raiser):
            error = self.refusal("authority-field", self.plan)
        # Re-raised in THIS loader's class, so a caller catching this module's refusal sees it.
        self.assertIsInstance(error, dpc.ContractError)
        self.assertNotIn("] [", str(error), "the code prefix is not applied twice")

        def unrelated(value, where="the candidate manifest"):
            raise ValueError("something else entirely")

        with mock.patch.object(dp._dx(), "assert_no_dependency_claim", unrelated):
            with self.assertRaises(ValueError) as caught:
                self.plan()
        self.assertIsNone(getattr(caught.exception, "code", None),
                          "an unrelated error is not relabelled as an authority field")

    def test_a_candidate_is_a_place_to_read_and_the_plan_says_so_where_it_is_read(self):
        plan = self.plan()
        self.assertIsNone(plan.context["authority"])
        self.assertEqual(plan.context["navigation"], dc.NO_DEPENDENCY_CLAIM)
        self.assertIn("not a dependency", plan.context["navigation"])

    def test_the_plan_is_frozen_and_its_maps_are_not_writable(self):
        plan = self.plan()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            plan.admissible = False
        for name in ("failure", "context", "retry"):
            with self.subTest(field=name):
                self.assertIsInstance(getattr(plan, name), types.MappingProxyType)
                with self.assertRaises(TypeError):
                    getattr(plan, name)["task"] = "D99"
        with self.assertRaises(TypeError):
            plan.retry["failed_attempt"]["result"] = "pass"
        self.assertIsInstance(plan.ladder, tuple)

    def test_this_module_plans_a_repair_and_performs_none_of_it(self):
        """The same AST sweep D11 and D13 apply to their halves, re-run over the whole file so
        the D17 half is inside it, plus the names a repair would be performed through."""
        text = (BIN_DIR / "decision_policy.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    calls.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    calls.add(fn.id)
        self.assertTrue(calls, "the AST walk found no calls, so the sweep below is vacuous")
        self.assertIn("plan_context_repair", {node.name for node in ast.walk(tree)
                                              if isinstance(node, ast.FunctionDef)})
        self.assertIn("_repair_in_force", calls, "the walk reaches the code that matters")
        for performer in ("open", "write_text", "mkdir", "unlink", "run", "Popen", "system",
                          "dispatch", "record_started", "record_finished", "admit", "ref_for",
                          "context_manifest", "urlopen"):
            with self.subTest(call=performer):
                self.assertNotIn(performer, calls)
        for pattern in ("subprocess", "Path.home(", "os.environ"):
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, text)

    def test_nothing_in_this_repository_plans_a_context_repair(self):
        """A green suite says this function works, never that anything invokes it. A repair can
        only happen to somebody if something calls this, and nothing does. When this list stops
        being empty, that is the signal to check the wiring rather than a failure."""
        callers = []
        for path in sorted(BIN_DIR.glob("*.py")):
            if path.name == "decision_policy.py":
                continue
            body = path.read_text(encoding="utf-8")
            for name in ("plan_context_repair", "ContextRepair", "REPAIR_PARAMETER"):
                if name in body:
                    callers.append(f"{path.name}:{name}")
        self.assertEqual(callers, [])

    def test_no_data_file_in_this_repository_asks_for_a_context_repair(self):
        """The dial exists in the contract's allowlist; no data file here sets it. Off is not
        merely this function's default, it is the state of the whole repository: there is no
        bundle to pin, so there is nothing for a caller to resolve even if one existed.

        Swept over every JSON and TOML a catalog could plausibly be, skipping only the
        generated docs tree. Python sources are excluded because naming the parameter is what
        the contract's allowlist and this module are FOR."""
        scanned, setters = 0, []
        for suffix in ("*.json", "*.toml"):
            for path in sorted(ROOT.rglob(suffix)):
                parts = set(path.parts)
                if ".git" in parts or "docs-site" in parts or "node_modules" in parts:
                    continue
                scanned += 1
                if dp.REPAIR_PARAMETER in path.read_text(encoding="utf-8", errors="replace"):
                    setters.append(str(path.relative_to(ROOT)))
        self.assertTrue(scanned > 10, f"only {scanned} files were swept, so this is vacuous")
        self.assertEqual(setters, [])

    # ---- I. it composes with the real seam ----------------------------------------------------

    def test_an_admissible_plan_composes_with_a_real_manifest_built_by_the_seam(self):
        """Every other test here hands the planner a manifest built in this file. This one hands
        it one `bin/decision_context.py` actually produced, from a temp tree with a canned git
        probe, so the two modules are proven to compose rather than merely to agree with a
        fixture's idea of the shape."""
        tree = _Tree()
        self.addCleanup(tree.cleanup)
        real = tree.manifest()
        self.assertEqual(real["status"], "candidates")
        self.assertTrue(real["candidates"], "the seam's own manifest must carry candidates")
        plan = self.plan(manifest=real, checkpoint=tree.head,
                         bundle=self.in_force(parameters={
                             dp.REPAIR_PARAMETER: True,
                             dp.REPAIR_FILES_PARAMETER: dc.MAX_CANDIDATES_CEILING}))
        self.assertTrue(plan.admissible, list(plan.reasons))
        self.assertEqual(plan.context["ref"], dc.context_ref(real))
        self.assertEqual(plan.context["revision"], tree.head)
        self.assertEqual(plan.retry["context_paths"],
                         tuple(row["path"] for row in real["candidates"]))
        # And the same real manifest against a tree whose head has moved is refused, so the
        # checkpoint check is reading the seam's own freshness block and not this file's.
        self.refused("checkpoint-moved", manifest=real, checkpoint=MOVED_HEAD)

if __name__ == "__main__":
    unittest.main()
