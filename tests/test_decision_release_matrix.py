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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
