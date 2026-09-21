"""D28 -- the Jev-free release matrix: what each harness may run, and what is absent.

`JevFreeMatrixTests` covers the decision section of `bin/release_gate.py`, the
`adaptive_decisions` rows this task added to `primitives/harness-capabilities.json`, and the
generated block of `docs/RELEASE.md` that renders both.

WHAT IS ACTUALLY UNDER TEST, in the order the acceptance asks it:

  * JEV-FREE, PROVED BY RUNNING RATHER THAN BY READING. `release_gate.jev_free_report` walks the
    decision surface by AST and says what it imports; that is a statement about source shape and
    this file does not stop there. Every network module is REFUSED at `sys.meta_path` and scrubbed
    from `sys.modules`, and under that refusal the whole decision surface is imported fresh, a
    request is answered through `rules` and through `replay`, and a rollback is taken and read
    back. The guard's own positive control runs in the same block: `import socket` inside it
    raises, so the imports that succeed mean something.
  * UNSUPPORTED IS EXPLICIT, AND DERIVED. `canary` and `active` are unavailable on every harness
    because `workflow_eval.CONFINED_DISPATCH_WIRED` is False; the matrix cell is computed from
    that constant and from `decision_policy.DEFERRED_MODES`, which is shown by flipping the
    constant and watching the cell move. A cell that survived the flip would be a typed cell.
  * TWO CLAIMS ABOUT CURSOR, KEPT APART. Its adaptive profile is `unsupported` pending
    independent proof AND its current CLI implementation is present, verified and dated. Both are
    asserted here, because reporting the second as absent would be a second, different untruth.
  * NO CREDENTIAL, NO PERFORMANCE CLAIM. The decision surface reads no environment variable at
    all; the rendered section carries no URL, no key shape and no measurement; and the row shape
    is closed, so a later edit cannot add a `speedup` column to a table whose point is that it
    makes no such claim.
  * THE OPTIONAL FALLBACK PASSES. No pointer is legacy, a rolled-back pointer is legacy, and
    `decision_policy.resolve_bundle` terminates at legacy with nothing to contact.
  * LIVE GATES LINKED. Every gate a running state would have to pass names an owner, a blocker
    code its owner actually declares, and a test id that resolves to real cases.

WHAT A PASSING RUN HERE DOES NOT ESTABLISH. It says nothing about any host's isolation, any
vendor client, or whether any decision mechanism helps. No capability row moves because of it:
`unknown` in the registry still means no, and the `adaptive_decisions` rows this task added start
`unknown` and stay there until somebody runs the thing.

SAFETY CONTRACT. Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify`
binary, reads a real harness home, spends anything, or touches a real store. Every prefs
directory, replay store and doctored repository root is a `tempfile.TemporaryDirectory`;
`POLYTROPOS_DATA_HOME` is redirected for this module's run so even a mistake lands in a
throwaway; and the import guard restores `sys.meta_path` and every module it scrubbed.
"""

import contextlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_decision_policy_bundle as tpb

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"

_COUNTER = [0]


