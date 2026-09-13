"""bin/kit_scheduler.py and the step-24 contract additions: artifact binding, evidence
freshness, refresh, and opt-in bounded concurrency.

SAFETY CONTRACT. No test here runs a harness CLI. Every dispatch is a throwaway shell stub
in a temp dir (through the scheduler's `StubDispatcher` and the process runner) or an
injected Python callable. The attempt ledger is a temp store; the per-user data root is
patched to a temp dir for the module. Verify commands run under the execution boundary in
`trusted-host` mode -- the confinement itself is proven in tests/test_exec_policy.py, and
what matters here is WHICH tree each check ran against. `git` is used only to make a temp
repository fingerprintable.
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_scheduler_test", BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ks = _load("kit_scheduler")
kc = ks._kc()                      # the scheduler's own copy: exception classes compare equal
al = kc._al()
ce = _load("cursor_execute")

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


STUB = """#!/bin/sh
# argv: --task ID --workspace DIR PROMPT
task="$2"
ws="$4"
printf '===CALL=== %s %s\\n' "$task" "$ws" >> "%LOG%"
printf '%s' "$5" > "%PROMPTS%/$task.txt"
%ACTION%
printf 'TRANSCRIPT-SENTINEL-%s\\n' "$task"
exit %RC%
"""


def _task_block(tid, verify, depends="(none)", independent=True, status="pending"):
    return (f"### {tid} — task {tid}\n- status: {status}\n- depends: {depends}\n"
            f"- independent: {'yes' if independent else 'no'}\n- evidence: regression\n\n"
            f"**Brief.** Do {tid}.\n\n**Acceptance.** {tid} done.\n\n**Verify.**\n```bash\n{verify}\n```\n\n")


def _kit_text(*blocks):
    return "## Phase 1 — only\n\n" + "".join(blocks)


class _Case(unittest.TestCase):
    """A temp checkout: `.claude/kits/fixturekit`, a stub, a temp store, a log of calls."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.kit = self.root / ".claude" / "kits" / "fixturekit"
        self.kit.mkdir(parents=True)
        self.store = self.root / "store"
        self.log = self.root / "stub.log"
        self.prompts = self.root / "prompts"
        self.prompts.mkdir()
        (self.root / "README.txt").write_text("hello\n")
        self.write_kit(_task_block("T1", "test -f out-T1.txt"),
                       _task_block("T2", "test -f out-T2.txt"),
                       _task_block("T3", "test -f out-T1.txt && test -f out-T2.txt",
                                   depends="T1, T2", independent=False))

    def tearDown(self):
        self._tmp.cleanup()

    def write_kit(self, *blocks):
        (self.kit / "TASKS.md").write_text(_kit_text(*blocks))

    def stub(self, action='printf "made by %s\\n" "$task" > "out-$task.txt"', rc=0, name="stub"):
        path = self.root / name
        path.write_text(STUB.replace("%LOG%", str(self.log)).replace("%PROMPTS%", str(self.prompts))
                        .replace("%ACTION%", action).replace("%RC%", str(rc)))
        path.chmod(0o755)
        return path

    def scheduler(self, dispatcher=None, **kw):
        kw.setdefault("store", self.store)
        kw.setdefault("workspace", self.root)
        kw.setdefault("exec_mode", "trusted-host")
        kw.setdefault("max_parallel", 2)
        out, err = io.StringIO(), io.StringIO()
        sched = ks.Scheduler(self.kit, "stub", dispatcher or ks.StubDispatcher(self.stub()),
                             out=out, err=err, **kw)
        sched._out, sched._err = out, err
        return sched

    def calls(self):
        return [ln.split()[1:] for ln in self.log.read_text().splitlines()
                if ln.startswith("===CALL===")] if self.log.exists() else []

    def tasks(self):
        return {t["id"]: t for t in kc.parse_tasks((self.kit / "TASKS.md").read_text())}

    def notes(self):
        p = self.kit / "NOTES.md"
        return p.read_text() if p.exists() else ""

    def ledger(self):
        return al.AttemptLedger(self.store, "fixturekit")

    def events(self, kind):
        return [e for e in self.ledger().events() if e["kind"] == kind]


# ---- snapshots and write sets --------------------------------------------------------------------

