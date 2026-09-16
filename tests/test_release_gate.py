"""bin/release_gate.py -- the release matrix computed from the evidence, never typed.

What these tests pin: every version in the matrix comes from the module or manifest that owns
it; every registry row keeps its three states; the stub-conformance column and the
installed-client column never merge (a passing test run cannot turn an `unknown` row into
`verified`); every test id the contract map names resolves to a real test; the packaging review
finds a store without its rule, a tracked file under one, an unclassified path, a manifest
mismatch, an unpinned action, and an unhashed package; the generated block is deterministic and
its drift is a finding; `reverify` partitions rows by date and edits nothing; every command the
checklist cites exists. The real tree passes the whole gate.

No test here reads a home directory, opens a store, or spawns a harness client. The gate's own
processes are read-only git verbs and, where a test asks for it, this repository's test loader
in-process on a temp module.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rg = _load("release_gate_under_test", BIN_DIR / "release_gate.py")
ha = _load("harness_adapter_for_gate", BIN_DIR / "harness_adapter.py")

MINIMAL_WORKFLOW = """\
# a comment that mentions pages: write and id-token: write on purpose
name: docs-site
permissions:
  contents: read
jobs:
  build:
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
  deploy:
    permissions:
      pages: write
      id-token: write
    steps:
      - uses: actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e # v4.0.5
"""

MINIMAL_REQUIREMENTS = """\
mkdocs==1.6.1 \\
    --hash=sha256:aaaa
mkdocs-material==9.7.7 \\
    --hash=sha256:bbbb
