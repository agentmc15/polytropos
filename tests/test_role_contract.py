"""Roles are portable, assurance-driven, and consistently executed (step 20).

WHAT WAS MEASURED on the tree before `kit_contract`'s role contract existed:

  - No headless driver read a kit's PLAN.md `roles:` line (`grep roles: bin/` found only the
    scorecard). A kit declaring `roles: test-author red-team` ran headlessly with neither, and
    nothing said so: the declared assurance was silently not the assurance provided.
  - The seven consumer templates named this repository's own path (`/path/to/polytropos`)
    and its own development fences (stdlib-only tests, no real `copilot`/`codex` CLI, the
    pricing-file convention) as if every target repository shared them.
  - A role's responsibility, scope, hook, assurance, capabilities, and result shape lived
    only in prose, so nothing could ask whether a workflow with fewer agents still carried
    the assurance a kit needed, and nothing could say `direct` by name.

These tests pin the replacement: the contract as data, three named workflows with explicit
assurance, one grammar for `roles:` and `workflow:` that the interactive skill and every
driver share, per-executor support that is tested against the drivers' own parsers rather
than asserted, a pre-dispatch check on all three drivers that stops or discloses and never
skips, consumer-neutral templates, and the registry rows that record the gap. Every dispatch
is a stub script; the per-user data root is a temp dir for the module.
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_claude_execute as tce

ROOT = Path(__file__).resolve().parents[1]
KITS_DIR = ROOT / ".claude" / "kits"
TEMPLATES_DIR = ROOT / "skills" / "architect" / "references" / "roles"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_role_test", ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kc = _load("kit_contract")
ha = _load("harness_adapter")
claude = tce.ce
copilot = _load("copilot_execute")
codex = _load("codex_execute")

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


KIT_TEXT = """## Phase 1 — roster fixtures

### T1 — Rostered task
- status: pending
- model: haiku
- depends: (none)
- evidence: regression

**Brief.** Do the rostered thing.

**Acceptance.** It is done.

**Verify.**