class SnapshotTests(_Case):
    def test_a_snapshot_copies_files_keeps_modes_skips_links_and_excluded_dirs(self):
        (self.root / ".git").mkdir()
        (self.root / ".git" / "HEAD").write_text("ref\n")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "x.js").write_text("x")
        script = self.root / "run.sh"
        script.write_text("#!/bin/sh\n")
        script.chmod(0o755)
        (self.root / "link.txt").symlink_to(self.root / "README.txt")
        dest = self.root / "store" / "copy"
        index = ks.snapshot_tree(self.root, dest)
        self.assertIn("README.txt", index)
        self.assertIn("run.sh", index)
        self.assertNotIn("link.txt", index)
        self.assertFalse(any(p.startswith(".git/") or p.startswith("node_modules/") for p in index))
        self.assertTrue(os.access(dest / "run.sh", os.X_OK))
        self.assertFalse((dest / "link.txt").exists())
        after = dict(index)
        (dest / "README.txt").write_text("changed\n")
        (dest / "new.txt").write_text("n\n")
        (dest / "run.sh").unlink()
        ws = ks.write_set(index, ks.index_tree(dest))
        self.assertEqual(ws, {"changed": ["README.txt"], "added": ["new.txt"], "removed": ["run.sh"]})
        self.assertEqual(ks.coordinator_paths({".claude/kits/k/TASKS.md", "a.txt"}, ".claude/kits/k"),
                         [".claude/kits/k/TASKS.md"])


# ---- the batch ----------------------------------------------------------------------------------------

class SequentialDefaultTests(_Case):
    def test_the_default_dispatches_one_task_like_a_driver(self):
        sched = self.scheduler(max_parallel=1)
        summary = sched.run()
        self.assertEqual(summary["results"], {"T1": "done"})
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.tasks()["T2"]["status"], "pending")
        self.assertTrue((self.root / "out-T1.txt").exists())
        self.assertIn("sequential, the default", sched.render_plan(sched.plan()))

    def test_the_bound_is_capped(self):
        sched = self.scheduler(max_parallel=99)
        self.assertEqual(sched.max_parallel, ks.MAX_MAX_PARALLEL)


class BatchTests(_Case):
    def test_two_independent_tasks_run_in_isolated_copies_and_are_integrated_then_verified(self):
        sched = self.scheduler(max_parallel=2)
        summary = sched.run()
        self.assertEqual(summary["results"], {"T1": "done", "T2": "done"})
        calls = self.calls()
        self.assertEqual(sorted(c[0] for c in calls), ["T1", "T2"])
        workspaces = {c[0]: c[1] for c in calls}
        self.assertNotEqual(workspaces["T1"], workspaces["T2"], "each task in its own copy")
        for ws in workspaces.values():
            self.assertTrue(ws.startswith(str(self.store)), "copies live outside the tree")
            self.assertFalse(Path(ws).exists(), "a clean copy is discarded after integration")
        # The merged tree carries both, and the joiner is ready only now.
        self.assertEqual((self.root / "out-T1.txt").read_text(), "made by T1\n")
        self.assertEqual((self.root / "out-T2.txt").read_text(), "made by T2\n")
        self.assertEqual(self.tasks()["T3"]["status"], "pending")
        self.assertEqual(kc.graph_state(list(self.tasks().values()))["frontier"], ["T3"])
        # Integration and the fresh check on the merged tree are recorded per task.
        self.assertEqual(sorted(e["task"] for e in self.events("integration.applied")), ["T1", "T2"])
        self.assertEqual([e["rc"] for e in self.events("integration.verified")], [0, 0])
        notes = self.notes()
        self.assertIn("- merged-tree verify: exit 0", notes)
        self.assertIn("- write-set: 0 changed, 1 added, 0 removed", notes)
        self.assertRegex(notes, r"outcome: T1 model=unpinned attempts=1 result=pass")
        self.assertRegex(notes, r"outcome: T2 model=unpinned attempts=1 result=pass")
        # The prompt names the task and the id preamble; the kit's own copy was never edited.
        self.assertIn("task=T1", (self.prompts / "T1.txt").read_text())
        self.assertIsNone(self.ledger().holder("T1"))
        self.assertEqual(len(self.events("scheduler.batch")), 1)

    def test_a_dispatch_failure_and_a_verify_failure_are_each_blocked_and_nothing_is_applied(self):
        stub = self.stub(action='if [ "$task" = T1 ]; then exit 3; fi; touch out-wrong.txt')
        summary = self.scheduler(ks.StubDispatcher(stub)).run()
        self.assertEqual(summary["results"], {"T1": "blocked", "T2": "blocked"})
        self.assertFalse((self.root / "out-wrong.txt").exists(), "a failed task's copy is not applied")
        notes = self.notes()
        self.assertIn("- dispatch: exit 3", notes)
        self.assertIn("- verify: exit 1", notes)
        self.assertEqual(summary["exit"], 1)