"""


class SmokeTarget(unittest.TestCase):
    """A real test the in-process runner can be pointed at."""

    def test_passes(self):
        self.assertTrue(True)


def _fixture_root(tmp, **overrides):
    """A minimal repository root the packaging review can read. Overrides replace the text of
    a file by relative path; a value of None deletes it."""
    root = Path(tmp)
    rd = _load("runtime_data_for_gate", BIN_DIR / "runtime_data.py")
    files = {
        ".gitignore": "".join(f"/{name}/\n" for name in rd.STORES) + "/value-report*.html\n",
        ".claude-plugin/plugin.json": json.dumps({"name": "polytropos", "version": "0.5.3",
                                                  "description": "d"}),
        ".claude-plugin/marketplace.json": json.dumps({"name": "polytropos-local", "plugins": [
            {"name": "polytropos", "description": "d"}]}),
        ".codex-plugin/plugin.json": json.dumps({"name": "polytropos", "version": "0.5.3+codex.1"}),
        ".agents/plugins/marketplace.json": json.dumps({"name": "polytropos-local",
                                                        "plugins": [{"name": "polytropos"}]}),
        ".github/workflows/docs-site.yml": MINIMAL_WORKFLOW,
        "docs-src/requirements.txt": MINIMAL_REQUIREMENTS,
        "SETUP.md": "| `python3` (3.11+) |\n",
    }
    files.update(overrides)
    for rel, text in files.items():
        path = root / rel
        if text is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


TRACKED_OK = ["bin/x.py", "tests/test_x.py", "docs/A.md", ".gitignore", "README.md"]


class ModuleShapeTests(unittest.TestCase):
    def test_module_carries_no_process_primitive_or_home_path(self):
        """Uses, not words: the contract map quotes test names that carry the word
        `subprocess`, so this matches an import or an attribute access, never a string."""
        source = (BIN_DIR / "release_gate.py").read_text(encoding="utf-8")
        for pattern in (r"^\s*(?:import|from)\s+subprocess\b", r"\bsubprocess\.\w+\(",
                        r"\bos\.system\(", r"\bPath\.home\(", r"\bexpanduser\(",
                        r"\burlopen\("):
            self.assertIsNone(re.search(pattern, source, re.M), pattern)

    def test_module_names_no_model_id_or_price(self):
        source = (BIN_DIR / "release_gate.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"claude-[a-z]+-\d|gpt-\d|\$\d", source))

    def test_git_read_refuses_a_verb_off_the_allowlist(self):
        with self.assertRaises(ValueError):
            rg.git_read(REPO_ROOT, "push")
        with self.assertRaises(ValueError):
            rg.git_read(REPO_ROOT, "commit", "-m", "x")

    def test_revision_reads_the_real_checkout(self):
        rev = rg.revision(REPO_ROOT)
        self.assertRegex(rev["sha"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(rev["dirty"], int)


class VersionTests(unittest.TestCase):
    def test_contract_versions_are_read_from_their_owners(self):
        rows = {r["contract"]: r for r in rg.contract_versions()}
        kc = _load("kit_contract_for_gate", BIN_DIR / "kit_contract.py")
        self.assertEqual(rows["task contract"]["version"], kc.CONTRACT_VERSION)
        self.assertEqual(rows["adapter contract"]["version"], ha.ADAPTER_VERSION)
        self.assertEqual(rows["release gate"]["version"], rg.GATE_VERSION)
        for row in rows.values():
            self.assertTrue(row["version"], row)

    def test_package_versions_read_manifests_pricing_and_toolchain(self):
        v = rg.package_versions(REPO_ROOT)
        self.assertEqual(v["plugin"]["name"], "polytropos")
        self.assertRegex(v["plugin"]["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(sorted(v["pricing"]), sorted(rg.PRICING_FILES))
        for entry in v["pricing"].values():
            self.assertRegex(entry["cached_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn("mkdocs-material", v["toolchain"])
        self.assertEqual(v["python_floor"], "3.11")
        self.assertTrue(v["matrix_pin"])


class MatrixTests(unittest.TestCase):
    def test_every_harness_row_keeps_its_three_states(self):
        matrix = rg.harness_matrix(REPO_ROOT)
        self.assertEqual(tuple(matrix), rg.HARNESSES)
        for harness, entry in matrix.items():
            self.assertTrue(entry["in_registry"], harness)
            self.assertTrue(entry["capabilities"], harness)
            for row in entry["capabilities"]:
                for key in ("product", "implemented", "verified"):
                    self.assertIn(row[key], ha.SUPPORT_STATES)
                self.assertEqual(row["effective"], ha.effective(row))

    def test_binary_names_come_from_the_drivers_own_parsers(self):
        ca = _load("cursor_adapter_for_gate", BIN_DIR / "cursor_adapter.py")
        self.assertEqual(rg.binary_name("cursor"), ca.BINARY)
        self.assertEqual(rg.binary_name("claude-code"), "claude")
        self.assertIsNone(rg.binary_name("stub"))

    def test_client_version_reads_not_recorded_until_a_row_names_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "primitives").mkdir()
            registry = json.loads((REPO_ROOT / "primitives" / "harness-capabilities.json").read_text())
            # The real codex rows carry a client version since the 2026-09-16 live run; the
            # shape under test is a harness with none, so strip them on the temp copy first.
            for row in registry["harnesses"]["codex"]["capabilities"].values():
                row.pop("client_version", None)
            (root / "primitives" / "harness-capabilities.json").write_text(json.dumps(registry))
            before = rg.harness_matrix(root, with_binaries=False)
            self.assertEqual(before["codex"]["client_version"], "not recorded")
            registry["harnesses"]["codex"]["capabilities"]["dispatch"]["client_version"] = "codex 1.2.3"
            (root / "primitives" / "harness-capabilities.json").write_text(json.dumps(registry))
            after = rg.harness_matrix(root, with_binaries=False)
            self.assertEqual(after["codex"]["client_version"], "codex 1.2.3")

    def test_role_support_is_kit_contracts(self):
        kc = _load("kit_contract_for_gate_roles", BIN_DIR / "kit_contract.py")
        matrix = rg.harness_matrix(REPO_ROOT, with_binaries=False)
        for harness in rg.HARNESSES:
            expected = {role: state for role, (state, _w) in kc.ROLE_SUPPORT[harness].items()}
            self.assertEqual(matrix[harness]["role_support"], expected, harness)

    def test_historical_matrix_is_summarised_and_never_rewritten(self):
        path = REPO_ROOT / "primitives" / "harness-matrix.json"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        hist = rg.historical_matrix(REPO_ROOT)
        self.assertTrue(hist["pin"])
        self.assertGreaterEqual(len(hist["rows"]), 4)
        for row in hist["rows"]:
            self.assertEqual(len(row["native"]) + len(row["fallback"]), 9, row["harness"])
        rg.render_block(REPO_ROOT)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


class ContractMapTests(unittest.TestCase):
    def test_every_contract_names_evidence_for_every_real_harness(self):
        for contract in rg.CONTRACTS:
            for harness in ("claude-code", "codex", "copilot", "cursor"):
                ids = contract["tests"].get(harness) or contract["tests"].get(rg.SHARED)
                self.assertTrue(ids, f"{contract['id']}: no tests for {harness} and none shared")

    def test_every_mapped_test_id_resolves_to_at_least_one_test(self):
        ids = set(rg.LEGACY_TESTS) | set(rg.NO_REAL_CLI_TESTS)
        for contract in rg.CONTRACTS:
            for cell in contract["tests"].values():
                ids.update(cell)
        resolved = rg.resolve_test_ids(sorted(ids))
        rotten = sorted(tid for tid, n in resolved.items() if not n)
        self.assertEqual(rotten, [], "these ids name no test any more")

    def test_legacy_and_no_real_cli_lists_are_populated(self):
        self.assertTrue(rg.LEGACY_TESTS)
        self.assertTrue(rg.NO_REAL_CLI_TESTS)

    def test_every_cited_capability_exists_in_the_registry(self):
        matrix = rg.harness_matrix(REPO_ROOT, with_binaries=False)
        for contract in rg.CONTRACTS:
            for harness, names in contract["capabilities"].items():
                rows = {r["name"] for r in matrix[harness]["capabilities"]}
                for name in names:
                    self.assertIn(name, rows, f"{contract['id']}: {harness}/{name}")

    def test_unresolved_id_is_reported_not_raised(self):
        resolved = rg.resolve_test_ids(["test_release_gate.NoSuchClass.test_x",
                                        "no_such_module.X.test_y",
                                        "test_release_gate.SmokeTarget.test_passes"])
        self.assertEqual(resolved["test_release_gate.NoSuchClass.test_x"], 0)
        self.assertEqual(resolved["no_such_module.X.test_y"], 0)
        self.assertEqual(resolved["test_release_gate.SmokeTarget.test_passes"], 1)

    def test_contracts_report_lists_unresolved_ids(self):
        broken = ({"id": "x", "title": "X", "steps": "00", "claim": "c", "capabilities": {},
                   "tests": {"codex": ("no_such_module.X.test_y",)}},)
        with mock.patch.object(rg, "CONTRACTS", broken):
            report = rg.contracts_report(REPO_ROOT)
        self.assertEqual(report["unresolved"], ["no_such_module.X.test_y"])


class StubVersusInstalledTests(unittest.TestCase):
    def test_installed_verdict_reads_the_registry_not_the_test_run(self):
        rows = {"dispatch": {"name": "dispatch", "verified": "unknown", "verified_on": None}}
        verdict = rg._installed_verdict(rows, ("dispatch",), ha)
        self.assertEqual(verdict["verdict"], "unknown")
        rows["dispatch"].update(verified="supported", verified_on="2026-09-06")
        self.assertEqual(rg._installed_verdict(rows, ("dispatch",), ha)["verdict"], "verified 2026-09-06")
        self.assertEqual(rg._installed_verdict(rows, ("absent",), ha)["verdict"], "missing row")
        own = rg._installed_verdict(rows, (), ha)
        self.assertEqual(own["verdict"], "polytropos's own")
        self.assertIn("stub conformance is the evidence", own["note"])

    def test_a_passing_run_never_changes_the_installed_column(self):
        passing = lambda ids: {"ran": len(ids), "failures": 0, "errors": 0, "skipped": 0,
                               "ok": True, "detail": ""}
        resolver = lambda ids: {tid: 1 for tid in ids}
        # `status` is a codex row nobody has run (its dispatch row was verified live on
        # 2026-09-16, which is exactly why this test must not lean on it).
        one = ({"id": "dispatch-failure", "title": "D", "steps": "07", "claim": "c",
                "capabilities": {"codex": ("status",)},
                "tests": {"codex": ("test_x.T.test_a",)}},)
        with mock.patch.object(rg, "CONTRACTS", one):
            report = rg.contracts_report(REPO_ROOT, run=True, resolver=resolver, runner=passing)
        cell = report["contracts"][0]["cells"]["codex"]
        self.assertTrue(cell["run"]["ok"])
        self.assertEqual(cell["installed_client"]["verdict"], "unknown")
        self.assertEqual(report["failed"], [])

    def test_a_failing_run_names_the_cell(self):
        failing = lambda ids: {"ran": len(ids), "failures": 1, "errors": 0, "skipped": 0,
                               "ok": False, "detail": "boom"}
        resolver = lambda ids: {tid: 1 for tid in ids}
        one = ({"id": "budget-admission", "title": "B", "steps": "08", "claim": "c",
                "capabilities": {}, "tests": {"cursor": ("test_x.T.test_a",)}},)
        with mock.patch.object(rg, "CONTRACTS", one), \
                mock.patch.object(rg, "LEGACY_TESTS", ()), mock.patch.object(rg, "NO_REAL_CLI_TESTS", ()):
            report = rg.contracts_report(REPO_ROOT, run=True, resolver=resolver, runner=failing)
        self.assertEqual(report["failed"], ["budget-admission/cursor"])

    def test_run_test_ids_runs_in_process_and_reports_failures(self):
        ok = rg.run_test_ids(["test_release_gate.SmokeTarget.test_passes"])
        self.assertEqual((ok["ran"], ok["ok"]), (1, True))
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "gate_fixture_failing.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n"
                "    def test_fail(self):\n        self.fail('meant to')\n", encoding="utf-8")
            bad = rg.run_test_ids(["gate_fixture_failing.T.test_fail"], tests_dir=tmp)
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["failures"], 1)
        self.assertIn("meant to", bad["detail"])
        sys.modules.pop("gate_fixture_failing", None)


class PackagingTests(unittest.TestCase):
    def test_minimal_root_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = rg.packaging_review(_fixture_root(tmp), tracked=TRACKED_OK)
        self.assertEqual(review["findings"], [], review)
        self.assertTrue(all(review["stores"].values()))

    def test_store_without_its_rule_is_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, **{".gitignore": "/memory/\n/value-report*.html\n"})
            review = rg.packaging_review(root, tracked=TRACKED_OK)
        self.assertTrue(any("'evals'" in f and "/evals/" in f for f in review["findings"]), review["findings"])
        self.assertFalse(review["stores"]["evals"])

    def test_tracked_file_under_a_store_is_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = rg.packaging_review(_fixture_root(tmp),
                                         tracked=TRACKED_OK + ["telemetry/claude/2026-09-01.json"])
        self.assertTrue(any("telemetry/claude/2026-09-01.json" in f for f in review["findings"]))

    def test_unclassified_top_level_path_and_forbidden_artifacts_are_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = rg.packaging_review(_fixture_root(tmp),
                                         tracked=TRACKED_OK + ["scratch/notes.txt", "bin/__pycache__/x.pyc",
                                                               "docs/.DS_Store"])
        joined = "\n".join(review["findings"])
        self.assertIn("'scratch'", joined)
        self.assertIn("bytecode", joined)
        self.assertIn("Finder metadata", joined)

    def test_manifest_mismatch_and_bad_version_are_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, **{
                ".claude-plugin/plugin.json": json.dumps({"name": "polytropos", "version": "0.5",
                                                          "description": "new"})})
            review = rg.packaging_review(root, tracked=TRACKED_OK)
        joined = "\n".join(review["findings"])
        self.assertIn("MAJOR.MINOR.PATCH", joined)
        self.assertIn("description differs", joined)

    def test_codex_version_off_the_plugin_base_is_a_note_not_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, **{
                ".codex-plugin/plugin.json": json.dumps({"name": "polytropos", "version": "0.4.0+codex.1"})})
            review = rg.packaging_review(root, tracked=TRACKED_OK)
        self.assertEqual(review["findings"], [])
        self.assertTrue(any("0.4.0+codex.1" in n for n in review["notes"]))

    def test_unpinned_action_and_credentials_outside_deploy_are_findings(self):
        bad = MINIMAL_WORKFLOW.replace(
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262", "actions/checkout@v4"
        ).replace("  build:\n    permissions:\n      contents: read\n",
                  "  build:\n    permissions:\n      contents: read\n      id-token: write\n")
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, **{".github/workflows/docs-site.yml": bad})
            review = rg.packaging_review(root, tracked=TRACKED_OK)
        joined = "\n".join(review["findings"])
        self.assertIn("not pinned to a full commit SHA", joined)
        self.assertIn("'id-token: write' appears outside the deploy job", joined)

    def test_a_comment_mentioning_a_credential_is_not_a_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            review = rg.packaging_review(_fixture_root(tmp), tracked=TRACKED_OK)
        self.assertFalse(any("outside the deploy job" in f for f in review["findings"]))

    def test_unhashed_package_is_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(tmp, **{"docs-src/requirements.txt": "mkdocs==1.6.1\n"})
            review = rg.packaging_review(root, tracked=TRACKED_OK)
        self.assertTrue(any("carries no sha256 hash" in f for f in review["findings"]))

    def test_real_tree_has_no_packaging_findings(self):
        review = rg.packaging_review(REPO_ROOT)
        self.assertEqual(review["findings"], [])
        self.assertIn("bin", review["inventory"])


class RegistryFindingsTests(unittest.TestCase):
    def _root_with(self, tmp, mutate):
        root = Path(tmp)
        (root / "primitives").mkdir()
        registry = json.loads((REPO_ROOT / "primitives" / "harness-capabilities.json").read_text())
        mutate(registry)
        (root / "primitives" / "harness-capabilities.json").write_text(json.dumps(registry))
        return root

    def test_real_registry_has_no_findings(self):
        self.assertEqual(rg.registry_findings(REPO_ROOT), [])

    def test_a_verification_since_the_gate_must_name_the_client_version(self):
        def undated(reg):
            row = reg["harnesses"]["codex"]["capabilities"]["dispatch"]
            row.update(verified="supported", verified_on=str(date.today()))
            row.pop("client_version", None)
        with tempfile.TemporaryDirectory() as tmp:
            findings = rg.registry_findings(self._root_with(tmp, undated))
        self.assertTrue(any("codex/dispatch" in f and "client_version" in f for f in findings), findings)

        def dated(reg):
            undated(reg)
            reg["harnesses"]["codex"]["capabilities"]["dispatch"]["client_version"] = "codex 1.0"
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(rg.registry_findings(self._root_with(tmp, dated)), [])

    def test_an_older_verification_without_a_version_is_not_rewritten_or_flagged(self):
        """A row verified before the gate existed recorded no client version and is not
        backfilled; the rule binds only from CLIENT_VERSION_REQUIRED_FROM onward. (Until
        2026-09-16 this test read the real claude-code/dispatch row, which carried exactly that
        shape; the live run re-dated it, so the shape is pinned on a temp registry now.)"""
        def older(reg):
            row = reg["harnesses"]["codex"]["capabilities"]["dispatch"]
            row.update(verified="supported", verified_on="2026-09-06")
            row.pop("client_version", None)
        with tempfile.TemporaryDirectory() as tmp:
            findings = rg.registry_findings(self._root_with(tmp, older))
        self.assertFalse(any("codex/dispatch" in f for f in findings), findings)

    def test_a_cited_capability_missing_from_the_registry_is_a_finding(self):
        def drop(reg):
            del reg["harnesses"]["cursor"]["capabilities"]["identity_probe"]
        with tempfile.TemporaryDirectory() as tmp:
            findings = rg.registry_findings(self._root_with(tmp, drop))
        self.assertTrue(any("identity_probe" in f and "dispatch-failure" in f for f in findings), findings)

    def test_a_dateless_supported_row_is_a_finding(self):
        def dateless(reg):
            row = reg["harnesses"]["copilot"]["capabilities"]["dispatch"]
            row.update(verified="supported")
            row.pop("verified_on", None)
        with tempfile.TemporaryDirectory() as tmp:
            findings = rg.registry_findings(self._root_with(tmp, dateless))
        self.assertTrue(any("copilot/dispatch" in f and "verified_on" in f for f in findings), findings)


class ReverifyTests(unittest.TestCase):
    def test_partitions_rows_by_date_and_edits_nothing(self):
        path = REPO_ROOT / "primitives" / "harness-capabilities.json"
        before = path.read_bytes()
        later = rg.reverify("claude-code", "2026-10-01", REPO_ROOT)
        self.assertIn("dispatch", later["revalidate"])
        self.assertIn("status", later["first_verification"])
        self.assertIn("confined_dispatch", later["recheck_unsupported"])
        earlier = rg.reverify("claude-code", "2026-09-01", REPO_ROOT)
        self.assertIn("dispatch", earlier["still_current"])
        self.assertNotIn("dispatch", earlier["revalidate"])
        self.assertEqual(path.read_bytes(), before)
        self.assertIn("writes nothing", later["record"])
        self.assertTrue(any("--dry-run" in c for c in later["commands"]))
        self.assertFalse(any("--live" in c for c in later["commands"]))

    def test_unknown_harness_raises(self):
        with self.assertRaises(ValueError):
            rg.reverify("gemini", "2026-10-01", REPO_ROOT)


class ReleaseDocTests(unittest.TestCase):
    def test_block_is_deterministic_and_carries_no_date_or_revision(self):
        """Registry `verified_on` dates are data and may equal today; what must not leak is
        the build date itself, so the render is compared under a different clock."""
        one = rg.render_block(REPO_ROOT)
        two = rg.render_block(REPO_ROOT)
        self.assertEqual(one, two)
        with mock.patch.object(rg, "date") as fake_date:
            fake_date.today.return_value = date(2001, 1, 1)
            self.assertEqual(rg.render_block(REPO_ROOT), one)
        self.assertNotIn("2001-01-01", one)
        self.assertIsNone(re.search(r"\b[0-9a-f]{40}\b", one))
        self.assertTrue(one.startswith(rg.BLOCK_START))
        self.assertTrue(one.rstrip().endswith(rg.BLOCK_END))

    def test_block_keeps_stub_and_installed_columns_apart(self):
        block = rg.render_block(REPO_ROOT)
        self.assertIn("| Harness | Stub conformance | Installed client |", block)
        self.assertIn("not recorded", block)
        self.assertIn("Prepared, not run", block)

    def test_real_release_doc_is_current_and_build_is_idempotent(self):
        self.assertIsNone(rg.check_release_doc(REPO_ROOT))
        before = (REPO_ROOT / rg.RELEASE_DOC).read_bytes()
        self.assertFalse(rg.build_release_doc(REPO_ROOT))
        self.assertEqual((REPO_ROOT / rg.RELEASE_DOC).read_bytes(), before)

    def test_drift_and_missing_markers_are_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            doc = root / rg.RELEASE_DOC
            doc.write_text(f"# R\n\n{rg.BLOCK_START}\nold\n{rg.BLOCK_END}\ntail\n", encoding="utf-8")
            with mock.patch.object(rg, "render_block", return_value=f"{rg.BLOCK_START}\nnew\n{rg.BLOCK_END}\n"):
                self.assertIn("stale", rg.check_release_doc(root))
                self.assertTrue(rg.build_release_doc(root))
                self.assertIsNone(rg.check_release_doc(root))
                self.assertEqual(doc.read_text(encoding="utf-8"),
                                 f"# R\n\n{rg.BLOCK_START}\nnew\n{rg.BLOCK_END}\ntail\n")
            doc.write_text("# R\nno markers\n", encoding="utf-8")
            self.assertIn("must carry", rg.check_release_doc(root))
            doc.unlink()
            self.assertIn("missing", rg.check_release_doc(root))


class CommandTests(unittest.TestCase):
    def test_every_cited_command_exists(self):
        self.assertEqual(rg.command_findings(REPO_ROOT), [])
        cited = dict(rg.checklist_commands())
        self.assertIn("bin/release_gate.py", cited)
        self.assertIn("bin/workflow_eval.py", cited)

    def test_a_renamed_subcommand_is_a_finding(self):
        bogus = ({"guarantee": "g", "evidence": "`python3 bin/workflow_eval.py promote` does it",
                  "limit": "`python3 bin/nonexistent_tool.py check`"},)
        with mock.patch.object(rg, "CHECKLIST", bogus):
            findings = rg.command_findings(REPO_ROOT)
        joined = "\n".join(findings)
        self.assertIn("workflow_eval.py promote", joined)
        self.assertIn("nonexistent_tool.py", joined)


class CliTests(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = rg.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_check_passes_on_the_real_tree(self):
        rc, out, _ = self._run(["check"])
        self.assertEqual(rc, 0, out)
        self.assertIn("verdict: OK", out)
        self.assertIn("contracts run: no", out)

    def test_check_json_carries_findings_and_revision(self):
        rc, out, _ = self._run(["check", "--json"])
        payload = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(payload["findings"], [])
        self.assertRegex(payload["revision"]["sha"], r"^[0-9a-f]{40}$")

    def test_check_exits_3_on_a_finding(self):
        with mock.patch.object(rg, "registry_findings", return_value=["registry: synthetic"]):
            rc, out, _ = self._run(["check"])
        self.assertEqual(rc, 3)
        self.assertIn("synthetic", out)

    def test_matrix_json_and_contracts_and_packaging_and_checklist(self):
        rc, out, _ = self._run(["matrix", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(json.loads(out)["harnesses"]), sorted(rg.HARNESSES))
        rc, out, _ = self._run(["contracts"])
        self.assertEqual(rc, 0, out)
        self.assertIn("Installed client", out)
        rc, out, _ = self._run(["packaging"])
        self.assertEqual(rc, 0, out)
        self.assertIn("verdict: OK", out)
        rc, out, _ = self._run(["checklist"])
        self.assertEqual(rc, 0)
        for heading in ("Release checklist", "Migration and rollback", "release triggers", "Prepared, not run"):
            self.assertIn(heading, out)

    def test_reverify_cli(self):
        rc, out, _ = self._run(["reverify", "--harness", "cursor", "--released", "2026-10-01"])
        self.assertEqual(rc, 0)
        self.assertIn("never verified; a first run", out)
        self.assertIn("this tool writes nothing", out)
        rc, out, _ = self._run(["reverify", "--harness", "cursor", "--released", "2026-10-01", "--json"])
        self.assertEqual(json.loads(out)["harness"], "cursor")


if __name__ == "__main__":
    unittest.main()
