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

import importlib.util
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