class ConflictTests(_Case):
    def test_two_workers_writing_one_file_block_the_second_and_keep_its_tree(self):
        stub = self.stub(action='printf "from %s\\n" "$task" > shared.txt; touch "out-$task.txt"')
        sched = self.scheduler(ks.StubDispatcher(stub), workers=1)
        summary = sched.run()
        self.assertEqual(summary["results"], {"T1": "done", "T2": "blocked"})
        self.assertEqual((self.root / "shared.txt").read_text(), "from T1\n")
        self.assertFalse((self.root / "out-T2.txt").exists(), "nothing of the conflicting task applied")
        conflict = self.events("integration.conflict")
        self.assertEqual([e["task"] for e in conflict], ["T2"])
        self.assertEqual(conflict[0]["overlap"], ["shared.txt"])
        kept = Path(conflict[0]["workspace"])
        self.assertEqual((kept / "shared.txt").read_text(), "from T2\n", "the worker's tree is kept")
        self.assertIn("integration-conflict", self.notes())
        self.assertIn("nothing was reset", self.notes())
        self.assertEqual(self.tasks()["T2"]["status"], "blocked")

    def test_a_file_the_user_changed_during_the_batch_is_never_overwritten(self):
        self.write_kit(_task_block("T1", "grep -q worker README.txt"))
        root = self.root

        def dispatcher(task, prompt, workspace):
            (Path(workspace) / "README.txt").write_text("worker edit\n")
            (root / "README.txt").write_text("user edit while the batch ran\n")
            return 0, "ok", {"outcome": "ok"}
        dispatcher.describe = lambda task, prompt, ws: ["python-callable"]
        summary = self.scheduler(dispatcher, max_parallel=1).run()
        self.assertEqual(summary["results"], {"T1": "blocked"})
        self.assertEqual((root / "README.txt").read_text(), "user edit while the batch ran\n")
        conflict = self.events("integration.conflict")[0]
        self.assertEqual(conflict["user_changed"], ["README.txt"])


class MergedTreeTests(_Case):
    def test_a_check_that_passes_in_the_copy_but_fails_on_the_merged_tree_blocks_without_reset(self):
        # T1's check is satisfied only while T2's output is absent: true in T1's own copy,
        # false once T2 is integrated beside it. The merged tree is what is judged.
        self.write_kit(_task_block("T1", "test -f out-T1.txt && test ! -f out-T2.txt"),
                       _task_block("T2", "test -f out-T2.txt"))
        sched = self.scheduler(workers=1)
        summary = sched.run()
        self.assertEqual(summary["results"], {"T1": "blocked", "T2": "done"})
        self.assertTrue((self.root / "out-T1.txt").exists(), "applied files are not reset")
        self.assertTrue((self.root / "out-T2.txt").exists())
        verified = {e["task"]: e["rc"] for e in self.events("integration.verified")}
        self.assertEqual(verified, {"T1": 1, "T2": 0})
        self.assertIn("merged-tree-verification", self.notes())
        self.assertIn("were NOT reset", self.notes())


class AdmissionTests(_Case):
    def test_one_admission_decision_covers_the_batch(self):
        (self.kit / "PLAN.md").write_text("# plan\n\nbudget: max-dispatches=1\n")
        sched = self.scheduler(max_parallel=2)
        summary = sched.run()
        self.assertEqual(summary["results"], {"T1": "done"})
        self.assertEqual(len(self.calls()), 1, "one dispatch left, one dispatched")
        self.assertEqual(self.tasks()["T2"]["status"], "pending", "the refused task is untouched")
        self.assertIsNone(self.ledger().holder("T2"), "its claim is released")
        notes = self.notes()
        self.assertEqual(notes.count("result=budget-stop"), 1)
        self.assertIn("budget-stop", sched._err.getvalue())
        adm = self.events("scheduler.admission")[0]
        self.assertEqual((adm["admitted"], adm["refused"]), (["T1"], ["T2"]))
        # The next run has nothing admitted: the ledger's own count says the cap is reached.
        plan = self.scheduler(max_parallel=2).plan()
        self.assertEqual([a["admitted"] for a in plan["admission"]], [False])


class CancellationTests(_Case):
    def test_cancel_releases_what_has_not_started_and_keeps_what_was_spent(self):
        stub = self.stub(action='if [ "$task" = T1 ]; then exit 2; fi; touch "out-$task.txt"')
        sched = self.scheduler(ks.StubDispatcher(stub), workers=1, stop_on_failure=True)
        summary = sched.run()
        self.assertEqual(summary["results"], {"T1": "blocked", "T2": "cancelled"})
        self.assertEqual(summary["cancelled"], ["T2"])
        self.assertEqual([c[0] for c in self.calls()], ["T1"], "T2 was never dispatched")
        self.assertEqual(self.tasks()["T2"]["status"], "pending", "a cancelled task never moved")
        self.assertRegex(self.notes(), r"outcome: T2 model=unpinned attempts=0 result=cancelled")
        cancelled = self.events("scheduler.cancelled")
        self.assertEqual([e["task"] for e in cancelled], ["T2"])
        self.assertIn("nothing spent", cancelled[0]["reason"])
        used = kc.combined_usage(self.notes(), self.ledger())
        self.assertEqual(used["max-dispatches"], 1, "T1's spend is not refunded")
        self.assertEqual(self.ledger().task_history("T2"), [], "no attempt for a cancelled task")
        self.assertIsNone(self.ledger().holder("T2"))
        self.assertIn("cancelled this task before dispatch", self.notes())

    def test_a_cancel_set_before_the_run_dispatches_nothing(self):
        event = threading.Event()
        event.set()
        sched = self.scheduler(cancel_event=event)
        summary = sched.run()
        self.assertEqual(self.calls(), [])
        self.assertEqual(summary["cancelled"], ["T1", "T2"])


