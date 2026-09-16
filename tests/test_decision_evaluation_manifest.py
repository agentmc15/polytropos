"""D06 -- immutable grouped evaluation partitions for the decision-improvement-v1 kit.

`EvaluationManifestTests` covers the manifest seam `bin/workflow_eval.py` gained in place of
its flat `holdout` list (`{"tasks": [...], "reserved_from": "routing tuning"}` -- no grouping,
no content identity, no record of what had been seen), which is the gap D03's authority
inventory names under "The evaluation envelope has no grouped, content-addressed partitions".

What is proven here, in the order the brief asks for it:

  * IDENTITY. A manifest's id is the sha256 of its immutable `content` and of nothing else.
    `created_at` and `created_by` are provenance and are outside the digest, so the same pool
    built twice by two people is the same manifest. Stability is proven across two SEPARATE
    interpreters under different `PYTHONHASHSEED`s, because the failure mode a single-process
    assertion cannot see is a `set` or a dict iteration order leaking into the bytes.
  * GROUPING. Related issue variants and mutation variants of one defect are one group and one
    partition. The contamination case is tested directly and from both sides: the allocator is
    shown never to split a group over a pool of 180 variants, and a hand-split manifest (one
    audit variant moved into development, the way a person would "fix" a partition by hand) is
    shown to be caught -- including after the tamperer recomputes the digest, which is the
    point at which the hash stops helping and the controller's rules are all that is left.
  * SEPARATION. Calibration is the only partition a fit may touch, and is therefore never
    citable as held-out evidence. A calibration-fitting exposure recorded against promotion
    spends promotion too. Audit is single-use.
  * LEAKAGE. A statement carrying a reference patch, a future fix message, a fix commit sha or
    a hidden label is refused, by kind and count and never by value. A leak in ONE variant
    quarantines its whole group, and quarantine is not a partition.
  * EXPOSURE. Exposure and retirement are an append-only log beside the manifest: recorded as
    facts, subtracted at read time, never rewriting the manifest (which would change its id and
    orphan every reference to it).
  * POST-HOC COHORTS. A cohort declared after results over its partition exist is refused at
    write time AND at read time, so an entry appended to the log out of band is still refused;
    naming items at selection time is refused outright.

And the thing this file is most careful NOT to claim: a digest is not enforcement. The tamper
tests below deliberately show a rewrite succeeding at the filesystem level and being DETECTED
afterwards, never prevented. `NOT_ENFORCEMENT_LABEL` says so inside the digest itself, and
`test_the_enforcement_disclaimer_rides_inside_the_digest` fails if anyone removes it. Whether
this host can enforce anything at all is D07's question, which is allowed to answer
`unavailable`.

============================================================================================
 SAFETY CONTRACT
============================================================================================
Every task record here is SYNTHETIC: hand-built dicts shaped like `repo_bench`'s pinned
`TASK_RECORD_KEYS`, with fake shas, fake diffs and fake statements. No real repository is
mined, no real issue is read, no real defect is used. No test invokes a real
`claude`/`codex`/`copilot`/`cursor`/`graphify` binary or touches a real `~/.claude`,
`~/.codex` or `~/.copilot`. Every store is a `tempfile.TemporaryDirectory()` and
`POLYTROPOS_DATA_HOME` is pinned to a temp directory for the whole module (the seam
`tests/test_workflow_eval.py` and `tests/test_decision_duration.py` already use), so no default
store can resolve into the real per-user data root. The one end-to-end `Evaluation` runs
entirely offline against a temp fixture repository built with `git`, dispatching a throwaway
shell stub through the process runner -- `test_workflow_eval`'s own fixtures, unmodified.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_workflow_eval as twe

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_manifest_test", BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


we = _load("workflow_eval")
rb = we._rb()
al = we._al()
rg = _load("release_gate")

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


REPO = "synthetic://fixture-repo"
BASE = "0" * 40
TEST_CMD = "python3 run_tests.py"


def diff(path, removed, added):
    """A synthetic unified diff. Nothing here came out of a real repository."""
    return (f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n-{removed}\n+{added}\n")


def task(task_id, *, issue=None, fix_commit=None, subject="", statement="the widget miscounts",
         mode="issue-replay", reference_patch=None, setup_patch=None, test_blobs=None,
         base_commit=BASE, size="S", statement_source="issue", oracle=True):
    """A task record shaped exactly like `repo_bench`'s pinned schema, invented from nothing."""
    return {
        "task_id": task_id, "mode": mode, "issue": issue, "base_commit": base_commit,
        "fix_commit": fix_commit, "subject": subject, "statement": statement,
        "statement_source": statement_source,
        "reference_patch": reference_patch if reference_patch is not None
        else diff("src/widget.py", "    return count - 1", "    return count"),
        "setup_patch": setup_patch, "test_blobs": test_blobs or {},
        "oracle_tests_available": oracle, "size_profile": size,
        "labels": [], "notes": [],
    }


def pool(n_defects=60, variants=3):
    """`n_defects` synthetic defects, each reported `variants` times as the SAME issue.

    Each variant patches a DIFFERENT file on purpose: nothing but the shared issue can group
    them, so a test that finds them grouped has found issue grouping and not a coincidence of
    paths.
    """
    out = []
    for d in range(n_defects):
        for v in range(variants):
            out.append(task(f"issue-{d}-v{v}", issue=d + 1,
                            statement=f"defect {d} shows up in path {v}",
                            reference_patch=diff(f"src/mod{d}_{v}.py", f"    old_{d}_{v}()",
                                                 f"    new_{d}_{v}()")))
    return out


