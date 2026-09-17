"""Protected experiment boundary: sentinels that attempt the forbidden thing for real.

WHAT THIS FILE REFUSES TO DO. It does not assert that the right flags were passed to
`sandbox-exec`. A profile string that looks correct proves nothing about what the kernel then
did with it, and this repository has already learned that lesson once (`tests/test_exec_policy.py`
says so in its own first paragraph). Every denial below is an operation that was actually
attempted -- an `open(2)` on a withheld answer, a write and an `unlink(2)` on the controller's
rules, a `link(2)` that tries to give a denied file a second name inside the workspace, a
`connect(2)` that tries to carry it off the machine -- and the assertion is about what the
operating system returned.

HOW A REFUSAL IS ATTRIBUTED. A non-zero exit status is not evidence: a typo, a missing file and
an enforced boundary all produce one. So every denial carries two independent witnesses that
`bin/exec_policy.py` records and `certify_profile` requires:

  1. a CONTROL leg -- the identical command against an identical mirror tree with no boundary,
     which must SUCCEED. If it does not, the sentinel reports `inconclusive` and certifies
     nothing, because whatever refused it was not the boundary.
  2. a PERMISSION SIGNAL -- `EPERM`/`EACCES` from the probe, or the OS's own
     "Operation not permitted" for the legs that die inside an interpreter or inside
     `sandbox-exec` itself. `ENOENT` is explicitly NOT a denial, and a test below proves the
     machinery says so when handed one.

A SKIP CANNOT CERTIFY, structurally. The live sentinels are skipped where the host cannot apply
a profile, but `certify_profile` is asserted on EVERY host: on an unavailable one it must return
`certified: False` with every sentinel named and marked `unavailable`. There is no arrangement
of skips that produces a certification.

Synthetic throughout: synthetic answers, a synthetic private key in a synthetic home, a
loopback socket this process opens and closes. No model is dispatched, no harness CLI is
invoked, no real home directory or store is read, and nothing is installed.
"""

import ast
import importlib.util
import inspect
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "exec_policy_boundary", ROOT / "bin" / "exec_policy.py")
ep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ep)

#: This host's answer for the one implemented profile. Computed once: it spawns a probe.
STATUS = ep.protected_profile_status()
ENFORCED = STATUS.enforced

requires_enforcement = unittest.skipUnless(
    ENFORCED,
    f"protected profile {STATUS.profile!r} is unavailable here ({STATUS.reason}); the live "
    f"sentinels cannot run, and the certification test below asserts they therefore certify "
    f"nothing",
)

#: D08's target module, loaded the same way as `ep` above -- a SEPARATE module object. That
#: matters: `wf._ep()` is `bin/workflow_eval.py`'s own loaded copy of `bin/exec_policy.py`, not
#: this file's `ep`. The two copies define distinct `SandboxUnavailable`/`ProfileStatus` classes,
#: so a status or exception built from `ep` cannot cross into `wf`'s except clauses (proven
#: below). Tests that need a specific unavailable reason build the status through `wf._ep()`;
#: everything else passes a bare profile name and lets `wf` resolve its own status internally.
WF_SPEC = importlib.util.spec_from_file_location(
    "workflow_eval_boundary", ROOT / "bin" / "workflow_eval.py")
wf = importlib.util.module_from_spec(WF_SPEC)
WF_SPEC.loader.exec_module(wf)

_LIVE = {}
_DATA_HOME = None


def setUpModule():
    """Pin the store root at a temp dir for the module's lifetime.

    `bin/exec_policy.py` resolves no store and reads no home, which is why nothing below needs
    the pin today. It is here so a later edit that reaches for one cannot reach a real one.
    """
    global _DATA_HOME
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-sentinel-home-")
    os.environ["POLYTROPOS_DATA_HOME"] = _DATA_HOME.name


def tearDownModule():
    os.environ.pop("POLYTROPOS_DATA_HOME", None)
    if _DATA_HOME is not None:
        _DATA_HOME.cleanup()


def live_report():
    """The real sentinel run for this host, computed once for the whole class."""
    if "report" not in _LIVE:
        _LIVE["report"] = ep.run_sentinels(status=STATUS)
        _LIVE["certification"] = ep.certify_profile(_LIVE["report"])
    return _LIVE["report"], _LIVE["certification"]


def rows(report):
    return {row["id"]: row for row in report["sentinels"]}


def a_certifiable_report():
    """A synthetic report that certifies, so each test below can break exactly one thing.

    Built from the real sentinel plan rather than from a handful of invented ids, so a sentinel
    added to `bin/exec_policy.py` cannot quietly fall out of these mutation checks.
    """
    plan = ep.sentinels_for("sandbox-exec")
    return {
        "version": ep.SENTINEL_VERSION,
        "profile": "darwin-seatbelt",
        "status": ep.PROFILE_ENFORCED,
        "mode": "enforced",
        "backend": "sandbox-exec",
        "platform": "darwin",
        "reason": None,
        "missing": [],
        "controlled_tree_intact": True,
        "enforcement_label": ep.NOT_ISOLATION_LABEL,
        "not_proven": list(ep.SENTINEL_NOT_PROVEN),
        "sentinels": [
            {
                "id": s.id,
                "role": s.role,
                "expect": s.expect,
                "outcome": "denied" if s.expect == "deny" else "allowed",
                "confinement": "sandbox-exec",
                "control": "succeeded" if s.expect == "deny" else "not-run",
                "denial_signal": "EPERM" if s.expect == "deny" else None,
                "effect_observed": s.expect == "allow",
                "why": s.why,
                "detail": None,
            }
            for s in plan
        ],
    }