class ResumeTests(_Case):
    def test_a_dead_runs_work_is_settled_before_anything_new_is_dispatched(self):
        ledger = self.ledger()
        ledger.append("verify.precheck", run="r0", task="T1", tautological=False, rc=1)
        ledger.record_started("r0", "T1", "initial", None)
        (self.root / "out-T1.txt").write_text("left by the dead run\n")
        text = (self.kit / "TASKS.md").read_text()
        (self.kit / "TASKS.md").write_text(kc.set_status(text, "T1", "in-progress"))
        sched = self.scheduler(max_parallel=1)
        self.assertEqual(sched.plan()["batch"], ["T1"], "the interrupted task comes first")
        summary = sched.run()
        self.assertEqual(summary["results"], {"T1": "done"})
        self.assertEqual(self.calls(), [], "nothing re-dispatched")
        self.assertIn("nothing was re-dispatched", sched._err.getvalue())
        self.assertIn("- reconciled: 1 earlier attempt(s)", self.notes())
        self.assertEqual(self.ledger().task_history("T1")[0]["finished"]["outcome"], al.OUTCOME_UNKNOWN)

    def test_a_task_a_live_run_holds_is_skipped_not_taken(self):
        self.ledger().claim("T1", "r-live")  # this process's pid: alive
        sched = self.scheduler(max_parallel=2)
        summary = sched.run()
        self.assertEqual(summary["results"], {"T2": "done"})
        self.assertIn("claim:", sched._err.getvalue())
        self.assertEqual(self.tasks()["T1"]["status"], "pending")


# ---- what a worker may not do -------------------------------------------------------------------------

class SecurityTests(_Case):
    def test_a_worker_that_edits_the_kit_is_recorded_and_never_integrated(self):
        stub = self.stub(action='touch "out-$task.txt"; echo tampered >> .claude/kits/fixturekit/TASKS.md')
        before_plan = (self.kit / "TASKS.md").read_text()
        summary = self.scheduler(ks.StubDispatcher(stub)).run()
        self.assertEqual(summary["results"], {"T1": "blocked", "T2": "blocked"})
        self.assertFalse((self.root / "out-T1.txt").exists(), "nothing of a violating worker is applied")
        violations = self.events("security.violation")
        self.assertEqual(sorted(v["task"] for v in violations), ["T1", "T2"])
        self.assertEqual(violations[0]["paths"], [".claude/kits/fixturekit/TASKS.md"])
        after = (self.kit / "TASKS.md").read_text()
        self.assertNotIn("tampered", after)
        self.assertEqual(after.replace("- status: blocked", "- status: pending"), before_plan)
        self.assertIn("coordinator-state-edit", self.notes())

    def test_a_worker_cannot_grant_itself_budget(self):
        (self.kit / "PLAN.md").write_text("# plan\n\nbudget: max-dispatches=1\n")
        stub = self.stub(action='touch "out-$task.txt"; printf "budget: max-dispatches=99\\n" > .claude/kits/fixturekit/PLAN.md')
        summary = self.scheduler(ks.StubDispatcher(stub), max_parallel=1).run()
        self.assertEqual(summary["results"], {"T1": "blocked"})
        self.assertEqual((self.kit / "PLAN.md").read_text(), "# plan\n\nbudget: max-dispatches=1\n")
        self.assertEqual(self.events("security.violation")[0]["paths"],
                         [".claude/kits/fixturekit/PLAN.md"])
        # The cap the worker tried to raise still holds for the next run.
        plan = self.scheduler(max_parallel=2).plan()
        self.assertEqual([a["admitted"] for a in plan["admission"]], [False])

    def test_a_worker_cannot_reach_the_main_tree_or_another_copy(self):
        seen = {}

        def dispatcher(task, prompt, workspace):
            seen[task["id"]] = Path(workspace).resolve()
            (Path(workspace) / f"out-{task['id']}.txt").write_text("x\n")
            return 0, "", {"outcome": "ok"}
        dispatcher.describe = lambda task, prompt, ws: ["python-callable"]
        self.scheduler(dispatcher).run()
        for tid, ws in seen.items():
            self.assertNotEqual(ws, self.root)
            self.assertFalse(str(ws).startswith(str(self.root) + os.sep + "."), "not inside the tree")
        self.assertNotEqual(seen["T1"], seen["T2"])