class EvaluationManifestTests(unittest.TestCase):

    def store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name) / "evals"

    def evaluation_case(self):
        """`test_workflow_eval`'s own offline fixture case, borrowed whole rather than
        reimplemented: a temp git repository, a throwaway shell stub, a temp store, and the
        real `Evaluation` driven through the process runner. Nothing in it reaches a harness
        CLI or a real home. It is instantiated, never collected -- it declares no test method
        and no `runTest`, so the loader yields nothing from it."""
        case = twe._Case()
        case.setUp()
        self.addCleanup(case.tearDown)
        return case

    def manifest(self, tasks=None, **kw):
        kw.setdefault("acceptance", TEST_CMD)
        return we.build_manifest(REPO, BASE, tasks if tasks is not None else pool(), **kw)

    # ---- the fixture is synthetic, and shaped like the real thing ---------------------------

    def test_every_fixture_task_is_synthetic_and_matches_the_pinned_mined_schema(self):
        # If `repo_bench.TASK_RECORD_KEYS` ever widens, this fails rather than letting the
        # manifest be built from a task shape that no longer exists.
        for record in (task("issue-1-v0", issue=1), pool(2, 2)[0]):
            self.assertEqual(set(record), set(rb.TASK_RECORD_KEYS))
        self.assertTrue(REPO.startswith("synthetic://"))
        self.assertEqual(BASE, "0" * 40, "a fake commit, never a real one")

    # ---- identity: hashes persist -----------------------------------------------------------

    def test_a_manifest_id_is_the_digest_of_its_content_and_only_its_content(self):
        tasks = pool(6, 2)
        first = we.build_manifest(REPO, BASE, tasks, acceptance=TEST_CMD, created_by="alice",
                                  created_at="2020-01-01T00:00:00+00:00")
        second = we.build_manifest(REPO, BASE, tasks, acceptance=TEST_CMD, created_by="bob",
                                   created_at="2031-12-31T23:59:59+00:00")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["sha"], second["sha"])
        self.assertEqual(first["sha"], we.manifest_digest(first["content"]))
        self.assertEqual(first["id"], first["sha"][:16])
        self.assertIn("created_at", first["digest"]["excludes"])
        self.assertIn("created_by", first["digest"]["excludes"])
        self.assertNotIn("created_at", first["content"])
        self.assertNotEqual(first["created_at"], second["created_at"])

    def test_the_digest_moves_when_any_of_the_four_identities_moves(self):
        base = pool(4, 2)
        original = self.manifest(base)["id"]
        for label, mutate in (
            ("code", lambda t: dict(t, base_commit="f" * 40)),
            ("task", lambda t: dict(t, statement=t["statement"] + " (reworded)")),
            ("artifact", lambda t: dict(t, reference_patch=diff("src/other.py", "-x", "+y"))),
        ):
            with self.subTest(identity=label):
                moved = [mutate(base[0])] + base[1:]
                self.assertNotEqual(self.manifest(moved)["id"], original)
        with self.subTest(identity="acceptance"):
            self.assertNotEqual(
                we.build_manifest(REPO, BASE, base, acceptance="pytest -q")["id"], original)

    def test_neither_task_order_nor_dict_order_moves_the_digest(self):
        tasks = pool(5, 3)
        shuffled = list(reversed(tasks))
        reordered = [{k: t[k] for k in reversed(list(t))} for t in shuffled]
        self.assertEqual(self.manifest(tasks)["id"], self.manifest(reordered)["id"])

    def test_the_digest_is_stable_across_processes_and_hash_seeds(self):
        # The failure a same-process assertion cannot see: a set's iteration order, or a dict
        # keyed by something str-hashed, reaching the canonical bytes. Two interpreters, two
        # PYTHONHASHSEEDs, one id -- or the manifest is not content-addressed at all.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "pool.json").write_text(json.dumps(pool(8, 3)))
        script = root / "digest.py"
        script.write_text(
            "import importlib.util, json, sys\n"
            "spec = importlib.util.spec_from_file_location('we', sys.argv[1])\n"
            "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\n"
            "tasks = json.loads(open(sys.argv[2]).read())\n"
            f"m = mod.build_manifest({REPO!r}, {BASE!r}, tasks, acceptance={TEST_CMD!r})\n"
            "print(m['id'], m['sha'])\n")
        ids = set()
        for seed in ("0", "1", "424242"):
            env = dict(os.environ, PYTHONHASHSEED=seed, POLYTROPOS_DATA_HOME=str(root / "data"))
            proc = subprocess.run([sys.executable, str(script), str(BIN_DIR / "workflow_eval.py"),
                                   str(root / "pool.json")],
                                  capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            ids.add(proc.stdout.strip())
        self.assertEqual(len(ids), 1, f"the digest moved between interpreters: {ids}")
        self.assertEqual(ids.pop().split()[0], self.manifest(pool(8, 3))["id"])

    def test_every_item_carries_code_task_acceptance_and_artifact_identities(self):
        manifest = self.manifest(pool(2, 2))
        for iid, item in manifest["content"]["items"].items():
            identity = item["identity"]
            self.assertEqual(set(identity), {"code", "task", "acceptance", "artifact"})
            self.assertEqual(identity["code"]["base_commit"], BASE)
            self.assertEqual(identity["acceptance"]["test_cmd_sha"], we._sha(TEST_CMD))
            self.assertTrue(identity["artifact"]["reference_patch_sha"])
            self.assertEqual(we.item_id(identity), iid)

    def test_the_manifest_stores_digests_of_the_answer_never_the_answer(self):
        # A manifest that carried the reference patch would be a leak vector of its own.
        secret = "    return SOLUTION_CONSTANT_42"
        tasks = [task("issue-9-v0", issue=9,
                      reference_patch=diff("src/a.py", "    return 0", secret))]
        body = json.dumps(self.manifest(tasks), sort_keys=True)
        self.assertNotIn(secret, body)
        self.assertNotIn("diff --git", body)
        self.assertIn(we._sha(diff("src/a.py", "    return 0", secret)), body)

    # ---- grouping: variants group ------------------------------------------------------------

    def test_issue_variants_of_one_defect_land_in_one_group_and_one_partition(self):
        # Three reports of one defect, each patching a different file: the shared issue is the
        # only thing that can group them.
        tasks = [task("issue-7-a", issue=7, statement="the total is off by one",
                      reference_patch=diff("src/total.py", "    n = n - 1", "    n = n")),
                 task("issue-7-b", issue=7, statement="totals disagree between views",
                      reference_patch=diff("src/view.py", "    show(n - 1)", "    show(n)")),
                 task("issue-7-c", issue=7, statement="a third report of the same miscount",
                      reference_patch=diff("src/api.py", "    emit(n - 1)", "    emit(n)"))]
        content = self.manifest(tasks)["content"]
        self.assertEqual(len(content["groups"]), 1)
        group = next(iter(content["groups"].values()))
        self.assertEqual(group["key"], "issue:7")
        self.assertEqual(len(group["items"]), 3)
        homes = {content["items"][i]["partition"] for i in group["items"]}
        self.assertEqual(len(homes), 1, "three variants of one defect, three partitions")

    def test_mutation_variants_of_one_site_land_in_one_group(self):
        # repo_bench's general mode injects one textual mutation per task and hands back the
        # reverse diff; two mutations of the same file are two variants of one site.
        tasks = [task("mut-1-parser", mode="general", statement_source="generated",
                      statement=rb.GENERAL_STATEMENT,
                      reference_patch=diff("src/parser.py", "    a = 1", "    a = 2"),
                      setup_patch=diff("src/parser.py", "    a = 2", "    a = 1")),
                 task("mut-2-parser", mode="general", statement_source="generated",
                      statement=rb.GENERAL_STATEMENT,
                      reference_patch=diff("src/parser.py", "    b = 3", "    b = 4"),
                      setup_patch=diff("src/parser.py", "    b = 4", "    b = 3"))]
        content = self.manifest(tasks)["content"]
        self.assertEqual(len(content["groups"]), 1)
        self.assertEqual(next(iter(content["groups"].values()))["key"], "site:src/parser.py")

    def test_the_allocator_never_splits_a_group_and_still_fills_every_partition(self):
        content = self.manifest(pool(60, 3))["content"]
        self.assertEqual(len(content["groups"]), 60)
        for group in content["groups"].values():
            homes = {content["items"][i]["partition"] for i in group["items"]}
            self.assertEqual(len(homes), 1, f"group {group['key']} split across {homes}")
            self.assertEqual(len(group["items"]), 3)
        for name in we.PARTITIONS:
            self.assertTrue(content["partitions"][name],
                            f"{name} drew nothing from 60 defects: the allocation is broken")
        self.assertEqual(we.verify_manifest(self.manifest(pool(60, 3))), [])

    def test_a_group_does_not_change_partition_when_the_code_moves(self):
        # If assignment moved with the revision, yesterday's audit material would be today's
        # development material and every audit result taken since would be contaminated.
        tasks = pool(40, 2)
        old = self.manifest(tasks)["content"]
        later = "a" * 40
        moved = [dict(t, base_commit=later) for t in tasks]
        new = we.build_manifest(REPO, later, moved, acceptance=TEST_CMD)["content"]
        self.assertNotEqual(we.manifest_digest(old), we.manifest_digest(new),
                            "a new revision is a new manifest -- only the ASSIGNMENT is stable")
        old_homes = {g["key"]: g["partition"] for g in old["groups"].values()}
        new_homes = {g["key"]: g["partition"] for g in new["groups"].values()}
        self.assertEqual(old_homes, new_homes)

    def test_a_hand_split_group_is_caught_even_after_the_tamperer_rehashes(self):
        store = self.store()
        manifest = self.manifest(pool(30, 2))
        we.write_manifest(store, manifest)
        audit = manifest["content"]["partitions"]["audit"]
        self.assertTrue(audit, "the fixture needs audit material to contaminate")
        victim = audit[0]
        group = manifest["content"]["items"][victim]["group"]

        # Exactly what a person does by hand when a partition "looks unbalanced": move one
        # variant across. Its sibling stays in audit, so the audit result for this defect was
        # already solved in development.
        tampered = json.loads(json.dumps(manifest))
        tampered["content"]["partitions"]["audit"].remove(victim)
        tampered["content"]["partitions"]["development"].append(victim)
        tampered["content"]["items"][victim]["partition"] = "development"
        kinds = {f["kind"] for f in we.verify_manifest(tampered)}
        self.assertIn("digest", kinds)
        self.assertIn("group-split", kinds)

        # Now the tamperer does the obvious next thing and recomputes the digest. The hash
        # stops saying anything at all; the CONTROLLER's rule is what is left.
        rehashed = json.loads(json.dumps(tampered))
        rehashed["sha"] = we.manifest_digest(rehashed["content"])
        rehashed["id"] = rehashed["sha"][:16]
        kinds = {f["kind"] for f in we.verify_manifest(rehashed)}
        self.assertNotIn("digest", kinds, "a recomputed digest agrees with itself -- of course")
        self.assertIn("group-split", kinds)
        split = next(f for f in we.verify_manifest(rehashed) if f["kind"] == "group-split")
        self.assertEqual(split["group"], group)
        with self.assertRaises(we.EvalError) as caught:
            we.require_held_out(store, rehashed, "audit")
        self.assertIn("group-split", str(caught.exception))

        # And it is no longer filed under its own id, so the reference that pointed here --
        # the envelope's `manifest_ref` -- stops resolving.
        (store / we.MANIFEST_DIR / f"{manifest['id']}.json").write_text(json.dumps(rehashed))
        with self.assertRaises(we.EvalError) as caught:
            we.read_manifest(store, manifest["id"])
        self.assertIn("not its content digest", str(caught.exception))

    # ---- calibration stays separate from promotion and audit ---------------------------------

    def test_calibration_is_a_fitting_partition_and_is_never_held_out_evidence(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        roles = manifest["content"]["rules"]["partitions"]
        self.assertTrue(roles["calibration"]["fitting"])
        self.assertFalse(roles["calibration"]["held_out"])
        for name in ("promotion", "audit"):
            self.assertFalse(roles[name]["fitting"])
            self.assertTrue(roles[name]["held_out"])
        with self.assertRaises(we.EvalError) as caught:
            we.require_held_out(store, manifest, "calibration")
        self.assertIn("not held-out evidence", str(caught.exception))
        # Fitting on it is fine, and is what it is for.
        fitted = we.select_cohort(store, manifest, "calibration", by="tester")
        self.assertEqual(fitted, sorted(manifest["content"]["partitions"]["calibration"]))

    def test_a_partition_a_fit_has_touched_is_spent_as_evidence(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        self.assertTrue(we.require_held_out(store, manifest, "promotion"))
        we.record_exposure(store, manifest, partition="promotion", purpose="calibration-fitting",
                           items=manifest["content"]["partitions"]["promotion"][:1], by="tester")
        with self.assertRaises(we.EvalError) as caught:
            we.require_held_out(store, manifest, "promotion")
        message = str(caught.exception)
        self.assertIn("calibration fit has been recorded", message)
        self.assertIn("spent as evidence", message)

    def test_audit_is_single_use_and_a_second_reading_is_refused(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        first = we.select_cohort(store, manifest, "audit", by="tester")
        self.assertTrue(first)
        with self.assertRaises(we.EvalError) as caught:
            we.select_cohort(store, manifest, "audit", by="tester")
        self.assertIn("single-use", str(caught.exception))

    # ---- leakage: stale/leaking statements fail ----------------------------------------------

    def test_a_statement_carrying_a_reference_patch_is_refused(self):
        leaking = task("issue-3-a", issue=3,
                       statement="here is the fix:\n" + diff("src/a.py", "    was_wrong(this)",
                                                             "    is_right(this_instead)"))
        with self.assertRaises(we.EvalError) as caught:
            self.manifest([leaking])
        message = str(caught.exception)
        self.assertIn("reference-patch", message)
        self.assertNotIn("is_right(this_instead)", message,
                         "a finding that quotes the leak copies it somewhere new")
        kinds = we.leak_summary(we.screen_statement(leaking))
        self.assertEqual(sorted(kinds), ["reference-patch"])

    def test_a_verbatim_patch_line_in_prose_is_caught_without_any_diff_marker(self):
        line = "    total = sum(row.amount for row in rows)"
        leaking = task("issue-4-a", issue=4,
                       statement=f"someone told me the answer is `{line}` but I am not sure",
                       reference_patch=diff("src/a.py", "    total = 0", line))
        findings = we.screen_statement(leaking)
        self.assertEqual([f["kind"] for f in findings], ["reference-patch"])
        self.assertIn("shared verbatim", findings[0]["evidence"])
        self.assertNotIn(line, json.dumps(findings))

    def test_a_future_fix_message_and_a_fix_commit_sha_are_refused(self):
        subject = "fix the off-by-one in the widget total"
        leaking = task("issue-5-a", issue=5, subject=subject, statement_source="commit-message",
                       statement=subject + "\n\nthe counter started at one.",
                       fix_commit="abc1234def5678")
        kinds = we.leak_summary(we.screen_statement(leaking))
        self.assertEqual(sorted(kinds), ["future-fix-message"])
        with_sha = task("issue-6-a", issue=6, fix_commit="abc1234def5678",
                        statement="this was fixed later in abc1234def5678, see there")
        self.assertEqual(sorted(we.leak_summary(we.screen_statement(with_sha))),
                         ["fix-commit-identity"])
        with self.assertRaises(we.EvalError) as caught:
            self.manifest([leaking, with_sha])
        self.assertIn("future-fix-message", str(caught.exception))
        self.assertIn("fix-commit-identity", str(caught.exception))

    def test_a_hidden_label_and_a_withheld_oracle_test_are_refused(self):
        blob = "def test_total():\n    assert widget.total(rows) == 42\n"
        for label, leaking in (
            ("marker", task("issue-8-a", issue=8,
                            statement="the widget miscounts. GROUND-TRUTH: it returns n-1")),
            ("test path", task("issue-8-b", issue=8,
                               statement="see tests/test_total.py for what it should do",
                               test_blobs={"tests/test_total.py": blob})),
            ("test body", task("issue-8-c", issue=8,
                               statement="the check is `assert widget.total(rows) == 42`",
                               test_blobs={"tests/test_total.py": blob})),
        ):
            with self.subTest(leak=label):
                self.assertEqual(sorted(we.leak_summary(we.screen_statement(leaking))),
                                 ["hidden-label"])

    def test_a_clean_statement_screens_clean_and_the_screen_claims_nothing_more(self):
        clean = task("issue-2-a", issue=2,
                     statement="Adding two rows and reading the total shows one row's worth. "
                               "Expected the sum of both.")
        self.assertEqual(we.screen_statement(clean), [])
        # The honest limit, asserted rather than assumed: a PARAPHRASE of the fix is a leak
        # this screen does not catch. Shape matching cannot prove absence -- the same caveat
        # bin/redact.py carries -- and no test here may be read as saying it can.
        paraphrased = task("issue-2-b", issue=2,
                           statement="just change the return so it stops subtracting one",
                           reference_patch=diff("src/a.py", "    return n - 1", "    return n"))
        self.assertEqual(we.screen_statement(paraphrased), [])

    def test_a_leak_in_one_variant_quarantines_the_whole_group(self):
        store = self.store()
        tasks = [task("issue-11-a", issue=11, statement="the total is wrong"),
                 task("issue-11-b", issue=11, statement="still wrong after a reload"),
                 task("issue-11-c", issue=11,
                      statement="the fix:\n" + diff("src/a.py", "    bad_call(here)",
                                                    "    good_call(here_instead)"))]
        manifest = self.manifest(tasks, on_leak="quarantine")
        content = manifest["content"]
        self.assertEqual(len(content["partitions"][we.QUARANTINE]), 3,
                         "knowing the answer to one variant is knowing it for its siblings")
        for name in we.PARTITIONS:
            self.assertEqual(content["partitions"][name], [])
        self.assertNotIn(we.QUARANTINE, we.PARTITIONS)
        we.write_manifest(store, manifest)
        for name in ("promotion", "audit"):
            with self.assertRaises(we.EvalError):
                we.require_held_out(store, manifest, name)
        self.assertEqual(sorted(we.manifest_summary(manifest)["leaks"]), ["reference-patch"])

    def test_a_leaking_item_smuggled_into_a_partition_is_a_finding(self):
        manifest = self.manifest(
            [task("issue-12-a", issue=12,
                  statement="the fix:\n" + diff("src/a.py", "    x = wrong_value()",
                                                "    x = right_value()"))],
            on_leak="quarantine")
        victim = manifest["content"]["partitions"][we.QUARANTINE][0]
        manifest["content"]["partitions"][we.QUARANTINE].remove(victim)
        manifest["content"]["partitions"]["audit"].append(victim)
        manifest["content"]["items"][victim]["partition"] = "audit"
        kinds = {f["kind"] for f in we.verify_manifest(manifest)}
        self.assertIn("leak-in-partition", kinds)

    # ---- staleness ---------------------------------------------------------------------------

    def test_a_task_that_moved_since_admission_is_stale_and_cannot_be_cited(self):
        store = self.store()
        tasks = pool(40, 2)
        manifest = self.manifest(tasks)
        we.write_manifest(store, manifest)
        self.assertEqual(we.verify_manifest(manifest, tasks=tasks), [])
        self.assertTrue(we.require_held_out(store, manifest, "audit", tasks=tasks))

        victim = manifest["content"]["items"][
            manifest["content"]["partitions"]["audit"][0]]["task_id"]
        moved = [dict(t, statement=t["statement"] + " -- restated")
                 if t["task_id"] == victim else t for t in tasks]
        findings = we.verify_manifest(manifest, tasks=moved)
        self.assertEqual([f["kind"] for f in findings], ["stale"])
        self.assertIn("task changed", findings[0]["detail"])
        with self.assertRaises(we.EvalError) as caught:
            we.require_held_out(store, manifest, "audit", tasks=moved)
        self.assertIn("stale", str(caught.exception))

    def test_a_changed_acceptance_command_makes_every_item_stale(self):
        tasks = pool(4, 2)
        manifest = self.manifest(tasks)
        clean = we.verify_manifest(manifest, tasks=tasks, acceptance=TEST_CMD)
        self.assertEqual(clean, [])
        findings = we.verify_manifest(manifest, tasks=tasks, acceptance="pytest -q")
        self.assertEqual(len(findings), len(manifest["content"]["items"]))
        self.assertTrue(all(f["kind"] == "stale" for f in findings))
        self.assertTrue(all("acceptance changed" in f["detail"] for f in findings))

    def test_a_vanished_task_is_stale_rather_than_silently_dropped(self):
        tasks = pool(3, 2)
        manifest = self.manifest(tasks)
        findings = we.verify_manifest(manifest, tasks=tasks[1:])
        self.assertEqual([f["kind"] for f in findings], ["stale"])
        self.assertIn("gone from the pool", findings[0]["detail"])

    # ---- exposure records --------------------------------------------------------------------

    def test_exposure_is_recorded_as_a_fact_with_its_purpose_items_and_order(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        items = manifest["content"]["partitions"]["development"][:2]
        we.record_exposure(store, manifest, partition="development", items=items, by="tester",
                           run="run-1", note="looked at while debugging")
        we.record_exposure(store, manifest, partition="audit", purpose="inspection",
                           items=manifest["content"]["partitions"]["audit"][:1], by="tester")
        entries, notes = we.exposure_log(store, manifest["id"])
        self.assertEqual(notes, [])
        self.assertEqual([e["kind"] for e in entries], ["exposure", "exposure"])
        self.assertEqual([e["seq"] for e in entries], [0, 1])
        self.assertEqual(entries[0]["purpose"], "development")
        self.assertEqual(entries[0]["items"], sorted(items))
        state = we.exposure_state(store, manifest)
        self.assertEqual(state["partitions"]["development"]["exposures"], 1)
        self.assertEqual(state["partitions"]["development"]["purposes"], {"development": 1})
        self.assertEqual(state["items"][items[0]]["exposures"], 1)
        self.assertEqual(state["entries"], 2)
        # An exposure grants nothing: the audit material it touched is now unusable, which is
        # the recorded consequence of a fact, not a permission that was refused.
        with self.assertRaises(we.EvalError) as caught:
            we.require_held_out(store, manifest, "audit")
        self.assertIn("'inspection'", str(caught.exception))

    def test_contaminated_material_is_retired_on_the_record_and_subtracted_at_read_time(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        promotion = manifest["content"]["partitions"]["promotion"]
        before = json.loads((store / we.MANIFEST_DIR / f"{manifest['id']}.json").read_text())
        we.retire(store, manifest, items=promotion[:1], reason="seen in a debugging session",
                  by="tester")
        after = json.loads((store / we.MANIFEST_DIR / f"{manifest['id']}.json").read_text())
        self.assertEqual(before, after,
                         "retirement is a fact about exposure; rewriting the manifest would "
                         "change its id and orphan every reference to it")
        state = we.exposure_state(store, manifest)
        self.assertEqual(state["items"][promotion[0]]["retired"]["reason"],
                         "seen in a debugging session")
        self.assertEqual(state["partitions"]["promotion"]["retired"], 1)
        self.assertEqual(state["partitions"]["promotion"]["usable"], len(promotion) - 1)
        with self.assertRaises(we.EvalError) as caught:
            we.require_held_out(store, manifest, "promotion")
        self.assertIn("was retired", str(caught.exception))
        self.assertEqual(
            we.require_held_out(store, manifest, "promotion", items=promotion[1:]),
            sorted(promotion[1:]))

    def test_retirement_without_a_reason_and_exposure_of_an_unknown_item_are_refused(self):
        store = self.store()
        manifest = self.manifest(pool(4, 2))
        we.write_manifest(store, manifest)
        with self.assertRaises(we.EvalError):
            we.retire(store, manifest, items=list(manifest["content"]["items"])[:1], reason="")
        with self.assertRaises(we.EvalError):
            we.record_exposure(store, manifest, partition="audit", items=["deadbeefdeadbeef"])
        with self.assertRaises(we.EvalError):
            we.record_exposure(store, manifest, partition="nowhere", items=[])
        with self.assertRaises(we.EvalError):
            we.record_exposure(store, manifest, partition="audit", purpose="because-i-said-so")

    def test_an_unreadable_exposure_line_is_counted_and_blocks_a_held_out_claim(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        we.record_exposure(store, manifest, partition="development", by="tester")
        log = store / we.MANIFEST_DIR / f"{manifest['id']}.log.jsonl"
        with log.open("a") as fh:
            fh.write("{not json at all\n")
        entries, notes = we.exposure_log(store, manifest["id"])
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(notes), 1)
        with self.assertRaises(we.EvalError) as caught:
            we.require_held_out(store, manifest, "audit")
        self.assertIn("record of what has been seen is incomplete", str(caught.exception))

    # ---- post-hoc cohort selection -----------------------------------------------------------

    def test_a_cohort_declared_before_results_is_usable_and_recorded(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        promotion = manifest["content"]["partitions"]["promotion"]
        we.declare_cohort(store, manifest, partition="promotion", cohort="pilot-a",
                          items=promotion[:2], by="tester", note="predeclared")
        chosen = we.select_cohort(store, manifest, "promotion", cohort="pilot-a", by="tester")
        self.assertEqual(chosen, sorted(promotion[:2]))
        state = we.exposure_state(store, manifest)
        self.assertIn("pilot-a", state["partitions"]["promotion"]["cohorts"])
        self.assertEqual(state["partitions"]["promotion"]["exposures"], 1)

    def test_a_cohort_declared_after_the_results_are_known_is_refused(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        promotion = manifest["content"]["partitions"]["promotion"]
        we.record_results(store, manifest, partition="promotion", run="run-1", by="tester")
        with self.assertRaises(we.EvalError) as caught:
            we.declare_cohort(store, manifest, partition="promotion", cohort="the-ones-that-won",
                              items=promotion[:2], by="tester")
        message = str(caught.exception)
        self.assertIn("post-hoc cohort selection refused", message)
        self.assertIn("before the outcomes exist", message)

    def test_naming_the_items_at_selection_time_is_refused_outright(self):
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        with self.assertRaises(we.EvalError) as caught:
            we.select_cohort(store, manifest, "promotion", by="tester",
                             items=manifest["content"]["partitions"]["promotion"][:1])
        self.assertIn("post-hoc cohort selection", str(caught.exception))
        with self.assertRaises(we.EvalError) as caught:
            we.select_cohort(store, manifest, "promotion", cohort="never-declared", by="tester")
        self.assertIn("never declared", str(caught.exception))

    def test_a_declaration_appended_out_of_band_after_a_result_is_still_refused_at_read_time(self):
        # `declare_cohort` refuses this at write time. Someone who appends the line themselves
        # gets past that check; the READER re-applies the order rule, so the selection still
        # fails. What this does NOT survive is a rewrite of the whole log, and nothing in a
        # file can -- that is the boundary D07 asks about, not one a digest supplies.
        store = self.store()
        manifest = self.manifest(pool(40, 2))
        we.write_manifest(store, manifest)
        promotion = manifest["content"]["partitions"]["promotion"]
        we.record_results(store, manifest, partition="promotion", run="run-1", by="tester")
        log = store / we.MANIFEST_DIR / f"{manifest['id']}.log.jsonl"
        with log.open("a") as fh:
            fh.write(json.dumps({"v": we.MANIFEST_VERSION, "kind": "cohort.declared",
                                 "manifest": manifest["id"], "partition": "promotion",
                                 "cohort": "smuggled", "items": promotion[:2],
                                 "by": "not-really", "at": "2020-01-01T00:00:00+00:00"}) + "\n")
        entries, _notes = we.exposure_log(store, manifest["id"])
        self.assertEqual([e["kind"] for e in entries], ["result", "cohort.declared"])
        with self.assertRaises(we.EvalError) as caught:
            we.select_cohort(store, manifest, "promotion", cohort="smuggled", by="tester")
        message = str(caught.exception)
        self.assertIn("post-hoc cohort selection refused", message)
        self.assertIn("after results over promotion were recorded", message)

    # ---- storage: one owner, one file, created once -------------------------------------------

    def test_a_manifest_file_is_created_once_and_never_rewritten(self):
        store = self.store()
        manifest = self.manifest(pool(6, 2))
        path = we.write_manifest(store, manifest)
        self.assertEqual(path.parent.name, we.MANIFEST_DIR)
        first = path.read_text()
        again = we.build_manifest(REPO, BASE, pool(6, 2), acceptance=TEST_CMD,
                                  created_by="somebody-else")
        self.assertEqual(again["id"], manifest["id"])
        we.write_manifest(store, again)
        self.assertEqual(path.read_text(), first, "the first write is the manifest")

        forged = json.loads(json.dumps(manifest))
        forged["content"]["base_commit"] = "9" * 40
        with self.assertRaises(we.EvalError) as caught:
            we.write_manifest(store, forged)
        self.assertIn("DIFFERENT content", str(caught.exception))
        self.assertEqual(path.read_text(), first, "nothing was overwritten")

    def test_reading_back_a_rewritten_manifest_fails_rather_than_returning_it(self):
        store = self.store()
        manifest = self.manifest(pool(6, 2))
        path = we.write_manifest(store, manifest)
        self.assertEqual(we.read_manifest(store, manifest["id"])["id"], manifest["id"])
        tampered = json.loads(path.read_text())
        tampered["content"]["rules"]["allocation"]["audit"] = 0
        path.write_text(json.dumps(tampered))
        with self.assertRaises(we.EvalError) as caught:
            we.read_manifest(store, manifest["id"])
        self.assertIn("rewritten since it was written", str(caught.exception))
        with self.assertRaises(we.EvalError):
            we.read_manifest(store, "0123456789abcdef")

    def test_a_manifest_id_can_never_name_a_path_outside_the_store(self):
        store = self.store()
        store.mkdir(parents=True)
        for hostile in ("../escape", "/etc/passwd", ".hidden", "a/b"):
            with self.subTest(id=hostile):
                with self.assertRaises(we._sp().SafePathError):
                    we.read_manifest(store, hostile)

    def test_the_evals_store_has_exactly_one_engine_naming_it(self):
        # "One local store, written by its own engine ONLY." `bin/runtime_data.py` declares the
        # store; `bin/workflow_eval.py` is the only module that resolves it. A second writer
        # would have to name it here.
        naming = sorted(p.name for p in BIN_DIR.glob("*.py")
                        if '"evals"' in p.read_text() or "'evals'" in p.read_text())
        self.assertEqual(naming, ["runtime_data.py", "workflow_eval.py"])
        self.assertIn("evals", _load("runtime_data").STORES)

    # ---- the envelope, end to end, through the owning evaluator ------------------------------

    def test_an_evaluation_persists_one_manifest_and_its_exposure_through_its_own_owner(self):
        case = self.evaluation_case()
        plan, tasks, adapter = case.plan()
        ev, env = case.evaluate(plan, tasks, adapter)

        holdout = env["holdout"]
        self.assertEqual(holdout["tasks"], sorted(t["task_id"] for t in tasks))
        self.assertEqual(holdout["reserved_from"], "routing tuning")
        self.assertEqual(holdout["partition"], "promotion")
        ref = holdout["manifest_ref"]
        self.assertEqual(sorted(ref), ["id", "sha", "v"])
        self.assertEqual(ref["v"], we.MANIFEST_VERSION)

        self.assertEqual(holdout["manifest_dir"], we.MANIFEST_DIR)
        stored = we.read_manifest(ev.run_dir, ref["id"])
        self.assertEqual(stored["sha"], ref["sha"])
        self.assertEqual(holdout["manifest"]["items"], len(stored["content"]["items"]))
        self.assertEqual(holdout["manifest"]["groups"], len(stored["content"]["groups"]))
        files = sorted(p.name for p in (ev.run_dir / we.MANIFEST_DIR).iterdir())
        self.assertEqual(files, [f"{ref['id']}.json", f"{ref['id']}.log.jsonl"])
        # The store root keeps exactly the run directories: readers walk it expecting that.
        self.assertEqual(sorted(p.name for p in case.store.iterdir()), [ev.run_id])

        entries, notes = we.exposure_log(ev.run_dir, ref["id"])
        self.assertEqual(notes, [])
        self.assertEqual([e["kind"] for e in entries], ["exposure", "result"])
        self.assertEqual(entries[0]["partition"], "promotion")
        self.assertEqual(entries[0]["purpose"], "promotion-evidence")
        self.assertEqual(entries[0]["run"], ev.run_id)
        self.assertEqual(entries[1]["run"], ev.run_id)

        # The manifest lives beside the runs, and is not reported as a malformed one.
        rows, notes = we.list_runs(case.store)
        self.assertEqual([r["run_id"] for r in rows], [ev.run_id])
        self.assertEqual(notes, [])

    def test_the_evaluations_quarantine_label_names_kinds_and_counts_never_values(self):
        # The stock fixture's statement IS its fix commit message (repo_bench falls back to it
        # without `gh`, labelled "weaker than issue text"), so this run's material screens
        # positive for `future-fix-message` by construction -- and is therefore never held-out
        # evidence. Recorded, not hidden, and never quoted.
        case = self.evaluation_case()
        plan, tasks, adapter = case.plan()
        ev, env = case.evaluate(plan, tasks, adapter)
        label = next(l for l in env["labels"] if l.startswith("1 task(s) quarantined"))
        self.assertIn("future-fix-message=1", label)
        self.assertNotIn(tasks[0]["subject"], label)
        self.assertEqual(env["holdout"]["manifest"]["quarantined"], 1)
        self.assertEqual(env["holdout"]["manifest"]["partitions"]["promotion"], 0)
        manifest = we.read_manifest(ev.run_dir, env["holdout"]["manifest_ref"]["id"])
        with self.assertRaises(we.EvalError):
            we.require_held_out(ev.run_dir, manifest, "promotion")

    def test_a_shared_manifest_root_is_not_reported_as_a_malformed_run(self):
        # The evaluator files its manifests inside its own run directory, but the root is the
        # CALLER's choice -- a pool shared across runs would put them at the store root. When
        # someone does, `list_runs` must not report the directory as a broken run.
        case = self.evaluation_case()
        plan, tasks, adapter = case.plan()
        ev, _env = case.evaluate(plan, tasks, adapter)
        shared = we.build_manifest(REPO, BASE, pool(4, 2), acceptance=TEST_CMD)
        we.write_manifest(case.store, shared)
        rows, notes = we.list_runs(case.store)
        self.assertEqual([r["run_id"] for r in rows], [ev.run_id])
        self.assertEqual(notes, [])
        self.assertEqual(we.read_manifest(case.store, shared["id"])["sha"], shared["sha"])

    def test_a_cohort_of_a_finished_runs_partition_can_no_longer_be_declared(self):
        case = self.evaluation_case()
        plan, tasks, adapter = case.plan()
        ev, env = case.evaluate(plan, tasks, adapter)
        manifest = we.read_manifest(ev.run_dir, env["holdout"]["manifest_ref"]["id"])
        with self.assertRaises(we.EvalError) as caught:
            we.declare_cohort(ev.run_dir, manifest, partition="promotion", cohort="after",
                              items=sorted(manifest["content"]["items"])[:1], by="tester")
        self.assertIn("post-hoc cohort selection refused", str(caught.exception))

    def test_an_evaluation_refuses_an_unknown_partition_before_it_runs_anything(self):
        case = self.evaluation_case()
        plan, tasks, adapter = case.plan()
        with self.assertRaises(we.EvalError):
            we.Evaluation(plan, tasks, adapter, store_dir=case.store, partition="quarantine")

    # ---- the rules ride inside the digest, and are not the digest ----------------------------

    def test_the_enforcement_disclaimer_rides_inside_the_digest(self):
        manifest = self.manifest(pool(3, 2))
        content = manifest["content"]
        self.assertEqual(content["rules"]["enforcement"], we.NOT_ENFORCEMENT_LABEL)
        self.assertIn(we.NOT_ENFORCEMENT_LABEL, content["labels"])
        self.assertIn("never prevents it", we.NOT_ENFORCEMENT_LABEL)
        self.assertIn("tamper-evident, not tamper-proof", we.NOT_ENFORCEMENT_LABEL)
        stripped = json.loads(json.dumps(content))
        stripped["rules"]["enforcement"] = ""
        stripped["labels"] = []
        self.assertNotEqual(we.manifest_digest(stripped), manifest["sha"],
                            "removing the disclaimer must move the id, or it is decoration")

    def test_the_immutable_rules_travel_with_the_manifest(self):
        content = self.manifest(pool(3, 2))["content"]
        rules = content["rules"]
        self.assertEqual(sorted(rules["partitions"]), sorted(we.PARTITIONS))
        self.assertEqual(rules["leak_kinds"], list(we.LEAK_KINDS))
        self.assertEqual(rules["exposure_purposes"], list(we.EXPOSURE_PURPOSES))
        self.assertIn("one defect, one group, one partition", rules["grouping"])
        self.assertIn("not of the repository revision", rules["assignment"])
        self.assertEqual(rules["allocation"], we.DEFAULT_ALLOCATION)
        for name in we.PARTITIONS:
            self.assertEqual(rules["partitions"][name], we.PARTITION_ROLES[name])

    def test_an_impossible_allocation_is_refused_rather_than_normalised(self):
        for bad in ({"nowhere": 1}, {"audit": -1}, {"audit": 0}):
            with self.subTest(allocation=bad):
                with self.assertRaises(we.EvalError):
                    self.manifest(pool(2, 1), allocation=bad)

    # ---- the constants this task was told not to move ----------------------------------------

    def test_the_ledger_envelope_version_did_not_move_and_the_manifest_has_its_own(self):
        # D04's rule, followed rather than restated: version the REFERENCED object, never the
        # envelope. `AttemptLedger.events()` counts every line whose `v` differs as corrupt, so
        # a bump would make every historical event in every user's store unreadable.
        self.assertEqual(al.LEDGER_VERSION, "polytropos.attempts/1")
        self.assertEqual(we.EVAL_VERSION, "polytropos.workflow-eval/1")
        self.assertEqual(we.MANIFEST_VERSION, "polytropos.eval-manifest/1")
        self.assertNotEqual(we.MANIFEST_VERSION, we.EVAL_VERSION)

    def test_the_manifest_version_is_declared_on_the_release_surface(self):
        self.assertIn(("evaluation manifest", "workflow_eval", "MANIFEST_VERSION"),
                      rg.VERSION_SOURCES)
        row = next(r for r in rg.contract_versions() if r["contract"] == "evaluation manifest")
        self.assertEqual(row["version"], we.MANIFEST_VERSION)
        self.assertEqual(row["owner"], "bin/workflow_eval.py")


if __name__ == "__main__":
    unittest.main()