def _load(name, alias=None):
    """One module, loaded by path. `bin/` is not a package, so two loaders of one file produce
    two incompatible sets of classes -- every fixture below is therefore built with the SAME
    instance the code under test reads."""
    _COUNTER[0] += 1
    spec = importlib.util.spec_from_file_location(
        alias or f"{name}_d28_{_COUNTER[0]}", BIN_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rg = _load("release_gate")

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    # Patched for THIS module's run only: discovery imports every test module before any runs,
    # so an import-time environment write would leak into every other module.
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


@contextlib.contextmanager
def refusing_imports(names):
    """Refuse every import of `names` for the duration -> the list of attempts that were refused.

    A `sys.meta_path` finder alone is not enough: an already-imported module is served from
    `sys.modules` before any finder is consulted, so the names are SCRUBBED first and restored
    byte-for-byte -- the same objects, not re-imported copies -- in `finally`.
    """
    names = frozenset(names)
    blocked = []

    class _Refuser:
        @staticmethod
        def find_spec(fullname, path=None, target=None):
            if fullname.split(".")[0] in names:
                blocked.append(fullname)
                raise ImportError(f"refused by the D28 guard: {fullname}")
            return None

    saved = {key: mod for key, mod in list(sys.modules.items())
             if key.split(".")[0] in names}
    for key in saved:
        del sys.modules[key]
    sys.meta_path.insert(0, _Refuser)
    try:
        yield blocked
    finally:
        sys.meta_path.remove(_Refuser)
        for key in [k for k in sys.modules if k.split(".")[0] in names]:
            del sys.modules[key]
        sys.modules.update(saved)


def request_payload(dc, al, kc, **over):
    """A well-formed `DecisionRequest` payload, parsed by the caller's OWN contract instance."""
    question = {
        "id": "q-context-missing", "version": "v1", "kind": "boolean",
        "question": "Did the failing attempt lack the interface contract it called across?",
        "rubric": {}, "outcomes": ["false", "true"], "abstention": "permitted",
        "dependencies": [], "sensitivity": "project-internal",
    }
    state = {"head": "0123abcd", "verify_rc": 1, "worktree_dirty": False}
    specs = [dc.parse_question(question, "q[0]")]
    payload = {
        "v": dc.CONTRACT_VERSION,
        "correlation_id": "corr-d28",
        "run": "2026-09-20-d28a",
        "task": "D28",
        "attempt": None,
        "intended_use": "recovery-selection",
        "task_ref": al.make_ref("D28", version=kc.CONTRACT_VERSION),
        "acceptance_ref": al.make_ref("acc-d28", sha="a" * 64, version=kc.CONTRACT_VERSION),
        "state": state,
        "state_sha": dc.state_digest(state),
        "alternatives": ["retry-same-model", "stop"],
        "questions": [question],
        "questions_sha": dc.questions_digest(specs),
        "eligibility": {"project": "polytropos", "providers": ["rules", "replay"],
                        "privacy": "project-local"},
        "deadline_s": 30,
        "resource_policy": {"operation_scope": "consult", "call_ceiling": 1, "repair_ceiling": 0},
        "admission_ref": al.make_ref("grant-d28", version=kc.CONTRACT_VERSION),
    }
    payload.update(over)
    return payload


def result_payload(dc, req, **over):
    """An already-valid `DecisionResult` -- the shape a provider would have returned -- for the
    replay store to hold."""
    answers = {spec.qualified_id: {"outcome": "true", "abstained": False, "raw": None,
                                   "calibrated": None, "vendor_confidence": None}
               for spec in req.questions}
    payload = {
        "v": dc.CONTRACT_VERSION, "correlation_id": req.correlation_id,
        "state_sha": req.state_sha, "questions_sha": req.questions_sha,
        "status": "ok", "answers": answers, "recommended": "stop", "evidence_refs": [],
        "requested_provider": "rules", "dispatched_provider": "rules",
        "observed_provider": None, "requested_model": None, "dispatched_model": None,
        "observed_model": None, "provider_contract_v": None,
        "duration": {"basis": "decision-latency", "seconds": 0.01, "source": "rules"},
        "usage": None, "note": None,
    }
    payload.update(over)
    return dc.parse_result(payload, req)


def doctored_root(tmp, sources):
    """A repository root carrying only `bin/<name>.py` for every module the scan reads, so that
    the scan's verdict is about the sources written here and nothing else."""
    root = Path(tmp)
    (root / "bin").mkdir(parents=True, exist_ok=True)
    for name in tuple(rg.DECISION_SURFACE) + tuple(rg.DECISION_STARTUP):
        (root / "bin" / f"{name}.py").write_text(
            sources.get(name, '"""a clean module."""\nimport json\n'), encoding="utf-8")
    return root


class JevFreeMatrixTests(unittest.TestCase):

    maxDiff = None

    # ==============================================================================================
    #  JEV-FREE, PROVED BY RUNNING
    # ==============================================================================================

    def test_the_import_guard_bites_which_is_what_makes_the_next_test_mean_anything(self):
        """The positive control, and it runs first on purpose. Under the guard a network import
        RAISES -- so a decision module that acquired one would fail the test below rather than
        sail through it."""
        with refusing_imports(rg.NETWORK_IMPORTS) as blocked:
            for source in ("import socket", "import urllib.request", "from http import client"):
                with self.subTest(source=source):
                    with self.assertRaises(ImportError):
                        exec(compile(source, "<d28-control>", "exec"), {})
        self.assertEqual([b.split(".")[0] for b in blocked], ["socket", "urllib", "http"])

    def test_the_whole_decision_surface_starts_with_every_network_module_refused(self):
        """Startup, in the task's sense: the four native drivers, the task contract, and every
        module that takes, records, replays or rolls back a decision, imported FRESH from disk
        with every network module scrubbed and refused. No key, no SDK, no endpoint, no socket."""
        names = tuple(rg.DECISION_SURFACE) + tuple(rg.DECISION_STARTUP)
        with refusing_imports(rg.NETWORK_IMPORTS) as blocked:
            for name in names:
                with self.subTest(module=name):
                    module = _load(name)
                    self.assertTrue(module.__doc__, name)
        self.assertEqual(blocked, [], "the decision surface reached for a network module")

    def test_rules_replay_and_rollback_all_run_with_every_network_module_refused(self):
        """The three surfaces the task names, exercised end to end inside the refusal.

        `rules` answers locally out of the request's own state; `replay` reads a record this test
        wrote into a temporary store and hands it back with the dispatch fields nulled; the
        rollback appends a generation and every future run reads legacy. Nothing is contacted,
        because there is nothing to contact.
        """
        with tempfile.TemporaryDirectory() as tmp, refusing_imports(rg.NETWORK_IMPORTS) as blocked:
            root = Path(tmp)
            prov = _load("decision_provider")
            we = _load("workflow_eval")
            dc = prov._contract()
            al = prov._al()
            kc = _load("kit_contract")
            dp = we._dp()
            req = dc.parse_request(request_payload(dc, al, kc))

            # RULES: a local computation with an empty default table -> an honest abstention.
            rules = dc.parse_result(prov.evaluate(req, mode="rules", provider="rules"), req)
            self.assertEqual(rules.status, "abstain")
            self.assertIsNone(rules.usage)

            # REPLAY: a miss abstains, and a hit reuses the record without dispatching.
            store = root / "replay"
            miss = dc.parse_result(
                prov.evaluate(req, mode="replay", provider="rules", store_dir=store), req)
            self.assertEqual(miss.status, "abstain")
            prov.record_result(store, req, result_payload(dc, req), provider="rules")
            hit = dc.parse_result(
                prov.evaluate(req, mode="replay", provider="rules", store_dir=store), req)
            self.assertEqual(hit.status, "ok")
            self.assertIsNone(hit.dispatched_provider)
            self.assertIsNone(hit.duration)
            self.assertTrue(hit.note.startswith(prov.REPLAY_NOTE_PREFIX))

            # ROLLBACK: a fallback its owner chose, recorded, contacting nothing.
            scope = {"project": tpb.PROJECT, "task_classes": [tpb.TASK_CLASS],
                     "intended_uses": [tpb.USE]}
            runtime = dp.runtime_facts(
                project=tpb.PROJECT, task_class=tpb.TASK_CLASS, intended_use=tpb.USE,
                components={"decision_contract": dc.CONTRACT_VERSION,
                            "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})
            resolution = dp.resolve_bundle(None, [], runtime)
            self.assertEqual(resolution.source, "legacy")
            entry = we.rollback_entry(scope=scope, resolution=resolution, by="d28",
                                      reason="the optional provider is absent")
            prefs = root / "prefs"
            we.swap_activation(prefs, scope, entry=entry, expected=None)
            answer = we.runtime_activation(prefs, scope)
            self.assertEqual(answer["mode"], "legacy")
            self.assertEqual(answer["reasons"], ["pointer-rolled-back"])
            self.assertIsNone(answer["pin"])
        self.assertEqual(blocked, [], "rules, replay or rollback reached for a network module")

    def test_the_optional_fallback_is_legacy_whether_or_not_a_pointer_was_ever_written(self):
        """The fallback the release claim rests on: with no pointer at all, a run is legacy and
        that is not an error. `decision_policy.resolve_bundle` terminates at legacy too, so there
        is no chain end that needs an optional provider to resolve."""
        with tempfile.TemporaryDirectory() as tmp:
            we = _load("workflow_eval")
            dp = we._dp()
            dc = dp._contract()
            kc = _load("kit_contract")
            scope = {"project": tpb.PROJECT, "task_classes": [tpb.TASK_CLASS],
                     "intended_uses": [tpb.USE]}
            answer = we.runtime_activation(Path(tmp) / "never-written", scope)
            self.assertEqual(answer["mode"], "legacy")
            self.assertEqual(answer["reasons"], ["no-pointer"])
            self.assertEqual(answer["deferred_modes"], list(dp.DEFERRED_MODES))
            runtime = dp.runtime_facts(
                project=tpb.PROJECT, task_class=tpb.TASK_CLASS, intended_use=tpb.USE,
                components={"decision_contract": dc.CONTRACT_VERSION,
                            "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})
            self.assertEqual(dp.resolve_bundle(None, [], runtime).source, "legacy")

    # ==============================================================================================
    #  THE SOURCE-SHAPE SCAN, AND THE PROOF THAT IT BITES
    # ==============================================================================================

    def test_the_real_tree_scans_clean_and_the_surface_reads_no_environment_variable(self):
        """Zero findings on this tree, and the distinction the scan is scoped around: the
        decision surface reads NO environment variable, while the startup path legitimately
        does, and the report says which modules those are rather than flattening them together."""
        report = rg.jev_free_report(ROOT)
        self.assertEqual(report["findings"], [])
        for name, row in report["surface"].items():
            self.assertTrue(row["readable"], name)
            self.assertEqual(row["environment"], [], name)
            self.assertEqual(row["optional_provider"], [], name)
            self.assertEqual(sorted(set(row["imports"]) & set(rg.NETWORK_IMPORTS)), [], name)
        for name, row in report["startup"].items():
            self.assertEqual(sorted(set(row["imports"]) & set(rg.NETWORK_IMPORTS)), [], name)
            self.assertEqual(row["optional_provider"], [], name)

    def test_a_network_import_an_optional_provider_or_an_environment_read_is_a_finding(self):
        """The guard, mutated one defect at a time against a doctored root. A clean root of the
        same shape scans clean, so each finding is attributable to the one line that caused it."""
        cases = {
            "a network import on the surface":
                ("decision_policy", "import socket\n", "imports 'socket'"),
            "a network import on the startup path":
                ("codex_execute", "import urllib.request\n", "imports 'urllib'"),
            "an optional provider imported":
                ("decision_provider", "import jev_sdk\n", "names 'jev_sdk'"),
            "an optional provider called":
                ("decision_eval", "def ask_jev():\n    return None\n", "names 'ask_jev'"),
            "an environment read on the surface":
                ("workflow_eval", "import os\nKEY = os.environ.get('X')\n",
                 "reads the environment"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            clean = doctored_root(Path(tmp) / "clean", {})
            self.assertEqual(rg.jev_free_report(clean)["findings"], [])
            for label, (module, source, expected) in cases.items():
                with self.subTest(case=label):
                    root = doctored_root(Path(tmp) / label.replace(" ", "-"), {module: source})
                    findings = rg.jev_free_report(root)["findings"]
                    self.assertTrue(any(expected in f and module in f for f in findings),
                                    f"{label}: {findings}")

    def test_prose_about_the_optional_provider_is_not_a_finding_but_a_call_is(self):
        """Uses, not words. Every document in this kit discusses the optional provider by name,
        and so does the module this scan lives in; a scan that could not tell a sentence from a
        call would fire on its own source and be switched off within a week."""
        with tempfile.TemporaryDirectory() as tmp:
            prose = ('"""Jev is an optional Release 2 provider and is not imported here."""\n'
                     '# jev: nothing in this module contacts one\n'
                     'NOTE = "no jev endpoint, key or SDK is assumed"\n')
            root = doctored_root(Path(tmp) / "prose", {"decision_contract": prose})
            self.assertEqual(rg.jev_free_report(root)["findings"], [])
            root = doctored_root(Path(tmp) / "call", {"decision_contract": prose + "jev()\n"})
            self.assertTrue(any("names 'jev'" in f for f in rg.jev_free_report(root)["findings"]))

    def test_an_unreadable_decision_module_is_a_finding_rather_than_an_empty_pass(self):
        """A surface this gate cannot read is one it cannot vouch for, so a missing or unparsable
        module fails rather than contributing nothing to the scan."""
        with tempfile.TemporaryDirectory() as tmp:
            root = doctored_root(Path(tmp) / "broken", {"improvement_loop": "def (\n"})
            findings = rg.jev_free_report(root)["findings"]
            self.assertTrue(any("improvement_loop" in f and "will not parse" in f
                                for f in findings), findings)
            (root / "bin" / "decision_context.py").unlink()
            self.assertTrue(any("decision_context" in f and "missing" in f
                                for f in rg.jev_free_report(root)["findings"]))

    # ==============================================================================================
    #  THE MATRIX: HARNESS, CLIENT, OS, ADAPTER, ENFORCEMENT, MODE, FALLBACK
    # ==============================================================================================

    def test_every_harness_row_answers_all_seven_columns(self):
        """One row per harness, and each of the seven things the task names is present and
        non-empty -- an absent column would be the failure mode this matrix exists to avoid."""
        matrix = rg.decision_matrix(ROOT)
        self.assertEqual([r["harness"] for r in matrix["rows"]], list(rg.HARNESSES))
        for row in matrix["rows"]:
            with self.subTest(harness=row["harness"]):
                self.assertEqual(sorted(row), sorted(rg.DECISION_ROW_KEYS))
                self.assertTrue(row["client"]["mode"])
                self.assertTrue(row["client"]["version"])
                self.assertIsInstance(row["os"], list)
                self.assertTrue(row["adapter"]["name"].startswith("workflow_eval."))
                self.assertIn("host_wide", row["enforcement"])
                self.assertTrue(row["mode"]["available"])
                self.assertEqual(row["fallback"]["mode"], "legacy")
                self.assertEqual(row["fallback"]["reason"], "no-pointer")

    def test_the_os_column_reports_only_confinement_evidence_that_was_actually_recorded(self):
        """Claude Code is the one harness with a confinement row, and the column names the host
        that row was measured on. Every other harness reads EMPTY rather than inheriting it:
        `confined_verify` being supported on one host is not an OS fact about another harness."""
        rows = {r["harness"]: r for r in rg.decision_matrix(ROOT)["rows"]}
        claude = {c["row"]: c for c in rows["claude-code"]["os"]}
        self.assertEqual(sorted(claude), ["confined_dispatch", "confined_verify"])
        self.assertEqual(claude["confined_verify"]["verified"], "supported")
        self.assertIn("sandbox-exec", claude["confined_verify"]["host"])
        self.assertEqual(claude["confined_dispatch"]["verified"], "unsupported")
        for harness in ("codex", "copilot", "cursor", "stub"):
            self.assertEqual(rows[harness]["os"], [], harness)

    def test_the_host_limitation_and_the_design_decision_are_linked_and_never_merged(self):
        """`claude-code.confined_dispatch` is a measured HOST limitation -- Seatbelt blocks the
        keychain the subscription credential lives in -- and it carries a date. `CONFINED_DISPATCH_
        WIRED` is a DESIGN decision about this repository. They travel in different columns of
        different tables, and a reader can tell which one a changed host would move."""
        matrix = rg.decision_matrix(ROOT)
        claude = {c["row"]: c for c in matrix["rows"][0]["os"]}
        self.assertEqual(matrix["rows"][0]["harness"], "claude-code")
        host = claude["confined_dispatch"]
        self.assertEqual(host["verified"], "unsupported")
        self.assertTrue(host["verified_on"], "a measured host limitation carries its date")
        self.assertIs(matrix["vocabulary"]["confined_dispatch_wired"], False)
        # The design decision reaches every harness; the host limitation reaches exactly one.
        blockers = {r["harness"]: r["mode"]["blocker"] for r in matrix["rows"]}
        self.assertEqual(set(blockers.values()), {"confining-dispatch-unwired"})
        with_rows = [r["harness"] for r in matrix["rows"]
                     if "confined_dispatch" in r["enforcement"]["rows"]]
        self.assertEqual(with_rows, ["claude-code"])

    def test_canary_and_active_are_unavailable_everywhere_and_the_cell_is_derived_not_typed(self):
        """The load-bearing one. Absent D23 evidence every running state is unavailable with the
        blocker its owner emits -- and then the constant is flipped and the SAME function returns
        a different cell. A cell that survived the flip would be a cell somebody typed."""
        we = rg._sibling("workflow_eval")
        dp = rg._sibling("decision_policy")
        for row in rg.decision_matrix(ROOT)["rows"]:
            with self.subTest(harness=row["harness"]):
                self.assertEqual(row["mode"]["unavailable"], list(dp.DEFERRED_MODES))
                self.assertEqual(row["mode"]["available"], list(dp.SELECTION_MODES))
                self.assertEqual(row["mode"]["blocker"], "confining-dispatch-unwired")
        with mock.patch.object(we, "CONFINED_DISPATCH_WIRED", True):
            flipped = rg.decision_matrix(ROOT)
        self.assertIs(flipped["vocabulary"]["confined_dispatch_wired"], True)
        for row in flipped["rows"]:
            self.assertEqual(row["mode"]["unavailable"], [], row["harness"])
            self.assertIsNone(row["mode"]["blocker"], row["harness"])

    def test_cursor_adaptive_is_unsupported_and_its_implementation_is_not_reported_absent(self):
        """Two claims, two places, both asserted. The adaptive profile is unsupported pending
        independent proof; the current CLI implementation is present, verified against a named
        client version and dated. Neither sentence is allowed to stand in for the other."""
        rows = {r["harness"]: r for r in rg.decision_matrix(ROOT)["rows"]}
        cursor = rows["cursor"]
        self.assertEqual(cursor["adaptive"]["effective"], "unsupported")
        self.assertEqual(cursor["adaptive"]["verified"], "unknown")
        present = {p["capability"]: p for p in cursor["implementation_present"]}
        for capability in ("dispatch", "identity_probe", "read_only_dispatch",
                           "structured_events", "durable_attempts", "independent_review"):
            self.assertIn(capability, present, "Cursor's implementation must not read as absent")
            self.assertTrue(present[capability]["verified_on"], capability)
            self.assertTrue(present[capability]["client_version"], capability)
        self.assertIn("Cursor", rg.CURSOR_ADAPTIVE_SCOPE_LABEL)
        self.assertIn(rg.CURSOR_ADAPTIVE_SCOPE_LABEL, rg.decision_matrix(ROOT)["labels"])
        # And the driver and adapter are untouched by this task: both still answer for Cursor.
        self.assertEqual(cursor["adapter"]["name"], "workflow_eval.cursor_adapter")
        self.assertTrue((BIN_DIR / "cursor_adapter.py").is_file())
        self.assertTrue((BIN_DIR / "cursor_execute.py").is_file())

    def test_the_adaptive_row_exists_on_every_harness_and_every_one_of_them_is_unknown(self):
        """A row this task ADDED, and it starts where an unrun thing starts. `unknown` means no;
        an added row that arrived `supported` would be the registry's own failure mode."""
        registry = json.loads((ROOT / "primitives" / "harness-capabilities.json")
                              .read_text(encoding="utf-8"))
        for harness, entry in registry["harnesses"].items():
            with self.subTest(harness=harness):
                row = entry["capabilities"].get(rg.ADAPTIVE_ROW)
                self.assertIsNotNone(row, f"{harness} has no {rg.ADAPTIVE_ROW} row")
                self.assertEqual(row["verified"], "unknown")
                self.assertIsNone(row["verified_on"])
                self.assertEqual(row["implemented"], "unsupported")
                self.assertEqual(row["product"], "not-applicable")
        for row in rg.decision_matrix(ROOT)["rows"]:
            self.assertEqual(row["adaptive"]["effective"], "unsupported", row["harness"])

    def test_the_row_shape_is_closed_so_no_measurement_column_can_be_added_later(self):
        """The refusal is reachable: narrow the closed key set and the builder raises rather than
        emitting a row with a key nobody vouched for."""
        self.assertNotIn("speedup", rg.DECISION_ROW_KEYS)
        shrunk = tuple(k for k in rg.DECISION_ROW_KEYS if k != "fallback")
        with mock.patch.object(rg, "DECISION_ROW_KEYS", shrunk):
            with self.assertRaises(ValueError) as raised:
                rg.decision_matrix(ROOT)
        self.assertIn("fallback", str(raised.exception))
        self.assertIn("NO performance claim", str(raised.exception))

    def test_the_rendered_section_carries_no_url_no_key_shape_and_no_measurement(self):
        """A shape check over the GENERATED text, which is the level the claim lives at: the
        release matrix must not acquire an endpoint, a credential or a number pretending to be a
        result. The behavioural claims are the tests above; this one guards the render."""
        matrix = rg.decision_matrix(ROOT)
        text = rg.render_decision(matrix, rg.decision_conformance(ROOT), rg.jev_free_report(ROOT))
        for pattern in (r"https?://", r"[A-Za-z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)",
                        r"\bBearer\b", r"\b\d+(?:\.\d+)?\s*(?:x faster|% faster|ms\b|speedup)"):
            self.assertIsNone(re.search(pattern, text), pattern)
        self.assertIn(rg.NO_PERFORMANCE_CLAIM_LABEL, text)
        self.assertIn(rg.ADAPTIVE_UNAVAILABLE_LABEL, text)

    def test_no_capability_row_anywhere_advertises_training_data_collection(self):
        """Constraint, not decoration: there is no call site for collection in the tree, so no
        harness may advertise it. The switches are off, `build_dataset` demands an explicit store,
        and the registry carries no row whose name would read as a collection capability."""
        td = rg._sibling("training_data")
        self.assertIs(td.COLLECTION_ENABLED, False)
        self.assertIs(td.CAPTURE_WIRED, False)
        registry = json.loads((ROOT / "primitives" / "harness-capabilities.json")
                              .read_text(encoding="utf-8"))
        for harness, entry in registry["harnesses"].items():
            for name in entry["capabilities"]:
                self.assertNotRegex(name, r"train|capture|collect|dataset", f"{harness}/{name}")
        self.assertIn(rg.TRAINING_NOT_AVAILABLE_LABEL, rg.decision_matrix(ROOT)["labels"])

    # ==============================================================================================
    #  BASELINE CONFORMANCE, LIVE GATES, AND THE GATE THAT READS THEM
    # ==============================================================================================

    def test_baseline_conformance_is_reported_per_adapter_and_never_merged(self):
        """Four adapters, four disjoint non-empty evidence sets, each resolving to real cases. A
        merged line would let three passing adapters carry a fourth, which is the exact thing the
        brief asks this table not to do."""
        report = rg.decision_conformance(ROOT)
        seen = {}
        for harness in ("claude-code", "codex", "copilot", "cursor"):
            cell = report["adapters"][harness]
            with self.subTest(harness=harness):
                self.assertTrue(cell["tests"], harness)
                self.assertEqual(cell["unresolved"], [], harness)
                self.assertGreater(cell["test_count"], 0, harness)
                self.assertIn(harness.replace("-code", ""), " ".join(cell["tests"]))
            for tid in cell["tests"]:
                self.assertNotIn(tid, seen, f"{tid} is claimed by {seen.get(tid)} and {harness}")
                seen[tid] = harness

    def test_every_live_gate_names_a_blocker_its_owner_declares_and_a_test_that_resolves(self):
        """The gates are LINKED, not listed: each blocker code is one an owner actually declares,
        and each proof id resolves to at least one case. A renamed test fails the gate here.

        THE NEGATIVE CASE IS LOAD-BEARING. Every blocker in the table is a known one today, so
        the `known_blocker` check has no way to be seen working from the real tree alone -- which
        is exactly how a live guard gets mistaken for decoration. A gate naming an invented
        blocker is therefore fed in, and the finding is followed all the way to `run_check`.
        """
        report = rg.decision_conformance(ROOT)
        self.assertEqual(report["unknown_blockers"], [])
        self.assertEqual(report["unresolved"], [])
        for gate in report["live_gates"]:
            with self.subTest(gate=gate["gate"]):
                self.assertTrue(gate["known_blocker"])
                self.assertTrue(gate["tests"])
                for tid, count in gate["resolved"].items():
                    self.assertGreater(count, 0, tid)
        self.assertIn("confining-dispatch-unwired",
                      [g["blocker"] for g in report["live_gates"]])
        invented = dict(rg.DECISION_LIVE_GATES[0], blocker="a-blocker-nobody-declares")
        with mock.patch.object(rg, "DECISION_LIVE_GATES", (invented,)):
            rogue = rg.decision_conformance(ROOT)
            self.assertIs(rogue["live_gates"][0]["known_blocker"], False)
            self.assertEqual(rogue["unknown_blockers"], ["a-blocker-nobody-declares"])
            checked = rg.run_check(ROOT)
        self.assertEqual(checked["exit"], rg.EXIT_DRIFT)
        self.assertTrue(any("a-blocker-nobody-declares" in finding
                            for finding in checked["findings"]), checked["findings"])

    def test_an_unresolvable_conformance_id_is_reported_rather_than_counted_as_passing(self):
        """A zero-case id is the failure mode the kit keeps hitting, so it is a finding here:
        `resolve_test_ids` returns zero and the report names the id."""
        report = rg.decision_conformance(ROOT, resolver=lambda ids: {tid: 0 for tid in ids})
        self.assertTrue(report["unresolved"])
        self.assertIn("test_decision_release_matrix.JevFreeMatrixTests", report["unresolved"])

    def test_the_gate_fails_on_a_decision_finding_and_passes_on_this_tree(self):
        """The wiring, proved by making the real gate fail for a real reason and then pass. The
        clean run is the whole gate on this tree, so a stale generated block fails here too."""
        with mock.patch.object(rg, "DECISION_SURFACE",
                               tuple(rg.DECISION_SURFACE) + ("no_such_decision_module",)):
            broken = rg.run_check(ROOT)
        self.assertEqual(broken["exit"], rg.EXIT_DRIFT)
        self.assertTrue(any("no_such_decision_module" in f for f in broken["findings"]))
        clean = rg.run_check(ROOT)
        self.assertEqual(clean["findings"], [])
        self.assertEqual(clean["exit"], rg.EXIT_OK)

    def test_the_generated_release_block_is_current_and_carries_the_decision_section(self):
        """`docs/RELEASE.md` is written by the generator and never by hand, so the section is
        asserted through `render_block` rather than by reading prose somebody could have typed."""
        self.assertIsNone(rg.check_release_doc(ROOT))
        text = (ROOT / rg.RELEASE_DOC).read_text(encoding="utf-8")
        block = text.split(rg.BLOCK_START, 1)[1].split(rg.BLOCK_END, 1)[0]
        self.assertIn("### Decision and improvement (Release 1)", block)
        self.assertIn(rg.ADAPTIVE_ROW, block)
        self.assertIn("confining-dispatch-unwired", block)
        self.assertIn(rg.NO_PERFORMANCE_CLAIM_LABEL, block)

    def test_the_decision_command_reports_and_spawns_nothing(self):
        """The CLI path, offline. `release_gate` has no process primitive of its own beyond
        read-only git, and `decision` does not reach even that."""
        import io as _io
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rg.main(["decision", "--repo-root", str(ROOT)])
        self.assertEqual(code, rg.EXIT_OK)
        self.assertIn("Decision and improvement (Release 1)", out.getvalue())
        out = _io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(rg.main(["decision", "--json", "--repo-root", str(ROOT)]),
                             rg.EXIT_OK)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["jev_free"]["findings"], [])
        self.assertEqual(len(payload["matrix"]["rows"]), len(rg.HARNESSES))


# ==================================================================================================
#  D29 -- OFFLINE CONFORMANCE
# ==================================================================================================
#
# WHAT A CONFORMANCE RUN IS FOR. D28 said what the release matrix CLAIMS. This says whether the
# claims hold HERE, in this checkout, on this host -- and, just as load-bearing, which of them
# this host could not put to the test at all.
#
# THERE ARE THREE OUTCOMES, NOT TWO. `pass`, `fail` and `unavailable`. `unavailable` is not a
# soft pass and not a soft fail: it is "no evidence was produced, because producing it needs
# something this run does not have and must not acquire" -- an installed vendor client, an OS
# enforcement boundary exercised for real, a non-stdlib site toolchain, a running pointer that
# cannot exist. A report that silently dropped those would read as a clean bill of health for
# things nobody looked at, which is the exact defect this task exists to avoid. So every
# unavailable check is COUNTED and NAMED, here and in `docs/DECISION-IMPROVEMENT-CONFORMANCE.md`,
# each with what is missing and what act would produce it.
#
# AND A REPORT OF ALL-UNAVAILABLE PROVES NOTHING. A registry of checks that may each answer
# "unavailable" is satisfiable by one that runs nothing, and reads identically. `run_conformance`
# therefore REFUSES to return a report in which no check passed. The complement holds too:
# `fail` is reachable, and three negative controls reach it, so a column of `pass` is not merely
# the only thing this machinery is capable of saying.
#
# WHAT A GREEN RUN HERE ESTABLISHES ABOUT NOTHING. No vendor client was run, no host was
# certified, no decision mechanism was measured, and no capability row moved: `unknown` in the
# registry still means no. Every store, home, prefs directory and doctored repository root below
# is a `tempfile.TemporaryDirectory`, and the checks that read THIS checkout read it only.

#: This report's own schema word. NEW, and deliberately not a bump of any existing `*_VERSION`:
#: a reader skips a record whose `v` it does not know, so raising one of those would discard
#: stored records in order to describe a document that has nothing to do with them.
CONFORMANCE_VERSION = "polytropos.decision-conformance/1"

#: The document this class is the other half of. It is a `docs/*.md` SOURCE, which is why
#: `docs_build` mirrors it and why `docs.generated-mirrors-carry-this-document` checks the mirror
#: against the generator's current output rather than against anything a hand could have typed.
CONFORMANCE_DOC = "docs/DECISION-IMPROVEMENT-CONFORMANCE.md"

PASS, FAIL, UNAVAILABLE = "pass", "fail", "unavailable"
CONFORMANCE_OUTCOMES = (PASS, FAIL, UNAVAILABLE)

#: The concerns the task names, in its own order. Every one carries at least one check and a
#: test below pins that, so an area cannot quietly lose its last check.
CONFORMANCE_AREAS = ("contracts", "privacy", "caps", "resume", "acceptance", "fallback",
                     "pins", "rollback", "migration", "package", "docs", "private-store")

_RUNNERS = {}
_UNSET = object()


class ConformanceRefused(AssertionError):
    """A report that establishes nothing, refused rather than returned."""


class _NotConforming(Exception):
    """One check's own refusal. This, and only this, is what `fail` means."""


def _expect(condition, detail):
    if not condition:
        raise _NotConforming(detail)


def _runs(check_id):
    def wrap(fn):
        _RUNNERS[check_id] = fn
        return fn
    return wrap


class _Env:
    """One conformance run's world: the modules under test, a scratch root, and a checkout.

    ONE SET OF MODULE INSTANCES. `bin/` is not a package, so two loaders of one file produce two
    incompatible sets of classes; every module below is reached through `workflow_eval`'s own
    cached `_sibling`, so a bundle one parsed is the bundle another reads.

    LAZILY, one at a time. `bin/exec_policy.py` imports `socket` at module level -- legitimately,
    since one of its sentinels is a loopback probe -- so eagerly loading it would make this class
    unconstructable inside `refusing_imports`, and the whole-run-under-refusal test below is
    precisely the thing that must be able to construct it.

    `root` is the checkout a check reads (the real one, or a doctored copy for a negative
    control) and `tracked` is git's answer for it -- overridable, because a doctored root has no
    git and a check that quietly skipped the tracked half would vouch for less than it says.
    """

    def __init__(self, tmp, root=ROOT, tracked=_UNSET):
        self.tmp = Path(tmp)
        self.root = Path(root)
        self._tracked = tracked
        self._n = 0
        self._mods = {}

    def _mod(self, key, build):
        if key not in self._mods:
            self._mods[key] = build()
        return self._mods[key]

    @property
    def we(self):
        return self._mod("workflow_eval", lambda: _load("workflow_eval"))

    @property
    def dp(self):
        return self._mod("decision_policy", self.we._dp)

    @property
    def dc(self):
        return self._mod("decision_contract", self.dp._contract)

    @property
    def al(self):
        return self._mod("attempt_ledger", self.dp._al)

    @property
    def kc(self):
        return self._mod("kit_contract", self.we._kc)

    @property
    def rt(self):
        return self._mod("runtime_data", lambda: self.we._sibling("runtime_data"))

    @property
    def rd(self):
        return self._mod("redact", self.we._rd)

    @property
    def ha(self):
        return self._mod("harness_adapter", self.we._ha)

    @property
    def ep(self):
        return self._mod("exec_policy", self.we._ep)

    @property
    def db(self):
        return self._mod("docs_build", lambda: _load("docs_build"))

    def work(self, name="work"):
        self._n += 1
        path = self.tmp / f"{self._n:02d}-{name}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def tracked(self):
        return rg.tracked_paths(self.root) if self._tracked is _UNSET else self._tracked

    def registry_path(self):
        return self.root / "primitives" / "harness-capabilities.json"

    def scope(self):
        return {"project": tpb.PROJECT, "task_classes": [tpb.TASK_CLASS],
                "intended_uses": [tpb.USE]}

    def runtime(self):
        return self.dp.runtime_facts(
            project=tpb.PROJECT, task_class=tpb.TASK_CLASS, intended_use=tpb.USE,
            components={"decision_contract": self.dc.CONTRACT_VERSION,
                        "task_contract": self.kc.CONTRACT_VERSION, "provider_contract": None})


# ---- the checks that RUN here --------------------------------------------------------------------

@_runs("contracts.payload-is-closed")
def _check_contracts_closed(env):
    dc = env.dc
    al, kc = dc._al(), dc._kc()
    codes = {}

    def refused(label, thunk):
        try:
            thunk()
        except dc.ContractError as exc:
            codes[label] = exc.code
        else:
            raise _NotConforming(f"{label} was accepted; this contract is closed and it is not")

    refused("duplicate key", lambda: dc.loads('{"status": "ok", "status": "invalid"}'))
    refused("non-finite number", lambda: dc.loads('{"probability": NaN}'))
    refused("unknown field",
            lambda: dc.parse_request(dict(request_payload(dc, al, kc), speedup=1.4)))
    refused("bool as a count", lambda: dc.parse_request(request_payload(
        dc, al, kc, resource_policy={"operation_scope": "consult", "call_ceiling": True,
                                     "repair_ceiling": 0})))
    refused("a wrong state identity",
            lambda: dc.parse_request(request_payload(dc, al, kc, state_sha="b" * 64)))
    _expect(codes["duplicate key"] == "duplicate-key", f"a duplicate key gave {codes}")
    _expect(codes["bool as a count"] == "wrong-type", f"a boolean count gave {codes}")
    _expect(codes["unknown field"] == "unknown-field", f"an unknown field gave {codes}")
    # ...and the well-formed payload still parses, so this is not a parser that refuses all.
    request = dc.parse_request(request_payload(dc, al, kc))
    _expect(request.correlation_id == "corr-d28", "the well-formed request did not parse")
    return ("refused " + "; ".join(f"{label} [{code}]" for label, code in sorted(codes.items()))
            + "; the well-formed request still parsed")


@_runs("contracts.stub-conformance-ids-resolve")
def _check_contract_ids(env):
    report = rg.contracts_report(env.root)
    _expect(not report["unresolved"],
            f"contract test id(s) resolve to no test: {report['unresolved']}")
    empty = sorted(f"{contract['id']}/{harness}"
                   for contract in report["contracts"]
                   for harness, cell in contract["cells"].items()
                   if cell["tests"] and cell["test_count"] == 0)
    _expect(not empty, f"mapped but zero-case contract cells: {empty}")
    decision = rg.decision_conformance(env.root)
    _expect(not decision["unresolved"],
            f"decision conformance id(s) resolve to no test: {decision['unresolved']}")
    _expect(not decision["unknown_blockers"],
            f"live gate(s) name a blocker no owner declares: {decision['unknown_blockers']}")
    cases = sum(cell["test_count"] for contract in report["contracts"]
                for cell in contract["cells"].values())
    return (f"{len(report['contracts'])} shared contracts, {cases} stub-conformance cases "
            f"resolved to real tests; every decision-conformance id and every live-gate blocker "
            f"resolves to its owner")


@_runs("privacy.free-text-is-redacted-and-bounded")
def _check_privacy(env):
    rd = env.rd
    secret = "AKIA" + "Q" * 16  # synthetic: a published SHAPE, never anybody's key
    text = f"the setup wrote {secret} into the log " + "y" * rd.DEFAULT_FIELD_LIMIT
    out = rd.redact(text)
    _expect(secret not in out["text"], "the value survived redaction")
    _expect("[redacted:aws-access-key-id]" in out["text"],
            f"no placeholder: {out['text'][:80]!r}")
    _expect(out["redactions"] == {"aws-access-key-id": 1},
            f"the report is by kind and count or it is itself a leak: {out['redactions']}")
    _expect(out["truncated"] is True and out["original_length"] == len(text),
            "an unbounded field is an unbounded disclosure, and this one was not bounded")
    _expect(len(out["text"]) <= rd.DEFAULT_FIELD_LIMIT + len(
        rd.TRUNCATION_NOTE.format(dropped=out["original_length"])),
        f"the bounded field is {len(out['text'])} chars")
    line = rd.describe({"redactions": out["redactions"], "truncated": 1})
    _expect("cannot prove no secret remains" in line,
            f"the summary claims more than shape-matching can: {line!r}")
    _expect(rd.redact("nothing to see here")["redactions"] == {},
            "a clean field was reported dirty")
    return (f"one kind caught by shape and reported as {out['redactions']}, the value absent "
            f"from the retained text, the field cut to {rd.DEFAULT_FIELD_LIMIT} chars and saying "
            f"so, and the summary refusing to claim absence")


@_runs("caps.unknown-is-no")
def _check_caps(env):
    ha = env.ha
    rows = ha.registry_capabilities("claude-code", path=env.registry_path())
    _expect(rg.ADAPTIVE_ROW in rows, f"no {rg.ADAPTIVE_ROW!r} row on claude-code")

    class _Probe(ha.Adapter):
        name = "conformance-probe"

        def capabilities(self):
            return rows

        def build_dispatch(self, task, model_id=None, prompt=""):  # pragma: no cover -- unused
            return []

    probe = _Probe()

    def refuses(name, why):
        try:
            probe.requires(name)
        except ha.CapabilityError:
            return
        raise _NotConforming(f"{why}: {name!r} was spent as though somebody had run it")

    # A row that is MERELY never-run: documented nowhere, implemented here, unrun. Its effective
    # state is `unknown`, and `requires` refuses it -- which is the whole of "unknown means no".
    unrun = sorted(name for name, row in rows.items() if ha.effective(row) == ha.UNKNOWN)
    _expect(unrun, "no claude-code row is merely unknown, so this probe proves nothing")
    refuses(unrun[0], "an unrun capability")
    refuses("a-row-that-does-not-exist", "an absent row")
    _expect(probe.supports("a-row-that-does-not-exist") == ha.UNKNOWN,
            "an absent row read as something other than unknown")
    mixed = ha.capability("mixed", product=ha.SUPPORTED, implemented=ha.SUPPORTED,
                          verified=ha.UNKNOWN)
    _expect(ha.effective(mixed) == ha.UNKNOWN,
            "documented and implemented but never run is unknown, not supported")
    # The adaptive row says TWO things and they must stay apart: `implemented: unsupported` is
    # the design decision that nothing is wired, and `verified: unknown` is that nobody has run
    # one. Its effective state is the weakest of the three, so `requires` refuses it either way.
    adaptive_row = rows[rg.ADAPTIVE_ROW]
    _expect(adaptive_row["implemented"] == ha.UNSUPPORTED,
            f"the adaptive mechanism reads implemented={adaptive_row['implemented']!r}")
    _expect(adaptive_row["verified"] == ha.UNKNOWN,
            f"the adaptive row reads verified={adaptive_row['verified']!r}; nobody has run one")
    _expect(ha.effective(adaptive_row) == ha.UNSUPPORTED,
            f"the adaptive row is effectively {ha.effective(adaptive_row)!r}")
    refuses(rg.ADAPTIVE_ROW, "an unwired, unrun capability")
    registry = ha.load_capabilities(env.registry_path())
    census, adaptive = {}, {}
    for harness, entry in sorted(registry["harnesses"].items()):
        for name, raw in (entry.get("capabilities") or {}).items():
            state = raw.get("verified", ha.UNKNOWN)
            census[state] = census.get(state, 0) + 1
            if name == rg.ADAPTIVE_ROW:
                adaptive[harness] = state
    stray = sorted(harness for harness, state in adaptive.items() if state != ha.UNKNOWN)
    _expect(not stray, f"an adaptive row moved off unknown without anybody running it: {stray}")
    return (f"`requires` refuses an unrun row ({unrun[0]!r}), an absent row and the adaptive "
            f"row; unknown is the effective state beside two supporteds; all {len(adaptive)} "
            f"adaptive-decision rows read implemented=unsupported and verified=unknown, kept "
            f"apart; the census by `verified` is {census} -- a dated observation, not a gate, "
            f"re-derived with `python3 bin/harness_adapter.py`")


@_runs("resume.interrupted-attempt-closes-unknown")
def _check_resume(env):
    al = env.al
    ledger = al.AttemptLedger(env.work("resume") / "attempts", "conformance")
    attempt = ledger.record_started(run="run-a", task="T1", op="initial", model="a-model")
    # THE CRASH, left exactly as a crash leaves it: a started attempt and no finish. Nothing
    # tidies up after it, because a killed process runs nothing.
    _expect([ev["attempt"] for ev in ledger.open_attempts("T1")] == [attempt],
            "the started attempt did not read back as open")
    closed = ledger.reconcile_open("run-b", "T1", note="the process died before it reported")
    _expect(closed == [attempt], f"resume closed {closed!r}")
    events = ledger.events()
    started = [ev for ev in events if ev["kind"] == "attempt.started"]
    finished = [ev for ev in events if ev["kind"] == "attempt.finished"]
    _expect(len(started) == 1, f"resume REPLAYED the attempt: {len(started)} started events")
    _expect(len(finished) == 1 and finished[0]["outcome"] == al.OUTCOME_UNKNOWN,
            f"the closing record is {finished and finished[0].get('outcome')!r}, not unknown")
    _expect(finished[0]["class"] == "unknown" and finished[0]["rc"] is None,
            "a closed-unknown attempt claimed a class or a return code nobody observed")
    _expect(finished[0]["reconciled_by"] == "run-b", "the closing record names no closer")
    _expect(ledger.open_attempts("T1") == [], "the attempt is still open after reconciliation")
    _expect(ledger.reconcile_open("run-c", "T1", note="again") == [],
            "a second resume closed something a second time")
    return (f"one started attempt, no finish, no tidy-up: resume closed it as "
            f"{al.OUTCOME_UNKNOWN!r} with class unknown and rc null, replayed nothing, and a "
            f"second resume closed nothing")


@_runs("acceptance.authority-never-arrives-as-advice")
def _check_acceptance(env):
    dc = env.dc
    al, kc = dc._al(), dc._kc()
    spellings = ("approve", "approved_by", "acceptance_override", "skip_review", "permission",
                 "max_dispatches", "budget.ceiling", "__approve__", "approve.", "argv")
    surfaces = 0
    for key in spellings:
        # SURFACE ONE: the request object itself.
        try:
            dc.parse_request(dict(request_payload(dc, al, kc), **{key: "yes"}))
        except dc.ContractError as exc:
            _expect(exc.code == "authority-field",
                    f"a request carrying {key!r} was refused as {exc.code!r}, not as authority")
            surfaces += 1
        else:
            raise _NotConforming(f"a decision request carried {key!r} and was accepted")
        # SURFACE TWO: the open state map, whose keys a caller chooses freely.
        try:
            dc.state_digest({"head": "0123abcd", key: "yes"})
        except dc.ContractError as exc:
            _expect(exc.code == "authority-field",
                    f"a state carrying {key!r} was refused as {exc.code!r}, not as authority")
            surfaces += 1
        else:
            raise _NotConforming(f"a state snapshot carried {key!r} and was accepted")
    _expect(len(dc.BANNED_FIELDS) >= len(spellings), "the banned vocabulary shrank")
    return (f"{len(spellings)} spellings of execution, permission, budget, acceptance, review "
            f"and promotion authority -- punctuation and namespacing included -- each refused "
            f"with code 'authority-field' on {surfaces} payload surfaces")


@_runs("fallback.absent-pointer-is-legacy")
def _check_absent_pointer(env):
    we = env.we
    scope = env.scope()
    root = env.work("pointer")
    empty = root / "prefs"
    empty.mkdir(parents=True)
    for label, prefs in (("no prefs directory at all", root / "never-created"),
                         ("a prefs directory with nothing in it", empty)):
        answer = we.runtime_activation(prefs, scope)
        _expect(answer["mode"] == "legacy" and answer["reasons"] == ["no-pointer"],
                f"{label}: {answer['mode']!r} {answer['reasons']!r}")
        _expect(answer["pin"] is None and we.pin_for_run(answer) is None
                and we.run_pin(answer) is None, f"{label}: a pin appeared from nowhere")
    _expect(we.ABSENT_POINTER_IS_LEGACY_LABEL
            in we.runtime_activation(root / "never-created", scope)["labels"],
            "the answer does not carry the label saying an absent pointer is not an error")
    generations, strays = we.activation_generations(empty, scope)
    _expect(generations == [] and strays == [], "an empty store reported generations")
    return ("three absences -- no store, no directory, no generation -- all answer legacy with "
            "reason 'no-pointer', none of them raises, and none of them mints a pin")


@_runs("fallback.resolution-terminates-at-legacy")
def _check_resolution(env):
    dp, dc, al = env.dp, env.dc, env.al
    runtime = env.runtime()
    unpinned = dp.resolve_bundle(None, [], runtime)
    _expect(unpinned.source == "legacy" and unpinned.bundle is None
            and unpinned.reasons == ("no-pin",), f"an unpinned run resolved {unpinned.source!r}")
    _expect(dict(unpinned.parameters) == {}, "legacy set parameters of its own")
    missing = dp.resolve_bundle(
        al.make_ref("a-bundle-nobody-has", sha="a" * 64, version=dc.BUNDLE_VERSION), [], runtime)
    _expect(missing.source == "legacy" and "bundle-unknown" in missing.reasons,
            f"a pin at a missing bundle resolved {missing.source!r} {missing.reasons!r}")
    garbage = dp.resolve_bundle({"id": "x"}, [], runtime)
    _expect(garbage.source == "legacy" and garbage.reasons == ("pin-not-a-reference",),
            f"a malformed pin resolved {garbage.reasons!r}")
    _expect("legacy" in dp.RESOLUTION_SOURCES and dp.SELECTION_MODES[0] == "legacy",
            "legacy is no longer the declared floor")
    return ("no pin, a pin at a bundle nobody has, and a pin that is not a reference all "
            "terminate at legacy with their own reason; legacy sets no parameters and reaching "
            "it contacts nothing")


@_runs("fallback.a-running-state-refuses")
def _check_running_refuses(env):
    """The load-bearing refusal, asserted rather than inferred from a constant.

    Added because a mutation probe showed the gap: flipping `CONFINED_DISPATCH_WIRED` to True in
    a copy of the tree moved no check at all -- only the generated release block noticed, because
    it renders the constant. A conformance report whose central safety property is enforced by a
    document mirror is not enforcing it. Every refusal below is reached with no fixture, and the
    last two lines show the refusal is READ FROM the constant at call time rather than typed in.
    """
    we = env.we
    permitted = {"v": we.ACTIVATION_VERSION, "target_state": "canary", "permitted": True,
                 "blockers": [], "requirements": [], "sha": "a-verdict-nobody-earned",
                 "unproven": list(we.ACTIVATION_UNPROVEN)}
    # EVERY OTHER ARGUMENT IS VALID, deliberately. An earlier draft passed `bundle_ref=None`, and
    # a mutation probe showed the cost: with the constant flipped to True the call still raised,
    # on the bundle reference, so the check "caught" the mutant by coincidence rather than by
    # observing a pointer get minted. Everything here is well formed, so the ONLY thing standing
    # between this call and a running pointer is the refusal under test.
    good_ref = env.dp.bundle_ref(tpb.bundle_payload())
    try:
        we.activation_entry(
            permitted, scope=env.scope(), bundle_ref=good_ref,
            eligibility={"task_classes": [tpb.TASK_CLASS], "cohort": [], "max_runs": 1},
            monitors=[we.ACTIVATION_MONITORS[0]], by="d29-conformance")
    except we.EvalError as exc:
        _expect("CONFINED_DISPATCH_WIRED" in str(exc),
                f"the refusal does not name what is unwired: {exc}")
    else:
        raise _NotConforming("a hand-built permitted verdict minted a running pointer")
    # A STORED entry, offered to the writer's own validator. Both shapes refuse: one with no gate
    # at all, one claiming a permitted gate a file cannot make true.
    base = we.rollback_entry(scope=env.scope(),
                            resolution=env.dp.resolve_bundle(None, [], env.runtime()),
                            by="d29-conformance", reason="a fixture")
    for gate, why in ((None, "a running entry with no gate verdict at all"),
                      (permitted, "a running entry claiming a gate this repository cannot grant")):
        try:
            we.validate_entry(dict(base, state="canary", gate=gate),
                              where="an offered generation")
        except we.EvalError:
            continue
        raise _NotConforming(f"{why} was accepted")
    prefs = env.work("running") / "prefs"
    try:
        we.swap_activation(prefs, env.scope(),
                           entry=dict(base, state="canary", gate=permitted), expected=None)
    except we.EvalError:
        pass
    else:
        raise _NotConforming("a canary pointer was written to a store")
    _expect(we.activation_generations(prefs, env.scope()) == ([], []),
            "the refused write left a generation behind")
    # DERIVED, NOT TYPED: the same gate block, read in a world where the path is wired, passes.
    _expect(we._unwired_dispatch(permitted, "a stored gate") is not None,
            "the re-derivation no longer refuses a permitted gate")
    with mock.patch.object(we, "CONFINED_DISPATCH_WIRED", True):
        _expect(we._unwired_dispatch(permitted, "a stored gate") is None,
                "the refusal is not derived from CONFINED_DISPATCH_WIRED at all; it is typed in, "
                "which means wiring the path would not change this answer")
    return ("no hand-built verdict mints a running pointer, a stored entry claiming a permitted "
            "gate is refused by the writer's validator and leaves no generation, and the same "
            "gate block passes when `CONFINED_DISPATCH_WIRED` is True -- so the refusal is read "
            "from that constant at call time and is not typed in")


@_runs("pins.a-run-carries-the-pin-it-started-under")
def _check_pins(env):
    we, dp = env.we, env.dp
    runtime = env.runtime()
    answer = we.runtime_activation(env.work("pins") / "prefs", env.scope())
    _expect(we.pin_for_run(answer) is None and we.run_pin(answer) is None,
            "an unpinned run produced a pin")
    unpinned = dp.pinned_bundle(None, [], runtime)
    _expect(unpinned["pinned"] is False and unpinned["acts"] is True
            and unpinned["resolution"].source == "legacy",
            f"a run that pinned nothing resolved {unpinned!r}")
    deferred = dp.pinned_bundle({"mode": "canary", "generation": 4, "activation": "act-x",
                                 "bundle_ref": None}, [], runtime)
    _expect(deferred["acts"] is False and deferred["generation"] == 4,
            f"a pin naming a deferred mode reported acts={deferred['acts']!r}")
    _expect("canary" in deferred["reason"],
            f"the refusal does not name the mode it refused: {deferred['reason']!r}")
    for broken, why in (({"mode": "legacy"}, "a pin missing three of its four keys"),
                        ("a-string", "a pin that is not an object"),
                        ({"mode": "sideways", "generation": 1, "activation": None,
                          "bundle_ref": None}, "a pin naming an undeclared mode")):
        try:
            dp.pinned_bundle(broken, [], runtime)
        except dp._contract().ContractError:
            continue
        raise _NotConforming(f"{why} was degraded to legacy instead of refused")
    return ("an unpinned run pins nothing and resolves legacy; a pin naming a deferred mode "
            "resolves which parameters it could read and still reports acts=False by name; and "
            "three malformed pins raise rather than degrading into a safe-looking legacy")


@_runs("rollback.appends-a-generation-and-deletes-nothing")
def _check_rollback(env):
    we, dp = env.we, env.dp
    scope = env.scope()
    prefs = env.work("rollback") / "prefs"
    resolution = dp.resolve_bundle(None, [], env.runtime())

    def entry(reason):
        return we.rollback_entry(scope=scope, resolution=resolution, by="d29-conformance",
                                 reason=reason)

    first = we.swap_activation(prefs, scope, entry=entry("the first rollback"), expected=None)
    path = prefs / we.POLICY_ACTIVATION / we.scope_key(scope) / "gen-000001.json"
    before = path.read_bytes()
    we.swap_activation(prefs, scope, entry=entry("the second rollback"), expected=1)
    generations, strays = we.activation_generations(prefs, scope)
    _expect(generations == [1, 2] and strays == [], f"the store holds {generations!r} {strays!r}")
    _expect(path.read_bytes() == before, "generation 1 was rewritten by a later rollback")
    history = we.activation_history(prefs, scope)
    _expect([row["generation"] for row in history["generations"]] == [1, 2],
            "the history has a hole in it, which is how a rollback comes to look undone")
    _expect(first["bundle_ref"] is None and first["gate"] is None,
            "a rolled-back pointer named a bundle or claimed a gate")
    _expect(first["fallback"]["in_force_for_future_runs"] == "legacy",
            "recording a fallback target was read as taking it")
    answer = we.runtime_activation(prefs, scope)
    _expect(answer["mode"] == "legacy" and answer["reasons"] == ["pointer-rolled-back"],
            f"a rolled-back pointer resolved {answer['mode']!r} {answer['reasons']!r}")
    # AN INTERRUPTED SWAP. A writer that read generation 1 and lost the race writes nothing at
    # all: the store is left as the winner left it, never half-way between the two.
    try:
        we.swap_activation(prefs, scope, entry=entry("a lost update"), expected=1)
    except we.ActivationConflict:
        pass
    else:
        raise _NotConforming("a stale swap overwrote a generation it had never read")
    _expect(we.activation_generations(prefs, scope)[0] == [1, 2],
            "the refused swap left something behind anyway")
    return ("two rollbacks append generations 1 and 2, generation 1 is byte-identical "
            "afterwards, every future run reads legacy with reason 'pointer-rolled-back', and a "
            "swap that lost the race writes nothing rather than half of something")


@_runs("migration.old-ledger-answers-unknown")
def _check_old_ledger(env):
    al = env.al
    root = env.work("old-ledger") / "attempts"
    ledger = al.AttemptLedger(root, "conformance")
    # THE GENUINELY OLD SHAPE: the keys `record_started` wrote before provenance references
    # existed, and no others. Not a current record with fields deleted -- that would only ever
    # prove that deleting a field works.
    old = {"v": al.LEDGER_VERSION, "ts": "2026-01-02T03:04:05Z", "kind": "attempt.started",
           "run": "run-old", "task": "T0", "attempt": "att-old", "op": "initial",
           "model": "a-model", "prompt_sha": None, "verify_sha": None, "artifact": None}
    env.rt.ensure_private(root / "conformance")
    (root / "conformance" / al.EVENTS_FILE).write_text(
        json.dumps(old, sort_keys=True) + "\n", encoding="utf-8")
    events = ledger.events()
    _expect(len(events) == 1 and ledger.corrupt == 0,
            f"the old line read as {len(events)} event(s), {ledger.corrupt} corrupt")
    read = al.provenance(events[0])
    _expect(read == {name: None for name in al.PROVENANCE_REFS},
            f"an old event invented provenance: {read!r}")
    _expect(al.ref_gaps(None) == sorted(al.REF_FIELDS),
            "an absent reference does not name every part it cannot answer")
    _expect(al.ref_gaps(al.make_ref("acc-1")) == ["sha", "v"],
            "a partially known reference does not name its gap")
    _expect(al.read_ref({"sha": "a" * 64}) is None and al.read_ref("acc-1") is None,
            "a reference-shaped value nothing minted was read as provenance")
    fresh = ledger.record_started(run="run-new", task="T1", op="initial", model="a-model")
    written = [ev for ev in ledger.events() if ev.get("attempt") == fresh][0]
    explicit = sorted(name for name in al.PROVENANCE_REFS if name in written)
    _expect(not explicit, f"a run that recorded no reference wrote explicit nulls: {explicit}")
    _expect(ledger.task_history("T0"), "the old attempt dropped out of the joined history")
    return ("an event written before the four provenance references existed reads back unknown "
            "on all four, names every part it cannot answer, and still joins into the history; "
            "an event written today without references is the same shape as it")


@_runs("migration.old-preferences-are-not-a-bundle")
def _check_old_preferences(env):
    dp, dc, we = env.dp, env.dc, env.we
    payload = tpb.preference_payload(by_task_class={"S": {"invented_knob": 2}})
    view = dp.describe_legacy_preferences(payload)
    _expect(view.reasons == (dp.LEGACY_PREFERENCE_REASON,), f"reasons {view.reasons!r}")
    _expect("invented_knob" in view.unmapped,
            f"a key this contract does not translate was translated anyway: {view.unmapped!r}")
    try:
        dc.parse_bundle(payload)
    except dc.ContractError:
        pass
    else:
        raise _NotConforming("a pull-only preference file parsed as an approved policy bundle")
    # THE OLD FILE, with every field added since absent -- built as the shape it was, not as
    # today's shape with keys removed.
    ancient = {"v": we.POLICY_VERSION, "defaults": {"workflow": "kit"}}
    older = dp.describe_legacy_preferences(ancient)
    _expect(older.policy_version is None,
            f"an absent revision count read as {older.policy_version!r} rather than unknown")
    _expect(dict(older.by_task_class) == {}, "an absent section was invented")
    _expect(dc.is_legacy_preference_payload(ancient) is True
            and dc.is_legacy_preference_payload({"v": dc.BUNDLE_VERSION}) is False,
            "the old shape and a bundle are no longer told apart by machine")
    converters = sorted(name for name in dir(dp)
                        if "preference" in name.lower() and "bundle" in name.lower())
    _expect(not converters, f"something now converts a preference into a bundle: {converters}")
    return ("the historical preference payload loads, names the keys it does not translate, and "
            "refuses to parse as a bundle; a file predating every field added since reads with "
            "those fields unknown rather than defaulted")


@_runs("migration.a-store-is-copied-never-relocated")
def _check_store_migration(env):
    rt = env.rt
    work = env.work("migration")
    repo = work / "checkout"
    (repo / "memory").mkdir(parents=True)
    (repo / "memory" / "facts.jsonl").write_text('{"fact": "original"}\n', encoding="utf-8")
    home = {"HOME": str(work / "home")}  # an explicit env, never this host's own home
    resolved = rt.resolve_store("memory", repo, env=home, platform="linux")
    _expect(resolved["origin"] == "legacy-in-tree" and Path(resolved["path"]) == repo / "memory",
            f"an existing in-tree store stopped being used: {resolved!r}")
    plan = rt.plan_migration("memory", repo, env=home, platform="linux")
    target = Path(plan["target"])
    _expect(plan["copy"] == ["facts.jsonl"] and not target.exists(),
            f"planning wrote something: {plan!r}")
    dry = rt.migrate("memory", repo, env=home, platform="linux", apply=False)
    _expect(dry["copied"] == [] and not target.exists(), f"a dry migration wrote {dry!r}")
    applied = rt.migrate("memory", repo, env=home, platform="linux", apply=True)
    _expect(applied["copied"] == ["facts.jsonl"], f"the migration copied {applied!r}")
    _expect((repo / "memory" / "facts.jsonl").is_file(),
            "THE ORIGINAL WAS MOVED: a migration copies, and user data is never relocated")
    _expect((target / "facts.jsonl").read_text(encoding="utf-8") == '{"fact": "original"}\n',
            "the copy does not match what it copied")
    _expect(stat.S_IMODE((target / "facts.jsonl").stat().st_mode) == rt.FILE_MODE,
            "the copy is not private")
    still = rt.resolve_store("memory", repo, env=home, platform="linux")
    _expect(still["origin"] == "legacy-in-tree",
            "a migration switched the store over; an in-tree store keeps being used")
    (repo / "memory" / "facts.jsonl").write_text('{"fact": "changed"}\n', encoding="utf-8")
    again = rt.migrate("memory", repo, env=home, platform="linux", apply=True)
    _expect(again["conflicts"] == ["facts.jsonl"] and again["copied"] == [],
            f"a second migration overwrote the destination: {again!r}")
    _expect((target / "facts.jsonl").read_text(encoding="utf-8") == '{"fact": "original"}\n',
            "an existing destination file was overwritten rather than reported as a conflict")
    return ("an in-tree store keeps being used before and after migrating; the migration COPIES, "
            "0600, leaving the original in place; a second run reports a conflict rather than "
            "overwriting; nothing is deleted and nothing is relocated")


@_runs("package.private-stores-are-not-packaged")
def _check_packaging(env):
    tracked = env.tracked()
    _expect(tracked is not None,
            "git could not list tracked files, so this run cannot vouch for the tracked half of "
            "packaging; that is a failed check and not a quiet skip")
    review = rg.packaging_review(env.root, tracked=tracked)
    _expect(review["findings"] == [], f"packaging findings: {review['findings']}")
    unignored = sorted(name for name, ok in review["stores"].items() if not ok)
    _expect(not unignored, f"store(s) with no root-anchored ignore rule: {unignored}")
    _expect(set(review["stores"]) == set(env.rt.STORES),
            f"the review covers {sorted(review['stores'])}; the stores are "
            f"{sorted(env.rt.STORES)}")
    inside = sorted(path for path in tracked
                    for store in env.rt.STORES if path.startswith(f"{store}/"))
    _expect(not inside, f"tracked file(s) under a private store: {inside}")
    return (f"{len(review['stores'])} private stores, each with its own root-anchored ignore "
            f"rule, none carrying a tracked file among {len(tracked)} tracked paths, and no "
            f"packaging finding at all")


@_runs("docs.generated-mirrors-carry-this-document")
def _check_docs(env):
    db = env.db
    source = env.root / CONFORMANCE_DOC
    _expect(source.is_file(), f"{CONFORMANCE_DOC} is absent")
    slug = db.deep_dive_slug(Path(CONFORMANCE_DOC).name)
    mirror = env.root / "docs-site" / "deep-dives" / f"{slug}.md"
    _expect(mirror.is_file(), f"{mirror} is missing; run `python3 bin/docs_build.py build`")
    expected = db.render_deep_dive_page(CONFORMANCE_DOC, source.read_text(encoding="utf-8"),
                                        db.deep_dive_page_map(env.root))
    _expect(mirror.read_text(encoding="utf-8") == expected,
            "the mirror is not this generator's current output for this source; a generated "
            "page is never hand-edited and never left stale")
    nav = (env.root / "mkdocs.yml").read_text(encoding="utf-8")
    _expect(nav.count(f"deep-dives/{slug}.md") == 1,
            f"mkdocs.yml carries the page {nav.count(f'deep-dives/{slug}.md')} time(s)")
    stale = rg.check_release_doc(env.root)
    _expect(stale is None, f"the generated release block is stale: {stale}")
    return (f"the conformance document has its mirror at deep-dives/{slug}.md, byte-identical "
            f"to the generator's current output, the nav carries it exactly once, and the "
            f"generated block of docs/RELEASE.md is current")


@_runs("private-store.defaults-outside-the-tree-and-private")
def _check_private_store(env):
    rt = env.rt
    work = env.work("private-store")
    repo = work / "fresh-checkout"
    repo.mkdir(parents=True)
    home = {"HOME": str(work / "home")}  # explicit: nothing here reads this host's own home
    for name in rt.STORES:
        resolved = rt.resolve_store(name, repo, env=home, platform="linux")
        path = Path(resolved["path"])
        _expect(resolved["origin"] == "user-data-root",
                f"{name} resolved by {resolved['origin']!r} in a fresh checkout")
        _expect(repo not in path.parents,
                f"{name} defaults to {path}, which is inside the checkout")
        _expect(not path.exists(), f"resolving {name} created it; a reader must not")
    second = work / "another-checkout"
    second.mkdir()
    _expect(rt.store_path("memory", repo, env=home, platform="linux")
            != rt.store_path("memory", second, env=home, platform="linux"),
            "two checkouts share one store")
    made = rt.ensure_private(Path(rt.store_path("memory", repo, env=home, platform="linux")))
    _expect(stat.S_IMODE(made.stat().st_mode) == rt.DIR_MODE,
            f"a created store is {oct(stat.S_IMODE(made.stat().st_mode))}, not "
            f"{oct(rt.DIR_MODE)}")
    _expect((rt.DIR_MODE, rt.FILE_MODE) == (0o700, 0o600), "the private modes changed")
    chosen = work / "chosen"
    ledger = env.al.AttemptLedger(chosen, "conformance")
    ledger.record_started(run="r", task="T", op="initial", model="m")
    _expect(ledger.events_path.is_file() and chosen in ledger.events_path.parents,
            "an explicit store directory was not honoured over the default")
    return (f"all {len(rt.STORES)} stores default outside the checkout, per user and per "
            f"checkout; resolving one creates nothing; a created one is 0700 with 0600 files; "
            f"and an explicit store directory is honoured over every default")


# ---- the registry, and the report it produces ----------------------------------------------------

#: Every check, in the task's own order of concerns. `kind` is `run` (this host produces the
#: evidence) or `unavailable` (it cannot: `why` says what is missing, `moves_it` says what act
#: would produce it). An `unavailable` row runs nothing, which is what the word means.
CONFORMANCE_CHECKS = (
    {"id": "contracts.payload-is-closed", "area": "contracts", "kind": "run",
     "question": "Does the decision contract refuse a duplicate key, an unknown field, a "
                 "bool-as-number, a non-finite number and a wrong state identity?"},
    {"id": "contracts.stub-conformance-ids-resolve", "area": "contracts", "kind": "run",
     "question": "Does every shared-contract and decision-conformance test id name real cases, "
                 "and does every live gate name a blocker its owner declares?"},
    {"id": "contracts.installed-client-conformance", "area": "contracts", "kind": "unavailable",
     "question": "Do the shared contracts hold against an INSTALLED vendor client?",
     "why": "no `claude`, `codex`, `copilot` or `cursor` binary is invoked by this run, by any "
            "test, or by any verify command: those calls spend the user's own credits and reach "
            "the network. Stub conformance is what this host can produce; the registry's "
            "installed-client column is the only other evidence, and it reads `unknown` for "
            "every capability nobody has run, where `unknown` means no",
     "moves_it": "run that harness's documented smoke on your own account, then record "
                 "`verified_on` and `client_version` in that registry row by hand"},
    {"id": "privacy.free-text-is-redacted-and-bounded", "area": "privacy", "kind": "run",
     "question": "Is user free text redacted and length-bounded before it is retained, and "
                 "reported by kind and count rather than by value?"},
    {"id": "caps.unknown-is-no", "area": "caps", "kind": "run",
     "question": "Is an unrun capability refused rather than spent, and is every "
                 "adaptive-decision row still unknown?"},
    {"id": "caps.os-enforcement-sentinels", "area": "caps", "kind": "unavailable",
     "question": "Does a protected profile actually DENY a hidden-answer read, a control-state "
                 "write, a controller mutation, a test escape and a judge write on this host?",
     "why": "`exec_policy.run_sentinels` is the only thing that answers it, and answering means "
            "spawning sandboxed processes and binding a loopback port. This run does not call "
            "it, so no sentinel report exists and `exec_policy.certify_profile` certifies "
            "nothing without one. Detecting a backend is not certifying one: "
            "`protected_profile_status` can report `enforced` on this host, which is a "
            "statement about a binary being present and never about what it denied",
     "moves_it": "run `exec_policy.run_sentinels` on a named profile and keep the report; a "
                 "skipped, unavailable, inconclusive or leaked sentinel certifies nothing"},
    {"id": "caps.confining-ledgered-dispatch", "area": "caps", "kind": "unavailable",
     "question": "Is there a dispatch path that confines what it spawns and ledgers it, so that "
                 "a running decision state could be reached at all?",
     "why": "there is not. `workflow_eval.CONFINED_DISPATCH_WIRED` is False -- a DESIGN "
            "DECISION, recorded once and reaching all five harnesses -- so `activation_decision` "
            "refuses every transition to `canary` and `active`, and `runtime_activation` "
            "resolves every run to legacy. It is linked to, and is not the same fact as, the "
            "MEASURED `claude-code.confined_dispatch` host-limitation row (macOS, 2026-09-06), "
            "which is one harness's observation on one platform",
     "moves_it": "wire a confining, ledgered dispatch path and flip that constant with its own "
                 "evidence; until then every check of a RUNNING state is a check of a refusal"},
    {"id": "resume.interrupted-attempt-closes-unknown", "area": "resume", "kind": "run",
     "question": "After a process dies between dispatch and its record, does resume close the "
                 "attempt as unknown without replaying it?"},
    {"id": "acceptance.authority-never-arrives-as-advice", "area": "acceptance", "kind": "run",
     "question": "Can execution, permission, budget, acceptance, review or promotion authority "
                 "arrive inside a decision payload, however it is spelled?"},
    {"id": "fallback.absent-pointer-is-legacy", "area": "fallback", "kind": "run",
     "question": "With no activation pointer of any kind, is a run legacy without erroring?"},
    {"id": "fallback.resolution-terminates-at-legacy", "area": "fallback", "kind": "run",
     "question": "Does bundle resolution always terminate at legacy, with nothing to contact?"},
    {"id": "fallback.a-running-state-refuses", "area": "fallback", "kind": "run",
     "question": "Does every route to a running decision state refuse, and is that refusal read "
                 "from its owning constant at call time rather than typed in?"},
    {"id": "pins.a-run-carries-the-pin-it-started-under", "area": "pins", "kind": "run",
     "question": "Does a run resolve only the pin it started under, and is a malformed pin "
                 "refused rather than degraded into legacy?"},
    {"id": "rollback.appends-a-generation-and-deletes-nothing", "area": "rollback", "kind": "run",
     "question": "Does a rollback append a generation, leave every earlier one byte-identical, "
                 "resolve future runs to legacy, and write nothing when it loses a race?"},
    {"id": "rollback.live-rollback-of-a-running-pointer", "area": "rollback",
     "kind": "unavailable",
     "question": "Does rolling back move a run that was actually FOLLOWING a bundle off it?",
     "why": "no running pointer has ever existed in this repository, and none can be minted "
            "while `workflow_eval.CONFINED_DISPATCH_WIRED` is False, so there is no run "
            "following a bundle to move. The mechanics are exercised on a rolled-back pointer "
            "in a temporary store; that establishes the store's behaviour and says nothing "
            "about a live cohort, a run in flight, or an external effect already taken",
     "moves_it": "the act that moves `caps.confining-ledgered-dispatch`, followed by an "
                 "approved activation and a rollback of it under observation"},
    {"id": "migration.old-ledger-answers-unknown", "area": "migration", "kind": "run",
     "question": "Does a ledger event written before the provenance references existed read "
                 "back as unknown rather than defaulted or back-filled?"},
    {"id": "migration.old-preferences-are-not-a-bundle", "area": "migration", "kind": "run",
     "question": "Does the historical preference file still load, and does it stay a preference "
                 "rather than becoming an approved policy bundle?"},
    {"id": "migration.a-store-is-copied-never-relocated", "area": "migration", "kind": "run",
     "question": "Does migrating a store copy it, keep using the in-tree one, and refuse to "
                 "overwrite or delete anything?"},
    {"id": "package.private-stores-are-not-packaged", "area": "package", "kind": "run",
     "question": "Is every private runtime store excluded from the package, with no tracked "
                 "file under one?"},
    {"id": "private-store.defaults-outside-the-tree-and-private", "area": "private-store",
     "kind": "run",
     "question": "Does every store default outside the checkout, per user and per checkout, "
                 "0700/0600, reached through its own explicit directory seam?"},
    {"id": "private-store.install-time-copy", "area": "private-store", "kind": "unavailable",
     "question": "Does an INSTALL of this plugin leave a legacy in-tree store behind in the "
                 "installed copy?",
     "why": "a plugin install copies the whole directory and does not consult `.gitignore`, so "
            "a legacy in-tree store would be copied with it. Answering this means reading and "
            "writing `~/.claude`, which nothing in this repository touches -- the remedy is "
            "printed, never executed",
     "moves_it": "the operator runs the prune runbook in `docs/PRIVACY.md` after "
                 "`claude plugin update`; it is manual by design"},
    {"id": "docs.generated-mirrors-carry-this-document", "area": "docs", "kind": "run",
     "question": "Is this document's generated mirror present, current byte for byte and in the "
                 "nav -- and is the generated release block current?"},
    {"id": "docs.site-build-strict", "area": "docs", "kind": "unavailable",
     "question": "Does `mkdocs build --strict` succeed over the generated site?",
     "why": "the site is the one surface with a non-stdlib toolchain, and that toolchain is "
            "hash-locked and installed only in CI or a throwaway venv. This repository is "
            "stdlib-only and installs nothing, so the strict build is not run here",
     "moves_it": "CI runs it on every push, installing `docs-src/requirements.txt` with "
                 "`--require-hashes`; locally it needs a throwaway venv"},
)


def run_conformance(env, checks=None, runners=None):
    """Every check, run or declared unavailable -> the report. REFUSES an empty establishment.

    A check that raises anything at all is a FAIL: a check that blew up did not pass, and
    reporting it as unavailable would let a broken probe masquerade as an honest gap.
    """
    checks = CONFORMANCE_CHECKS if checks is None else checks
    runners = _RUNNERS if runners is None else runners
    rows = []
    for spec in checks:
        if spec["kind"] == "unavailable":
            rows.append(dict(spec, outcome=UNAVAILABLE, detail=spec["why"]))
            continue
        runner = runners.get(spec["id"])
        if runner is None:
            rows.append(dict(spec, outcome=FAIL,
                             detail="no runner is registered for this check id"))
            continue
        try:
            rows.append(dict(spec, outcome=PASS, detail=runner(env)))
        except _NotConforming as exc:
            rows.append(dict(spec, outcome=FAIL, detail=str(exc)))
        except Exception as exc:  # noqa: BLE001 -- a check that blew up did not pass
            rows.append(dict(spec, outcome=FAIL,
                             detail=f"the check itself raised {type(exc).__name__}: {exc}"))
    counts = {outcome: sum(1 for row in rows if row["outcome"] == outcome)
              for outcome in CONFORMANCE_OUTCOMES}
    report = {
        "v": CONFORMANCE_VERSION,
        "checks": rows,
        "counts": counts,
        "areas": sorted({row["area"] for row in rows}),
        "unavailable": [row["id"] for row in rows if row["outcome"] == UNAVAILABLE],
        "failed": [row["id"] for row in rows if row["outcome"] == FAIL],
    }
    if counts[PASS] == 0:
        raise ConformanceRefused(
            f"no check passed: {counts[UNAVAILABLE]} unavailable, {counts[FAIL]} failed. A "
            f"report with no passing check establishes nothing -- one in which every outcome is "
            f"'unavailable' is satisfiable by a registry that runs nothing at all, and reads "
            f"identically -- so it is refused rather than returned")
    return report


_DOC_ROW = re.compile(r"^\|\s*`(?P<id>[a-z0-9.\-]+)`\s*\|\s*(?P<area>[a-z\-]+)\s*\|\s*"
                      r"\*\*(?P<outcome>pass|fail|unavailable)\*\*\s*\|", re.M)


def document_rows(text):
    """The conformance table as the document states it -> `{id: (area, outcome)}`."""
    return {match.group("id"): (match.group("area"), match.group("outcome"))
            for match in _DOC_ROW.finditer(text)}


class JevFreeConformanceTests(unittest.TestCase):
    """D29 -- the offline conformance run, and the document that reports it.

    `CONFORMANCE_CHECKS` is the authority for what conformance means here; the document is the
    half a person reads, and every assertion below exists to stop the two drifting.
    """

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="polytropos-d29-")
        cls.env = _Env(cls._tmp.name)
        cls.report = run_conformance(cls.env)
        cls.doc_path = ROOT / CONFORMANCE_DOC
        cls.doc = cls.doc_path.read_text(encoding="utf-8") if cls.doc_path.is_file() else ""

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _one(self, check_id):
        """One check, re-run beside a cheap passing one so the report is returnable at all."""
        spec = [dict(s) for s in CONFORMANCE_CHECKS if s["id"] == check_id]
        self.assertEqual(len(spec), 1, check_id)
        control = [dict(s) for s in CONFORMANCE_CHECKS
                   if s["id"] == "contracts.payload-is-closed"]
        report = run_conformance(self.env, checks=spec + control)
        return [row for row in report["checks"] if row["id"] == check_id][0]

    # ==============================================================================================
    #  THE RUN ITSELF
    # ==============================================================================================

    def test_every_check_that_runs_here_passes_and_its_failures_are_named_not_counted(self):
        """The run, first. A failure is reported with the check's OWN detail rather than as a
        tally, because a tally is what you read when nobody meant to fix it."""
        failed = [(row["id"], row["detail"]) for row in self.report["checks"]
                  if row["outcome"] == FAIL]
        self.assertEqual(failed, [],
                         "\n".join(f"{cid}: {detail}" for cid, detail in failed))

    def test_the_report_carries_three_outcomes_and_unavailable_is_neither_of_the_others(self):
        counts = self.report["counts"]
        self.assertEqual(sorted(counts), sorted(CONFORMANCE_OUTCOMES))
        self.assertEqual(sum(counts.values()), len(CONFORMANCE_CHECKS))
        self.assertGreater(counts[UNAVAILABLE], 0,
                           "a conformance run on this host cannot exercise an installed client "
                           "or an OS enforcement boundary; reporting none of that is the defect")
        self.assertEqual(counts[FAIL], 0)
        self.assertEqual(len(self.report["unavailable"]), counts[UNAVAILABLE])
        self.assertEqual(self.report["v"], CONFORMANCE_VERSION)

    def test_at_least_one_check_actually_passed_on_this_host(self):
        """THE POSITIVE CONTROL. Without it, a wall of refusals and gaps is satisfiable by a
        registry that produces no evidence at all, and reads exactly the same."""
        passed = [row["id"] for row in self.report["checks"] if row["outcome"] == PASS]
        self.assertGreater(len(passed), 0)
        self.assertIn("package.private-stores-are-not-packaged", passed)
        for row in self.report["checks"]:
            if row["outcome"] == PASS:
                self.assertTrue(row["detail"].strip(),
                                f"{row['id']} passed without saying what it established")

    def test_a_report_in_which_nothing_passed_is_refused_rather_than_returned(self):
        """And that refusal bites: the same machinery, given a registry in which every row is
        unavailable, refuses instead of reporting a clean run."""
        hollow = tuple(dict(spec, kind="unavailable", why=spec.get("why", "declared unavailable"),
                            moves_it=spec.get("moves_it", "n/a"))
                       for spec in CONFORMANCE_CHECKS)
        with self.assertRaises(ConformanceRefused) as caught:
            run_conformance(self.env, checks=hollow)
        self.assertIn("establishes nothing", str(caught.exception))

    # ==============================================================================================
    #  THE FAIL OUTCOME IS REACHABLE -- THREE NEGATIVE CONTROLS
    # ==============================================================================================

    def test_a_store_without_its_ignore_rule_fails_the_packaging_check(self):
        """A doctored checkout whose `.gitignore` has lost one store's root-anchored rule. The
        check must report `fail` -- not `unavailable`, and not a pass with a note."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rules = (ROOT / ".gitignore").read_text(encoding="utf-8")
            broken = "\n".join(line for line in rules.splitlines() if line.strip() != "/memory/")
            (root / ".gitignore").write_text(broken + "\n", encoding="utf-8")
            env = _Env(root / "scratch", root=root, tracked=[])
            row = self._only(env, "package.private-stores-are-not-packaged")
        self.assertEqual(row["outcome"], FAIL)
        self.assertIn("store 'memory' has no root-anchored rule", row["detail"])

    def test_a_contract_test_id_that_names_nothing_fails_the_contracts_check(self):
        with mock.patch.object(rg, "LEGACY_TESTS",
                               tuple(rg.LEGACY_TESTS) + ("test_nothing.NoSuchTests.test_none",)):
            row = self._one("contracts.stub-conformance-ids-resolve")
        self.assertEqual(row["outcome"], FAIL)
        self.assertIn("test_nothing.NoSuchTests.test_none", row["detail"])

    def test_an_absent_generated_mirror_fails_the_docs_check(self):
        with mock.patch.object(sys.modules[__name__], "CONFORMANCE_DOC",
                               "docs/A-DOCUMENT-NOBODY-WROTE.md"):
            row = self._one("docs.generated-mirrors-carry-this-document")
        self.assertEqual(row["outcome"], FAIL)
        self.assertIn("A-DOCUMENT-NOBODY-WROTE.md", row["detail"])

    def test_a_check_that_blows_up_is_a_failure_and_never_an_honest_gap(self):
        """The route into `run_conformance`'s general `except`. A probe that raised is a probe
        that established nothing, and reporting it as `unavailable` would let a broken check
        wear the same word as a real, named, acted-upon gap."""
        spec = [dict(s) for s in CONFORMANCE_CHECKS
                if s["kind"] == "run" and s["id"] != "contracts.payload-is-closed"][:1]
        control = [dict(s) for s in CONFORMANCE_CHECKS
                   if s["id"] == "contracts.payload-is-closed"]

        def explode(env):
            raise RuntimeError("the probe itself is broken")

        report = run_conformance(
            self.env, checks=spec + control,
            runners=dict(_RUNNERS, **{spec[0]["id"]: explode}))
        row = [r for r in report["checks"] if r["id"] == spec[0]["id"]][0]
        self.assertEqual(row["outcome"], FAIL)
        self.assertIn("the check itself raised RuntimeError", row["detail"])
        self.assertEqual(report["counts"][UNAVAILABLE], 0)

    def test_a_missing_runner_is_a_failure_rather_than_a_silently_skipped_check(self):
        spec = [dict(s) for s in CONFORMANCE_CHECKS
                if s["kind"] == "run" and s["id"] != "contracts.payload-is-closed"][:1]
        control = [dict(s) for s in CONFORMANCE_CHECKS
                   if s["id"] == "contracts.payload-is-closed"]
        runners = {k: v for k, v in _RUNNERS.items() if k != spec[0]["id"]}
        report = run_conformance(self.env, checks=spec + control, runners=runners)
        row = [r for r in report["checks"] if r["id"] == spec[0]["id"]][0]
        self.assertEqual(row["outcome"], FAIL)
        self.assertIn("no runner is registered", row["detail"])

    def test_a_run_that_cannot_ask_git_fails_the_packaging_check_rather_than_skipping_it(self):
        """The route into the packaging check's own `tracked is not None` guard. `packaging_review`
        degrades a git it cannot reach to a NOTE, so a check that just read its findings would
        pass while vouching for only half of what it claims."""
        env = _Env(self.env.tmp / "no-git", root=ROOT, tracked=None)
        row = self._only(env, "package.private-stores-are-not-packaged")
        self.assertEqual(row["outcome"], FAIL)
        self.assertIn("cannot vouch for the tracked half", row["detail"])

    def _only(self, env, check_id):
        """One check against a doctored env, with a control that passes there too."""
        specs = [dict(s) for s in CONFORMANCE_CHECKS
                 if s["id"] in (check_id, "contracts.payload-is-closed")]
        report = run_conformance(env, checks=specs)
        outcomes = {row["id"]: row["outcome"] for row in report["checks"]}
        self.assertEqual(outcomes["contracts.payload-is-closed"], PASS,
                         "the control did not pass, so the doctored result proves nothing")
        return [row for row in report["checks"] if row["id"] == check_id][0]

    # ==============================================================================================
    #  THE UNAVAILABLE OUTCOME, NAMED AND DERIVED WHERE IT CAN BE
    # ==============================================================================================

    def test_every_unavailable_check_says_what_is_missing_and_what_would_produce_it(self):
        """An unavailable row that did not say what act would move it is a gap nobody can
        close, which is a worse record than no row at all."""
        unavailable = [row for row in self.report["checks"] if row["outcome"] == UNAVAILABLE]
        self.assertTrue(unavailable)
        for row in unavailable:
            with self.subTest(check=row["id"]):
                self.assertGreater(len(row["why"]), 120, row["id"])
                self.assertGreater(len(row["moves_it"]), 40, row["id"])
                self.assertEqual(row["detail"], row["why"])

    def test_the_unavailable_enforcement_rows_are_derived_from_their_owner_not_typed(self):
        """`caps.confining-ledgered-dispatch` and `rollback.live-rollback-of-a-running-pointer`
        are unavailable because one constant is False. If somebody wires it, this fails, and the
        rows have to be reclassified rather than going on reading `unavailable` by habit."""
        self.assertIs(self.env.we.CONFINED_DISPATCH_WIRED, False)
        self.assertEqual(list(self.env.dp.DEFERRED_MODES), ["canary", "active"])
        self.assertNotIn("canary", self.env.dp.SELECTION_MODES)
        rows = {row["id"]: row for row in self.report["checks"]}
        for check_id in ("caps.confining-ledgered-dispatch",
                         "rollback.live-rollback-of-a-running-pointer"):
            with self.subTest(check=check_id):
                self.assertEqual(rows[check_id]["outcome"], UNAVAILABLE)
                self.assertIn("CONFINED_DISPATCH_WIRED", rows[check_id]["why"])

    def test_detecting_a_confinement_backend_is_not_certifying_one(self):
        """Why `caps.os-enforcement-sentinels` is unavailable rather than passing: this host may
        well report an enforced profile, and `certify_profile` still certifies nothing without a
        sentinel report, which this run did not produce."""
        ep = self.env.ep
        status = ep.protected_profile_status()
        self.assertIn(status.status, (ep.PROFILE_ENFORCED, ep.PROFILE_UNAVAILABLE))
        for report in ({}, {"status": ep.PROFILE_ENFORCED, "backend": "sandbox-exec",
                            "controlled_tree_intact": True, "sentinels": ()}):
            verdict = ep.certify_profile(report)
            self.assertFalse(verdict["certified"], verdict)
        row = {r["id"]: r for r in self.report["checks"]}["caps.os-enforcement-sentinels"]
        self.assertIn("sentinel", row["why"].lower())

    def test_no_check_that_runs_here_reaches_a_network_module(self):
        """The runnable checks again, with every network module refused at the import hook. One
        that reached for a transport would raise, which `run_conformance` reports as a FAIL
        rather than swallowing. The two excluded checks are the two that legitimately spawn
        read-only git or load the whole test suite through the loader."""
        excluded = ("contracts.stub-conformance-ids-resolve",
                    "package.private-stores-are-not-packaged")
        with tempfile.TemporaryDirectory() as tmp, refusing_imports(rg.NETWORK_IMPORTS) as blocked:
            env = _Env(tmp)
            report = run_conformance(env, checks=tuple(
                spec for spec in CONFORMANCE_CHECKS
                if spec["kind"] == "run" and spec["id"] not in excluded))
        self.assertEqual([row["id"] for row in report["checks"] if row["outcome"] != PASS], [])
        self.assertEqual(blocked, [], f"a conformance check reached for {blocked}")

    # ==============================================================================================
    #  THE DOCUMENT AND THE RUN DO NOT DRIFT
    # ==============================================================================================

    def test_the_document_states_every_check_with_the_outcome_this_run_derived(self):
        self.assertTrue(self.doc_path.is_file(),
                        f"{CONFORMANCE_DOC} is absent; it is this task's other half")
        stated = document_rows(self.doc)
        derived = {row["id"]: (row["area"], row["outcome"]) for row in self.report["checks"]}
        self.assertEqual(stated, derived,
                         "the conformance document and the run that produces it disagree")

    def test_the_documents_counts_are_the_runs_counts(self):
        counts = self.report["counts"]
        line = (f"{counts[PASS]} passed, {counts[FAIL]} failed, "
                f"{counts[UNAVAILABLE]} unavailable")
        self.assertIn(line, self.doc,
                      f"the document does not carry the line {line!r} this run derived")

    def test_the_document_names_every_unavailable_check_in_its_own_section(self):
        """Counting them is not naming them: a reader has to be able to see WHICH ones."""
        parts = self.doc.split("## What this run could not establish", 1)
        self.assertEqual(len(parts), 2, "the document has no section for what it could not do")
        for check_id in self.report["unavailable"]:
            with self.subTest(check=check_id):
                self.assertIn(f"`{check_id}`", parts[1])

    def test_the_document_makes_no_performance_claim_and_activates_nothing(self):
        lowered = self.doc.lower()
        for word in ("speedup", "win rate", "winrate", "faster than", "cheaper than",
                     "% better", "outperform"):
            self.assertNotIn(word, lowered, f"the document claims {word!r}")
        self.assertIn("activates nothing", lowered)
        self.assertIn("no capability row moves because of this run", lowered)

    def test_every_named_area_carries_a_check_and_no_check_invents_an_area(self):
        areas = {spec["area"] for spec in CONFORMANCE_CHECKS}
        self.assertEqual(sorted(areas), sorted(CONFORMANCE_AREAS))
        for area in CONFORMANCE_AREAS:
            with self.subTest(area=area):
                self.assertIn(f"`{area}`", self.doc)

    def test_the_check_registry_is_closed_and_every_runnable_check_has_a_runner(self):
        ids = [spec["id"] for spec in CONFORMANCE_CHECKS]
        self.assertEqual(len(ids), len(set(ids)), "a duplicated check id")
        base = {"id", "area", "kind", "question"}
        for spec in CONFORMANCE_CHECKS:
            with self.subTest(check=spec["id"]):
                self.assertIn(spec["kind"], ("run", "unavailable"))
                extra = {"why", "moves_it"} if spec["kind"] == "unavailable" else set()
                self.assertEqual(set(spec), base | extra)
                if spec["kind"] == "run":
                    self.assertIn(spec["id"], _RUNNERS)
        self.assertEqual(sorted(_RUNNERS),
                         sorted(spec["id"] for spec in CONFORMANCE_CHECKS
                                if spec["kind"] == "run"))

    def test_the_document_says_how_to_reproduce_the_run_and_bumps_no_existing_version(self):
        self.assertIn("test_decision_release_matrix.JevFreeConformanceTests", self.doc)
        self.assertIn(CONFORMANCE_VERSION, self.doc)
        for other in (rg.GATE_VERSION, self.env.we.ACTIVATION_VERSION,
                      self.env.dc.CONTRACT_VERSION, self.env.al.LEDGER_VERSION):
            self.assertNotEqual(CONFORMANCE_VERSION, other)



# ==================================================================================================
#  D30 -- THE V1 HANDOFF, CHECKED AGAINST THE TREE IT DESCRIBES
# ==================================================================================================
#
# The task's own declared check is `assert 'deferred' in t and 'not authorization' in t and
# 'rollback' in t` -- a bare substring scan over the document. This kit has already shipped two
# defects of exactly that shape: prose describing a guard satisfied a scan looking for the guard,
# and a search for a call inside a function body matched the DOCSTRING explaining the check. So
# the declared check is treated here as a floor, and the class below is the enforcement.
#
# WHAT IT ASSERTS. Not that the handoff contains words -- that its CLAIMS still hold against the
# tree: every repository path, command and test id it names resolves; the constants it quotes are
# still those values; its conformance figures and its six unavailable checks are the conformance
# DOCUMENT's own, so the two cannot drift; the readiness codes it prints are the ten the module
# emits; the redaction scope is the module's; the task inventory is the kit's, with nothing listed
# that the kit still calls pending or blocked; every deferred item is still `pending` where its own
# kit records it; and the release checklist points a reader at both documents.
#
# WHAT IT DOES NOT ASSERT. That any sentence of the handoff is TRUE. A document can be wrong in
# ways no test reaches; this class stops it rotting silently, which is a smaller claim.
#
# Every assertion is paired with an anti-vacuity floor. A scan over "every path the document names"
# passes trivially over a document that names none, so each collector asserts it found a plausible
# number of things before it checks them.

HANDOFF_DOC = "docs/DECISION-IMPROVEMENT-V1-HANDOFF.md"
KIT_TASKS = ".claude/kits/decision-improvement-v1/TASKS.md"
OPTIONAL_TASKS = "tasks/kits/decision-improvement/OPTIONAL-TASKS.md"
V2_TASKS = ".claude/kits/decision-improvement-v2/TASKS.md"

#: The statuses a kit task may carry. `kit_contract` owns the vocabulary; it is re-spelled here
#: only to assert that a ledger this class reads has not grown a sixth word.
TASK_STATUSES = ("pending", "in-progress", "done", "blocked")

_BACKTICKED = re.compile(r"`([^`\n]+)`")
_REPO_PATH = re.compile(
    r"^(?:bin|tests|docs|docs-src|docs-site|primitives|skills|data|tasks|\.claude)"
    r"/[A-Za-z0-9._/\-]+$")
_TEST_ID = re.compile(r"\btest_[a-z0-9_]+(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_HANDOFF_CMD = re.compile(r"python3 (bin/[a-z_]+\.py)(?: ([a-z][a-z-]*))?")
_HANDOFF_TASK_ROW = re.compile(r"^\| (D\d+) \|", re.M)
_INDENTED_CODE_TOKEN = re.compile(r"^    ([a-z][a-z0-9-]+)$", re.M)
_TABLE_ID = re.compile(r"^\| `([a-z0-9.\-]+)` \|", re.M)
_WORD_NUMBER = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def task_statuses(text):
    """A kit TASKS.md -> `{id: status}`, read off the two fields the contract defines."""
    out, current = {}, None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- id: "):
            current = stripped[len("- id: "):].strip()
        elif stripped.startswith("- status: ") and current:
            out[current] = stripped[len("- status: "):].strip()
            current = None
    return out


def _section(text, heading):
    """The body between `heading` and the next heading of the same or higher level."""
    start = text.find(heading)
    if start < 0:
        return ""
    body = text[start + len(heading):]
    end = len(body)
    for marker in ("\n## ", "\n### "):
        found = body.find(marker)
        if 0 <= found < end:
            end = found
    return body[:end]


class V1HandoffTests(unittest.TestCase):
    """D30 -- the Release 1 handoff, asserted against the tree rather than scanned for words."""

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / HANDOFF_DOC
        cls.doc = cls.path.read_text(encoding="utf-8")
        cls.flat = " ".join(cls.doc.split())
        cls.lowered = cls.doc.lower()
        cls.conformance = (ROOT / CONFORMANCE_DOC).read_text(encoding="utf-8")
        cls.we = _load("workflow_eval", alias="workflow_eval_d30")
        cls.td = _load("training_data", alias="training_data_d30")

    # ----------------------------------------------------------------------------------------
    #  EVERYTHING IT NAMES HAS TO EXIST
    # ----------------------------------------------------------------------------------------

    def test_every_repository_path_the_handoff_names_resolves_on_disk(self):
        """A handoff whose file names have rotted is worse than no handoff: it sends the next
        reader to a path that no longer exists and reads as authoritative while doing it."""
        named = sorted({token for token in _BACKTICKED.findall(self.doc)
                        if _REPO_PATH.match(token)})
        self.assertGreaterEqual(len(named), 15,
                                "the handoff names almost no repository path -- either it was "
                                "gutted or this collector stopped matching")
        missing = [name for name in named if not (ROOT / name).exists()]
        self.assertEqual(missing, [], f"the handoff names path(s) that do not exist: {missing}")

    def test_every_test_id_the_handoff_names_resolves_to_real_cases(self):
        """THE DEFECT THIS CLASS EXISTS FOR. Naming a test is the cheapest way to make a
        document look enforced, and a renamed or deleted class leaves the sentence standing.
        `resolve_test_ids` returns 0 for an id that loads nothing, so a zero here is a rotten
        citation rather than an exception."""
        ids = sorted({tid.rstrip(".") for tid in _TEST_ID.findall(self.doc)
                      if "." in tid.rstrip(".")})
        self.assertGreaterEqual(len(ids), 5, "the handoff cites almost no test")
        counts = rg.resolve_test_ids(ids)
        rotten = sorted(tid for tid, count in counts.items() if count == 0)
        self.assertEqual(rotten, [], f"the handoff names test id(s) that resolve to nothing: "
                                     f"{rotten}")

    def test_every_command_the_handoff_names_exists_with_the_subcommand_it_names(self):
        """The same rot, one surface over: a subcommand renamed out from under a runbook."""
        named = sorted(set(_HANDOFF_CMD.findall(self.doc)))
        self.assertGreaterEqual(len(named), 10, "the handoff names almost no command")
        findings = []
        for script, sub in named:
            if not (ROOT / script).is_file():
                findings.append(f"{script} does not exist")
                continue
            if not sub:
                continue
            subs = rg._subcommands(rg._sibling(Path(script).stem))
            if subs and sub not in subs:
                findings.append(f"`{script} {sub}` is not one of {sorted(subs)}")
        self.assertEqual(findings, [], f"the handoff names command(s) that have rotted: {findings}")

    # ----------------------------------------------------------------------------------------
    #  THE CONSTANTS IT QUOTES
    # ----------------------------------------------------------------------------------------

    def test_the_constants_the_handoff_quotes_still_hold_the_values_it_quotes(self):
        """Both halves, because either one alone is satisfiable by a lie: the module still holds
        the value, AND the document still says so. A flipped constant with an unchanged handoff
        fails here rather than shipping as a document that describes a different repository."""
        self.assertIs(self.we.CONFINED_DISPATCH_WIRED, False)
        self.assertIs(self.td.COLLECTION_ENABLED, False)
        self.assertIs(self.td.CAPTURE_WIRED, False)
        for sentence in (
                "`workflow_eval.CONFINED_DISPATCH_WIRED` is `False`",
                "| `training_data.COLLECTION_ENABLED` | `False` |",
                "| `training_data.CAPTURE_WIRED` | `False` |",
                "`build_dataset` | requires an explicit `store_dir`",
        ):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, self.flat)

    def test_the_handoff_reports_the_capture_hook_as_uncalled_and_the_tree_agrees(self):
        """`CAPTURE_WIRED` is a LABEL, not the lock -- the handoff says so, and what actually
        keeps the hook uncalled is the structural test it cites. Asserted here by resolving that
        test id, so the sentence cannot outlive the check it leans on.

        THE WORDING IS THE ASSERTION, and an earlier version of this test pinned a FALSE one.
        "no call site anywhere in the tree" is not true and never was: `_demo` calls
        `capture_hook` six times, once with `enabled=True` into a `tempfile.mkdtemp` store, and
        the tests call it too. What the structural guard proves is narrower and is the real
        claim -- it skips `training_data.py` itself and pins the set of OTHER `bin/` modules
        naming it -- so the document must say "no PRODUCTION call site" and name the demo and
        the tests as the call sites that do exist. The false phrasing is refused explicitly
        below, because a test that enforces a falsehood makes it load-bearing.
        """
        self.assertIn("there is no production call site; the only call sites are its own "
                      "offline `demo` and its tests", self.flat)
        self.assertIn("`python3 bin/training_data.py demo` does call the hook", self.flat)
        self.assertNotIn("no call site anywhere in the tree", self.flat)
        self.assertIn("not \"three locks\"", self.flat)
        structural = ("test_training_data.SnapshotTests"
                      ".test_no_production_path_calls_the_capture_hook")
        self.assertIn(structural, self.doc)
        self.assertGreater(rg.resolve_test_ids([structural])[structural], 0)
        # The same correction in the generated release block's own label, so the two surfaces
        # cannot drift back apart: the gate renders this string into `docs/RELEASE.md`.
        self.assertIn("there is no production call site", rg.TRAINING_NOT_AVAILABLE_LABEL)
        self.assertNotIn("anywhere in the tree", rg.TRAINING_NOT_AVAILABLE_LABEL)

    # ----------------------------------------------------------------------------------------
    #  AGREEMENT WITH THE CONFORMANCE DOCUMENT
    # ----------------------------------------------------------------------------------------

    def test_the_conformance_figures_the_handoff_states_are_the_conformance_documents_own(self):
        """Cross-document, in the direction that matters. D29's class already pins its document
        against a live run; this pins the handoff against that document, so the chain from the
        run to the sentence a person reads has no unchecked link in it."""
        rows = document_rows(self.conformance)
        self.assertGreaterEqual(len(rows), 20, "the conformance table did not parse")
        tally = {outcome: sum(1 for _, (_, o) in rows.items() if o == outcome)
                 for outcome in CONFORMANCE_OUTCOMES}
        match = re.search(r"\*\*(\d+) pass, (\d+) fail, (\d+) unavailable across (\d+) checks\*\*",
                          self.flat)
        self.assertIsNotNone(match, "the handoff no longer states the conformance figures")
        stated = [int(group) for group in match.groups()]
        self.assertEqual(stated, [tally[PASS], tally[FAIL], tally[UNAVAILABLE], len(rows)])

    def test_the_unavailable_checks_the_handoff_lists_are_exactly_the_documents(self):
        """Set equality in both directions. Dropping one would let the handoff read cleaner than
        the run was; inventing one would name a gap nobody found."""
        expected = {cid for cid, (_, outcome) in document_rows(self.conformance).items()
                    if outcome == UNAVAILABLE}
        self.assertEqual(len(expected), 6, "the conformance document no longer has six gaps")
        section = _section(self.doc, "The six checks that produced no evidence")
        listed = set(_TABLE_ID.findall(section))
        self.assertEqual(listed, expected)

    def test_the_handoff_states_that_conformance_covers_this_checkout_only(self):
        for sentence in ("this checkout only", "one platform, one Python, no installed copy"):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, self.flat)

    # ----------------------------------------------------------------------------------------
    #  TRAINING DATA: THE CODES, NOT THE TALLY
    # ----------------------------------------------------------------------------------------

    def test_the_readiness_codes_the_handoff_prints_are_the_ten_the_module_emits(self):
        """The handoff's own argument is that the GATE TALLY is a property of the input shape and
        the CODES are the unconditional statement. That argument is only worth anything while the
        printed codes are the module's, so they are compared as a set."""
        listed = set(_INDENTED_CODE_TOKEN.findall(self.doc))
        self.assertEqual(listed, set(self.td.readiness_codes()))

    def test_the_handoff_cites_the_codes_rather_than_the_tally_as_what_denies_readiness(self):
        self.assertIn("Cite the codes; never cite the tally.", self.flat)
        self.assertIn("The tally is a property of the input shape, not of the mechanism",
                      self.flat)
        # The one tally it does state is labelled with the input shape it describes.
        self.assertIn("The standing report \u2014 no records, an empty store \u2014 reads 0 met, "
                      "4 unmet, 7 unknown.", self.flat)

    def test_the_redaction_scope_the_handoff_states_is_the_modules(self):
        """Two covered fields and ten uncovered ones, read from the owner. A handoff that
        widened the covered set on paper would be claiming a privacy property nobody built."""
        covered = re.search(r"`training_data\.REDACTED_FIELDS` names \*\*(\w+)\*\*", self.flat)
        uncovered = re.search(r"`training_data\.NOT_REDACTED_FIELDS` names \*\*(\w+)\*\*",
                              self.flat)
        self.assertIsNotNone(covered)
        self.assertIsNotNone(uncovered)
        self.assertEqual(_WORD_NUMBER[covered.group(1)], len(self.td.REDACTED_FIELDS))
        self.assertEqual(_WORD_NUMBER[uncovered.group(1)], len(self.td.NOT_REDACTED_FIELDS))
        self.assertEqual(self.td.NOT_REDACTED_FIELDS[:2],
                         ("question.spec.question", "question.spec.rubric"))
        self.assertIn("No sentence here says that no secret can get through", self.flat)

    def test_revocation_reach_is_the_owners_and_the_handoff_never_claims_removal(self):
        """`identified-only` is the whole point of this row and the easiest thing in the document
        to soften by accident."""
        for artifact, reach in self.td.REVOCATION_REACH.items():
            with self.subTest(artifact=artifact):
                self.assertIn(f"| `{artifact}` | `{reach}` |", self.doc)
        self.assertEqual(self.td.REVOCATION_REACH["trained-checkpoint"], "identified-only")
        self.assertIn("Revocation removes nothing from a model", self.flat)
        for claim in ("removes it from the model", "removed from the model",
                      "erased from the model", "deleted from the model"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, self.lowered)

    def test_the_operator_exposure_obligation_is_open_and_its_code_still_exists(self):
        """The residual hazard is asymmetric and the handoff states it as an obligation rather
        than a gate. The code that carries the remedy is the module's, so it is checked."""
        self.assertIn("exposure-not-recorded-in-the-eval-store", self.td.readiness_codes())
        self.assertIn("**This is an open operator obligation, not a closed gate.**", self.flat)

    # ----------------------------------------------------------------------------------------
    #  THE INVENTORY AND THE DEFERRED REGISTER
    # ----------------------------------------------------------------------------------------

    def test_the_task_inventory_is_the_kits_and_lists_nothing_still_pending_or_blocked(self):
        """Both directions. A task added to the kit and absent from the handoff fails here, and
        so does a handoff row for a task the kit has not finished."""
        statuses = task_statuses((ROOT / KIT_TASKS).read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(statuses), 30)
        for task_id, status in statuses.items():
            with self.subTest(task=task_id):
                self.assertIn(status, TASK_STATUSES)
        listed = set(_HANDOFF_TASK_ROW.findall(self.doc))
        self.assertEqual(listed, set(statuses))
        unfinished = sorted(tid for tid in listed
                            if statuses[tid] in ("pending", "blocked"))
        self.assertEqual(unfinished, [], f"the handoff lists unfinished task(s): {unfinished}")

    def test_every_deferred_item_is_still_pending_where_its_own_kit_records_it(self):
        """The defer register is only honest while the thing it defers has not quietly started.
        Both source kits are read; a status that moved fails here rather than in a reader's
        expectations."""
        sources = {OPTIONAL_TASKS: ("O01", "O02", "O03", "O04"),
                   V2_TASKS: ("J01", "J02", "J03", "J04")}
        for source, ids in sources.items():
            statuses = task_statuses((ROOT / source).read_text(encoding="utf-8"))
            for task_id in ids:
                with self.subTest(task=task_id):
                    self.assertIn(task_id, statuses, f"{source} no longer records {task_id}")
                    self.assertEqual(statuses[task_id], "pending")
                    self.assertIn(task_id, self.doc)
        self.assertIn("**R08 families**", self.doc)
        self.assertIn("**M01**", self.doc)
        self.assertIn("Entry gate", self.doc)
        self.assertIn("never authorizes Release 2", self.flat)

    def test_the_deferred_register_names_what_is_not_deferred_beside_what_is(self):
        """Cursor's shipped implementation and existing concurrency are intact; only new adaptive
        extension is deferred. Reporting them as absent would be a second, different untruth, and
        the registry rows that say so are checked rather than trusted."""
        registry = json.loads((ROOT / "primitives" / "harness-capabilities.json")
                              .read_text(encoding="utf-8"))
        rows = registry["harnesses"]["cursor"]["capabilities"]
        verified = sorted(name for name, row in rows.items()
                          if row.get("verified") == "supported")
        self.assertGreaterEqual(len(verified), 6, "Cursor's verified rows have gone")
        self.assertEqual(rows["adaptive_decisions"]["verified"], "unknown")
        self.assertIn("Cursor's current CLI implementation is present and verified", self.flat)
        self.assertIn("existing concurrency, Cursor's shipped CLI implementation, and the four "
                      "drivers' native loops", self.flat)

    # ----------------------------------------------------------------------------------------
    #  WHAT THE DOCUMENT IS NOT
    # ----------------------------------------------------------------------------------------

    def test_the_release_checklist_now_points_a_reader_at_both_release_documents(self):
        """D29's named gap, closed here. `release_gate check` resolves every command the
        checklist names, so this also proves the new row did not name a rotten one."""
        evidence = " ".join(row["evidence"] for row in rg.CHECKLIST)
        self.assertIn(CONFORMANCE_DOC, evidence)
        self.assertIn(HANDOFF_DOC, evidence)
        self.assertEqual(rg.command_findings(ROOT), [])
        self.assertIsNone(rg.check_release_doc(ROOT),
                          "the generated block of docs/RELEASE.md is stale; "
                          "run `python3 bin/release_gate.py build`")

    def test_the_handoff_makes_no_performance_claim_and_takes_no_release_action(self):
        """A token scan, and it is labelled as one. The whole-document sweep
        `workflow_eval.assert_no_gain_claim` is deliberately NOT applied: one of its spellings is
        a word in the name of the work, so it would refuse an honest document. That limitation is
        disclosed in the handoff rather than patched around by widening an exemption."""
        for word in ("speedup", "win rate", "winrate", "faster than", "cheaper than",
                     "% better", "outperform", "roi"):
            with self.subTest(word=word):
                self.assertNotIn(word, self.lowered)
        for sentence in ("not authorization", "no release action", "activates nothing",
                         "moves no capability row"):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, self.lowered)
        self.assertIn("`unknown` in the registry means no", self.flat)
        self.assertIn("No trial has run under any of this work.", self.flat)

    def test_the_accepted_commit_is_reported_as_a_branch_fact_and_not_as_a_release(self):
        """A handoff that read as though its commit were released would be the one untruth that
        costs the most, because every other statement here is scoped to it."""
        self.assertIn("812a76e0f6caa712c15124a8a0ba4bd3872a4ca3", self.doc)
        self.assertIn("**not merged and not pushed**", self.doc)
        self.assertIn("None of it is a property of `main`", self.flat)

    def test_the_scope_sentence_admits_what_is_not_a_property_of_the_reported_commit(self):
        """The document, the checklist row that cites it, the class that enforces it and the D21
        hardening all land in the commit that CARRIES the document, which is later than the one
        it reports. "Everything this document describes is a property of that commit" was
        therefore false for those four, and a reader at HEAD was misled by it. No sha is asserted
        here beyond the reported one: a digit written into the document goes stale on the next
        commit, so what is pinned is the FORMULATION that stays true plus the measurement."""
        self.assertIn("A document cannot be wholly a property of a commit that precedes it.",
                      self.flat)
        self.assertIn("are properties of the commit that CARRIES this file, which is later than "
                      "the commit above and one further ahead of `main`", self.flat)
        self.assertIn("`git log main..HEAD --oneline | wc -l` is the measurement", self.flat)
        self.assertNotIn("Everything this document describes is a property of that commit",
                         self.flat)

    def test_the_register_names_the_three_limits_the_last_phase_review_found(self):
        """The reader-facing register, not the kit's notes. Each of the three was proven by
        mutation or by running the two gates, and each was recorded only where readers do not
        look. Asserted phrase by phrase so a failure says WHICH limit went missing rather than
        that some sweep no longer matched."""
        for phrase in (
                # The module-level write the function sweep cannot see.
                "would execute at import, and no guard here would see it",
                "**bounded, not unbounded**",
                "The shipped `bin/improvement_loop.py` is itself clean.",
                # What a green release gate does and does not establish.
                "**A green release gate does not establish that any decision module works.**",
                "**one version string each, and calls no function in any of them.**",
                # The two gates that disagree, with the staleness attributed away from this kit.
                "**Two gates disagree on this checkout, and the release gate does not consult "
                "installed harness freshness.**",
                "**pre-existing and is not this release's**",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.flat)
        # The sweep the first limit is about has to be the one that exists.
        sweep = "test_decision_workbench.BoundedProposalTests"
        self.assertIn(sweep, self.doc)
        self.assertGreater(rg.resolve_test_ids([sweep])[sweep], 0)
        # And the second limit's subject is still coupled the way it says -- through version
        # constants in `VERSION_SOURCES`, one row per named object, and nothing else.
        coupled = {module for _, module, _ in rg.VERSION_SOURCES}
        for module in ("decision_contract", "decision_provider", "decision_eval",
                       "decision_context"):
            with self.subTest(module=module):
                self.assertIn(module, coupled)

    def test_the_conformance_documents_closed_gap_carries_a_dated_correction(self):
        """D30 registered the checklist row that this gap says is missing, and the conformance
        document carries no revision pin -- so the sentence read as present-tense fact. It is
        annotated forward rather than rewritten, because rewriting a dated artifact to match a
        later tree is backdating. Both halves are asserted: the stale present-tense claim is gone
        and the correction is dated."""
        conformance = " ".join(self.conformance.split())
        self.assertNotIn("This document is not cited by `release_gate.CHECKLIST`", conformance)
        self.assertIn("**Correction recorded 2026-09-21: closed.**", conformance)
        self.assertIn("when this gap was written on 2026-09-20", conformance)
        evidence = " ".join(row["evidence"] for row in rg.CHECKLIST)
        self.assertIn(CONFORMANCE_DOC, evidence)

    def test_the_declared_task_check_passes_and_is_named_as_a_floor(self):
        """The task's own check, run here so it cannot be the only place it was run -- beside the
        sentence saying what it is worth."""
        for needle in ("deferred", "not authorization", "rollback"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.lowered)
        self.assertIn("The declared task check is a text scan and is worth exactly what a text "
                      "scan is worth.", self.flat)
        self.assertIn("test_decision_release_matrix.V1HandoffTests", self.doc)

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