class ProtectedProfileSentinelTests(unittest.TestCase):
    maxDiff = None

    # -- the certification contract, asserted on every host ------------------------------------

    def test_this_host_certifies_only_what_its_sentinels_actually_proved(self):
        """The one test that makes a skip harmless: it runs everywhere.

        Where the profile is enforceable, the live run must certify. Where it is not, the same
        function must refuse -- with every sentinel present by name and marked `unavailable`,
        so an absent sentinel and one that could not run never look alike.
        """
        report, certification = live_report()
        self.assertEqual(report["version"], ep.SENTINEL_VERSION)
        if ENFORCED:
            self.assertTrue(certification["certified"], certification["blocking"])
            self.assertEqual(certification["satisfied"], certification["required"])
            self.assertEqual(report["backend"], "sandbox-exec")
        else:
            self.assertFalse(certification["certified"])
            self.assertTrue(certification["blocking"])
            self.assertIn(STATUS.reason, str(certification["blocking"]))
            for row in report["sentinels"]:
                self.assertEqual(row["outcome"], "unavailable", row["id"])

    def test_an_unavailable_profile_certifies_nothing_even_where_one_is_enforceable(self):
        """Asserted on EVERY host, including this one, by running the plan against a status
        that says unavailable. Without this, the refusal path would only ever be exercised on
        the hosts that cannot exercise anything."""
        unavailable = ep.protected_profile_status("container")
        report = ep.run_sentinels("container", status=unavailable)
        self.assertEqual(report["status"], ep.PROFILE_UNAVAILABLE)
        self.assertEqual(report["mode"], None)
        self.assertTrue(report["sentinels"], "an unavailable profile still names its sentinels")
        for row in report["sentinels"]:
            self.assertEqual(row["outcome"], "unavailable")
            self.assertEqual(row["control"], "not-run")
        certification = ep.certify_profile(report)
        self.assertFalse(certification["certified"])

    # -- the five acceptance sentinels, against the real operating system ---------------------

    @requires_enforcement
    def test_hidden_answers_are_unreadable_and_the_kernel_is_what_said_so(self):
        report, _certification = live_report()
        by_id = rows(report)
        for sentinel_id in ("hidden-answer-read", "hidden-oracle-test-read",
                            "hidden-directory-listing", "hidden-symlink-read",
                            "hidden-hardlink-read", "setup-escape-copy-hidden"):
            with self.subTest(sentinel=sentinel_id):
                row = by_id[sentinel_id]
                self.assertEqual(row["outcome"], "denied", row)
                # The distinction this whole task turns on: refused, not absent.
                self.assertIn(row["denial_signal"], ("EPERM", "EACCES"), row)
                self.assertNotEqual(row["denial_signal"], "ENOENT")
                self.assertEqual(row["control"], "succeeded", "unattributed refusal")
                self.assertFalse(row["effect_observed"])

    @requires_enforcement
    def test_the_controllers_code_labels_and_mode_cannot_be_touched(self):
        report, _certification = live_report()
        by_id = rows(report)
        for sentinel_id in ("controller-code-write", "controller-code-unlink",
                            "controller-manifest-write", "controller-mode-change",
                            "judge-controller-write"):
            with self.subTest(sentinel=sentinel_id):
                row = by_id[sentinel_id]
                self.assertEqual(row["outcome"], "denied", row)
                self.assertIn(row["denial_signal"], ("EPERM", "EACCES"), row)
                self.assertEqual(row["control"], "succeeded")
        # And the witness that no combination of the above changed a byte or a mode bit.
        self.assertTrue(report["controlled_tree_intact"])

    @requires_enforcement
    def test_neither_the_candidate_nor_the_judge_can_write_what_it_does_not_own(self):
        """The judge reads the answer and returns a verdict; recording acceptance is the
        controller's, and the workspace it grades is the candidate's. Separation is asserted in
        both directions, not only against the party it is most tempting to distrust."""
        report, _certification = live_report()
        by_id = rows(report)
        for sentinel_id in ("accepted-state-write-candidate", "judge-accepted-state-write",
                            "judge-candidate-write"):
            with self.subTest(sentinel=sentinel_id):
                row = by_id[sentinel_id]
                self.assertEqual(row["outcome"], "denied", row)
                self.assertIn(row["denial_signal"], ("EPERM", "EACCES"), row)
                self.assertEqual(row["control"], "succeeded")

    @requires_enforcement
    def test_a_malicious_setup_or_test_command_cannot_escape_the_boundary(self):
        """The escape that needs no change to the approved command: the test line is fixed and
        the candidate rewrites what it imports. Plus the two escapes a candidate reaches for
        when the filesystem says no -- re-exec under its own permissive profile, and the
        network."""
        report, _certification = live_report()
        by_id = rows(report)
        for sentinel_id in ("test-escape-import", "sandbox-renest-escape",
                            "network-exfiltration", "credential-read",
                            "cross-role-scratch-write"):
            with self.subTest(sentinel=sentinel_id):
                row = by_id[sentinel_id]
                self.assertEqual(row["outcome"], "denied", row)
                self.assertIn(row["denial_signal"], ep.PERMISSION_SIGNALS, row)
                self.assertEqual(row["control"], "succeeded")
                self.assertFalse(row["effect_observed"])

    @requires_enforcement
    def test_an_ordinary_build_and_an_ordinary_grading_still_succeed(self):
        """Weighted the same as the denials on purpose. A host where nothing can run at all
        would produce an identical-looking wall of refusals, and this is the row that tells the
        two apart."""
        report, _certification = live_report()
        by_id = rows(report)
        for sentinel_id in ("allowed-build", "allowed-judge-grade"):
            with self.subTest(sentinel=sentinel_id):
                row = by_id[sentinel_id]
                self.assertEqual(row["outcome"], "allowed", row)
                self.assertEqual(row["rc"], 0)
                self.assertTrue(row["effect_observed"])
                self.assertEqual(row["confinement"], "sandbox-exec")

    @requires_enforcement
    def test_every_protected_leg_ran_under_the_backend_and_never_trusted_host(self):
        report, _certification = live_report()
        for row in report["sentinels"]:
            with self.subTest(sentinel=row["id"]):
                self.assertEqual(row["confinement"], "sandbox-exec")
                self.assertNotEqual(row["confinement"], "trusted-host")
                # The control leg is the one thing that runs unconfined, and it says so.
                if row["control"] != "not-run":
                    self.assertEqual(row["control_confinement"], "trusted-host")

    @requires_enforcement
    def test_a_failure_that_is_not_a_refusal_is_not_counted_as_a_denial(self):
        """The mutation that matters most, run against the live OS.

        A sentinel pointed at a path that is simply not there fails exactly as loudly as one the
        kernel refused. Machinery that could not tell them apart would certify a profile from a
        typo. Here the same code path is handed an absent file: the control leg also fails, the
        signal is `ENOENT`, and the verdict is `inconclusive`, not `denied`.
        """
        fabricated = ep._Sentinel(
            "fabricated-missing-path", "candidate", "deny", "probe", (),
            ep._PROBE + ("read", "{hidden}/there-is-no-such-file.txt"), None,
            "a sentinel aimed at nothing at all")
        root = tempfile.mkdtemp(prefix="polytropos-sentinel-selftest-")
        try:
            layout = ep._write_fixture_tree(root)
            profile = ep.ProtectedProfile(layout, status=STATUS)
            record = ep._run_one_sentinel(
                fabricated, profile, layout, sys.executable or "python3", 1, 60)
        finally:
            ep._rmtree(root)
        self.assertEqual(record["outcome"], "inconclusive", record)
        self.assertEqual(record["denial_signal"], "ENOENT")
        self.assertEqual(record["control"], "failed")
        self.assertFalse(ep.certify_profile(
            {"status": ep.PROFILE_ENFORCED, "backend": "sandbox-exec",
             "controlled_tree_intact": True, "sentinels": [record]})["certified"])

    # -- an unsupported host or profile is TYPED, never a downgrade ---------------------------

    def test_an_unknown_profile_name_is_typed_unavailable(self):
        status = ep.protected_profile_status("no-such-profile")
        self.assertEqual(status.status, ep.PROFILE_UNAVAILABLE)
        self.assertEqual(status.reason, "unknown-profile")
        self.assertIsNone(status.mode)
        self.assertTrue(any("darwin-seatbelt" in item for item in status.missing))

    def test_a_declared_but_unimplemented_profile_is_unavailable_on_every_host(self):
        """Two profiles this repo can describe and cannot enforce. They report `unavailable`
        with their prerequisites named -- which is also the honest answer to "could a stronger
        boundary be used here": yes, after an installation nothing in this kit authorizes."""
        for name in ("container", "linux-bubblewrap"):
            with self.subTest(profile=name):
                status = ep.protected_profile_status(name, platform="linux")
                self.assertEqual(status.status, ep.PROFILE_UNAVAILABLE)
                self.assertEqual(status.reason, "not-implemented")
                self.assertTrue(status.missing)
                self.assertTrue(any("install" in item for item in status.missing), status.missing)

    def test_a_host_with_no_backend_is_unavailable_rather_than_unconfined(self):
        for platform in ("linux", "win32", "freebsd14"):
            with self.subTest(platform=platform):
                status = ep.protected_profile_status("darwin-seatbelt", platform=platform)
                self.assertEqual(status.status, ep.PROFILE_UNAVAILABLE)
                self.assertEqual(status.reason, "platform-mismatch")
        no_backend = ep.protected_profile_status(
            "darwin-seatbelt", platform="darwin", backend=None)
        self.assertEqual(no_backend.reason, "no-confinement-backend")

    def test_a_backend_that_cannot_be_applied_is_unavailable_not_merely_present(self):
        """Detecting a backend and being able to USE it are different questions: Seatbelt does
        not nest, so a controller already inside a profile has the binary and no boundary."""
        status = ep.protected_profile_status(
            "darwin-seatbelt", platform="darwin", backend="sandbox-exec", usable=False)
        self.assertEqual(status.status, ep.PROFILE_UNAVAILABLE)
        self.assertEqual(status.reason, "backend-unusable")
        self.assertIsNone(status.mode)

    def test_an_unavailable_profile_never_selects_trusted_host(self):
        status = ep.protected_profile_status("container")
        self.assertIsNone(status.mode)
        self.assertNotIn("trusted-host", str(status.as_dict()))
        with self.assertRaises(ep.SandboxUnavailable) as caught:
            status.require_enforced()
        message = str(caught.exception)
        self.assertIn("NO trusted-host fallback", message)
        self.assertIn("container", message)

    def test_the_protected_runner_cannot_be_asked_for_an_unconfined_run(self):
        """Not a default, not a convention: there is no parameter to pass.

        `run_confined` keeps its `mode` because verification legitimately has a named opt-out.
        A protected experiment does not, so the way through is removed rather than defended.
        """
        for method in (ep.ProtectedProfile.run, ep.ProtectedProfile.run_shell):
            with self.subTest(method=method.__name__):
                self.assertNotIn("mode", inspect.signature(method).parameters)

    def test_running_under_an_unavailable_profile_raises_instead_of_degrading(self):
        root = tempfile.mkdtemp(prefix="polytropos-sentinel-refusal-")
        try:
            layout = ep._write_fixture_tree(root)
            unavailable = ep.protected_profile_status("container")
            profile = ep.ProtectedProfile(layout, profile="container", status=unavailable)
            with self.assertRaises(ep.SandboxUnavailable):
                profile.run("candidate", ["/bin/echo", "hi"])
            marker = Path(root) / "candidate" / "ran.txt"
            self.assertFalse(marker.exists())
        finally:
            ep._rmtree(root)

    # -- certification algebra: what cannot pass ----------------------------------------------

    def test_the_synthetic_baseline_report_certifies_so_each_mutation_means_something(self):
        self.assertTrue(ep.certify_profile(a_certifiable_report())["certified"])

    def test_a_skipped_or_unavailable_sentinel_cannot_certify_a_profile(self):
        for outcome in ("unavailable", "skipped", "error", "inconclusive"):
            with self.subTest(outcome=outcome):
                report = a_certifiable_report()
                report["sentinels"][0]["outcome"] = outcome
                verdict = ep.certify_profile(report)
                self.assertFalse(verdict["certified"])
                self.assertIn(report["sentinels"][0]["id"],
                              [item["id"] for item in verdict["blocking"]])

    def test_a_sentinel_that_is_simply_absent_cannot_certify_a_profile(self):
        report = a_certifiable_report()
        dropped = report["sentinels"].pop(0)
        verdict = ep.certify_profile(report)
        self.assertFalse(verdict["certified"])
        self.assertIn("did not appear", str(verdict["blocking"]))
        self.assertIn(dropped["id"], [item["id"] for item in verdict["blocking"]])

    def test_a_leak_cannot_certify_a_profile(self):
        report = a_certifiable_report()
        report["sentinels"][0]["outcome"] = "leaked"
        self.assertFalse(ep.certify_profile(report)["certified"])

    def test_a_denial_without_a_successful_control_leg_certifies_nothing(self):
        report = a_certifiable_report()
        denial = next(row for row in report["sentinels"] if row["expect"] == "deny")
        denial["control"] = "failed"
        verdict = ep.certify_profile(report)
        self.assertFalse(verdict["certified"])
        self.assertIn("unattributed", str(verdict["blocking"]))

    def test_a_missing_file_dressed_as_a_denial_certifies_nothing(self):
        report = a_certifiable_report()
        denial = next(row for row in report["sentinels"] if row["expect"] == "deny")
        denial["denial_signal"] = "ENOENT"
        verdict = ep.certify_profile(report)
        self.assertFalse(verdict["certified"])
        self.assertIn("not the OS refusing it", str(verdict["blocking"]))

    def test_a_trusted_host_leg_can_never_be_counted_as_enforcement(self):
        report = a_certifiable_report()
        report["sentinels"][0]["confinement"] = "trusted-host"
        verdict = ep.certify_profile(report)
        self.assertFalse(verdict["certified"])
        self.assertIn("trusted-host", str(verdict["blocking"]))

    def test_a_mutated_controller_tree_certifies_nothing_however_the_rows_read(self):
        report = a_certifiable_report()
        report["controlled_tree_intact"] = False
        verdict = ep.certify_profile(report)
        self.assertFalse(verdict["certified"])
        self.assertIn("byte-identical", str(verdict["blocking"]))

    def test_an_unenforced_status_cannot_certify_however_good_the_rows_look(self):
        report = a_certifiable_report()
        report["status"] = ep.PROFILE_UNAVAILABLE
        report["reason"] = "backend-unusable"
        self.assertFalse(ep.certify_profile(report)["certified"])

    def test_every_acceptance_question_must_be_answered_by_a_sentinel_that_ran(self):
        for question, ids in ep.SENTINEL_ACCEPTANCE.items():
            with self.subTest(question=question):
                report = a_certifiable_report()
                report["sentinels"] = [row for row in report["sentinels"]
                                       if row["id"] not in ids]
                verdict = ep.certify_profile(report)
                self.assertFalse(verdict["certified"])

    def test_the_acceptance_map_and_the_plan_do_not_drift_apart(self):
        """Structural, so a sentinel cannot be added without an acceptance question, or an
        acceptance question left pointing at an id that no longer exists."""
        known = {s.id for s in ep.SENTINELS}
        self.assertEqual(len(known), len(ep.SENTINELS), "duplicate sentinel id")
        mapped = {sentinel_id for ids in ep.SENTINEL_ACCEPTANCE.values() for sentinel_id in ids}
        self.assertEqual(mapped - known, set(), "acceptance names a sentinel that does not exist")
        self.assertEqual(known - mapped, set(), "a sentinel answers no acceptance question")
        for expected in ("hidden-read-denied", "controller-write-denied", "judge-write-denied",
                         "test-escape-denied", "allowed-fixture-works"):
            self.assertIn(expected, ep.SENTINEL_ACCEPTANCE)

    def test_a_backend_specific_sentinel_is_dropped_from_the_plan_and_from_what_is_required(self):
        """Not silently: an escape that only applies to one backend must not sit in another
        backend's plan reporting `unavailable` forever, and must not be required of it."""
        plan = {s.id for s in ep.sentinels_for("sandbox-exec")}
        other = {s.id for s in ep.sentinels_for("bubblewrap")}
        self.assertIn("sandbox-renest-escape", plan)
        self.assertNotIn("sandbox-renest-escape", other)

    # -- the layout: a worktree is not isolation ----------------------------------------------

    def test_a_single_tree_holding_everything_is_refused_however_many_directories_it_has(self):
        """The refusal that makes "a worktree is not isolation" machine-checked.

        A candidate workspace that CONTAINS the controller's rules, the withheld answers or the
        accepted state is not a protected layout: the workspace is writable by construction, so
        everything inside it is too.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for relative in ep.ProtectedLayout.REQUIRED_DIRS + ("home",):
                (root / relative).mkdir(parents=True, exist_ok=True)
            nested = root / "candidate" / "controller"
            nested.mkdir(parents=True)
            with self.assertRaises(ep.ProtectedLayoutError) as caught:
                ep.ProtectedLayout(root, home=root / "home", controller=nested)
            self.assertIn("worktree, not isolation", str(caught.exception))

    def test_a_root_that_is_a_symlink_into_another_root_is_refused(self):
        """Realpath, not the string. Two names for one directory are one directory."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for relative in ep.ProtectedLayout.REQUIRED_DIRS + ("home",):
                (root / relative).mkdir(parents=True, exist_ok=True)
            (root / "hidden").rmdir()
            (root / "hidden").symlink_to(root / "candidate", target_is_directory=True)
            with self.assertRaises(ep.ProtectedLayoutError):
                ep.ProtectedLayout(root, home=root / "home")

    def test_a_layout_missing_a_root_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for relative in ep.ProtectedLayout.REQUIRED_DIRS:
                (root / relative).mkdir(parents=True, exist_ok=True)
            (root / "scratch" / "judge").rmdir()
            with self.assertRaises(ep.ProtectedLayoutError) as caught:
                ep.ProtectedLayout(root, home=root)
            self.assertIn("scratch/judge", str(caught.exception))

    def test_the_controller_gets_no_policy_because_it_applies_the_boundary(self):
        root = tempfile.mkdtemp(prefix="polytropos-sentinel-roles-")
        try:
            layout = ep._write_fixture_tree(root)
            with self.assertRaises(ep.ProtectedLayoutError) as caught:
                layout.policy_for("controller")
            self.assertIn("APPLIES this boundary", str(caught.exception))
            with self.assertRaises(ep.ProtectedLayoutError):
                layout.policy_for("proposer")
        finally:
            ep._rmtree(root)

    def test_each_role_gets_its_own_scratch_so_one_cannot_plant_files_in_anothers_tmpdir(self):
        root = tempfile.mkdtemp(prefix="polytropos-sentinel-scratch-")
        try:
            layout = ep._write_fixture_tree(root)
            scratches = {role: layout.policy_for(role).scratch for role in ep.PROTECTED_ROLES}
            self.assertEqual(len(set(scratches.values())), len(ep.PROTECTED_ROLES), scratches)
            for role, scratch in scratches.items():
                self.assertEqual(layout.policy_for(role).environment()["TMPDIR"], scratch)
        finally:
            ep._rmtree(root)

    def test_the_judge_may_read_the_answers_the_candidate_may_not(self):
        """Separation, not uniform restriction: grading without the reference is not grading.
        What the judge does not get is the accepted state, and the sentinel above proves the
        kernel agrees."""
        root = tempfile.mkdtemp(prefix="polytropos-sentinel-roles2-")
        try:
            layout = ep._write_fixture_tree(root)
            candidate = layout.policy_for("candidate")
            judge = layout.policy_for("judge")
            self.assertIn(layout.hidden, candidate.deny_read)
            self.assertNotIn(layout.hidden, judge.deny_read)
            self.assertEqual(candidate.workspace, layout.candidate)
            self.assertEqual(judge.workspace, layout.judge)
            self.assertNotEqual(judge.workspace, candidate.workspace)
            for policy in (candidate, judge):
                self.assertFalse(policy.allow_network)
                self.assertNotIn(layout.accepted, (policy.workspace, policy.scratch))
                self.assertNotIn(layout.controller, (policy.workspace, policy.scratch))
        finally:
            ep._rmtree(root)

    def test_a_synthetic_home_is_what_the_sentinels_declare_confidential(self):
        """The credential sentinel reads a synthetic key in a synthetic home. Nothing here may
        name -- let alone open -- the user's real `~/.claude`, `~/.codex` or `~/.ssh`."""
        root = tempfile.mkdtemp(prefix="polytropos-sentinel-home2-")
        try:
            layout = ep._write_fixture_tree(root)
            self.assertTrue(layout.home.startswith(os.path.realpath(root)))
            self.assertTrue(layout.deny_read, "the synthetic home declared nothing confidential")
            for denied in layout.deny_read:
                self.assertTrue(denied.startswith(layout.home), denied)
                self.assertFalse(denied.startswith(os.path.realpath(Path.home())), denied)
        finally:
            ep._rmtree(root)

    # -- what the report says about itself -----------------------------------------------------

    def test_the_report_carries_its_version_and_states_what_it_does_not_prove(self):
        report, certification = live_report()
        self.assertEqual(report["version"], ep.SENTINEL_VERSION)
        self.assertEqual(ep.SENTINEL_VERSION, "polytropos.sentinels/1")
        self.assertIn("hash", report["enforcement_label"])
        self.assertIn("worktree", report["enforcement_label"].lower())
        self.assertTrue(report["not_proven"])
        joined = " ".join(report["not_proven"])
        # The three limits a reader is most likely to over-read the certification past.
        self.assertIn("metadata", joined.lower())
        self.assertIn("mach-lookup", joined)
        self.assertIn("model dispatch", joined)
        self.assertEqual(certification["not_proven"], report["not_proven"])

    def test_the_ledger_envelope_version_is_not_what_this_report_stamps(self):
        """D04's trap, restated: version the referenced object, never the envelope."""
        self.assertTrue(ep.SENTINEL_VERSION.startswith("polytropos.sentinels/"))
        self.assertNotIn("attempts", ep.SENTINEL_VERSION)

    def test_the_existing_verification_boundary_still_names_trusted_host_as_its_opt_out(self):
        """The protected profile removes the opt-out for ITSELF and changes nothing about
        verification, where a named, self-reporting opt-out is the sanctioned behaviour."""
        with tempfile.TemporaryDirectory() as td:
            policy = ep.ExecPolicy(td, name="verify")
            result = ep.run_confined(["/bin/echo", "hi"], policy, mode="trusted-host")
            self.assertEqual(result["confinement"], "trusted-host")
            with self.assertRaises(ep.SandboxUnavailable) as caught:
                ep.run_confined(["/bin/echo", "hi"], policy, mode="enforced", backend=None)
            self.assertIn("trusted-host", str(caught.exception))


