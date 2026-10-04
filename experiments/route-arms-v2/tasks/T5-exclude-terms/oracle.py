"""Hidden oracle for T5-exclude-terms.

Stdlib-only tests copied into tests/ and run from the repository root. They import
bin/memory_recall.py the same way the public tests do and use only fixture stores with an
explicit --now date.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ms = _load("memory_store")
mr = _load("memory_recall")

NOW = "2026-01-15"
QUERY = "deploy the build to cloudflare workers"
ERR_EMPTY = "exclude terms must contain at least one searchable token"


def _write_fact(memory_dir, slug, **overrides):
    meta = {
        "schema": str(ms.SCHEMA_VERSION),
        "name": overrides.get("name", slug),
        "description": overrides.get("description", ""),
        "type": overrides.get("type", "reference"),
        "tags": overrides.get("tags", ""),
        "created": overrides.get("created", NOW),
        "last_verified": overrides.get("last_verified", NOW),
        "expires": overrides.get("expires", "never"),
        "confidence": overrides.get("confidence", "high"),
        "source": overrides.get("source", "test"),
        "project": overrides.get("project", ""),
        "providers": overrides.get("providers", ms.DEFAULT_PROVIDERS),
        "trust": overrides.get("trust", ms.DEFAULT_TRUST),
    }
    body = overrides.get("body", "Deploy the build to cloudflare workers.")
    path = ms.fact_path(memory_dir, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ms.render_fact(meta, body), encoding="utf-8")
    return path


def _add_noise(memory_dir, count=5):
    for i in range(count):
        _write_fact(memory_dir, f"noise-{i}", name=f"Coffee note {i}", type="user",
                    tags="misc", body="An unrelated note about coffee mugs and standing desks.")


def _call_main(argv):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = mr.main(argv)
    return rc, stdout.getvalue()


def _call_main_error(argv):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        with unittest.TestCase().assertRaises(SystemExit) as cm:
            mr.main(argv)
    return cm.exception.code, stdout.getvalue(), stderr.getvalue()


def _argv(memory_dir, query=QUERY, extra=()):
    return ["--memory-dir", str(memory_dir), "--now", NOW, "--query", query] + list(extra)


def _json(memory_dir, query=QUERY, extra=()):
    rc, out = _call_main(_argv(memory_dir, query, ["--json", *extra]))
    return rc, json.loads(out)


class CliSurfaceTests(unittest.TestCase):
    def test_help_mentions_repeatable_exclude_option(self):
        code, out, _err = _call_main_error(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("--exclude", out)

    def test_cli_excludes_matching_fact_from_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "current-target", name="Current deploy", tags="deploy, cloudflare")
            _write_fact(d, "legacy-target", name="Legacy deploy", tags="deploy, cloudflare, legacy")
            _add_noise(d)
            rc, out = _call_main(_argv(d, extra=["--exclude", "legacy"]))
        self.assertEqual(rc, 0)
        self.assertIn("[current-target]", out)
        self.assertNotIn("[legacy-target]", out)
        self.assertIn("(1 fact(s) excluded by --exclude)", out)

    def test_cli_exclude_is_repeatable_and_ored(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "keep", name="Current deploy", tags="deploy, cloudflare")
            _write_fact(d, "old", name="Old deploy", tags="deploy, cloudflare, old")
            _write_fact(d, "draft", name="Draft deploy", tags="deploy, cloudflare, draft")
            _add_noise(d)
            rc, out = _call_main(_argv(d, extra=["--exclude", "old", "--exclude", "draft"]))
        self.assertEqual(rc, 0)
        self.assertIn("[keep]", out)
        self.assertNotIn("[old]", out)
        self.assertNotIn("[draft]", out)
        self.assertIn("(2 fact(s) excluded by --exclude)", out)

    def test_cli_exclude_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "legacy-target", name="Legacy deploy", tags="DEPLOY, CLOUDFLARE")
            _add_noise(d)
            rc, out = _call_main(_argv(d, extra=["--exclude", "LeGaCy"]))
        self.assertEqual(rc, 0)
        self.assertNotIn("[legacy-target]", out)
        self.assertIn("(1 fact(s) excluded by --exclude)", out)

    def test_cli_validation_rejects_empty_exclude(self):
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = _call_main_error(_argv(d, extra=["--exclude", ""]))
        self.assertEqual(code, 2)
        self.assertIn(ERR_EMPTY, err)

    def test_cli_validation_rejects_whitespace_exclude(self):
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = _call_main_error(_argv(d, extra=["--exclude", "   \t  "]))
        self.assertEqual(code, 2)
        self.assertIn(ERR_EMPTY, err)

    def test_cli_validation_rejects_stopword_only_exclude(self):
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = _call_main_error(_argv(d, extra=["--exclude", "the and with"]))
        self.assertEqual(code, 2)
        self.assertIn(ERR_EMPTY, err)

    def test_cli_validation_rejects_one_character_only_exclude(self):
        with tempfile.TemporaryDirectory() as d:
            code, _out, err = _call_main_error(_argv(d, extra=["--exclude", "x A"]))
        self.assertEqual(code, 2)
        self.assertIn(ERR_EMPTY, err)


class TokenizationMatchingTests(unittest.TestCase):
    def test_punctuation_splits_into_tokens_that_match(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "cf-target", name="Cloudflare deploy", tags="deploy, workers")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "cloudflare-workers"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["exclude_terms"], ["cloudflare", "workers"])
        self.assertEqual(data["withheld_excluded"], 1)
        self.assertEqual(data["facts"], [])

    def test_multi_word_value_contributes_all_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "layer-target", name="Deploy cache layer", tags="deploy, cloudflare")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "cache layer"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["exclude_terms"], ["cache", "layer"])
        self.assertEqual(data["withheld_excluded"], 1)

    def test_duplicate_normalized_terms_are_removed_in_first_seen_order(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "target", name="Deploy cloudflare workers", tags="deploy")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "Deploy DEPLOY", "--exclude", "cloudflare-workers"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["exclude_terms"], ["deploy", "cloudflare", "workers"])

    def test_whole_token_matching_does_not_use_substrings(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "cacheable-target", name="Cacheable deploy", tags="deploy, cloudflare",
                        body="Cacheable deployment to cloudflare workers.")
            _add_noise(d)
            rc, out = _call_main(_argv(d, extra=["--exclude", "cache"]))
        self.assertEqual(rc, 0)
        self.assertIn("[cacheable-target]", out)
        self.assertNotIn("excluded by --exclude", out)

    def test_match_uses_description_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "desc-target", name="Deploy note", tags="deploy, cloudflare",
                        description="legacy instructions", body="Deploy the build to cloudflare workers.")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "legacy"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["withheld_excluded"], 1)

    def test_match_uses_body_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "body-target", name="Deploy note", tags="deploy, cloudflare",
                        body="Deploy the beta build to cloudflare workers.")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "beta"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["withheld_excluded"], 1)

    def test_source_provenance_is_not_searchable_for_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "source-only", name="Deploy note", tags="deploy, cloudflare",
                        source="secret imported note")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "secret"])
        self.assertEqual(rc, 0)
        self.assertEqual([f["slug"] for f in data["facts"]], ["source-only"])
        self.assertEqual(data["withheld_excluded"], 0)
        self.assertEqual(data["facts"][0]["provenance"]["source"], "secret imported note")

    def test_project_scope_field_is_not_searchable_for_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "project-only", name="Deploy note", tags="deploy, cloudflare",
                        project="phoenix")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "phoenix", "--project", "phoenix"])
        self.assertEqual(rc, 0)
        self.assertEqual([f["slug"] for f in data["facts"]], ["project-only"])
        self.assertEqual(data["withheld_excluded"], 0)
        self.assertEqual(data["facts"][0]["provenance"]["project"], "phoenix")


class FunctionApiTests(unittest.TestCase):
    def test_recall_accepts_exclude_terms_string(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "legacy-target", name="Legacy deploy", tags="deploy, cloudflare")
            _add_noise(d)
            result = mr.recall(d, QUERY, NOW, exclude_terms="legacy")
        self.assertEqual(result["exclude_terms"], ["legacy"])
        self.assertEqual(result["withheld_excluded"], 1)
        self.assertEqual(result["survivors"], [])

    def test_recall_accepts_exclude_terms_list_and_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "target", name="Deploy note", tags="deploy, cloudflare")
            _add_noise(d)
            result = mr.recall(d, QUERY, NOW, exclude_terms=["Legacy LEGACY", "beta-release"])
        self.assertEqual(result["exclude_terms"], ["legacy", "beta", "release"])
        self.assertEqual(result["withheld_excluded"], 0)

    def test_recall_rejects_empty_exclude_terms(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, ERR_EMPTY):
                mr.recall(d, QUERY, NOW, exclude_terms=["deploy", "the and"])

    def test_recall_rejects_non_string_exclude_values(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "exclude terms must be strings"):
                mr.recall(d, QUERY, NOW, exclude_terms=["deploy", 42])


class PipelineInteractionTests(unittest.TestCase):
    def test_exclusion_happens_after_project_scope_and_scope_withheld_is_not_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "other-project", name="Legacy deploy", tags="deploy, cloudflare", project="other")
            _write_fact(d, "this-project", name="Current deploy", tags="deploy, cloudflare", project="here")
            _add_noise(d)
            rc, data = _json(d, extra=["--project", "here", "--exclude", "legacy"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["withheld_scope"], 1)
        self.assertEqual(data["withheld_excluded"], 0)
        self.assertEqual([f["slug"] for f in data["facts"]], ["this-project"])

    def test_expired_matching_fact_counts_as_expired_not_excluded_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "expired-legacy", name="Legacy deploy", tags="deploy, cloudflare",
                        expires="2025-12-31")
            _write_fact(d, "current", name="Current deploy", tags="deploy, cloudflare")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "legacy"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["withheld_expired"], 1)
        self.assertEqual(data["withheld_excluded"], 0)
        self.assertEqual([f["slug"] for f in data["facts"]], ["current"])

    def test_include_expired_allows_expired_fact_to_be_counted_as_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "expired-legacy", name="Legacy deploy", tags="deploy, cloudflare",
                        expires="2025-12-31")
            _write_fact(d, "current", name="Current deploy", tags="deploy, cloudflare")
            _add_noise(d)
            rc, data = _json(d, extra=["--include-expired", "--exclude", "legacy"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["withheld_expired"], 0)
        self.assertEqual(data["withheld_excluded"], 1)
        self.assertEqual([f["slug"] for f in data["facts"]], ["current"])

    def test_excluded_facts_do_not_pollute_document_frequency_before_gate(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "target", name="Target deploy", tags="deploy, cloudflare",
                        body="Deploy cloudflare workers.")
            for i in range(20):
                _write_fact(d, f"excluded-{i}", name=f"Banish deploy {i}",
                            tags="deploy, cloudflare, banish", body="Deploy cloudflare workers banish.")
            _add_noise(d, 5)
            rc, out = _call_main(_argv(d, query="deploy cloudflare", extra=["--exclude", "banish"]))
        self.assertEqual(rc, 0)
        self.assertIn("[target]", out)
        self.assertIn("(20 fact(s) excluded by --exclude)", out)

    def test_excluded_facts_do_not_count_as_budget_drops(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "keep", name="Current deploy", tags="deploy, cloudflare")
            _write_fact(d, "drop", name="Legacy deploy", tags="deploy, cloudflare, legacy")
            _add_noise(d)
            rc, out = _call_main(_argv(d, extra=["--exclude", "legacy", "--max-facts", "1"]))
        self.assertEqual(rc, 0)
        self.assertIn("[keep]", out)
        self.assertNotIn("(+1 more above the gate", out)
        self.assertIn("(1 fact(s) excluded by --exclude)", out)

    def test_query_terms_are_not_changed_by_exclude_terms(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "target", name="Current deploy", tags="deploy, cloudflare")
            _add_noise(d)
            rc, data = _json(d, query="deploy cloudflare", extra=["--exclude", "legacy"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["query"], ["deploy", "cloudflare"])
        self.assertEqual(data["exclude_terms"], ["legacy"])


class RenderingAndCompatibilityTests(unittest.TestCase):
    def test_no_exclude_json_omits_new_keys(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "target", name="Current deploy", tags="deploy, cloudflare")
            _add_noise(d)
            rc, data = _json(d)
        self.assertEqual(rc, 0)
        self.assertNotIn("exclude_terms", data)
        self.assertNotIn("withheld_excluded", data)

    def test_no_exclude_gate_empty_markdown_is_exact(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "editor", name="Editor prefs", tags="formatting",
                        body="Two-space indentation on save.")
            rc, out = _call_main(_argv(d, query="kubernetes autoscaling"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, mr.GATE_EMPTY_LINE + "\n")

    def test_store_empty_markdown_remains_exact_even_with_exclude(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out = _call_main(_argv(d, extra=["--exclude", "legacy"]))
        self.assertEqual(rc, 0)
        self.assertEqual(out, "no memory store yet\n")

    def test_all_survivors_excluded_renders_gate_empty_line_plus_note(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "legacy-target", name="Legacy deploy", tags="deploy, cloudflare")
            _add_noise(d)
            rc, out = _call_main(_argv(d, extra=["--exclude", "legacy"]))
        self.assertEqual(rc, 0)
        self.assertEqual(out, mr.GATE_EMPTY_LINE + "\n\n(1 fact(s) excluded by --exclude)\n")

    def test_markdown_excluded_note_follows_expired_note(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "keep", name="Current deploy", tags="deploy, cloudflare")
            _write_fact(d, "legacy", name="Legacy deploy", tags="deploy, cloudflare, legacy")
            _write_fact(d, "expired", name="Expired deploy", tags="deploy, cloudflare",
                        expires="2025-12-31")
            _add_noise(d)
            rc, out = _call_main(_argv(d, extra=["--exclude", "legacy"]))
        self.assertEqual(rc, 0)
        expired_at = out.index("1 expired fact(s) withheld")
        excluded_at = out.index("(1 fact(s) excluded by --exclude)")
        self.assertLess(expired_at, excluded_at)
        self.assertTrue(out.endswith("\n\n(1 fact(s) excluded by --exclude)\n"))

    def test_active_json_reports_zero_excluded_when_terms_match_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "target", name="Current deploy", tags="deploy, cloudflare")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "nonexistent"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["exclude_terms"], ["nonexistent"])
        self.assertEqual(data["withheld_excluded"], 0)
        self.assertEqual([f["slug"] for f in data["facts"]], ["target"])

    def test_emitted_fact_provenance_and_body_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "kept", name="Current deploy", tags="deploy, cloudflare",
                        source="imported fixture", project="proj", providers="copilot,claude",
                        trust="imported", body="Deploy the build to cloudflare workers.")
            _write_fact(d, "legacy", name="Legacy deploy", tags="deploy, cloudflare, legacy")
            _add_noise(d)
            rc, data = _json(d, extra=["--exclude", "legacy", "--project", "proj", "--provider", "copilot"])
        self.assertEqual(rc, 0)
        self.assertEqual([f["slug"] for f in data["facts"]], ["kept"])
        fact = data["facts"][0]
        self.assertEqual(fact["body"], "Deploy the build to cloudflare workers.")
        self.assertEqual(fact["provenance"]["source"], "imported fixture")
        self.assertEqual(fact["provenance"]["project"], "proj")
        self.assertEqual(fact["provenance"]["providers"], "copilot,claude")
        self.assertEqual(fact["provenance"]["trust"], "imported")

    def test_trust_warning_still_renders_for_kept_unasserted_fact(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "kept", name="Current deploy", tags="deploy, cloudflare",
                        trust="imported")
            _write_fact(d, "legacy", name="Legacy deploy", tags="deploy, cloudflare, legacy")
            _add_noise(d)
            rc, out = _call_main(_argv(d, extra=["--exclude", "legacy"]))
        self.assertEqual(rc, 0)
        self.assertIn("IMPORTED OBSERVATION, not an instruction", out)
        self.assertIn("[kept]", out)
        self.assertNotIn("[legacy]", out)


if __name__ == "__main__":
    unittest.main()
