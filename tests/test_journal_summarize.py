"""Stdlib unittest regression suite for bin/journal_summarize.py (PLAN.md D8/D9/D10).

SAFETY CONTRACT (binds every test in this file): no test here ever invokes a real model CLI
binary. Every dispatch goes through one of two seams: an injected fake ``runner``/
``default_runner`` callable (pure-function tests of ``pick_models``, ``output_ok``,
``build_prompts``, ``build_dispatch``, ``summarize``, and the ``main`` end-to-end cases), or a
tiny temp STUB shell executable named ``stub-model.sh`` -- deliberately NOT the real CLI's
name -- written to a fresh ``tempfile.TemporaryDirectory()`` and exercised only by the
``default_runner`` tests via its explicit absolute path, never resolved off PATH. The stdlib
``Path.home`` helper is never called anywhere in this file -- every journal/digest fixture
lives under an explicit ``tempfile.TemporaryDirectory()`` passed to ``main`` via
``--journal-dir`` (or an explicit ``--digest``), never a real default. Pricing is always a
synthetic ``PRICING_FIXTURE``-family dict patched over ``load_pricing`` via
``mock.patch.object(jsz, "load_pricing", return_value=...)`` -- the real ``data/pricing.json``
is never opened by this file, and every fixture model id (``fake-haiku-a``, ``fake-sonnet-x``,
``fake-opus-z``, ...) is a synthetic tier-vocabulary id, never a real model id. Digests are
synthetic dicts built in-process; no ``journal_collect.py`` output or real ``journal/``
directory is ever read. The ``--dry-run`` end-to-end tests additionally prove the negative by
patching ``default_runner`` with a "bomb" callable that raises ``AssertionError`` if invoked at
all, then asserting ``--dry-run`` still exits 0 and writes nothing.

bin/ is not a package; journal_summarize.py is loaded via importlib by absolute path computed
from this file's own location (BIN_DIR), mirroring tests/test_journal_collect.py.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


jsz = _load("journal_summarize")


# ---- fixtures ---------------------------------------------------------------------------------

# A synthetic STUB executable name used wherever the default_runner subprocess seam is
# exercised for real. Deliberately not the real CLI's name.
STUB_NAME = "stub-model.sh"

# Logs argv (joined) and the full stdin to two files, then echoes a canned doc file's content
# to stdout and exits 0 -- proves the prompt arrives on stdin, never in argv.
STUB_SHELL_TEMPLATE = (
    "#!/bin/sh\n"
    "printf '%s' \"$*\" > \"{argv_log}\"\n"
    "cat > \"{stdin_log}\"\n"
    "cat \"{doc_file}\"\n"
)

VALID_DOC = "# Stub heading\n\n" + ("Body text from the stub. " * 20) + "\n"
SHORT_DOC = "# too short\n"
HEADINGLESS_DOC = "No heading on this one.\n" + ("padding text " * 30)

# Tier vocabulary ("haiku"/"sonnet"/"opus") is the sanctioned structural exception; every
# model id here is synthetic and deliberately absent from the real data/pricing.json.
PRICING_FIXTURE = {
    "models": {
        "fake-haiku-b": {"tier": "haiku"},
        "fake-haiku-a": {"tier": "haiku"},
        "fake-sonnet-x": {"tier": "sonnet"},
        "fake-opus-z": {"tier": "opus"},
    }
}

# No haiku-tier entry at all -- proves pick_models skips a missing tier and falls through.
SONNET_ONLY_FIXTURE = {
    "models": {
        "fake-sonnet-x": {"tier": "sonnet"},
        "fake-opus-z": {"tier": "opus"},
    }
}

# Only a tier outside TIER_LADDER -- pick_models must raise ValueError (empty ladder).
NO_LADDER_TIER_FIXTURE = {
    "models": {
        "fake-frontier-q": {"tier": "frontier"},
    }
}

MODELS_TWO = ["fake-sonnet-x", "fake-opus-z"]


def _digest(date_str, **overrides):
    d = {
        "schema_version": 1,
        "date": date_str,
        "generated_at": "2026-07-01T05:00:00+00:00",
        "day_start": f"{date_str}T00:00:00+00:00",
        "timezone": "utc",
        "sources": {
            "git": {
                "repos": [
                    {"name": "polytropos", "branch": "main",
                     "commits": [{"subject": "Add daily-journal kit"}]},
                ]
            },
        },
        "totals": {"sessions": 3, "cost_usd": 1.23},
        "signals": {
            "kit_tasks": [{"kit": "daily-journal", "id": "T9", "title": "regression tests",
                            "status": "in-progress", "model": "sonnet"}],
            "inbox": ["follow up on pricing sync"],
            "wip": [{"repo": "polytropos", "branch": "main", "dirty": 2}],
        },
    }
    d.update(overrides)
    return d


SAMPLE_DIGEST = _digest("2026-06-30")


def _call_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = jsz.main(argv)
    return rc, buf.getvalue()


def _write_digest(journal_dir, digest):
    day_dir = journal_dir / str(digest["date"])
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "digest.json").write_text(json.dumps(digest))
    return day_dir


def _scripted_runner(script):
    """Build a fake ``runner(argv, prompt) -> (rc, text)`` keyed by the model id (the last argv
    element, per build_dispatch's shape). ``.calls`` records every ``(model_id, prompt)`` pair
    actually dispatched, in order."""
    calls = []

    def runner(argv, prompt):
        model_id = argv[-1]
        calls.append((model_id, prompt))
        return script[model_id]

    runner.calls = calls
    return runner


# ---- 1. pick_models -----------------------------------------------------------------------

class PickModelsTests(unittest.TestCase):
    def test_order_within_tier_matches_pricing_file_order(self):
        ladder = jsz.pick_models(PRICING_FIXTURE, "haiku")
        self.assertEqual(ladder[0], "fake-haiku-b")  # first haiku entry in dict/file order

    def test_start_tier_haiku_escalates_to_sonnet(self):
        ladder = jsz.pick_models(PRICING_FIXTURE, "haiku")
        self.assertEqual(ladder, ["fake-haiku-b", "fake-sonnet-x"])

    def test_start_tier_sonnet_escalates_to_opus(self):
        ladder = jsz.pick_models(PRICING_FIXTURE, "sonnet")
        self.assertEqual(ladder, ["fake-sonnet-x", "fake-opus-z"])

    def test_start_tier_opus_is_ladder_end_single_model(self):
        ladder = jsz.pick_models(PRICING_FIXTURE, "opus")
        self.assertEqual(ladder, ["fake-opus-z"])

    def test_cap_at_two_never_reaches_opus_from_haiku_start(self):
        ladder = jsz.pick_models(PRICING_FIXTURE, "haiku")
        self.assertEqual(len(ladder), 2)
        self.assertNotIn("fake-opus-z", ladder)

    def test_skipped_missing_tier_falls_through_to_next_present_tier(self):
        ladder = jsz.pick_models(SONNET_ONLY_FIXTURE, "haiku")
        self.assertEqual(ladder, ["fake-sonnet-x", "fake-opus-z"])

    def test_bad_start_tier_raises_value_error(self):
        with self.assertRaises(ValueError):
            jsz.pick_models(PRICING_FIXTURE, "bogus-tier")

    def test_empty_start_tier_raises_value_error(self):
        with self.assertRaises(ValueError):
            jsz.pick_models(PRICING_FIXTURE, "")

    def test_no_models_at_or_above_start_tier_raises_value_error(self):
        with self.assertRaises(ValueError):
            jsz.pick_models(NO_LADDER_TIER_FIXTURE, "haiku")


# ---- 2. output_ok --------------------------------------------------------------------------

class OutputOkTests(unittest.TestCase):
    def test_empty_string_is_not_ok(self):
        self.assertFalse(jsz.output_ok(""))

    def test_short_heading_doc_is_not_ok(self):
        self.assertFalse(jsz.output_ok(SHORT_DOC))

    def test_headingless_long_doc_is_not_ok(self):
        self.assertGreaterEqual(len(HEADINGLESS_DOC.strip()), jsz.MIN_OK_CHARS)
        self.assertFalse(jsz.output_ok(HEADINGLESS_DOC))

    def test_exactly_min_length_heading_doc_is_ok(self):
        text = "#" + ("x" * (jsz.MIN_OK_CHARS - 1))
        self.assertEqual(len(text.strip()), jsz.MIN_OK_CHARS)
        self.assertTrue(jsz.output_ok(text))

    def test_one_under_min_length_heading_doc_is_not_ok(self):
        text = "#" + ("x" * (jsz.MIN_OK_CHARS - 2))
        self.assertEqual(len(text.strip()), jsz.MIN_OK_CHARS - 1)
        self.assertFalse(jsz.output_ok(text))


# ---- 3. build_prompts ----------------------------------------------------------------------

class BuildPromptsTests(unittest.TestCase):
    def _check(self, date_str, expected_next_date):
        digest = _digest(date_str)
        prompts = jsz.build_prompts(digest)
        self.assertEqual(set(prompts), {"narrative", "technical", "next_day"})

        compact = json.dumps(digest, indent=None, separators=(",", ":"))
        tail = "Respond with ONLY the markdown document."

        narrative = prompts["narrative"]
        self.assertIn(f"# Work journal — {date_str}\n\n", narrative)
        self.assertIn(compact, narrative)
        self.assertIn(tail, narrative)

        technical = prompts["technical"]
        self.assertIn(f"# Technical summary — {date_str}\n\n", technical)
        self.assertIn(compact, technical)
        self.assertIn(tail, technical)
        i1 = technical.index("## Sessions & cost")
        i2 = technical.index("## Models")
        i3 = technical.index("## Repos & commits")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)

        next_day = prompts["next_day"]
        self.assertIn(f"# Plan for {expected_next_date}\n\n", next_day)
        self.assertIn(compact, next_day)
        self.assertIn(tail, next_day)
        j1 = next_day.index("## Start here")
        j2 = next_day.index("## To-dos")
        j3 = next_day.index("## How to run")
        self.assertLess(j1, j2)
        self.assertLess(j2, j3)

    def test_month_rollover_june_to_july(self):
        self._check("2026-06-30", "2026-07-01")

    def test_year_rollover_december_to_january(self):
        self._check("2026-12-31", "2027-01-01")


# ---- 4. build_dispatch ---------------------------------------------------------------------

class BuildDispatchTests(unittest.TestCase):
    def test_argv_shape(self):
        bin_path = str(Path("/nonexistent") / STUB_NAME)
        argv = jsz.build_dispatch("fake-sonnet-x", bin_path)
        self.assertEqual(argv, [bin_path, "-p", "--model", "fake-sonnet-x"])

    def test_prompt_never_appears_in_argv(self):
        bin_path = str(Path("/nonexistent") / STUB_NAME)
        prompt = jsz.build_prompts(SAMPLE_DIGEST)["technical"]
        argv = jsz.build_dispatch("fake-sonnet-x", bin_path)
        self.assertFalse(any(prompt in str(a) for a in argv))
        self.assertEqual(len(argv), 4)


# ---- 5. summarize ---------------------------------------------------------------------------

class SummarizeTests(unittest.TestCase):
    def test_accepts_first_model_no_escalation(self):
        runner = _scripted_runner({
            "fake-sonnet-x": (0, VALID_DOC),
            "fake-opus-z": (0, VALID_DOC),
        })
        docs, meta = jsz.summarize(SAMPLE_DIGEST, MODELS_TWO, runner)
        self.assertEqual(set(docs), set(jsz.DOCS))
        for doc in jsz.DOCS:
            self.assertEqual(meta["docs"][doc]["model"], "fake-sonnet-x")
            self.assertFalse(meta["docs"][doc]["escalated"])
            self.assertEqual(meta["docs"][doc]["attempts"],
                              [{"model": "fake-sonnet-x", "rc": 0, "ok": True}])
        self.assertEqual(len(runner.calls), len(jsz.DOCS))

    def test_escalates_on_nonzero_rc(self):
        runner = _scripted_runner({
            "fake-sonnet-x": (1, ""),
            "fake-opus-z": (0, VALID_DOC),
        })
        docs, meta = jsz.summarize(SAMPLE_DIGEST, MODELS_TWO, runner)
        self.assertEqual(set(docs), set(jsz.DOCS))
        for doc in jsz.DOCS:
            self.assertEqual(meta["docs"][doc]["model"], "fake-opus-z")
            self.assertTrue(meta["docs"][doc]["escalated"])
            self.assertEqual(len(meta["docs"][doc]["attempts"]), 2)
            self.assertFalse(meta["docs"][doc]["attempts"][0]["ok"])
            self.assertTrue(meta["docs"][doc]["attempts"][1]["ok"])

    def test_escalates_on_short_output(self):
        runner = _scripted_runner({
            "fake-sonnet-x": (0, SHORT_DOC),
            "fake-opus-z": (0, VALID_DOC),
        })
        docs, meta = jsz.summarize(SAMPLE_DIGEST, MODELS_TWO, runner)
        self.assertEqual(set(docs), set(jsz.DOCS))
        for doc in jsz.DOCS:
            self.assertTrue(meta["docs"][doc]["escalated"])

    def test_escalates_on_headingless_output(self):
        runner = _scripted_runner({
            "fake-sonnet-x": (0, HEADINGLESS_DOC),
            "fake-opus-z": (0, VALID_DOC),
        })
        docs, meta = jsz.summarize(SAMPLE_DIGEST, MODELS_TWO, runner)
        self.assertEqual(set(docs), set(jsz.DOCS))
        for doc in jsz.DOCS:
            self.assertTrue(meta["docs"][doc]["escalated"])

    def test_both_models_fail_doc_omitted_and_marked_failed(self):
        runner = _scripted_runner({
            "fake-sonnet-x": (1, ""),
            "fake-opus-z": (0, HEADINGLESS_DOC),
        })
        docs, meta = jsz.summarize(SAMPLE_DIGEST, MODELS_TWO, runner)
        self.assertEqual(docs, {})
        for doc in jsz.DOCS:
            self.assertNotIn(doc, docs)
            self.assertTrue(meta["docs"][doc]["failed"])
            attempts = meta["docs"][doc]["attempts"]
            self.assertEqual(len(attempts), 2)
            self.assertFalse(attempts[0]["ok"])
            self.assertFalse(attempts[1]["ok"])

    def test_at_most_two_attempts_even_with_longer_models_list(self):
        models_long = ["fake-sonnet-x", "fake-opus-z", "fake-extra-w"]
        runner = _scripted_runner({
            "fake-sonnet-x": (1, ""),
            "fake-opus-z": (1, ""),
            "fake-extra-w": (0, VALID_DOC),  # would succeed, but must never be tried
        })
        docs, meta = jsz.summarize(SAMPLE_DIGEST, models_long, runner)
        self.assertEqual(docs, {})
        for doc in jsz.DOCS:
            self.assertEqual(len(meta["docs"][doc]["attempts"]), 2)
            self.assertTrue(meta["docs"][doc]["failed"])
        called_models = {model_id for model_id, _ in runner.calls}
        self.assertNotIn("fake-extra-w", called_models)

    def test_meta_records_generated_at_and_start_models(self):
        runner = _scripted_runner({
            "fake-sonnet-x": (0, VALID_DOC),
            "fake-opus-z": (0, VALID_DOC),
        })
        _, meta = jsz.summarize(SAMPLE_DIGEST, MODELS_TWO, runner)
        self.assertEqual(meta["start_models"], MODELS_TWO)
        self.assertIn("generated_at", meta)


# ---- 6. default_runner against a stub executable -------------------------------------------

class DefaultRunnerStubExecutableTests(unittest.TestCase):
    def test_stub_executable_rc0_and_prompt_travels_via_stdin(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            argv_log = tmp / "argv.log"
            stdin_log = tmp / "stdin.log"
            doc_file = tmp / "doc.md"
            doc_file.write_text(VALID_DOC)

            stub_path = tmp / STUB_NAME
            stub_path.write_text(STUB_SHELL_TEMPLATE.format(
                argv_log=argv_log, stdin_log=stdin_log, doc_file=doc_file))
            stub_path.chmod(0o755)

            prompt = "distinctive prompt marker xyz-does-not-belong-in-argv"
            rc, out = jsz.default_runner(
                [str(stub_path), "-p", "--model", "fake-sonnet-x"], prompt)

            self.assertEqual(rc, 0)
            self.assertTrue(jsz.output_ok(out))
            self.assertEqual(stdin_log.read_text(), prompt)
            argv_logged = argv_log.read_text()
            self.assertIn("--model", argv_logged)
            self.assertIn("fake-sonnet-x", argv_logged)
            self.assertNotIn(prompt, argv_logged)  # prompt only ever arrives via stdin

    def test_nonexistent_binary_returns_rc127_never_resolving_a_bare_binary_name(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            # A fully-qualified, nonexistent path -- proves default_runner never falls back
            # to a PATH search for any bare binary name (real or otherwise).
            missing = Path(tmp_s) / "does-not-exist-binary"
            rc, out = jsz.default_runner(
                [str(missing), "-p", "--model", "fake-sonnet-x"], "some prompt text")
            self.assertEqual(rc, 127)
            self.assertIn("not found", out)


# ---- 7. main end-to-end (mocked default_runner + patched pricing) --------------------------

def _fake_runner_always_ok(argv, prompt):
    return (0, VALID_DOC)


def _fake_runner_next_day_always_fails(argv, prompt):
    if "# Plan for" in prompt:
        return (0, HEADINGLESS_DOC)
    return (0, VALID_DOC)


def _bomb_runner(argv, prompt):
    raise AssertionError("default_runner must never be called during --dry-run")


class MainEndToEndTests(unittest.TestCase):
    def test_success_writes_three_docs_and_meta_exit_zero(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            journal_dir = Path(tmp_s) / "journal"
            day_dir = _write_digest(journal_dir, SAMPLE_DIGEST)

            with mock.patch.object(jsz, "load_pricing", return_value=PRICING_FIXTURE), \
                 mock.patch.object(jsz, "default_runner", _fake_runner_always_ok):
                rc, _ = _call_main(
                    ["--journal-dir", str(journal_dir), "--date", SAMPLE_DIGEST["date"]])

            self.assertEqual(rc, 0)
            self.assertTrue((day_dir / "narrative.md").is_file())
            self.assertTrue((day_dir / "technical.md").is_file())
            self.assertTrue((day_dir / "next-day.md").is_file())
            meta = json.loads((day_dir / "summary-meta.json").read_text())
            self.assertEqual(set(meta["docs"]), set(jsz.DOCS))

    def test_doc_that_always_fails_exit_three_and_file_absent(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            journal_dir = Path(tmp_s) / "journal"
            day_dir = _write_digest(journal_dir, SAMPLE_DIGEST)

            with mock.patch.object(jsz, "load_pricing", return_value=PRICING_FIXTURE), \
                 mock.patch.object(jsz, "default_runner", _fake_runner_next_day_always_fails):
                rc, _ = _call_main(
                    ["--journal-dir", str(journal_dir), "--date", SAMPLE_DIGEST["date"]])

            self.assertEqual(rc, 3)
            self.assertTrue((day_dir / "narrative.md").is_file())
            self.assertTrue((day_dir / "technical.md").is_file())
            self.assertFalse((day_dir / "next-day.md").is_file())
            meta = json.loads((day_dir / "summary-meta.json").read_text())
            self.assertTrue(meta["docs"]["next_day"]["failed"])

    def test_dry_run_writes_nothing_and_never_calls_the_runner(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            journal_dir = Path(tmp_s) / "journal"
            day_dir = _write_digest(journal_dir, SAMPLE_DIGEST)

            with mock.patch.object(jsz, "load_pricing", return_value=PRICING_FIXTURE), \
                 mock.patch.object(jsz, "default_runner", _bomb_runner):
                rc, out = _call_main([
                    "--journal-dir", str(journal_dir), "--date", SAMPLE_DIGEST["date"],
                    "--dry-run",
                ])

            self.assertEqual(rc, 0)
            self.assertIn(jsz.PRIVACY_NOTE, out)
            self.assertEqual(out.count("=== PROMPT:"), 3)
            self.assertIn("=== PROMPT: narrative ===", out)
            self.assertIn("=== PROMPT: technical ===", out)
            self.assertIn("=== PROMPT: next_day ===", out)
            for name in ("narrative.md", "technical.md", "next-day.md", "summary-meta.json"):
                self.assertFalse((day_dir / name).exists())


# ---- 8. --model explicit id + error paths ---------------------------------------------------

class MainExplicitModelAndErrorsTests(unittest.TestCase):
    def test_explicit_model_is_single_model_list_no_escalation(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            journal_dir = Path(tmp_s) / "journal"
            day_dir = _write_digest(journal_dir, SAMPLE_DIGEST)

            with mock.patch.object(jsz, "load_pricing", return_value=PRICING_FIXTURE), \
                 mock.patch.object(jsz, "default_runner", _fake_runner_always_ok):
                rc, _ = _call_main([
                    "--journal-dir", str(journal_dir), "--date", SAMPLE_DIGEST["date"],
                    "--model", "fake-opus-z",
                ])

            self.assertEqual(rc, 0)
            meta = json.loads((day_dir / "summary-meta.json").read_text())
            self.assertEqual(meta["start_models"], ["fake-opus-z"])
            for doc in jsz.DOCS:
                self.assertFalse(meta["docs"][doc]["escalated"])
                self.assertEqual(len(meta["docs"][doc]["attempts"]), 1)

    def test_unknown_model_raises_systemexit(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            journal_dir = Path(tmp_s) / "journal"
            _write_digest(journal_dir, SAMPLE_DIGEST)

            with mock.patch.object(jsz, "load_pricing", return_value=PRICING_FIXTURE):
                with self.assertRaises(SystemExit):
                    jsz.main([
                        "--journal-dir", str(journal_dir), "--date", SAMPLE_DIGEST["date"],
                        "--model", "not-a-fixture-model-id",
                    ])

    def test_missing_digest_raises_systemexit_naming_the_path(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            journal_dir = Path(tmp_s) / "journal"  # no digest ever written here
            expected_path = journal_dir / "2026-07-02" / "digest.json"

            with mock.patch.object(jsz, "load_pricing", return_value=PRICING_FIXTURE):
                with self.assertRaises(SystemExit) as cm:
                    jsz.main([
                        "--journal-dir", str(journal_dir), "--date", "2026-07-02",
                    ])

            self.assertIn(str(expected_path), str(cm.exception.code))


if __name__ == "__main__":
    unittest.main()
