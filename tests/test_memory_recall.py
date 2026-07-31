"""Stdlib unittest regression suite for bin/memory_recall.py (PLAN.md D4/D5/D6 recall engine).

SAFETY CONTRACT (binds every test in this file): no test here ever reads or writes the real
gitignored ``memory/`` store at the plugin root, and no test here resolves the caller's real
home directory via the stdlib ``Path.home`` helper. Every ``mr.main([...])`` / ``mr.recall(...)``
call passes an EXPLICIT ``--memory-dir`` (or path) pointed at a fresh
``tempfile.TemporaryDirectory()`` fixture plus an EXPLICIT ``--now YYYY-MM-DD`` — never the real
defaults ``memory_recall.py`` falls back to at runtime, and never wall-clock "today". The recall
engine writes nothing anywhere (``--demo`` writes only inside its own temp dir). The ONLY
subprocess use anywhere in this file is one determinism smoke that invokes
``bin/memory_recall.py --demo`` via ``sys.executable`` (a sanctioned self-invocation, not a
third-party CLI); it reads no store and writes nothing outside the tool's own temp dir.

``bin/`` is not a package; both modules are loaded via importlib by absolute path computed from
this file's own location (``BIN_DIR``), mirroring ``tests/test_journal_collect.py``.
"""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
RECALL_PY = BIN_DIR / "memory_recall.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ms = _load("memory_store")
mr = _load("memory_recall")

NOW = "2026-01-15"


def _write_fact(memory_dir, slug, **overrides):
    """Write a fact file directly (bypassing the store CLI's add-time --now stamping and dedup
    gate) so recall tests can pin exact dates, tags, and bodies. Returns the written Path."""
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
    }
    body = overrides.get("body", "")
    path = ms.fact_path(memory_dir, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ms.render_fact(meta, body))
    return path


def _add_noise(memory_dir, count=5):
    """Write ``count`` unrelated facts (no query term anywhere) so a realistic corpus size
    keeps BM25 idf meaningful — in a tiny homogeneous store a term shared by every fact has
    near-zero idf and nothing clears the gate, which is correct BM25 behavior, not a bug."""
    for i in range(count):
        _write_fact(memory_dir, f"noise-{i}", name=f"Coffee note {i}", type="user",
                    tags="misc", body="An unrelated note about coffee mugs and standing desks.")