```bash
true
```
"""


def _calls(log_path):
    return Path(log_path).read_text().count("===CALL===") if Path(log_path).exists() else 0


# ---- 1. the contract as data ----------------------------------------------------------------------

class VocabularyTests(unittest.TestCase):
    def test_the_roles_and_their_order_are_the_ones_the_skills_state(self):
        self.assertEqual(kc.STANDING_ROLES, ("implementer", "verifier", "reviewer"))
        self.assertEqual(kc.OPTIONAL_ROLES, ("scout", "test-author", "second-verifier",
                                             "red-team", "security-auditor", "docs-editor",
                                             "synthesizer"))
        self.assertEqual(sorted(kc.PIPELINE_ORDER), sorted(kc.ALL_ROLES))
        self.assertEqual(len(set(kc.PIPELINE_ORDER)), len(kc.PIPELINE_ORDER))
        self.assertEqual(kc.WORKFLOWS, ("direct", "reviewed", "extended"))
        self.assertEqual(kc.DEFAULT_WORKFLOW, "reviewed")

    def test_every_role_has_a_complete_contract(self):
        fields = {"responsibility", "scope", "hook", "assurance", "artifacts", "capabilities",
                  "produces_findings", "result"}
        for role in kc.ALL_ROLES:
            with self.subTest(role=role):
                c = kc.ROLE_CONTRACTS[role]
                self.assertEqual(set(c), fields)
                self.assertTrue(c["responsibility"])
                self.assertIn(c["scope"], kc.ROLE_SCOPES)
                self.assertTrue(c["hook"])
                self.assertTrue(c["assurance"] is None or c["assurance"] in kc.ASSURANCE_KINDS)
                self.assertTrue(c["artifacts"])
                self.assertTrue(set(c["capabilities"]) <= set(kc.CAPABILITY_GRANTS))
                self.assertIsInstance(c["produces_findings"], bool)
                self.assertTrue(c["result"])
        self.assertEqual(set(kc.ROLE_CONTRACTS), set(kc.ALL_ROLES))

    def test_read_only_roles_hold_no_write_grant_and_write_roles_hold_exactly_theirs(self):
        writes = {g for g in kc.CAPABILITY_GRANTS if g.startswith("write-")}
        for role in ("verifier", "reviewer", "scout", "second-verifier", "red-team",
                     "security-auditor"):
            self.assertFalse(writes & set(kc.ROLE_CONTRACTS[role]["capabilities"]), role)
        self.assertEqual(writes & set(kc.ROLE_CONTRACTS["test-author"]["capabilities"]),
                         {"write-tests"})
        self.assertEqual(writes & set(kc.ROLE_CONTRACTS["docs-editor"]["capabilities"]),
                         {"write-docs"})
        self.assertEqual(writes & set(kc.ROLE_CONTRACTS["synthesizer"]["capabilities"]),
                         {"write-notes"})

    def test_finding_producers_report_confirmed_and_the_others_do_not(self):
        for role, c in kc.ROLE_CONTRACTS.items():
            with self.subTest(role=role):
                if c["produces_findings"]:
                    self.assertIn("findings", c["result"])
                    self.assertIn("confirmed", c["result"])
                else:
                    self.assertNotIn("findings", c["result"])

    def test_the_result_envelope_names_cost_basis_latency_and_unknown(self):
        for field in ("role", "scope", "scope_id", "model", "artifacts", "cost_basis",
                      "latency_s", "unknown"):
            self.assertIn(field, kc.RESULT_ENVELOPE)

    def test_workflow_assurance_is_explicit_and_direct_drops_independent_review(self):
        self.assertEqual(kc.WORKFLOW_ASSURANCE["direct"], ("deterministic-check",))
        self.assertIn("independent-review", kc.WORKFLOW_ASSURANCE["reviewed"])
        self.assertIn("independent-verification", kc.WORKFLOW_ASSURANCE["reviewed"])
        self.assertEqual(kc.WORKFLOW_ROLES["direct"], ("implementer",))
        self.assertEqual(kc.WORKFLOW_ROLES["reviewed"], kc.STANDING_ROLES)


# ---- 2. one grammar -------------------------------------------------------------------------------

class GrammarTests(unittest.TestCase):
    def test_roles_line_parses_or_refuses(self):
        self.assertIsNone(kc.parse_plan_roles(None))
        self.assertIsNone(kc.parse_plan_roles("# plan\nbudget: max-dispatches=2\n"))
        self.assertIsNone(kc.parse_plan_roles("roles:\n"))
        self.assertEqual(kc.parse_plan_roles("roles: test-author red-team"),
                         ["test-author", "red-team"])
        with self.assertRaisesRegex(kc.RosterError, "'chef' is not a role"):
            kc.parse_plan_roles("roles: chef")
        with self.assertRaisesRegex(kc.RosterError, "standing role"):
            kc.parse_plan_roles("roles: verifier")
        with self.assertRaisesRegex(kc.RosterError, "declared twice"):
            kc.parse_plan_roles("roles: scout scout")

    def test_workflow_line_parses_or_refuses(self):
        self.assertIsNone(kc.parse_plan_workflow(""))
        self.assertEqual(kc.parse_plan_workflow("workflow: direct\n"), "direct")
        with self.assertRaisesRegex(kc.RosterError, "not a workflow"):
            kc.parse_plan_workflow("workflow: lean")

    def test_the_default_is_the_trio_and_declared_roles_make_it_extended(self):
        trio = kc.resolve_roster("")
        self.assertEqual(trio["workflow"], "reviewed")
        self.assertEqual(trio["roles"], ["implementer", "verifier", "reviewer"])
        self.assertTrue(trio["binding_review"])
        ext = kc.resolve_roster("roles: red-team scout\n")
        self.assertEqual(ext["workflow"], "extended")
        self.assertEqual(ext["roles"], ["scout", "implementer", "verifier", "red-team",
                                        "reviewer"], "pipeline order, not declaration order")
        self.assertEqual(ext["declared"], ["red-team", "scout"])
        self.assertEqual(ext["assurance"],
                         ["deterministic-check", "independent-verification",
                          "independent-review", "adversarial-test", "grounding"],
                         "the workflow's assurance, then each declared role's kind")
        self.assertEqual(ext["hooks"]["red-team"], "after the verifier passes, before done")

    def test_direct_must_be_named_and_never_beside_roles(self):
        direct = kc.resolve_roster("workflow: direct\n")
        self.assertEqual(direct["roles"], ["implementer"])
        self.assertEqual(direct["assurance"], ["deterministic-check"])
        self.assertFalse(direct["binding_review"])
        with self.assertRaisesRegex(kc.RosterError, "cannot declare roles"):
            kc.resolve_roster("workflow: direct\nroles: scout\n")
        with self.assertRaisesRegex(kc.RosterError, "cannot declare roles"):
            kc.resolve_roster("workflow: reviewed\nroles: scout\n")
        with self.assertRaisesRegex(kc.RosterError, "declares no roles"):
            kc.resolve_roster("workflow: extended\n")
        self.assertEqual(kc.resolve_roster("workflow: extended\nroles: scout\n")["workflow"],
                         "extended")

    def test_every_legacy_kit_parses_and_the_two_with_roles_resolve_as_extended(self):
        seen = {}
        for plan in sorted(KITS_DIR.glob("*/PLAN.md")):
            roster = kc.resolve_roster(plan.read_text())
            seen[plan.parent.name] = roster
        self.assertGreater(len(seen), 20)
        with_roles = {slug: r["declared"] for slug, r in seen.items() if r["declared"]}
        self.assertEqual(with_roles, {"aesop-fold": ["test-author"],
                                      "docs-site": ["test-author", "docs-editor"]})
        for slug, roster in seen.items():
            self.assertEqual(roster["workflow"], "extended" if slug in with_roles
                             else "reviewed", slug)


# ---- 3. what each executor can run, tested against the drivers -----------------------------------

class SupportTests(unittest.TestCase):
    def test_the_interactive_skill_sequences_everything(self):
        roster = kc.resolve_roster("roles: " + " ".join(kc.OPTIONAL_ROLES))
        support = kc.roster_support(roster, "interactive")
        self.assertEqual(support["gap"], [])
        self.assertEqual(support["partial"], [])
        self.assertTrue(all(lvl == "sequenced" for lvl, _n in support["levels"].values()))

    def test_every_headless_driver_refuses_the_optional_roles_and_discloses_the_verifier(self):
        roster = kc.resolve_roster("roles: test-author docs-editor")
        for executor in ("claude-code", "copilot", "codex"):
            with self.subTest(executor=executor):
                support = kc.roster_support(roster, executor)
                self.assertEqual(support["gap"], ["test-author", "docs-editor"])
                self.assertEqual(support["partial"], ["verifier"])
                self.assertEqual(support["levels"]["implementer"][0], "sequenced")
                self.assertEqual(support["levels"]["reviewer"][0], "sequenced")

    def test_cursor_is_unknown_not_assumed(self):
        support = kc.roster_support(kc.resolve_roster(""), "cursor")
        self.assertEqual(support["unknown"], ["implementer", "verifier", "reviewer"])
        with self.assertRaises(kc.RosterError):
            kc.roster_support(kc.resolve_roster(""), "vscode")

    def test_the_support_table_matches_what_the_drivers_parsers_expose(self):
        # `sequenced` for implementer/reviewer means `run` and `review` exist; `unsupported`
        # for the optional roles means nothing sequences them: Codex refuses any other role
        # outright, and the other two drivers' `run` takes exactly one role per invocation.
        for module, executor in ((claude, "claude-code"), (copilot, "copilot"),
                                 (codex, "codex")):
            with self.subTest(executor=executor):
                parser = module.build_parser()
                subs = next(a for a in parser._actions if a.dest == "command").choices
                self.assertIn("run", subs)
                self.assertIn("review", subs)
                run_flags = {a.dest for a in subs["run"]._actions}
                self.assertIn("roster_gap", run_flags)
                gap = next(a for a in subs["run"]._actions if a.dest == "roster_gap")
                self.assertEqual(tuple(gap.choices), kc.GAP_MODES)
                self.assertEqual(gap.default, "stop")
                self.assertNotIn("roles", run_flags, "no driver claims to take a roster")
        # Codex's `run` refuses any role but implementer, which is what `unsupported` for its
        # optional roles rests on; probed through the real command line on a temp kit.
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp) / "fixturekit"
            kit.mkdir()
            (kit / "TASKS.md").write_text(KIT_TEXT)
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                codex.main(["run", "--kit", str(kit), "--role", "scout", "--codex-bin", "x"])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("ordinary implementation only", err.getvalue())

    def test_the_registry_records_the_gap_per_harness(self):
        for harness in ("claude-code", "codex", "copilot"):
            with self.subTest(harness=harness):
                rows = ha.registry_capabilities(harness)
                self.assertEqual(ha.effective(rows["extended_roles"]), ha.UNSUPPORTED)
                self.assertEqual(ha.effective(rows["independent_review"]), ha.UNKNOWN,
                                 "implemented but never run live")
                self.assertIn("ROLE_SUPPORT", rows["extended_roles"]["source"])
        cursor = ha.registry_capabilities("cursor")
        self.assertEqual(ha.effective(cursor["extended_roles"]), ha.UNKNOWN)


# ---- 4. the pre-dispatch check on every driver ----------------------------------------------------

class RosterCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.kit = self.tmp / "fixturekit"
        self.kit.mkdir()
        (self.kit / "TASKS.md").write_text(KIT_TEXT)
        self.log = self.tmp / "stub.log"
        self.stub = tce._write_stub(self.tmp, self.log)
        self.store = self.tmp / "store"
        tce._write_agent_bundle(self.tmp, "fixturekit", "implementer", tce.PREAMBLE_FIXTURE_BODY)

    def tearDown(self):
        self._tmp.cleanup()

    def _each_driver(self):
        yield "claude-code", claude, "--claude-bin"
        yield "copilot", copilot, "--copilot-bin"
        yield "codex", codex, "--codex-bin"

    def _run(self, driver, flag, *extra, expect_exit=None):
        out, err = io.StringIO(), io.StringIO()
        argv = ["run", "--kit", str(self.kit), flag, str(self.stub),
                "--attempt-store", str(self.store), *extra]
        patches = []
        if driver is claude:
            patches = [mock.patch.object(claude, "REPO_ROOT", self.tmp),
                       mock.patch.object(claude, "load_pricing",
                                         return_value=tce.PRICING_FIXTURE)]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            if expect_exit is None:
                driver.main(argv)
            else:
                with self.assertRaises(SystemExit) as ctx:
                    driver.main(argv)
                self.assertEqual(ctx.exception.code, expect_exit, err.getvalue())
        return out.getvalue(), err.getvalue()

    def _snapshot(self):
        return {p.name: p.read_bytes() for p in self.kit.iterdir() if p.is_file()}

    def test_a_declared_role_no_driver_can_run_stops_every_driver_before_any_write(self):
        (self.kit / "PLAN.md").write_text("# plan\nroles: test-author\n")
        for name, driver, flag in self._each_driver():
            with self.subTest(driver=name):
                before = self._snapshot()
                _out, err = self._run(driver, flag, expect_exit=2)
                self.assertEqual(self._snapshot(), before)
                self.assertEqual(_calls(self.log), 0)
                self.assertFalse(self.store.exists(), "refused before the ledger was opened")
                self.assertIn("gap: test-author is not executed by this driver", err)
                self.assertIn("/polytropos:execute fixturekit", err)
                self.assertIn("--roster-gap disclose", err)
                self.assertIn("nothing is dispatched", err)

    def test_the_preview_refuses_the_same_way(self):
        (self.kit / "PLAN.md").write_text("# plan\nroles: red-team\n")
        for name, driver, flag in self._each_driver():
            with self.subTest(driver=name):
                out, err = self._run(driver, flag, "--dry-run", expect_exit=2)
                self.assertEqual(out, "", "no preview of a run that would refuse")
                self.assertIn("gap: red-team", err)

    def test_a_grammar_error_stops_every_driver(self):
        for plan, needle in (("roles: chef\n", "'chef' is not a role"),
                             ("workflow: lean\n", "not a workflow"),
                             ("workflow: direct\nroles: scout\n", "cannot declare roles")):
            (self.kit / "PLAN.md").write_text(plan)
            for name, driver, flag in self._each_driver():
                with self.subTest(driver=name, plan=plan):
                    _out, err = self._run(driver, flag, expect_exit=2)
                    self.assertIn(needle, err)
                    self.assertEqual(_calls(self.log), 0)

    def test_disclose_proceeds_with_the_gap_printed_and_recorded(self):
        (self.kit / "PLAN.md").write_text("# plan\nroles: test-author\n")
        _out, err = self._run(claude, "--claude-bin", "--roster-gap", "disclose")
        self.assertIn("proceeding WITHOUT test-author", err)
        self.assertEqual(_calls(self.log), 1)
        ledger = kc.open_ledger(self.kit, store=self.store)
        checks = [e for e in ledger.events() if e["kind"] == "roster.checked"]
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["gap"], ["test-author"])
        self.assertEqual(checks[0]["gap_mode"], "disclose")
        self.assertEqual(checks[0]["workflow"], "extended")
        self.assertEqual(checks[0]["executor"], "claude-code")
        self.assertEqual(checks[0]["task"], "T1")

    def test_the_default_trio_runs_with_its_partial_verifier_disclosed_not_refused(self):
        _out, err = self._run(claude, "--claude-bin")
        self.assertIn("roster: workflow=reviewed roles=implementer,verifier,reviewer", err)
        self.assertIn("partial: verifier", err)
        self.assertNotIn("gap:", err)
        self.assertEqual(_calls(self.log), 1)
        ledger = kc.open_ledger(self.kit, store=self.store)
        check = next(e for e in ledger.events() if e["kind"] == "roster.checked")
        self.assertEqual(check["gap"], [])
        self.assertEqual(check["partial"], ["verifier"])
        self.assertEqual(check["assurance"],
                         ["deterministic-check", "independent-verification",
                          "independent-review"])

    def test_direct_runs_and_records_that_no_independent_review_was_declared(self):
        (self.kit / "PLAN.md").write_text("# plan\nworkflow: direct\n")
        _out, err = self._run(claude, "--claude-bin")
        self.assertIn("roster: workflow=direct roles=implementer assurance=deterministic-check",
                      err)
        self.assertEqual(_calls(self.log), 1)
        ledger = kc.open_ledger(self.kit, store=self.store)
        check = next(e for e in ledger.events() if e["kind"] == "roster.checked")
        self.assertEqual(check["workflow"], "direct")
        self.assertEqual(check["assurance"], ["deterministic-check"])

    def test_status_shows_the_roster_on_every_driver(self):
        (self.kit / "PLAN.md").write_text("# plan\nroles: scout\n")
        for _name, driver, _flag in self._each_driver():
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                driver.main(["status", "--kit", str(self.kit)])
            self.assertEqual(out.getvalue().splitlines()[-1],
                             "roster: workflow=extended roles=scout,implementer,verifier,"
                             "reviewer assurance=deterministic-check+independent-verification"
                             "+independent-review+grounding")
        (self.kit / "PLAN.md").write_text("# plan\nroles: chef\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            claude.main(["status", "--kit", str(self.kit)])
        self.assertIn("roster: INVALID -- roles: 'chef' is not a role", out.getvalue())


# ---- 5. consumer-neutral templates -----------------------------------------------------------------

class TemplateTests(unittest.TestCase):
    REPO_SPECIFIC = ("path/to/polytropos", "stdlib", "copilot", "codex", "~/.claude",
                     "pricing file", "CLAUDE.md invariant", "bin/")

    def test_every_optional_role_has_a_template_and_no_template_names_this_repo(self):
        names = {p.stem for p in TEMPLATES_DIR.glob("*.md")}
        self.assertEqual(names, set(kc.OPTIONAL_ROLES))
        for path in TEMPLATES_DIR.glob("*.md"):
            text = path.read_text()
            with self.subTest(template=path.name):
                self.assertIn("<slug>", text)
                self.assertIn("<repo-root>", text)
                self.assertIn("GUARDRAILS.md", text)
                scrubbed = text.replace("/polytropos:execute", "")
                for token in self.REPO_SPECIFIC:
                    self.assertNotIn(token, scrubbed, f"{path.name} still names {token!r}")
                self.assertNotIn("polytropos", scrubbed.lower())

    def test_templates_agree_with_the_contracts_write_grants(self):
        for role in kc.OPTIONAL_ROLES:
            text = (TEMPLATES_DIR / f"{role}.md").read_text()
            grants = set(kc.ROLE_CONTRACTS[role]["capabilities"])
            with self.subTest(role=role):
                if grants & {"write-code", "write-tests", "write-docs", "write-notes"}:
                    self.assertIn("Scoped-write law", text)
                    self.assertNotIn("tools: Bash, Read, Grep, Glob", text)
                else:
                    self.assertIn("tools: Bash, Read, Grep, Glob", text)


# ---- 6. the command line ----------------------------------------------------------------------------

class CommandLineTests(unittest.TestCase):
    def _cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kc._cli(argv)
        return code, out.getvalue(), err.getvalue()

    def test_roster_reports_per_executor_and_exits_by_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "PLAN.md").write_text("roles: test-author\n")
            code, out, _err = self._cli(["roster", "--kit", tmp])
            self.assertEqual(code, 0)
            self.assertIn("executor=interactive", out)
            code, out, _err = self._cli(["roster", "--kit", tmp, "--executor", "codex"])
            self.assertEqual(code, 1)
            self.assertIn("gap: test-author", out)
            code, out, _err = self._cli(["roster", "--kit", tmp, "--executor", "codex",
                                         "--json"])
            blob = json.loads(out)
            self.assertEqual(blob["support"]["gap"], ["test-author"])
            self.assertEqual(blob["contracts"]["test-author"]["assurance"], "adversarial-test")
            self.assertEqual(blob["roster"]["workflow"], "extended")
            (Path(tmp) / "PLAN.md").write_text("roles: chef\n")
            code, _out, err = self._cli(["roster", "--kit", tmp])
            self.assertEqual(code, 2)
            self.assertIn("'chef' is not a role", err)

    def test_demo_walks_the_rosters(self):
        code, out, _err = self._cli(["demo"])
        self.assertEqual(code, 0)
        self.assertIn("[workflow: direct]", out)
        self.assertIn("gap: red-team is not executed by this driver", out)
        self.assertIn("roster: INVALID -- roles: 'chef' is not a role", out)


if __name__ == "__main__":
    unittest.main()