class RevisionTests(_Case):
    def _propose(self, payload):
        return ('mkdir -p .polytropos; cat > .polytropos/revision.json <<EOF\n'
                + json.dumps(payload) + '\nEOF\ntouch "out-$task.txt"')

    def test_a_proposal_touching_acceptance_is_refused_whole(self):
        stub = self.stub(action=self._propose({"add_depends": {"T3": ["T1"]}, "verify": "true"}))
        summary = self.scheduler(ks.StubDispatcher(stub), max_parallel=1, accept_revisions=True).run()
        self.assertEqual(summary["results"], {"T1": "done"})
        refused = self.events("plan.revision-refused")
        self.assertEqual(len(refused), 1)
        self.assertIn("verify", refused[0]["reason"])
        self.assertIn("refused whole", refused[0]["reason"])
        self.assertEqual(self.tasks()["T3"]["depends"], ["T1", "T2"], "nothing applied")
        self.assertNotIn("revision.json", self.notes())

    def test_a_dependency_addition_is_recorded_not_applied_by_default(self):
        stub = self.stub(action=self._propose({"reason": "T2 needs T1's output",
                                               "add_depends": {"T2": ["T1"]},
                                               "new_tasks": [{"id": "T4", "title": "split out"}]}))
        summary = self.scheduler(ks.StubDispatcher(stub), max_parallel=1).run()
        self.assertEqual(summary["results"], {"T1": "done"})
        proposed = self.events("plan.revision-proposed")[0]
        self.assertEqual(proposed["add_depends"], {"T2": ["T1"]})
        self.assertEqual(proposed["new_tasks"], ["T4"])
        self.assertEqual(proposed["affected"], ["T1", "T2"])
        self.assertEqual(self.tasks()["T2"]["depends"], [], "recorded, not applied")
        self.assertEqual(self.events("plan.revised"), [])
        self.assertIn("- plan-revision: proposed", self.notes())

    def test_accept_revisions_applies_a_valid_edge_and_refuses_a_cycle(self):
        stub = self.stub(action=self._propose({"add_depends": {"T2": ["T1"]}}))
        summary = self.scheduler(ks.StubDispatcher(stub), max_parallel=1, accept_revisions=True).run()
        self.assertEqual(summary["results"], {"T1": "done"})
        self.assertEqual(self.tasks()["T2"]["depends"], ["T1"])
        self.assertEqual(self.events("plan.revised")[0]["add_depends"], {"T2": ["T1"]})
        self.assertEqual(kc.validate_graph(list(self.tasks().values())), [])
        # A second proposal that would close a cycle is refused with the finding.
        stub = self.stub(action=self._propose({"add_depends": {"T1": ["T3"]}}))
        summary = self.scheduler(ks.StubDispatcher(stub), max_parallel=1, accept_revisions=True).run()
        self.assertEqual(summary["results"], {"T2": "done"})
        refused = self.events("plan.revision-refused")
        self.assertTrue(any("invalidate the graph" in r["reason"] for r in refused))
        self.assertEqual(self.tasks()["T1"]["depends"], [])

    def test_the_proposal_channel_is_not_part_of_the_write_set(self):
        stub = self.stub(action=self._propose({"reason": "x"}))
        self.scheduler(ks.StubDispatcher(stub), max_parallel=1).run()
        self.assertFalse((self.root / ".polytropos").exists())
        self.assertIn("- write-set: 0 changed, 1 added, 0 removed", self.notes())


# ---- the manifest and its bound --------------------------------------------------------------------------

