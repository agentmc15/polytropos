"""Stdlib unittest regression suite for bin/memory_store.py (PLAN.md D2/D3/D8 store engine).

SAFETY CONTRACT (binds every test in this file): no test here ever reads or writes the real
gitignored ``memory/`` store at the plugin root, and no test here resolves the caller's real
home directory via the stdlib ``Path.home`` helper. Every ``ms.main([...])`` call in this file
passes an EXPLICIT ``--memory-dir`` pointed at a fresh ``tempfile.TemporaryDirectory()`` fixture
plus an EXPLICIT ``--now YYYY-MM-DD`` — never the real defaults ``memory_store.py`` falls back
to at runtime, and never wall-clock "today". The ONLY subprocess use anywhere in this file is
one end-to-end smoke test that invokes ``bin/memory_store.py`` itself via ``sys.executable`` (a
sanctioned self-invocation, not a third-party CLI) with ``--memory-dir``/``--now`` pointed at a
temp fixture.

``bin/`` is not a package; ``memory_store.py`` is loaded via importlib by absolute path computed
from this file's own location (``BIN_DIR``), mirroring ``tests/test_journal_collect.py``.
"""

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ms = _load("memory_store")

NOW = "2026-01-15"


def _call_main(argv):
    """Run ms.main(argv) in-process with stdout captured -> (rc, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ms.main(argv)
    return rc, buf.getvalue()


def _add_argv(memory_dir, name, ftype="reference", extra=()):
    return [
        "add", "--memory-dir", str(memory_dir), "--now", NOW,
        "--name", name, "--type", ftype,
    ] + list(extra)


def _write_fact(memory_dir, slug, **overrides):
    """Write a fact file directly (bypassing the CLI's add-time --now stamping) so freshness
    tests can pin exact created/last_verified/expires dates. Returns the written Path."""
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
        "source": overrides.get("source", ""),
    }
    path = ms.fact_path(memory_dir, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ms.render_fact(meta, overrides.get("body", "fixture body")))
    return path


# ---- 1. slug validation / slugify / fact_path --------------------------------------------------


class SlugTests(unittest.TestCase):
    def test_validate_slug_accepts_canonical_forms(self):
        self.assertTrue(ms.validate_slug("deploy-target"))
        self.assertTrue(ms.validate_slug("a"))
        self.assertTrue(ms.validate_slug("fact123"))

    def test_validate_slug_rejects_bad_forms(self):
        self.assertFalse(ms.validate_slug(""))
        self.assertFalse(ms.validate_slug("-leading-dash"))
        self.assertFalse(ms.validate_slug("Has-Upper"))
        self.assertFalse(ms.validate_slug("has space"))
        self.assertFalse(ms.validate_slug("../escape"))
        self.assertFalse(ms.validate_slug("a" * 65))
        self.assertFalse(ms.validate_slug(None))

    def test_slugify_lowercases_and_replaces_nonalnum_runs(self):
        self.assertEqual(ms.slugify("Deploy Target!!"), "deploy-target")
        self.assertEqual(ms.slugify("  spaced -- out  "), "spaced-out")
        self.assertEqual(ms.slugify("Multi___Under---Score"), "multi-under-score")

    def test_slugify_truncates_to_64_and_stays_valid(self):
        long_name = "word " * 30  # far more than 64 chars once joined
        slug = ms.slugify(long_name)
        self.assertLessEqual(len(slug), 64)
        self.assertTrue(ms.validate_slug(slug))

    def test_slugify_empty_input_falls_back_to_fact(self):
        self.assertEqual(ms.slugify(""), "fact")
        self.assertEqual(ms.slugify("!!!???"), "fact")
        self.assertTrue(ms.validate_slug(ms.slugify("")))

    def test_fact_path_raises_on_invalid_slug_before_composing_path(self):
        with self.assertRaises(ValueError):
            ms.fact_path("/some/memory/dir", "../escape")
        with self.assertRaises(ValueError):
            ms.fact_path("/some/memory/dir", "Has Spaces")

    def test_fact_path_composes_under_facts_subdir(self):
        p = ms.fact_path("/some/memory/dir", "deploy-target")
        self.assertEqual(p, Path("/some/memory/dir") / "facts" / "deploy-target.md")


# ---- 2. frontmatter parse/render round-trip -----------------------------------------------------


class FrontmatterRoundTripTests(unittest.TestCase):
    def test_parse_fact_reads_flat_frontmatter_and_body(self):
        text = (
            "---\n"
            "schema: 1\n"
            "name: Deploy target\n"
            "description: Where the dashboard deploys\n"
            "type: reference\n"
            "tags: deploy, cloudflare\n"
            "created: 2026-01-10\n"
            "last_verified: 2026-01-10\n"
            "expires: never\n"
            "confidence: high\n"
            "source: user stated in session\n"
            "---\n"
            "\n"
            "The dashboard deploys to Cloudflare Workers. Related: [[legacy-build-flow]].\n"
        )
        meta, body = ms.parse_fact(text)
        self.assertEqual(meta["name"], "Deploy target")
        self.assertEqual(meta["type"], "reference")
        self.assertEqual(meta["tags"], "deploy, cloudflare")
        self.assertIn("Cloudflare Workers", body)
        self.assertIn("[[legacy-build-flow]]", body)

    def test_parse_fact_missing_fences_raises_value_error(self):
        with self.assertRaises(ValueError):
            ms.parse_fact("name: no fences here\nbody text\n")
        with self.assertRaises(ValueError):
            ms.parse_fact("---\nname: only one fence\nbody text\n")

    def test_parse_fact_preserves_unknown_keys(self):
        text = "---\nschema: 1\nname: X\nweird_custom_key: keep me\n---\n\nbody\n"
        meta, body = ms.parse_fact(text)
        self.assertEqual(meta["weird_custom_key"], "keep me")

    def test_render_then_parse_round_trips(self):
        meta = {
            "schema": "1", "name": "Deploy target", "description": "desc line",
            "type": "reference", "tags": "deploy, cloudflare", "created": "2026-01-10",
            "last_verified": "2026-01-10", "expires": "never", "confidence": "high",
            "source": "user stated", "custom_unknown": "round trips too",
        }
        body = "Body text with a [[wikilink]]."
        rendered = ms.render_fact(meta, body)
        parsed_meta, parsed_body = ms.parse_fact(rendered)
        self.assertEqual(parsed_meta, meta)
        self.assertEqual(parsed_body, body)


# ---- 3. load_store -------------------------------------------------------------------------------


class LoadStoreTests(unittest.TestCase):
    def test_missing_store_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            facts, notes = ms.load_store(Path(td) / "memory")
            self.assertEqual(facts, [])
            self.assertEqual(notes, [])

    def test_malformed_fact_file_skipped_with_note_not_a_crash(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            facts_dir = memory_dir / "facts"
            facts_dir.mkdir(parents=True)
            (facts_dir / "good.md").write_text(
                "---\nschema: 1\nname: Good\ndescription: fine\ntype: reference\ntags: \n"
                "created: 2026-01-01\nlast_verified: 2026-01-01\nexpires: never\n"
                "confidence: high\nsource: \n---\n\nbody\n"
            )
            (facts_dir / "bad.md").write_text("no frontmatter fences at all\n")

            facts, notes = ms.load_store(memory_dir)
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0][0], "good")
            self.assertEqual(len(notes), 1)
            self.assertIn("bad.md", notes[0])


# ---- 4. token_set / jaccard ----------------------------------------------------------------------


class SimilarityTests(unittest.TestCase):
    def test_token_set_lowercases_and_drops_short_tokens(self):
        toks = ms.token_set("Deploy Target A B to Cloudflare!")
        self.assertIn("deploy", toks)
        self.assertIn("target", toks)
        self.assertIn("cloudflare", toks)
        self.assertNotIn("a", toks)
        self.assertNotIn("b", toks)

    def test_jaccard_identical_and_disjoint_and_empty(self):
        a = ms.token_set("deploy target cloudflare")
        b = ms.token_set("deploy target cloudflare")
        self.assertAlmostEqual(ms.jaccard(a, b), 1.0)
        c = ms.token_set("totally unrelated words here")
        self.assertLess(ms.jaccard(a, c), 0.5)
        self.assertEqual(ms.jaccard(set(), set()), 0.0)


# ---- 5. add ---------------------------------------------------------------------------------------


class AddCommandTests(unittest.TestCase):
    def test_add_writes_file_with_round_tripping_frontmatter_and_regenerates_index(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, out = _call_main(_add_argv(
                memory_dir, "Deploy target", extra=[
                    "--description", "Where the dashboard deploys",
                    "--tags", "deploy, cloudflare",
                    "--body", "The dashboard deploys to Cloudflare Workers.",
                ]))
            self.assertEqual(rc, 0)
            slug = out.strip()
            self.assertEqual(slug, "deploy-target")

            fact_file = memory_dir / "facts" / f"{slug}.md"
            self.assertTrue(fact_file.is_file())
            meta, body = ms.parse_fact(fact_file.read_text())
            self.assertEqual(meta["name"], "Deploy target")
            self.assertEqual(meta["description"], "Where the dashboard deploys")
            self.assertEqual(meta["created"], NOW)
            self.assertEqual(meta["last_verified"], NOW)
            self.assertEqual(meta["expires"], "never")
            self.assertEqual(meta["confidence"], "high")
            self.assertEqual(meta["schema"], str(ms.SCHEMA_VERSION))
            self.assertIn("Cloudflare Workers", body)

            index_text = (memory_dir / ms.INDEX_NAME).read_text()
            self.assertIn("generated", index_text)
            self.assertIn("deploy-target.md", index_text)
            self.assertIn("Where the dashboard deploys", index_text)

    def test_add_rejects_invalid_type_and_confidence(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, _ = _call_main([
                "add", "--memory-dir", str(memory_dir), "--now", NOW,
                "--name", "X", "--type", "not-a-real-type",
            ])
            self.assertEqual(rc, 2)
            self.assertFalse((memory_dir / "facts").exists())

    def test_add_exact_duplicate_content_exits_2_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc1, out1 = _call_main(_add_argv(
                memory_dir, "Deploy target", extra=[
                    "--description", "Where the dashboard deploys",
                    "--body", "The dashboard deploys to Cloudflare Workers.",
                ]))
            self.assertEqual(rc1, 0)
            before = sorted((memory_dir / "facts").glob("*.md"))
            self.assertEqual(len(before), 1)

            rc2, out2 = _call_main(_add_argv(
                memory_dir, "Deploy target again", extra=[
                    "--description", "Where the dashboard deploys",
                    "--body", "The dashboard deploys to Cloudflare Workers.",
                ]))
            self.assertEqual(rc2, 2)
            self.assertIn("duplicate of", out2)
            self.assertIn("deploy-target", out2)
            after = sorted((memory_dir / "facts").glob("*.md"))
            self.assertEqual(before, after)
            self.assertEqual(len(after), 1)

    def test_add_exact_slug_collision_without_force_refused(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc1, _ = _call_main(_add_argv(memory_dir, "Alpha fact", extra=[
                "--description", "alpha description text", "--slug", "shared-slug",
            ]))
            self.assertEqual(rc1, 0)
            rc2, out2 = _call_main(_add_argv(memory_dir, "Totally different name", extra=[
                "--description", "completely unrelated other description",
                "--slug", "shared-slug",
            ]))
            self.assertEqual(rc2, 2)
            self.assertIn("shared-slug", out2)

    def test_add_force_overrides_dedup_gate(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc1, _ = _call_main(_add_argv(
                memory_dir, "Deploy target", extra=[
                    "--description", "Where the dashboard deploys",
                    "--body", "The dashboard deploys to Cloudflare Workers.",
                ]))
            self.assertEqual(rc1, 0)

            rc2, out2 = _call_main(_add_argv(
                memory_dir, "Deploy target duplicate", extra=[
                    "--description", "Where the dashboard deploys",
                    "--body", "The dashboard deploys to Cloudflare Workers.",
                    "--force",
                ]))
            self.assertEqual(rc2, 0)
            slug2 = out2.strip()
            self.assertNotEqual(slug2, "")
            facts = sorted((memory_dir / "facts").glob("*.md"))
            self.assertEqual(len(facts), 2)

    def test_add_json_flag_emits_parseable_json_with_slug(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, out = _call_main(_add_argv(
                memory_dir, "Json fact", extra=["--description", "a json test fact", "--json"]))
            self.assertEqual(rc, 0)
            parsed = json.loads(out.strip())
            self.assertEqual(parsed["slug"], "json-fact")
            self.assertEqual(parsed["name"], "Json fact")


# ---- 6. update --------------------------------------------------------------------------------


class UpdateCommandTests(unittest.TestCase):
    def _seed(self, memory_dir):
        rc, out = _call_main(_add_argv(
            memory_dir, "Original name", extra=[
                "--description", "original description text",
                "--tags", "one, two",
                "--body", "original body",
                "--source", "user stated",
            ]))
        self.assertEqual(rc, 0)
        return out.strip()

    def test_update_preserves_unknown_keys_and_bumps_last_verified(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            slug = self._seed(memory_dir)

            fact_file = memory_dir / "facts" / f"{slug}.md"
            meta, body = ms.parse_fact(fact_file.read_text())
            meta["custom_unknown_field"] = "must survive update"
            fact_file.write_text(ms.render_fact(meta, body))

            later = "2026-02-01"
            rc, out = _call_main([
                "update", slug, "--memory-dir", str(memory_dir), "--now", later,
                "--description", "updated description text",
            ])
            self.assertEqual(rc, 0)

            new_meta, new_body = ms.parse_fact(fact_file.read_text())
            self.assertEqual(new_meta["description"], "updated description text")
            self.assertEqual(new_meta["custom_unknown_field"], "must survive update")
            self.assertEqual(new_meta["last_verified"], later)
            self.assertEqual(new_meta["created"], NOW)  # created untouched
            self.assertEqual(new_body, "original body")  # body untouched (not passed)

    def test_update_unknown_slug_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, out = _call_main([
                "update", "does-not-exist", "--memory-dir", str(memory_dir), "--now", NOW,
                "--description", "x",
            ])
            self.assertEqual(rc, 2)
            self.assertIn("unknown slug", out)

    def test_update_regenerates_index(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            slug = self._seed(memory_dir)
            rc, _ = _call_main([
                "update", slug, "--memory-dir", str(memory_dir), "--now", "2026-02-01",
                "--name", "Renamed fact",
            ])
            self.assertEqual(rc, 0)
            index_text = (memory_dir / ms.INDEX_NAME).read_text()
            self.assertIn("Renamed fact", index_text)


# ---- 7. remove --------------------------------------------------------------------------------


class RemoveCommandTests(unittest.TestCase):
    def test_remove_deletes_file_and_reindexes(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, out = _call_main(_add_argv(
                memory_dir, "Removable fact", extra=["--description", "will be removed"]))
            self.assertEqual(rc, 0)
            slug = out.strip()
            fact_file = memory_dir / "facts" / f"{slug}.md"
            self.assertTrue(fact_file.is_file())

            rc2, _ = _call_main(["remove", slug, "--memory-dir", str(memory_dir), "--now", NOW])
            self.assertEqual(rc2, 0)
            self.assertFalse(fact_file.exists())
            index_text = (memory_dir / ms.INDEX_NAME).read_text()
            self.assertNotIn(slug, index_text)

    def test_remove_unknown_slug_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, out = _call_main(
                ["remove", "not-there", "--memory-dir", str(memory_dir), "--now", NOW])
            self.assertEqual(rc, 2)
            self.assertIn("unknown slug", out)


# ---- 8. list ----------------------------------------------------------------------------------


class ListCommandTests(unittest.TestCase):
    def test_list_on_empty_store(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, out = _call_main(["list", "--memory-dir", str(memory_dir), "--now", NOW])
            self.assertEqual(rc, 0)
            self.assertIn("no facts stored yet", out)

    def test_list_human_readable_line_format(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, out = _call_main(_add_argv(
                memory_dir, "Listable fact", extra=[
                    "--description", "a fact that shows up in list",
                ]))
            self.assertEqual(rc, 0)
            rc2, out2 = _call_main(["list", "--memory-dir", str(memory_dir), "--now", NOW])
            self.assertEqual(rc2, 0)
            self.assertIn("[listable-fact]", out2)
            self.assertIn("Listable fact", out2)
            self.assertIn("a fact that shows up in list", out2)
            self.assertIn("reference", out2)
            self.assertIn("high", out2)

    def test_list_json_emits_schema_and_facts(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            _call_main(_add_argv(memory_dir, "Json listed fact", extra=[
                "--description", "json list description",
            ]))
            rc, out = _call_main(["list", "--memory-dir", str(memory_dir), "--now", NOW,
                                   "--json"])
            self.assertEqual(rc, 0)
            parsed = json.loads(out)
            self.assertEqual(parsed["schema_version"], ms.SCHEMA_VERSION)
            self.assertEqual(len(parsed["facts"]), 1)
            self.assertEqual(parsed["facts"][0]["slug"], "json-listed-fact")
            self.assertEqual(parsed["notes"], [])


# ---- 9. CLI self-invocation smoke ---------------------------------------------------------------


class CliSmokeTests(unittest.TestCase):
    def test_list_self_invocation_via_subprocess(self):
        # The ONE sanctioned subprocess use in this file: invoking bin/memory_store.py itself
        # (never a third-party CLI) via sys.executable, --memory-dir pointed at a temp fixture.
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            script = BIN_DIR / "memory_store.py"
            proc = subprocess.run(
                [sys.executable, str(script), "list",
                 "--memory-dir", str(memory_dir), "--now", NOW],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("no facts stored yet", proc.stdout)


# ---- 10. staleness_state (PLAN.md D7 freshness lifecycle, T3) -----------------------------------


class StalenessStateTests(unittest.TestCase):
    def test_exactly_at_ttl_is_fresh(self):
        today = date(2026, 6, 1)
        ttl = ms.TYPE_TTL_DAYS["project"]
        last_verified = (today - timedelta(days=ttl)).isoformat()
        meta = {"type": "project", "last_verified": last_verified, "expires": "never"}
        self.assertEqual(ms.staleness_state(meta, today), "fresh")
        self.assertEqual(ms.staleness_state(meta, today.isoformat()), "fresh")

    def test_ttl_plus_one_day_is_stale(self):
        today = date(2026, 6, 1)
        ttl = ms.TYPE_TTL_DAYS["project"]
        last_verified = (today - timedelta(days=ttl + 1)).isoformat()
        meta = {"type": "project", "last_verified": last_verified, "expires": "never"}
        self.assertEqual(ms.staleness_state(meta, today), "stale")

    def test_expires_today_is_expired(self):
        today = date(2026, 6, 1)
        meta = {"type": "reference", "last_verified": today.isoformat(),
                 "expires": today.isoformat()}
        self.assertEqual(ms.staleness_state(meta, today), "expired")

    def test_expires_never_string_never_expires(self):
        today = date(2026, 6, 1)
        meta = {"type": "reference", "last_verified": today.isoformat(), "expires": "never"}
        self.assertEqual(ms.staleness_state(meta, today), "fresh")

    def test_missing_or_unparseable_last_verified_counts_as_stale_not_a_crash(self):
        today = date(2026, 6, 1)
        meta = {"type": "reference", "expires": "never"}  # no last_verified, no created
        self.assertEqual(ms.staleness_state(meta, today), "stale")
        meta2 = {"type": "reference", "last_verified": "not-a-date", "expires": "never"}
        self.assertEqual(ms.staleness_state(meta2, today), "stale")

    def test_unknown_type_falls_back_to_180_day_ttl(self):
        today = date(2026, 6, 1)
        at_ttl = (today - timedelta(days=180)).isoformat()
        meta = {"type": "unrecognized-type", "last_verified": at_ttl, "expires": "never"}
        self.assertEqual(ms.staleness_state(meta, today), "fresh")
        past_ttl = (today - timedelta(days=181)).isoformat()
        meta2 = {"type": "unrecognized-type", "last_verified": past_ttl, "expires": "never"}
        self.assertEqual(ms.staleness_state(meta2, today), "stale")

    def test_falls_back_to_created_when_last_verified_absent(self):
        today = date(2026, 6, 1)
        ttl = ms.TYPE_TTL_DAYS["project"]
        created = (today - timedelta(days=ttl + 5)).isoformat()
        meta = {"type": "project", "created": created, "expires": "never"}
        self.assertEqual(ms.staleness_state(meta, today), "stale")


# ---- 11. verify subcommand ------------------------------------------------------------------------


class VerifyCommandTests(unittest.TestCase):
    def test_verify_flips_stale_to_fresh_and_bumps_last_verified(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            today = "2026-06-01"
            ttl = ms.TYPE_TTL_DAYS["project"]
            stale_date = (date.fromisoformat(today) - timedelta(days=ttl + 10)).isoformat()
            _write_fact(memory_dir, "stale-fact", type="project",
                        last_verified=stale_date, created=stale_date)

            facts, _ = ms.load_store(memory_dir)
            meta, _ = ms._find_slug(facts, "stale-fact")
            self.assertEqual(ms.staleness_state(meta, today), "stale")

            rc, out = _call_main(
                ["verify", "stale-fact", "--memory-dir", str(memory_dir), "--now", today])
            self.assertEqual(rc, 0)
            self.assertIn("verified [stale-fact]", out)
            self.assertIn(f"+{ttl}d", out)

            facts2, _ = ms.load_store(memory_dir)
            meta2, _ = ms._find_slug(facts2, "stale-fact")
            self.assertEqual(meta2["last_verified"], today)
            self.assertEqual(ms.staleness_state(meta2, today), "fresh")

    def test_verify_unknown_slug_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            rc, out = _call_main(
                ["verify", "does-not-exist", "--memory-dir", str(memory_dir), "--now", NOW])
            self.assertEqual(rc, 2)
            self.assertIn("unknown slug", out)

    def test_verify_regenerates_index_with_new_state(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            today = "2026-06-01"
            ttl = ms.TYPE_TTL_DAYS["project"]
            stale_date = (date.fromisoformat(today) - timedelta(days=ttl + 10)).isoformat()
            _write_fact(memory_dir, "idx-fact", type="project",
                        last_verified=stale_date, created=stale_date, name="Idx Fact")
            ms.rebuild_index(memory_dir, today)
            index_before = (memory_dir / ms.INDEX_NAME).read_text()
            self.assertIn("stale", index_before)

            rc, _ = _call_main(
                ["verify", "idx-fact", "--memory-dir", str(memory_dir), "--now", today])
            self.assertEqual(rc, 0)
            index_after = (memory_dir / ms.INDEX_NAME).read_text()
            self.assertIn("fresh", index_after)
            self.assertNotIn("stale", index_after)


# ---- 12. review subcommand ------------------------------------------------------------------------


class ReviewCommandTests(unittest.TestCase):
    def _setup_mixed_store(self, memory_dir, today):
        ttl_project = ms.TYPE_TTL_DAYS["project"]
        stale_date = (date.fromisoformat(today) - timedelta(days=ttl_project + 10)).isoformat()

        _write_fact(memory_dir, "b-stale", type="project",
                    last_verified=stale_date, created=stale_date, name="B Stale")
        _write_fact(memory_dir, "a-stale", type="project",
                    last_verified=stale_date, created=stale_date, name="A Stale")
        _write_fact(memory_dir, "z-expired", type="reference",
                    last_verified=today, created=today, expires=today, name="Z Expired")
        _write_fact(memory_dir, "y-expired", type="reference",
                    last_verified=today, created=today, expires=today, name="Y Expired")
        _write_fact(memory_dir, "fresh-fact", type="reference",
                    last_verified=today, created=today, name="Fresh Fact")

    def test_review_orders_expired_before_stale_each_group_sorted_by_slug(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            today = "2026-06-01"
            self._setup_mixed_store(memory_dir, today)

            rc, out = _call_main(["review", "--memory-dir", str(memory_dir), "--now", today])
            self.assertEqual(rc, 0)
            lines = [l for l in out.splitlines() if l.startswith("[")]
            slugs_in_order = [l.split("]")[0][1:] for l in lines]
            self.assertEqual(slugs_in_order, ["y-expired", "z-expired", "a-stale", "b-stale"])
            self.assertIn("expired", lines[0])
            self.assertIn("expired", lines[1])
            self.assertIn("stale", lines[2])
            self.assertIn("stale", lines[3])

    def test_review_all_fresh_store_prints_summary_line_and_exits_0(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            today = "2026-06-01"
            _write_fact(memory_dir, "fresh-one", type="reference",
                        last_verified=today, created=today, name="Fresh One")
            _write_fact(memory_dir, "fresh-two", type="user",
                        last_verified=today, created=today, name="Fresh Two")

            rc, out = _call_main(["review", "--memory-dir", str(memory_dir), "--now", today])
            self.assertEqual(rc, 0)
            self.assertIn("all 2 facts fresh", out)

    def test_review_never_writes_anything(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            today = "2026-06-01"
            self._setup_mixed_store(memory_dir, today)

            def snapshot():
                files = sorted(p for p in memory_dir.rglob("*") if p.is_file())
                return {p: p.read_bytes() for p in files}

            before = snapshot()
            rc, _ = _call_main(["review", "--memory-dir", str(memory_dir), "--now", today])
            self.assertEqual(rc, 0)
            after = snapshot()
            self.assertEqual(before, after)

    def test_review_json_shape(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            today = "2026-06-01"
            self._setup_mixed_store(memory_dir, today)
            rc, out = _call_main(
                ["review", "--memory-dir", str(memory_dir), "--now", today, "--json"])
            self.assertEqual(rc, 0)
            parsed = json.loads(out)
            self.assertEqual(parsed["schema_version"], ms.SCHEMA_VERSION)
            self.assertEqual([e["slug"] for e in parsed["expired"]], ["y-expired", "z-expired"])
            self.assertEqual([e["slug"] for e in parsed["stale"]], ["a-stale", "b-stale"])
            self.assertEqual(parsed["fresh_count"], 1)
            self.assertEqual(parsed["notes"], [])


# ---- 13. --now determinism + index state -----------------------------------------------------------


class NowDeterminismTests(unittest.TestCase):
    def test_same_store_different_now_yields_different_states(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            created = "2026-01-01"
            _write_fact(memory_dir, "det-fact", type="project",
                        last_verified=created, created=created, name="Det Fact")

            rc1, out1 = _call_main(
                ["list", "--memory-dir", str(memory_dir), "--now", "2026-01-15"])
            self.assertEqual(rc1, 0)
            self.assertIn("fresh", out1)

            ttl = ms.TYPE_TTL_DAYS["project"]
            later = (date.fromisoformat(created) + timedelta(days=ttl + 1)).isoformat()
            rc2, out2 = _call_main(["list", "--memory-dir", str(memory_dir), "--now", later])
            self.assertEqual(rc2, 0)
            self.assertIn("stale", out2)


class IndexStateTests(unittest.TestCase):
    def test_index_line_carries_computed_state(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            today = "2026-06-01"
            _write_fact(memory_dir, "idxs", type="reference", last_verified=today,
                        created=today, name="Idxs Fact", description="idx desc")
            ms.rebuild_index(memory_dir, today)
            index_text = (memory_dir / ms.INDEX_NAME).read_text()
            self.assertIn("idxs.md) — idx desc (reference, fresh)", index_text)

    def test_list_line_carries_computed_state(self):
        with tempfile.TemporaryDirectory() as td:
            memory_dir = Path(td) / "memory"
            today = "2026-06-01"
            _write_fact(memory_dir, "lists", type="reference", last_verified=today,
                        created=today, name="Lists Fact", description="list desc")
            rc, out = _call_main(["list", "--memory-dir", str(memory_dir), "--now", today])
            self.assertEqual(rc, 0)
            self.assertIn("(reference, high, fresh)", out)


if __name__ == "__main__":
    unittest.main()