class _RaisingRunner:
    """A runner that RAISES if ever invoked -- a canned return value is too weak a witness that
    a provider runner was never reached; this makes the failure loud and unmistakable."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, cwd):
        self.calls.append((argv, cwd))
        raise AssertionError(f"provider runner reached: argv={argv!r} cwd={cwd!r}")


class UnavailableProfileTests(unittest.TestCase):
    """decision-improvement D08: `bin/workflow_eval.py`'s protected-trial/autopromotion gate.

    D07 built an available boundary that nothing calls yet. This proves the ONE chokepoint a
    future protected live trial (D18) or autopromotion (D23) must pass through first: an
    unavailable profile refuses BEFORE any provider runner is reached, never falls back to
    trusted-host, carries its evidence into the run envelope's own fields, and never claims a
    certification this per-dispatch check did not itself run -- while offline synthetic analysis
    and manual proposal drafting keep working, at zero cost, whether or not D07 is available.
    """

    maxDiff = None

    # -- runtime proof: the gate raises BEFORE any runner is reached ---------------------------

    def test_a_protected_live_trial_is_refused_before_any_runner_is_reached(self):
        runner = _RaisingRunner()
        with self.assertRaises(wf._ep().SandboxUnavailable):
            wf.run_protected_dispatch(wf.PROTECTED_LIVE_TRIAL, runner, ["/bin/echo", "hi"], ".",
                                      profile="container")
        self.assertEqual(runner.calls, [])

    def test_autopromotion_is_refused_before_any_runner_is_reached(self):
        runner = _RaisingRunner()
        with self.assertRaises(wf._ep().SandboxUnavailable):
            wf.run_protected_dispatch(wf.AUTOPROMOTION, runner, ["/bin/echo", "hi"], ".",
                                      profile="container")
        self.assertEqual(runner.calls, [])

    def test_no_runner_is_reached_for_any_missing_enforcement_requirement(self):
        """Drives several distinct D07 refusal reasons -- not-implemented, unknown-profile,
        platform-mismatch -- through the SAME gate, each with its own loud runner."""
        wf_ep = wf._ep()
        cases = {
            "not-implemented": ("container", None),
            "unknown-profile": ("no-such-profile", None),
            "platform-mismatch": (
                "darwin-seatbelt",
                wf_ep.protected_profile_status("darwin-seatbelt", platform="linux"),
            ),
        }
        for reason, (profile, status) in cases.items():
            with self.subTest(reason=reason):
                runner = _RaisingRunner()
                with self.assertRaises(wf_ep.SandboxUnavailable):
                    wf.run_protected_dispatch(wf.PROTECTED_LIVE_TRIAL, runner,
                                              ["/bin/echo", "hi"], ".",
                                              profile=profile, status=status)
                self.assertEqual(runner.calls, [])

    # -- no trusted-host fallback, ever ---------------------------------------------------------

    def test_the_refusal_message_reuses_d07s_own_no_fallback_wording(self):
        with self.assertRaises(wf._ep().SandboxUnavailable) as caught:
            wf.require_protected_trial(wf.PROTECTED_LIVE_TRIAL, profile="container")
        message = str(caught.exception)
        self.assertTrue(message.startswith(f"{wf.PROTECTED_LIVE_TRIAL} refused -- "), message)
        self.assertIn("NO trusted-host fallback", message)
        self.assertIn("container", message)

    def test_autopromotion_refusal_names_itself_not_the_trial(self):
        with self.assertRaises(wf._ep().SandboxUnavailable) as caught:
            wf.require_protected_trial(wf.AUTOPROMOTION, profile="container")
        message = str(caught.exception)
        self.assertTrue(message.startswith(f"{wf.AUTOPROMOTION} refused -- "), message)
        self.assertNotIn(f"{wf.PROTECTED_LIVE_TRIAL} refused", message)

    def test_the_gate_functions_have_no_mode_parameter_to_offer_a_way_around_it(self):
        for func in (wf.require_protected_trial, wf.run_protected_dispatch,
                    wf.protected_trial_evidence):
            with self.subTest(func=func.__name__):
                self.assertNotIn("mode", inspect.signature(func).parameters)

    # -- refusal evidence is typed and carried into the EXISTING result owner ------------------

    def test_the_raised_refusal_carries_typed_evidence_for_the_caller_to_record(self):
        wf_ep = wf._ep()
        with self.assertRaises(wf_ep.SandboxUnavailable) as caught:
            wf.require_protected_trial(wf.AUTOPROMOTION, profile="container")
        evidence = caught.exception.evidence
        self.assertEqual(evidence["profile"], "container")
        self.assertEqual(evidence["status"], wf_ep.PROFILE_UNAVAILABLE)
        self.assertIsNone(evidence["mode"])
        self.assertEqual(evidence["reason"], "not-implemented")
        self.assertEqual(evidence["sentinel_outcomes"], ["unavailable"])
        self.assertFalse(evidence["certified"])
        self.assertEqual(evidence["sentinel_count"], len(wf_ep.sentinels_for("container")))

    def test_carry_protected_evidence_writes_only_into_the_envelopes_existing_labels_and_notes(self):
        evidence = wf.protected_trial_evidence("container")
        envelope = {"labels": ["existing label"], "notes": ["existing note"], "run_id": "r1"}
        returned = wf.carry_protected_evidence(envelope, evidence, wf.PROTECTED_LIVE_TRIAL)
        self.assertIs(returned, envelope)
        self.assertEqual(envelope["labels"][0], "existing label")
        self.assertEqual(len(envelope["labels"]), 2)
        self.assertIn("unavailable", envelope["labels"][1])
        self.assertEqual(len(envelope["notes"]), 2)
        # No second store, no new top-level key -- the same fields every other run-level caveat
        # (cost-ceiling, overspend, aborted) already lands in.
        self.assertEqual(set(envelope), {"labels", "notes", "run_id"})

    def test_run_protected_dispatch_carries_refusal_evidence_into_the_given_envelope(self):
        envelope = {"labels": [], "notes": []}
        runner = _RaisingRunner()
        with self.assertRaises(wf._ep().SandboxUnavailable):
            wf.run_protected_dispatch(wf.AUTOPROMOTION, runner, ["/bin/echo", "hi"], ".",
                                      profile="container", envelope=envelope)
        self.assertEqual(runner.calls, [])
        self.assertEqual(len(envelope["labels"]), 1)
        self.assertIn("unavailable", envelope["labels"][0])
        self.assertEqual(len(envelope["notes"]), 1)
        self.assertEqual(set(envelope), {"labels", "notes"})

    # -- no live-ready claim ---------------------------------------------------------------------

    def test_an_unavailable_gate_never_reads_as_live_ready(self):
        evidence = wf.protected_trial_evidence("container")
        for value in evidence.values():
            self.assertNotIn("live-ready", str(value).lower())
            self.assertNotIn("live ready", str(value).lower())
        self.assertNotIn("live_ready", evidence)

    def test_the_gate_never_self_certifies_on_the_enforced_path_either(self):
        """Even where this host enforces, a per-dispatch check does not itself run the sentinel
        battery or claim certification -- that claim is D07's own (`certify_profile`), earned
        once per host/profile, never manufactured here on every trial."""
        evidence = wf.protected_trial_evidence(status=STATUS)
        if ENFORCED:
            self.assertIsNone(evidence["certified"])
            self.assertIsNone(evidence["sentinel_outcomes"])
            self.assertEqual(evidence["mode"], "enforced")
        else:
            self.assertIsNone(evidence["mode"])

    # -- offline synthetic analysis and manual drafting are unaffected, and cost nothing --------

    def test_offline_demo_dispatches_nothing_and_is_unaffected_by_an_unavailable_profile(self):
        """`_demo()` is workflow_eval's OWN offline synthetic-analysis path: a stub adapter, no
        real CLI, and it already calls `build_proposal` internally. It must keep working exactly
        as it always has whether or not D07's profile is available, because it never asks."""
        self.assertFalse(wf._ep().protected_profile_status("container").enforced)
        out = io.StringIO()
        with mock.patch.object(wf, "default_runner",
                               side_effect=AssertionError("a real dispatch path was reached")):
            code = wf._demo(out=out)
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("nothing dispatched a model", text)
        self.assertIn("propose refused", text)  # build_proposal ran, unaffected by the profile

    # -- structural proof: the dispatch call site is downstream of the gate --------------------

    def test_the_gate_call_precedes_the_runner_call_in_run_protected_dispatch(self):
        source = (ROOT / "bin" / "workflow_eval.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "run_protected_dispatch")
        gate_call = next(n for n in ast.walk(fn) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Name)
                         and n.func.id == "require_protected_trial")
        runner_call = next(n for n in ast.walk(fn) if isinstance(n, ast.Call)
                           and isinstance(n.func, ast.Name) and n.func.id == "runner")
        self.assertLess(gate_call.lineno, runner_call.lineno,
                        "the gate must run before the dispatch it guards")

    def test_no_bare_runner_call_exists_outside_the_gated_chokepoint(self):
        """Structural: the ONLY place in `bin/workflow_eval.py` that calls a bare `runner(...)`
        (as opposed to `self.runner(...)`, `git_runner(...)`, `test_runner(...)` or
        `verify_runner(...)`) is `run_protected_dispatch`. A future edit that adds a second
        protected dispatch path bypassing the gate would add a second such call site, and this
        fails the moment it does."""
        source = (ROOT / "bin" / "workflow_eval.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        class _Finder(ast.NodeVisitor):
            def __init__(self):
                self.stack = []
                self.hits = []

            def visit_FunctionDef(self, node):  # noqa: N802 -- ast.NodeVisitor's own naming
                self.stack.append(node.name)
                self.generic_visit(node)
                self.stack.pop()

            def visit_Call(self, node):  # noqa: N802
                if isinstance(node.func, ast.Name) and node.func.id == "runner":
                    self.hits.append((self.stack[-1] if self.stack else None, node.lineno))
                self.generic_visit(node)

        finder = _Finder()
        finder.visit(tree)
        self.assertTrue(finder.hits, "expected at least one bare runner(...) call site")
        for fn_name, lineno in finder.hits:
            self.assertEqual(fn_name, "run_protected_dispatch",
                            f"a bare runner(...) call at line {lineno} bypasses the gate "
                            f"(found inside {fn_name!r})")

    def test_manual_proposal_functions_never_reference_the_protected_profile_gate(self):
        """Structural counterpart to the demo runtime proof: the manual report/proposal
        workbench does not merely happen to skip the gate today, it never names it."""
        source = (ROOT / "bin" / "workflow_eval.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"require_protected_trial", "run_protected_dispatch",
                    "protected_trial_evidence", "carry_protected_evidence", "_ep"}
        for name in ("build_proposal", "review_proposal", "apply_proposal", "rollback_policy"):
            with self.subTest(function=name):
                fn = next(n for n in ast.walk(tree)
                         if isinstance(n, ast.FunctionDef) and n.name == name)
                called = {n.func.id for n in ast.walk(fn)
                         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
                overlap = called & forbidden
                self.assertFalse(overlap, f"{name} references the protected gate: {overlap}")

    # -- the gate is independent of Evaluation, not a method on it ------------------------------

    def test_the_gate_functions_are_plain_module_functions_not_evaluation_methods(self):
        for name in ("require_protected_trial", "protected_trial_evidence",
                    "run_protected_dispatch", "carry_protected_evidence"):
            with self.subTest(name=name):
                func = getattr(wf, name)
                self.assertNotIn("self", inspect.signature(func).parameters)
                self.assertFalse(hasattr(wf.Evaluation, name),
                                f"{name} must not be an Evaluation method")


if __name__ == "__main__":
    unittest.main()
