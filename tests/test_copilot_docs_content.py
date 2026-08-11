"""Live-content regression suite for the ``copilot-docs/`` documentation center (T7).

Unlike ``tests/test_copilot_docs.py`` (which exercises ``bin/copilot_docs.py`` as a pure,
synthetic-fixture unit under temporary directories), this suite reads the REAL, checked-in
``copilot-docs/`` tree and the REAL ``data/pricing.copilot.json`` / ``prefs/copilot.json``
files at the repository root, entirely read-only. It proves the center actually satisfies the
PLAN's content contract: complete skill/agent coverage, honest slash-command wording, correct
generated provenance, no hardcoded live model ids outside generated blocks, correct AIC-report
accounting, HTML parity/accessibility, valid internal links, and a fully static, side-effect-free
generator.

SAFETY CONTRACT: no ``subprocess``, no network, no ``Path.home()``, and no writes anywhere. Every
path is repo-relative, derived from ``Path(__file__).resolve().parent.parent``. ``bin/`` is not a
package, so ``bin/copilot_docs.py`` is loaded via importlib by absolute path, mirroring
``tests/test_copilot_docs.py``. Reading ``prefs/copilot.json`` through
``copilot_prefs.effective_prefs`` is the one real-repo-state read this suite performs, and it is
strictly read-only (that file is itself gitignored user data, never written here).
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
DOCS_ROOT = REPO_ROOT / "copilot-docs"
MANIFEST_PATH = DOCS_ROOT / "manifest.json"
REPORT_PATH = DOCS_ROOT / "aic-report.json"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cd = _load("copilot_docs")

H2_RE = re.compile(r"^## (\S.*)$", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$", re.MULTILINE)
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
HTML_HREF_RE = re.compile(r'href="([^"]+)"')
HTML_ID_RE = re.compile(r'id="([^"]+)"')

# Exact expected Markdown/HTML pairs, per the PLAN's file tree — the manifest-declared eight
# authored guides plus the generator-owned AIC report pair.
EXPECTED_MANIFEST_PAIRS = {
    ("README.md", "index.html"),
    ("INSTALL.md", "install.html"),
    ("SAFETY.md", "safety.html"),
    ("SKILLS.md", "skills.html"),
    ("AGENTS.md", "agents.html"),
    ("MODELS.md", "models.html"),
    ("COSTS.md", "costs.html"),
    ("WORKFLOWS.md", "workflows.html"),
}
AIC_REPORT_PAIR = ("AIC-REPORT.md", "aic-report.html")

EXPECTED_SKILLS = {
    "architect", "bench-routing", "budget", "context-weight", "effort", "escalate", "execute",
    "frontier-check", "journal", "lessons-loop", "route", "usage",
}
EXPECTED_AGENTS = {
    "architect", "bench-routing", "context-weight", "effort", "escalate", "frontier-check",
    "implementer", "journal", "reviewer", "route", "usage", "verifier",
}


def _read(relpath):
    return (DOCS_ROOT / relpath).read_text(encoding="utf-8")


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _report():
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _pricing():
    return cd._pricing_module().load_pricing()


def _prefs(pricing):
    # Reads the repository's own real prefs/copilot.json, read-only — the sanctioned seam,
    # never a machine-specific home directory.
    return cd._prefs_module().effective_prefs(pricing)


def _h2_names(markdown_text):
    return {m.group(1).strip() for m in H2_RE.finditer(markdown_text)}


def _h2_names_ordered(markdown_text):
    return [m.group(1).strip() for m in H2_RE.finditer(markdown_text)]


def _bare(name):
    """Strip a Markdown inline-code fence (`` `name` ``) if present."""
    name = name.strip()
    if name.startswith("`") and name.endswith("`"):
        name = name[1:-1]
    return name


def _heading_ids(markdown_text):
    """Compute the same stable heading ids ``render_markdown`` would assign, in document
    order, using the real ``slugify_heading`` — used to validate same-document ``#anchor``
    links without re-rendering the whole document."""
    used = set()
    ids = []
    for m in HEADING_RE.finditer(markdown_text):
        ids.append(cd.slugify_heading(m.group(2), used))
    return ids


def _all_markdown_files():
    return sorted(DOCS_ROOT.glob("*.md"))


def _all_html_files():
    return sorted(DOCS_ROOT.glob("*.html"))


class ManifestInventoryTests(unittest.TestCase):
    def test_manifest_declares_exactly_the_planned_markdown_html_pairs(self):
        manifest = _manifest()
        pairs = {(d["markdown"], d["html"]) for d in manifest["documents"]}
        self.assertEqual(pairs, EXPECTED_MANIFEST_PAIRS)

    def test_no_undeclared_markdown_or_html_files_under_docs_root(self):
        manifest = _manifest()
        declared_md = {d["markdown"] for d in manifest["documents"]} | {AIC_REPORT_PAIR[0]}
        declared_html = {d["html"] for d in manifest["documents"]} | {AIC_REPORT_PAIR[1]}
        on_disk_md = {p.name for p in _all_markdown_files()}
        on_disk_html = {p.name for p in _all_html_files()}
        self.assertEqual(on_disk_md, declared_md)
        self.assertEqual(on_disk_html, declared_html)

    def test_only_aic_report_is_deterministic_markdown(self):
        manifest = _manifest()
        for doc in manifest["documents"]:
            self.assertEqual(
                doc["authoring"]["mode"], "estimated",
                f"{doc['markdown']} should be estimated authoring; only AIC-REPORT.md is "
                "deterministic",
            )
        report = _report()
        aic_row = next(
            r for r in report["documents"]
            if r["path"] == AIC_REPORT_PAIR[0] and r["kind"] == "markdown"
        )
        self.assertEqual(aic_row["authoring_mode"], "deterministic")

    def test_every_estimated_entry_has_a_live_tier_and_profile_symbol(self):
        manifest = _manifest()
        pricing = _pricing()
        prefs_mod = cd._prefs_module()
        prefs = _prefs(pricing)
        for doc in manifest["documents"]:
            authoring = doc["authoring"]
            self.assertEqual(authoring["mode"], "estimated")
            tier = authoring["tier"]
            profile = authoring["input_profile"]
            model_id = prefs_mod.resolve_tier(pricing, tier, prefs)
            self.assertIsNotNone(model_id, f"{doc['markdown']}: tier {tier!r} has no resolution")
            self.assertIn(profile, pricing["task_profiles"], f"{doc['markdown']}: unknown profile")


class SkillCoverageTests(unittest.TestCase):
    def test_discovered_skills_match_skills_md_headings_exactly(self):
        discovered = {row["name"] for row in cd.discover_skills(REPO_ROOT)}
        self.assertEqual(discovered, EXPECTED_SKILLS)
        headings = {_bare(h) for h in _h2_names(_read("SKILLS.md"))}
        self.assertEqual(headings, EXPECTED_SKILLS)

    def test_skills_md_intro_covers_name_syntax_autoload_session_model_and_honesty(self):
        intro = _read("SKILLS.md")
        self.assertIn("/name", intro)
        self.assertIn("auto-load", intro.lower())
        self.assertRegex(intro, r"whatever model that session already has\s*\n?\s*selected")
        self.assertIn("true custom slash command", intro.lower())

    def test_each_skill_section_has_when_how_and_safety_content(self):
        text = _read("SKILLS.md")
        sections = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
        self.assertEqual(len(sections), len(EXPECTED_SKILLS))
        for section in sections:
            name = _bare(section.splitlines()[0].strip())
            body = section.lower()
            self.assertIn("when to use it", body, f"{name}: missing when-to-use guidance")
            self.assertIn("how to request it", body, f"{name}: missing how-to-invoke guidance")
            self.assertIn("safety and cost notes", body, f"{name}: missing safety/cost notes")


class AgentCoverageTests(unittest.TestCase):
    def test_discovered_agents_match_agents_md_headings_exactly(self):
        discovered = {row["name"] for row in cd.discover_agents(REPO_ROOT)}
        self.assertEqual(discovered, EXPECTED_AGENTS)
        headings = {_bare(h) for h in _h2_names(_read("AGENTS.md"))}
        self.assertEqual(headings, EXPECTED_AGENTS)

    def test_agents_md_intro_covers_isolation_invocation_pin_prefs_and_precedence(self):
        intro = _read("AGENTS.md")
        self.assertIn("persona-isolated", intro.lower())
        self.assertIn("/agent", intro)
        self.assertIn("pin a specific model", intro.lower())
        # Prefs limitation: an agent's own configured pin is not rewritten by preferences.
        self.assertIn("never rewrite", intro.lower())
        # Personal-agent precedence rule.
        self.assertIn("user-level", intro.lower())
        self.assertIn("wins", intro.lower())

    def test_execute_and_lessons_loop_are_not_agent_headings(self):
        headings = {_bare(h) for h in _h2_names(_read("AGENTS.md"))}
        self.assertNotIn("execute", headings)
        self.assertNotIn("lessons-loop", headings)

    def test_workflow_roles_present_as_agent_headings(self):
        headings = {_bare(h) for h in _h2_names(_read("AGENTS.md"))}
        for role in ("implementer", "reviewer", "verifier"):
            self.assertIn(role, headings)


class RequiredGuideContentTests(unittest.TestCase):
    def test_install_guide_has_install_discovery_commands_and_placeholder_troubleshooting(self):
        text = _read("INSTALL.md")
        self.assertIn("bin/harness_select.py install", text)
        self.assertIn("--dry-run", text)
        self.assertIn("/skills reload", text)
        self.assertIn("/skills list", text)
        self.assertIn("/skills info", text)
        self.assertIn("/agent", text)
        self.assertIn("{{POLYTROPOS_ROOT}}", text)

    def test_workflows_guide_has_exactly_the_seven_pinned_headings(self):
        headings = _h2_names_ordered(_read("WORKFLOWS.md"))
        expected = [
            "Route a task", "Architect → execute", "Verify → escalate",
            "Usage and cost review", "Daily journal", "Effort and frontier decision",
            "Lessons loop",
        ]
        # (Sanity: the same seven headings regardless of authored ordering churn — this
        # assertion is exact-order because the guide is written as a sequential walkthrough.)
        self.assertEqual(headings, expected)

    def test_costs_guide_distinguishes_estimate_actual_proxy_and_aiu(self):
        text = _read("COSTS.md")
        self.assertIn("prospective", text.lower())
        self.assertIn("historical usage-log estimate", text.lower())
        self.assertIn("proxy", text.lower())
        self.assertIn("AIU", text)
        self.assertIn("AIC", text)

    def test_safety_guide_states_no_live_cli_no_real_home_and_serial_execution(self):
        text = _read("SAFETY.md")
        low = text.lower()
        self.assertIn("never invoke a real harness cli", low.replace("copilot/codex/claude", ""))
        self.assertTrue(
            "never invoke" in low or "invoke a real" in low or "spending a real user" in low
        )
        self.assertIn("real user home directory", low)
        self.assertIn("no parallel-subagent fan-out", low)


class SlashCommandHonestyTests(unittest.TestCase):
    NEGATION_WORDS = ("not ", "never ", "isn't", "n't ", "neither ")

    def _all_authored_text(self):
        return "\n".join(_read(p.name) for p in _all_markdown_files() if p.name != "AIC-REPORT.md")

    def test_at_least_one_explicit_not_a_true_custom_slash_command_statement(self):
        corpus = re.sub(r"\s+", " ", self._all_authored_text().lower())
        found = (
            "true custom slash command" in corpus
            or "true custom slash-command registry" in corpus
            or "custom, user-defined copilot slash-command registry" in corpus
        )
        self.assertTrue(found, "expected an explicit slash-command honesty statement")

    def test_no_affirmative_custom_slash_command_claim(self):
        corpus = self._all_authored_text()
        banned_patterns = [
            r"\bis a custom slash command\b",
            r"\bis a true custom slash command\b",
            r"\bregisters? native commands?\b",
            r"\bnative slash-command registry\b",
        ]
        for pattern in banned_patterns:
            for m in re.finditer(pattern, corpus, re.IGNORECASE):
                start = max(0, m.start() - 80)
                window = corpus[start:m.end()].lower()
                self.assertTrue(
                    any(neg in window for neg in self.NEGATION_WORDS),
                    f"affirmative-looking slash-command claim with no nearby negation: "
                    f"{corpus[m.start():m.end()]!r}",
                )

    def test_every_slash_mentioning_sentence_carries_a_negation(self):
        corpus = self._all_authored_text()
        sentences = re.split(r"(?<=[.!?])\s+", corpus)
        for sentence in sentences:
            low = sentence.lower()
            if "slash" not in low or "command" not in low:
                continue
            if "/name" in sentence or "/route" in sentence or "/architect" in sentence:
                # Placeholder or example invocation syntax, not a claim about registries.
                continue
            self.assertTrue(
                any(neg in low for neg in self.NEGATION_WORDS),
                f"slash-command sentence lacks an honesty negation: {sentence!r}",
            )


class GeneratedProvenanceAndPrefsTests(unittest.TestCase):
    def test_every_generated_block_in_authored_markdown_carries_full_provenance(self):
        pricing = _pricing()
        pricing_path = cd._pricing_module().PRICING_PATH
        snapshot = cd.build_pricing_snapshot(pricing, pricing_path, REPO_ROOT)
        found_any = False
        for md_path in _all_markdown_files():
            if md_path.name == "AIC-REPORT.md":
                continue
            text = md_path.read_text(encoding="utf-8")
            pairs = cd._scan_markers(text)
            for name, _bs, be, es, _ee in pairs:
                found_any = True
                block = text[be:es]
                self.assertIn(str(pricing_path.name), text)
                self.assertIn(snapshot["cached_date"], block, f"{md_path.name}#{name}")
                self.assertIn(snapshot["pricing_sha256"], block, f"{md_path.name}#{name}")
                self.assertIn(snapshot["roster_sha256"], block, f"{md_path.name}#{name}")
        self.assertTrue(found_any, "expected at least one generated block in the authored guides")

    def test_report_prefs_equal_the_recorded_build_snapshot(self):
        report = _report()
        pricing = _pricing()
        recorded_prefs = cd.reconstruct_prefs_from_snapshot(report["prefs_snapshot"])
        # `prefs/copilot.json` is gitignored USER DATA, so a fresh clone (or a secondary
        # worktree) legitimately has no live prefs file while the committed docs record the
        # pins they were built with. In that configuration this freshness check has nothing
        # real to compare against — an absent personal file is not evidence the docs are
        # stale — so skip with a reason instead of failing every prefs-less checkout.
        # Where a live prefs file EXISTS, the assertions below stay exactly as strict.
        prefs_path = cd._prefs_module().DEFAULT_PREFS_PATH
        snapshot_has_state = bool(
            report["prefs_snapshot"].get("pins") or report["prefs_snapshot"].get("excludes")
        )
        if not prefs_path.exists() and snapshot_has_state:
            self.skipTest(
                "live prefs/copilot.json absent but the recorded snapshot carries prefs — "
                "docs freshness is unverifiable in this checkout, not stale"
            )
        live_prefs = _prefs(pricing)
        self.assertEqual(recorded_prefs["pins"], live_prefs.get("pins") or {})
        self.assertEqual(
            sorted(recorded_prefs["excludes"]), sorted(live_prefs.get("excludes") or [])
        )

    def test_no_selected_document_model_is_excluded(self):
        report = _report()
        excludes = set(report["prefs_snapshot"]["excludes"])
        for row in report["documents"]:
            model_id = row.get("resolved_model_id")
            if model_id is not None:
                self.assertNotIn(model_id, excludes, f"{row['path']} resolved to an excluded id")

    def test_frontier_resolution_equals_recorded_frontier_pin_when_present(self):
        report = _report()
        pins = report["inputs"]["prefs"]["pins"]
        if "frontier" not in pins:
            self.skipTest("no frontier pin recorded")
        pricing = _pricing()
        prefs_mod = cd._prefs_module()
        reconstructed = cd.reconstruct_prefs_from_snapshot(report["prefs_snapshot"])
        resolved = prefs_mod.resolve_tier(pricing, "frontier", reconstructed)
        self.assertEqual(resolved, pins["frontier"])

    def test_excluded_configured_agent_pin_is_flagged_not_recommended(self):
        pricing = _pricing()
        prefs = _prefs(pricing)
        rows = cd.annotate_agent_rows(cd.discover_agents(REPO_ROOT), pricing, prefs)
        excluded_rows = [r for r in rows if r["is_excluded"]]
        if not excluded_rows:
            self.skipTest("no agent currently carries an excluded configured pin")
        agents_text = _read("AGENTS.md").lower()
        for row in excluded_rows:
            self.assertIn("disclosure", agents_text)
            self.assertNotRegex(
                agents_text,
                r"recommend(ed|s)?\s+(swapping|replacing|switching)\s+" + re.escape(row["model"]),
            )
        # The generated table itself must show "yes" in the Excluded column for that row.
        table_block = re.search(
            r"<!-- BEGIN GENERATED: agents-inventory -->(.*?)<!-- END GENERATED: agents-inventory -->",
            _read("AGENTS.md"), re.DOTALL,
        ).group(1)
        for row in excluded_rows:
            line = next(l for l in table_block.splitlines() if f"`{row['name']}`" in l)
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            self.assertEqual(cells[4], "yes", f"{row['name']} should show Excluded=yes")


class NoHardcodedLiveIdsTests(unittest.TestCase):
    def test_no_live_model_id_in_generator_source_or_manifest(self):
        pricing = _pricing()
        source = (BIN_DIR / "copilot_docs.py").read_text(encoding="utf-8")
        manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
        for model_id in pricing["models"]:
            self.assertNotIn(model_id, source, f"live model id leaked into generator: {model_id}")
            self.assertNotIn(model_id, manifest_text, f"live model id leaked into manifest: {model_id}")

    def test_no_live_model_id_in_authored_markdown_outside_generated_blocks(self):
        pricing = _pricing()
        for md_path in _all_markdown_files():
            if md_path.name == "AIC-REPORT.md":
                continue
            text = md_path.read_text(encoding="utf-8")
            stripped = cd.strip_generated_blocks(text)
            for model_id in pricing["models"]:
                self.assertNotIn(
                    model_id, stripped,
                    f"live model id {model_id!r} leaked into authored prose of {md_path.name}",
                )


class AicReportSemanticsTests(unittest.TestCase):
    def test_exactly_one_row_per_manifest_markdown_and_html_path(self):
        manifest = _manifest()
        report = _report()
        expected_paths = set()
        for doc in manifest["documents"]:
            expected_paths.add(doc["markdown"])
            expected_paths.add(doc["html"])
        expected_paths.add(AIC_REPORT_PAIR[0])
        expected_paths.add(AIC_REPORT_PAIR[1])
        rows_by_path = {}
        for row in report["documents"]:
            self.assertNotIn(row["path"], rows_by_path, f"duplicate row for {row['path']}")
            rows_by_path[row["path"]] = row
        self.assertEqual(set(rows_by_path), expected_paths)

    def test_authored_markdown_rows_are_nonnegative_prospective_estimates(self):
        report = _report()
        for row in report["documents"]:
            if row["kind"] == "markdown" and not row.get("self_reference"):
                self.assertEqual(row["authoring_mode"], "estimated")
                self.assertGreaterEqual(row["cost"]["aic"], 0.0)
                self.assertGreaterEqual(row["cost"]["usd"], 0.0)
                self.assertIn("uncertainty", row["cost"])

    def test_html_and_report_rows_are_zero_cost(self):
        report = _report()
        for row in report["documents"]:
            if row["kind"] == "html" or row.get("self_reference"):
                self.assertEqual(row["cost"]["aic"], 0.0)
                self.assertEqual(row["cost"]["usd"], 0.0)

    def test_html_rows_point_at_their_markdown_source(self):
        manifest = _manifest()
        report = _report()
        by_path = {r["path"]: r for r in report["documents"]}
        for doc in manifest["documents"]:
            html_row = by_path[doc["html"]]
            self.assertEqual(html_row["markdown_source"], doc["markdown"])
        aic_html_row = by_path[AIC_REPORT_PAIR[1]]
        self.assertEqual(aic_html_row["markdown_source"], AIC_REPORT_PAIR[0])

    def test_totals_equal_sum_of_authored_markdown_only(self):
        report = _report()
        expected_usd = expected_aic = 0.0
        for row in report["documents"]:
            if row["kind"] == "markdown" and not row.get("self_reference"):
                expected_usd += row["cost"]["usd"]
                expected_aic += row["cost"]["aic"]
        self.assertAlmostEqual(report["totals"]["usd"], expected_usd, places=9)
        self.assertAlmostEqual(report["totals"]["aic"], expected_aic, places=9)

    def test_measured_and_assumed_fields_are_kept_separate(self):
        report = _report()
        for row in report["documents"]:
            if row["kind"] == "markdown" and not row.get("self_reference"):
                measurement = row["measurement"]
                cost = row["cost"]
                self.assertIn("bytes", measurement)
                self.assertIn("words", measurement)
                self.assertIn("ai_output_lexemes", measurement)
                self.assertIn("assumed_input_tokens", cost)
                # The measured output stand-in and the declared/assumed input never share a key.
                self.assertNotEqual(
                    set(measurement) & {"assumed_input_tokens"}, {"assumed_input_tokens"}
                )

    def test_pricing_cached_date_and_hashes_are_present(self):
        report = _report()
        ps = report["pricing_snapshot"]
        for key in ("path", "cached_date", "pricing_sha256", "roster_sha256"):
            self.assertIn(key, ps)
            self.assertTrue(ps[key])


class HtmlParityAccessibilityTests(unittest.TestCase):
    def test_in_process_check_reports_no_drift_and_is_read_only(self):
        pricing_mod = cd._pricing_module()
        pricing = pricing_mod.load_pricing()
        manifest = _manifest()
        recorded = _report()

        before = {p: p.read_bytes() for p in DOCS_ROOT.rglob("*") if p.is_file()}

        drift = cd.detect_drift(recorded, pricing, pricing_mod.PRICING_PATH, manifest, REPO_ROOT)
        self.assertEqual(drift, [])

        reconstructed_prefs = cd.reconstruct_prefs_from_snapshot(recorded["prefs_snapshot"])
        _report2, plan = cd.plan_with_aic_report(
            manifest, REPO_ROOT, DOCS_ROOT, pricing, pricing_mod.PRICING_PATH, reconstructed_prefs,
        )
        stale = cd.check_artifacts(plan, DOCS_ROOT)
        self.assertEqual(stale, [])

        after = {p: p.read_bytes() for p in DOCS_ROOT.rglob("*") if p.is_file()}
        self.assertEqual(before, after, "in-process check must never write anything")

    def test_each_html_title_and_headings_correspond_to_its_markdown(self):
        manifest = _manifest()
        for doc in manifest["documents"]:
            md_text = _read(doc["markdown"])
            html_text = _read(doc["html"])
            title_m = re.search(r"<title>([^<]*)</title>", html_text)
            self.assertIsNotNone(title_m)
            self.assertEqual(title_m.group(1), doc["title"])
            # The rendered body's own H1/H2/... headings from the Markdown source must all be
            # present (by stable id) somewhere in the HTML.
            for heading_id in _heading_ids(md_text):
                self.assertIn(f'id="{heading_id}"', html_text, f"{doc['html']}: missing #{heading_id}")

    def test_html_has_skip_link_nav_main_companion_link_and_stylesheet(self):
        for html_path in _all_html_files():
            text = html_path.read_text(encoding="utf-8")
            self.assertIn('class="skip-link"', text)
            self.assertIn("<nav", text)
            self.assertIn('id="main"', text)
            self.assertIn('class="source-link"', text)
            self.assertIn('rel="stylesheet"', text)

    def test_html_has_no_script_tag_or_external_url(self):
        for html_path in _all_html_files():
            text = html_path.read_text(encoding="utf-8")
            self.assertNotIn("<script", text.lower())
            for href in HTML_HREF_RE.findall(text):
                self.assertFalse(
                    href.startswith(("http://", "https://", "//")),
                    f"{html_path.name}: external URL {href!r}",
                )


class LinkValidationTests(unittest.TestCase):
    def test_markdown_local_links_resolve_to_existing_files_or_anchors(self):
        for md_path in _all_markdown_files():
            text = md_path.read_text(encoding="utf-8")
            own_ids = set(_heading_ids(text))
            for url in MD_LINK_RE.findall(text):
                if url.startswith(("http://", "https://", "mailto:")):
                    continue
                target, _, frag = url.partition("#")
                if target == "":
                    self.assertIn(
                        frag, own_ids, f"{md_path.name}: dangling same-file anchor #{frag}"
                    )
                    continue
                target_path = DOCS_ROOT / target
                self.assertTrue(
                    target_path.is_file(), f"{md_path.name}: missing local link target {target!r}"
                )
                if frag and target_path.suffix == ".md":
                    target_ids = set(_heading_ids(target_path.read_text(encoding="utf-8")))
                    self.assertIn(frag, target_ids, f"{md_path.name} -> {target}#{frag}")

    def test_html_local_hrefs_resolve_to_existing_files_or_ids(self):
        for html_path in _all_html_files():
            text = html_path.read_text(encoding="utf-8")
            own_ids = set(HTML_ID_RE.findall(text))
            for href in HTML_HREF_RE.findall(text):
                if href.startswith(("http://", "https://", "mailto:", "//")):
                    continue
                target, _, frag = href.partition("#")
                if target == "":
                    self.assertIn(frag, own_ids, f"{html_path.name}: dangling same-file id #{frag}")
                    continue
                target_path = DOCS_ROOT / target
                self.assertTrue(
                    target_path.is_file(), f"{html_path.name}: missing local href target {target!r}"
                )
                if frag and target_path.suffix == ".html":
                    target_ids = set(HTML_ID_RE.findall(target_path.read_text(encoding="utf-8")))
                    self.assertIn(frag, target_ids, f"{html_path.name} -> {href}")

    def test_generated_html_document_links_point_at_html_companions_not_markdown(self):
        manifest = _manifest()
        md_to_html = {d["markdown"]: d["html"] for d in manifest["documents"]}
        html_to_md = {d["html"]: d["markdown"] for d in manifest["documents"]}
        for html_path in _all_html_files():
            text = html_path.read_text(encoding="utf-8")
            own_markdown_source = html_to_md.get(html_path.name)
            for href in HTML_HREF_RE.findall(text):
                target, _, _frag = href.partition("#")
                if target not in md_to_html:
                    continue
                # The one sanctioned exception: the HTML shell's own "View Markdown source"
                # link, which legitimately points back at that same document's own Markdown.
                if target == own_markdown_source:
                    continue
                self.fail(
                    f"{html_path.name}: HTML document links directly to Markdown {target!r} "
                    f"instead of its HTML companion {md_to_html[target]!r}"
                )


class SafetyStaticScopeTests(unittest.TestCase):
    FORBIDDEN_PATTERNS = (
        r"\bimport subprocess\b",
        r"\bsubprocess\.\w+\(",
        r"\bos\.system\(",
        r"\bPath\.home\(\)",
        r"\bsocket\.\w+\(",
        r"\burllib\.request\b",
        r"\bhttp\.client\b",
    )

    def test_generator_source_contains_no_process_network_or_home_primitive(self):
        source = (BIN_DIR / "copilot_docs.py").read_text(encoding="utf-8")
        # Strip RST-style inline-code spans (``...`` / `...`) used throughout this file's own
        # docstrings to *describe* the safety contract in prose (e.g. "no ``Path.home()``") —
        # only real code outside those spans should ever trip a forbidden pattern.
        code_only = re.sub(r"``[^`]*``|`[^`]*`", "", source)
        for pattern in self.FORBIDDEN_PATTERNS:
            self.assertNotRegex(code_only, pattern, f"forbidden primitive found: {pattern}")

    def test_check_leaves_docs_root_byte_identical(self):
        pricing_mod = cd._pricing_module()
        pricing = pricing_mod.load_pricing()
        manifest = _manifest()
        recorded = _report()
        reconstructed_prefs = cd.reconstruct_prefs_from_snapshot(recorded["prefs_snapshot"])

        before = {p: p.read_bytes() for p in DOCS_ROOT.rglob("*") if p.is_file()}
        _report2, plan = cd.plan_with_aic_report(
            manifest, REPO_ROOT, DOCS_ROOT, pricing, pricing_mod.PRICING_PATH, reconstructed_prefs,
        )
        cd.check_artifacts(plan, DOCS_ROOT)
        after = {p: p.read_bytes() for p in DOCS_ROOT.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