def _call_main(argv):
    """Run mr.main(argv) in-process with stdout captured -> (rc, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mr.main(argv)
    return rc, buf.getvalue()


def _recall_argv(memory_dir, query, extra=()):
    return ["--memory-dir", str(memory_dir), "--now", NOW, "--query", query] + list(extra)


class ConstantsTests(unittest.TestCase):
    def test_pinned_constants_exact(self):
        self.assertEqual(mr.MAX_FACTS, 5)
        self.assertEqual(mr.BUDGET_CHARS, 4000)
        self.assertEqual(mr.GATE_MIN_SCORE, 1.0)
        self.assertEqual(mr.GATE_MIN_TERMS, 2)
        self.assertEqual(mr.K_SAT, 1.2)
        self.assertEqual(mr.STALE_MULT, 0.6)
        self.assertEqual(mr.CONF_MULT, {"high": 1.0, "medium": 0.9, "low": 0.7})
        self.assertEqual(mr.FIELD_WEIGHTS,
                         {"name": 3, "tags": 3, "description": 2, "body": 1})
        self.assertEqual(mr.GATE_EMPTY_LINE,
                         "no memory above the relevance gate for this query")
        self.assertIn("the", mr.STOPWORDS)
        self.assertIn("with", mr.STOPWORDS)


class GateTests(unittest.TestCase):
    def test_irrelevant_query_recalls_nothing(self):
        """A populated store queried about none of its facts -> the pinned gate-empty line,
        exit 0 (an empty recall is a SUCCESS, not an error — PLAN.md D6)."""
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "editor-prefs", name="Editor preferences", type="user",
                        tags="editor, formatting", body="Two-space indentation on save.")
            _write_fact(d, "favorite-color", name="Favorite color", type="user",
                        tags="preference", body="The favorite color is teal.")
            rc, out = _call_main(_recall_argv(d, "kubernetes cluster autoscaling"))
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), mr.GATE_EMPTY_LINE)

    def test_gate_tag_exception_single_term(self):
        """A single-term query matching an EXACT tag token surfaces the fact even though it
        matched fewer than GATE_MIN_TERMS distinct terms (PLAN.md D6 tag exception). Rare-term
        idf (from the surrounding corpus) plus the tag+name+body weight clears GATE_MIN_SCORE."""
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "k8s-cluster", name="Kubernetes cluster", type="reference",
                        tags="kubernetes, ops",
                        body="The kubernetes cluster runs the kubernetes workloads.")
            _add_noise(d)  # raise idf for the rare 'kubernetes' term
            rc, out = _call_main(_recall_argv(d, "kubernetes"))
        self.assertEqual(rc, 0)
        self.assertIn("[k8s-cluster]", out)
        self.assertIn("Recalled memory (1 facts", out)


class ExpiredStaleTests(unittest.TestCase):
    def test_expired_withheld_and_stale_marked(self):
        """Expired facts are absent from recall AND counted as withheld; a stale fact is
        present, carries the STALE marker, and scores BELOW an otherwise-identical fresh fact
        (PLAN.md D5/D7). Both non-expired facts share body/tags so only freshness differs."""
        with tempfile.TemporaryDirectory() as d:
            body = "Deploy the build to cloudflare workers."
            tags = "deploy, cloudflare"
            _write_fact(d, "fresh-fact", name="Fresh deploy note", type="reference",
                        tags=tags, created="2026-01-10", last_verified="2026-01-10", body=body)
            # project TTL is 90d; verified 2025-09-01 is >90d before 2026-01-15 -> stale.
            _write_fact(d, "stale-fact", name="Stale deploy note", type="project",
                        tags=tags, created="2025-09-01", last_verified="2025-09-01", body=body)
            _write_fact(d, "gone-fact", name="Expired deploy note", type="reference",
                        tags=tags, expires="2025-12-31", body=body)
            _add_noise(d)

            rc, out = _call_main(_recall_argv(d, "deploy the build to cloudflare workers"))
            rc_json, out_json = _call_main(
                _recall_argv(d, "deploy the build to cloudflare workers", ["--json"]))

        self.assertEqual(rc, 0)
        self.assertEqual(rc_json, 0)
        # Expired absent from the surfaced block, counted as withheld.
        self.assertNotIn("[gone-fact]", out)
        self.assertIn("1 expired fact(s) withheld", out)
        # Stale present and marked.
        self.assertIn("[stale-fact]", out)
        self.assertIn("STALE, verify before relying", out)
        # Stale scores below the otherwise-identical fresh fact.
        data = json.loads(out_json)
        self.assertEqual(data["withheld_expired"], 1)
        scores = {f["slug"]: f["score"] for f in data["facts"]}
        self.assertIn("fresh-fact", scores)
        self.assertIn("stale-fact", scores)
        self.assertLess(scores["stale-fact"], scores["fresh-fact"])
        self.assertEqual([f["slug"] for f in data["facts"]], ["fresh-fact", "stale-fact"])

    def test_include_expired_surfaces_and_counts_in_corpus(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "gone-fact", name="Expired deploy note", type="reference",
                        tags="deploy, cloudflare", expires="2025-12-31",
                        body="Deploy the build to cloudflare workers now.")
            _add_noise(d)
            rc, out = _call_main(
                _recall_argv(d, "deploy the build to cloudflare workers", ["--include-expired"]))
        self.assertEqual(rc, 0)
        self.assertIn("[gone-fact]", out)
        self.assertNotIn("expired fact(s) withheld", out)


class BudgetTests(unittest.TestCase):
    def test_budget_truncates_whole_facts(self):
        """A gate survivor that would overflow --budget-chars is dropped ENTIRELY (never a
        partial body) with a trailing +N more line; a smaller earlier fact still lands whole."""
        with tempfile.TemporaryDirectory() as d:
            big_body = "Deploy the build to cloudflare workers. " + ("x" * 600)
            _write_fact(d, "small-fact", name="Small deploy", type="reference",
                        tags="deploy, cloudflare", last_verified="2026-01-10",
                        body="Deploy the build to cloudflare workers.")
            _write_fact(d, "big-fact", name="Big deploy", type="reference",
                        tags="deploy, cloudflare", last_verified="2026-01-09", body=big_body)
            _add_noise(d)
            # Budget fits the small fact but not the big one.
            rc, out = _call_main(
                _recall_argv(d, "deploy the build to cloudflare workers",
                             ["--budget-chars", "200"]))
        self.assertEqual(rc, 0)
        self.assertIn("[small-fact]", out)
        self.assertNotIn("[big-fact]", out)
        # No partial body of the dropped fact leaked.
        self.assertNotIn("xxxxx", out)
        self.assertIn("(+1 more above the gate", out)

    def test_top_fact_exceeds_budget_emits_pointer(self):
        """The single edge case: when the TOP survivor's body alone exceeds the budget, its
        header lands with a pointer line instead of the body (never a partial body)."""
        with tempfile.TemporaryDirectory() as d:
            huge = "Deploy the build to cloudflare workers. " + ("y" * 5000)
            _write_fact(d, "huge-fact", name="Huge deploy", type="reference",
                        tags="deploy, cloudflare", body=huge)
            _add_noise(d)
            rc, out = _call_main(
                _recall_argv(d, "deploy the build to cloudflare workers",
                             ["--budget-chars", "150"]))
        self.assertEqual(rc, 0)
        self.assertIn("[huge-fact]", out)
        self.assertIn("body exceeds budget — read memory/facts/huge-fact.md", out)
        self.assertNotIn("yyyyy", out)

    def test_max_facts_cap_drops_with_more_line(self):
        with tempfile.TemporaryDirectory() as d:
            for i, lv in enumerate(["2026-01-10", "2026-01-09", "2026-01-08"]):
                _write_fact(d, f"deploy-{i}", name=f"Deploy note {i}", type="reference",
                            tags="deploy, cloudflare", last_verified=lv,
                            body="Deploy the build to cloudflare workers.")
            _add_noise(d)
            rc, out = _call_main(
                _recall_argv(d, "deploy the build to cloudflare workers", ["--max-facts", "1"]))
        self.assertEqual(rc, 0)
        self.assertIn("Recalled memory (1 facts", out)
        self.assertIn("(+2 more above the gate", out)


class OrderingTests(unittest.TestCase):
    def test_tiebreak_last_verified_then_slug(self):
        """Equal final scores -> fresher last_verified first; equal dates -> slug ascending.
        All three facts share body/tags/type/confidence so raw scores are identical."""
        with tempfile.TemporaryDirectory() as d:
            body = "Deploy the build to cloudflare workers."
            tags = "deploy, cloudflare"
            # zulu & alpha share the newest date -> slug ascending between them; older is last.
            _write_fact(d, "zulu", name="Z", type="reference", tags=tags,
                        created="2026-01-12", last_verified="2026-01-12", body=body)
            _write_fact(d, "alpha", name="A", type="reference", tags=tags,
                        created="2026-01-12", last_verified="2026-01-12", body=body)
            _write_fact(d, "middle", name="M", type="reference", tags=tags,
                        created="2026-01-05", last_verified="2026-01-05", body=body)
            _add_noise(d)
            rc, out = _call_main(
                _recall_argv(d, "deploy the build to cloudflare workers", ["--json"]))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        order = [f["slug"] for f in data["facts"]]
        # Same score across all three; newest date pair ordered by slug, then the older one.
        self.assertEqual(order, ["alpha", "zulu", "middle"])
        self.assertAlmostEqual(data["facts"][0]["score"], data["facts"][2]["score"])


class JsonShapeTests(unittest.TestCase):
    def test_json_shape_and_rounding(self):
        with tempfile.TemporaryDirectory() as d:
            _write_fact(d, "deploy-target", name="Deploy target", type="reference",
                        tags="deploy, cloudflare",
                        body="Deploy the build to cloudflare workers.")
            _add_noise(d)
            rc, out = _call_main(
                _recall_argv(d, "deploy the build to cloudflare workers", ["--json"]))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(set(data.keys()),
                         {"schema_version", "query", "facts", "dropped_for_budget",
                          "withheld_expired", "notes"})
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["query"], ["deploy", "build", "cloudflare", "workers"])
        fact = data["facts"][0]
        self.assertEqual(set(fact.keys()),
                         {"slug", "name", "type", "confidence", "state", "score", "chars",
                          "body"})
        # score rounded to 4 decimals.
        self.assertEqual(fact["score"], round(fact["score"], 4))
        self.assertEqual(data["dropped_for_budget"], 0)
        self.assertEqual(data["withheld_expired"], 0)


class MissingStoreTests(unittest.TestCase):
    def test_missing_store_dir_friendly_line(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "does-not-exist"
            rc, out = _call_main(_recall_argv(missing, "deploy build cloudflare"))
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "no memory store yet")

    def test_missing_store_json(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "does-not-exist"
            rc, out = _call_main(_recall_argv(missing, "deploy build", ["--json"]))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["facts"], [])
        self.assertEqual(data["withheld_expired"], 0)


class DemoDeterminismTests(unittest.TestCase):
    def test_demo_byte_stable_via_self_invocation(self):
        """The ONE sanctioned subprocess: invoke the tool itself twice via sys.executable and
        assert byte-identical output (PLAN.md determinism tripwire)."""
        run1 = subprocess.run([sys.executable, str(RECALL_PY), "--demo"],
                              capture_output=True, text=True)
        run2 = subprocess.run([sys.executable, str(RECALL_PY), "--demo"],
                              capture_output=True, text=True)
        self.assertEqual(run1.returncode, 0)
        self.assertEqual(run2.returncode, 0)
        self.assertEqual(run1.stdout, run2.stdout)
        # The demo visibly demonstrates all three safeguards.
        self.assertIn("[deploy-target]", run1.stdout)
        self.assertIn("STALE, verify before relying", run1.stdout)
        self.assertIn("expired fact(s) withheld", run1.stdout)
        self.assertIn("(+1 more above the gate", run1.stdout)


if __name__ == "__main__":
    unittest.main()