class ManifestTests(_Case):
    def test_the_manifest_carries_artifacts_and_verdicts_but_no_transcript(self):
        sched = self.scheduler()
        summary = sched.run()
        manifest = json.loads(Path(summary["manifest"]).read_text())
        self.assertEqual(manifest["v"], ks.MANIFEST_VERSION)
        self.assertEqual({t["id"]: t["verdict"] for t in manifest["tasks"]}, {"T1": "done", "T2": "done"})
        self.assertEqual(manifest["tasks"][0]["artifacts"]["added"], ["out-T1.txt"])
        self.assertNotIn("TRANSCRIPT-SENTINEL", json.dumps(manifest), "worker output never reaches the integrator")
        self.assertEqual(manifest["sizing"]["label"], "est.")
        self.assertIn("no integrator model named", manifest["sizing"]["note"])
        self.assertEqual(self.events("integration.manifest")[0]["refused"], False)

    def test_thresholds_are_read_from_each_harness_own_file_under_its_own_field(self):
        codex = json.loads((ROOT / "data" / "pricing.codex.json").read_text())["models"]
        cid = next(m for m, v in codex.items() if isinstance(v.get("long_context"), dict))
        b = ks.manifest_bound("codex", cid)
        self.assertEqual(b["threshold_tokens"], codex[cid]["long_context"]["threshold_input_tokens"])
        self.assertEqual(b["field"], "long_context.threshold_input_tokens")
        copilot = json.loads((ROOT / "data" / "pricing.copilot.json").read_text())["models"]
        pid = next(m for m, v in copilot.items() if isinstance(v.get("long_context"), dict))
        b = ks.manifest_bound("copilot", pid)
        self.assertEqual(b["threshold_tokens"], copilot[pid]["long_context"]["threshold_tokens"])
        claude = json.loads((ROOT / "data" / "pricing.json").read_text())["models"]
        mid = next(m for m, v in claude.items() if isinstance(v.get("context_window"), int))
        b = ks.manifest_bound("claude-code", mid)
        self.assertEqual(b["threshold_tokens"], claude[mid]["context_window"])
        self.assertEqual(b["field"], "context_window")
        b = ks.manifest_bound("cursor", "anything")
        self.assertIsNone(b["threshold_tokens"])
        self.assertIn("unbounded", b["note"])
        self.assertIsNone(ks.manifest_bound("codex", "no-such-model")["threshold_tokens"])
        with self.assertRaises(ks.SchedulerError):
            ks.manifest_bound("vscode", "x")

    def test_over_threshold_trims_diagnostics_with_a_note_and_far_over_refuses(self):
        entries = [{"task": {"id": f"T{i}"}, "run": "r", "workspace": "/w",
                    "write_set": {"changed": [], "added": [f"f{i}.txt"], "removed": []},
                    "result": {"status": "done", "verify_rc": 0, "verify_evidence": "x" * 500},
                    "revision": None} for i in range(3)]
        m = ks.build_manifest("b", entries, "stub")
        full = ks.estimate_tokens(json.dumps(m, sort_keys=True))
        m, s = ks.fit_manifest(ks.build_manifest("b", entries, "stub"),
                               {"threshold_tokens": full - 1, "note": "n"})
        self.assertTrue(s["trimmed"])
        self.assertFalse(s["refused"])
        self.assertIn("diagnostics dropped", s["note"])
        self.assertTrue(all(t["diagnostics"] == "" for t in m["tasks"]))
        m, s = ks.fit_manifest(ks.build_manifest("b", entries, "stub"),
                               {"threshold_tokens": 5, "note": "n"})
        self.assertTrue(s["refused"])
        self.assertIn("split the batch", s["note"])
        m, s = ks.fit_manifest(ks.build_manifest("b", entries, "stub"),
                               {"threshold_tokens": None, "note": "no threshold recorded"})
        self.assertEqual(s["note"], "no threshold recorded")
        self.assertFalse(s["trimmed"] or s["refused"])

    def test_a_refused_manifest_stops_integration_and_keeps_the_copies(self):
        with mock.patch.object(ks, "manifest_bound", return_value={"threshold_tokens": 3, "note": "tiny"}):
            sched = self.scheduler(integrator=("codex", "x"), keep_workspaces=True)
            summary = sched.run()
        self.assertEqual(summary["results"], {"T1": "blocked", "T2": "blocked"})
        self.assertFalse((self.root / "out-T1.txt").exists())
        self.assertTrue(self.events("integration.manifest")[0]["refused"])
        self.assertIn("integration refused", sched._err.getvalue())
        self.assertIn("integration-refused", self.notes())


# ---- dry run, demo, CLI ---------------------------------------------------------------------------------

class DryRunAndCliTests(_Case):
    def test_dry_run_claims_nothing_copies_nothing_spawns_nothing(self):
        sched = self.scheduler()
        with mock.patch.object(ks, "snapshot_tree", side_effect=AssertionError("copied")):
            summary = sched.run(dry_run=True)
        self.assertEqual(summary["batch"], ["T1", "T2"])
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.store.exists())
        self.assertIn("nothing claimed, copied, or spawned", sched._out.getvalue())
        self.assertIn("--task T1", sched._out.getvalue())

    def test_the_cli_runs_a_stub_batch_and_plans(self):
        stub = self.stub()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = ks.main(["run", "--kit", str(self.kit), "--harness", "stub", "--stub-bin", str(stub),
                          "--max-parallel", "2", "--attempt-store", str(self.store),
                          "--workspace", str(self.root), "--exec-mode", "trusted-host"])
        self.assertEqual(rc, 0)
        self.assertIn("T1=done, T2=done", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = ks.main(["plan", "--kit", str(self.kit), "--attempt-store", str(self.store),
                          "--workspace", str(self.root), "--max-parallel", "2", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["batch"], ["T3"])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ks.main(["run", "--kit", str(self.kit), "--harness", "stub"]), 2)

    def test_the_demo_runs_offline(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ks.main(["demo"])
        text = out.getvalue()
        self.assertIn("T1=done, T2=done", text)
        self.assertIn("T2=blocked", text)
        self.assertIn("from T1", text)
        self.assertIn("unbounded", text)

    def test_the_module_carries_no_shell_strings_and_no_bare_subprocess(self):
        source = (BIN_DIR / "kit_scheduler.py").read_text()
        for banned in ("import subprocess", "shell=True", "os.system", "Path.home("):
            self.assertNotIn(banned, source)


# ---- evidence freshness (the contract half of step 24) -------------------------------------------------------

def _git(root, *args):
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.name=t", "-c",
                    "user.email=t@example.com", *args], cwd=root, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class FreshnessTests(_Case):
    def setUp(self):
        super().setUp()
        _git(self.root, "init", "-q")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "init")
        self.by_id = self.tasks()

    def accept(self, tid, run_id):
        lifecycle = kc.TaskRun(self.ledger(), run_id, self.by_id[tid], workspace=self.root,
                               actor="test", role="implementer")
        lifecycle.begin()
        lifecycle.project("done", "pass", outcome_line=True)
        lifecycle.end()
        text = (self.kit / "TASKS.md").read_text()
        (self.kit / "TASKS.md").write_text(kc.set_status(text, tid, "done"))
        self.by_id = self.tasks()

    def test_an_acceptance_binds_upstream_versions_and_a_re_acceptance_makes_them_stale(self):
        self.accept("T1", "r1")
        self.accept("T2", "r2")
        self.accept("T3", "r3")
        ledger = self.ledger()
        acc = ledger.latest_acceptance("T3")
        self.assertEqual(set(acc["upstream"]), {"T1", "T2"})
        self.assertEqual(acc["upstream"]["T1"], ledger.latest_artifact("T1"))
        self.assertIsNotNone(acc["artifact"])
        fresh = kc.evidence_freshness(list(self.by_id.values()), ledger)
        self.assertEqual({t: f["state"] for t, f in fresh.items()}, {"T1": "fresh", "T2": "fresh", "T3": "fresh"})
        # T1 is redone on a changed tree: its artifact version moves, T3's evidence is stale.
        (self.root / "README.txt").write_text("changed by T1's rerun\n")
        self.accept("T1", "r4")
        fresh = kc.evidence_freshness(list(self.by_id.values()), self.ledger())
        self.assertEqual(fresh["T3"]["state"], "stale")
        self.assertEqual(fresh["T3"]["changed"], ["T1"])
        self.assertEqual(fresh["T1"]["state"], "fresh")
        graph = kc.graph_state(list(self.by_id.values()), freshness=fresh)
        self.assertEqual(graph["stale"], ["T3"])
        self.assertIn("stale evidence: T3 (upstream T1", kc.render_graph_state(graph))

    def test_dependents_of_a_stale_acceptance_are_not_ready_and_refresh_is_the_named_way(self):
        self.write_kit(_task_block("T1", "true"), _task_block("T2", "true", depends="T1"),
                       _task_block("T3", "true", depends="T2"))
        self.by_id = self.tasks()
        self.accept("T1", "r1")
        self.accept("T2", "r2")
        (self.root / "README.txt").write_text("changed\n")
        self.accept("T1", "r3")
        tasks = list(self.tasks().values())
        fresh = kc.kit_freshness(self.kit, tasks, store=self.store)
        r = kc.readiness(tasks, freshness=fresh)
        self.assertIsNone(r["task"])
        self.assertIn("T3 waits on T2 [done (stale)]", kc.render_graph_state(r["graph"]))
        r = kc.readiness(tasks, "T3", freshness=fresh)
        self.assertIsNone(r["task"])
        self.assertIn("whose acceptance is stale", r["reason"])
        self.assertIn("refresh --task T2", r["reason"])
        r = kc.readiness(tasks, "T2", freshness=fresh)
        self.assertEqual(r["mode"], kc.REFRESH_MODE)
        r = kc.readiness(tasks, "T2", allow_rerun=True, freshness=fresh)
        self.assertEqual(r["mode"], "rerun", "--rerun still means rerun")
        # Without freshness (a caller that did not ask), nothing changes: the old rule holds.
        self.assertEqual(kc.readiness(tasks)["task"]["id"], "T3")

    def test_refresh_re_verifies_without_dispatch_and_rebinds_or_blocks(self):
        self.write_kit(_task_block("T1", "true"), _task_block("T2", "test -f ok.txt", depends="T1"))
        self.by_id = self.tasks()
        self.accept("T1", "r1")
        self.accept("T2", "r2")
        (self.root / "README.txt").write_text("changed\n")
        self.accept("T1", "r3")
        tasks = list(self.tasks().values())
        fresh = kc.kit_freshness(self.kit, tasks, store=self.store)
        self.assertEqual(fresh["T2"]["state"], "stale")
        calls = []

        def runner(cmd):
            calls.append(cmd)
            return (0, "ok") if (self.root / "ok.txt").exists() else (1, "missing")
        # Fails: the tree no longer satisfies T2 -> blocked, nothing dispatched, zero attempts.
        result = kc.refresh_task(self.kit, self.by_id["T2"], "r5", runner, actor="refresh",
                                 store=self.store, workspace=self.root, freshness=fresh)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(calls, ["test -f ok.txt"])
        self.assertEqual(self.tasks()["T2"]["status"], "blocked")
        notes = self.notes()
        self.assertIn("- refresh: re-verified only, nothing dispatched", notes)
        self.assertRegex(notes, r"outcome: T2 model=unpinned attempts=0 result=blocked")
        self.assertEqual(self.events("evidence.refreshed")[0]["changed"], ["T1"])
        # Passes: re-bound to T1's current artifact -> fresh again.
        (self.root / "ok.txt").write_text("y\n")
        text = (self.kit / "TASKS.md").read_text()
        (self.kit / "TASKS.md").write_text(kc.set_status(text, "T2", "in-progress"))
        (self.kit / "TASKS.md").write_text(kc.set_status((self.kit / "TASKS.md").read_text(), "T2", "done"))
        self.by_id = self.tasks()
        result = kc.refresh_task(self.kit, self.by_id["T2"], "r6", runner, actor="refresh",
                                 store=self.store, workspace=self.root, freshness=fresh)
        self.assertEqual(result["status"], "done")
        fresh = kc.kit_freshness(self.kit, list(self.tasks().values()), store=self.store)
        self.assertEqual(fresh["T2"]["state"], "fresh")

    def test_a_legacy_acceptance_is_unknown_not_stale_and_status_says_nothing_alarming(self):
        ledger = self.ledger()
        ledger.record_projected("r0", "T1", "done", "pass", outcome_line=True)  # no artifact fields
        ledger.record_projected("r0", "T3", "done", "pass", outcome_line=True)
        text = (self.kit / "TASKS.md").read_text()
        for tid in ("T1", "T2", "T3"):
            text = kc.set_status(text, tid, "done")
        (self.kit / "TASKS.md").write_text(text)
        tasks = list(self.tasks().values())
        fresh = kc.kit_freshness(self.kit, tasks, store=self.store)
        self.assertEqual(fresh["T3"]["state"], "unknown")
        self.assertIn("before upstream artifact versions were recorded", fresh["T3"]["reason"])
        graph = kc.graph_state(tasks, freshness=fresh)
        self.assertEqual(graph["stale"], [])
        self.assertEqual(kc.render_graph_state(graph), "graph: complete -- every task is done")

    def test_the_contract_cli_reports_freshness_and_refreshes(self):
        self.write_kit(_task_block("T1", "true"), _task_block("T2", "true", depends="T1"))
        self.by_id = self.tasks()
        self.accept("T1", "r1")
        self.accept("T2", "r2")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = kc._cli(["freshness", "--kit", str(self.kit), "--attempt-store", str(self.store)])
        self.assertEqual(rc, 0)
        self.assertIn("evidence: T2 fresh", out.getvalue())
        (self.root / "README.txt").write_text("changed\n")
        self.accept("T1", "r3")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = kc._cli(["freshness", "--kit", str(self.kit), "--attempt-store", str(self.store)])
        self.assertEqual(rc, 1)
        self.assertIn("evidence: T2 stale", out.getvalue())
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = kc._cli(["graph", "--kit", str(self.kit), "--attempt-store", str(self.store)])
        self.assertIn("stale evidence: T2", out.getvalue())
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = kc._cli(["refresh", "--kit", str(self.kit), "--task", "T2",
                              "--attempt-store", str(self.store), "--exec-mode", "trusted-host"])
        finally:
            os.chdir(cwd)
        self.assertEqual(rc, 0)
        self.assertIn("nothing dispatched", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(kc._cli(["freshness", "--kit", str(self.kit),
                                      "--attempt-store", str(self.store)]), 0)
        # Refreshing a fresh task needs --force; an unknown task and a pending task are refused.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(kc._cli(["refresh", "--kit", str(self.kit), "--task", "T2",
                                      "--attempt-store", str(self.store)]), 2)
        self.assertIn("not stale", err.getvalue())


class DriverFreshnessTests(_Case):
    def test_a_driver_refuses_a_task_whose_upstream_acceptance_is_stale(self):
        _git(self.root, "init", "-q")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "init")
        self.write_kit(_task_block("T1", "true"), _task_block("T2", "true", depends="T1"),
                       _task_block("T3", "true", depends="T2"))
        by_id = self.tasks()

        def accept(tid, run_id):
            lc = kc.TaskRun(self.ledger(), run_id, by_id[tid], workspace=self.root, actor="t")
            lc.begin()
            lc.project("done", "pass", outcome_line=True)
            lc.end()
            text = (self.kit / "TASKS.md").read_text()
            (self.kit / "TASKS.md").write_text(kc.set_status(text, tid, "done"))
        accept("T1", "r1")
        accept("T2", "r2")
        (self.root / "README.txt").write_text("changed\n")
        accept("T1", "r3")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                ce.main(["run", "--kit", str(self.kit), "--task", "T3", "--cursor-bin",
                         str(self.root / "never"), "--attempt-store", str(self.store)])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("whose acceptance is stale", err.getvalue())
        self.assertEqual(self.tasks()["T3"]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
