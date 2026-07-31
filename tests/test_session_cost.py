"""Regression tests for bin/session_cost.py.

Safety contract: no test reads the real ~/.claude or ~/.copilot, resolves the
real home directory, invokes any model, or touches the network. Every run is against
synthetic JSONL transcript fixtures in tempfile.TemporaryDirectory dirs with a
synthetic pricing dict (fake ids/rates) passed to the pure functions or patched
over load_pricing. No real model ids or prices are asserted.
"""

import importlib.util
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sc = _load("session_cost")

# Synthetic pricing — fake ids, round rates, fake multipliers. Frontier is the
# priciest (the default counterfactual target).
FIXTURE = {
    "cached_date": "2020-01-01",
    "billing_mode": "subscription",
    "cache_read_multiplier": 0.1,
    "cache_write_multiplier_5m": 1.25,
    "models": {
        "fake-frontier": {"display": "Fake Frontier", "tier": "frontier",
                          "input_per_mtok": 10.0, "output_per_mtok": 50.0},
        "fake-opus": {"display": "Fake Opus", "tier": "opus",
                      "input_per_mtok": 5.0, "output_per_mtok": 25.0},
        "fake-mid": {"display": "Fake Mid", "tier": "mid",
                     "input_per_mtok": 2.0, "output_per_mtok": 10.0},
        "fake-cheap": {"display": "Fake Cheap", "tier": "cheap",
                       "input_per_mtok": 1.0, "output_per_mtok": 5.0},
    },
}


def _line(model, mid, ts="2020-06-01T00:00:00Z",
          inp=0, out=0, cache_read=0, cache_write=0, sidechain=False):
    return json.dumps({
        "timestamp": ts,
        "isSidechain": sidechain,
        "message": {
            "id": mid,
            "model": model,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
            },
        },
    })


class CollectTests(unittest.TestCase):
    def test_global_dedup_across_files(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            main = root / "main.jsonl"
            main.write_text("\n".join([
                _line("fake-opus", "m1", out=1000),
                _line("fake-mid", "m2", out=500),
                "not json", "{}",  # robustness
            ]) + "\n")
            sub = root / "sub.output"
            sub.write_text("\n".join([
                _line("fake-mid", "m2", out=500),   # duplicate id -> ignored
                _line("fake-cheap", "m3", out=100),
            ]) + "\n")
            data = sc.collect([main, sub], FIXTURE)
        self.assertEqual(data["by_model"]["fake-opus"]["msgs"], 1)
        self.assertEqual(data["by_model"]["fake-mid"]["msgs"], 1)  # not 2
        self.assertEqual(data["by_model"]["fake-cheap"]["msgs"], 1)
        self.assertEqual(data["grand"]["output"], 1000 + 500 + 100)
        self.assertEqual(data["unique_messages"], 3)
        self.assertEqual(data["files_read"], 2)

    def test_unpriced_bucket_and_full_price(self):
        with TemporaryDirectory() as d:
            main = Path(d) / "main.jsonl"
            main.write_text("\n".join([
                _line("fake-opus", "m1", inp=1000, out=500,
                      cache_read=10000, cache_write=2000),
                _line("totally-unknown-model", "m9", out=999),
            ]) + "\n")
            data = sc.collect([main], FIXTURE)
        # (1000*5 + 500*25 + 10000*5*0.1 + 2000*5*1.25) / 1e6
        self.assertAlmostEqual(data["by_model"]["fake-opus"]["cost"], 0.035, places=9)
        self.assertEqual(data["unpriced"]["totally-unknown-model"], 999)
        self.assertNotIn("totally-unknown-model", data["by_model"])

    def test_read_error_collected_not_raised(self):
        data = sc.collect([Path("/no/such/file.jsonl")], FIXTURE)
        self.assertEqual(data["files_read"], 0)
        self.assertTrue(data["read_errors"])


class CounterfactualTests(unittest.TestCase):
    def _data(self):
        with TemporaryDirectory() as d:
            main = Path(d) / "m.jsonl"
            main.write_text("\n".join([
                _line("fake-opus", "m1", out=1000),
                _line("fake-mid", "m2", out=500),
                _line("fake-cheap", "m3", out=100),
            ]) + "\n")
            return sc.collect([main], FIXTURE)

    def test_counterfactual_prices_whole_volume_at_target(self):
        rep = sc.build_report(self._data(), "fake-frontier", FIXTURE, "subscription")
        # actual: 1000*25 + 500*10 + 100*5, all /1e6
        self.assertAlmostEqual(rep["actual_total"], 0.0305, places=9)
        # all-frontier: total output 1600 * 50 / 1e6
        self.assertAlmostEqual(rep["cf_total"], 0.08, places=9)
        self.assertAlmostEqual(rep["savings"], 0.08 - 0.0305, places=9)
        self.assertAlmostEqual(rep["ratio"], 0.08 / 0.0305, places=6)

    def test_frontier_row_unchanged_under_frontier_counterfactual(self):
        with TemporaryDirectory() as d:
            main = Path(d) / "m.jsonl"
            main.write_text(_line("fake-frontier", "m1", out=1000) + "\n")
            data = sc.collect([main], FIXTURE)
        rep = sc.build_report(data, "fake-frontier", FIXTURE, "api")
        row = next(r for r in rep["rows"] if r["key"] == "fake-frontier")
        self.assertAlmostEqual(row["actual_usd"], row["at_counterfactual_usd"], places=12)

    def test_vs_a_cheaper_model_costs_less(self):
        rep = sc.build_report(self._data(), "fake-mid", FIXTURE, "api")
        self.assertLess(rep["cf_total"], rep["actual_total"])  # mid is cheaper than the opus/frontier mix


class ResolveModelTests(unittest.TestCase):
    def test_default_is_frontier_tier(self):
        self.assertEqual(sc.resolve_counterfactual_model(None, FIXTURE), "fake-frontier")

    def test_explicit_model(self):
        self.assertEqual(sc.resolve_counterfactual_model("fake-mid", FIXTURE), "fake-mid")

    def test_unknown_raises_valueerror(self):
        with self.assertRaises(ValueError):
            sc.resolve_counterfactual_model("nope-not-real", FIXTURE)


class FindAndDiscoverTests(unittest.TestCase):
    def test_find_by_id_nested(self):
        with TemporaryDirectory() as d:
            proj = Path(d) / "some-slug"
            proj.mkdir()
            t = proj / "abc123.jsonl"
            t.write_text(_line("fake-mid", "m1", out=1) + "\n")
            found = sc.find_main_transcript("abc123", d)
        self.assertEqual(found, t)

    def test_find_default_latest(self):
        with TemporaryDirectory() as d:
            proj = Path(d) / "slug"
            proj.mkdir()
            old = proj / "old.jsonl"
            new = proj / "new.jsonl"
            old.write_text("{}\n")
            new.write_text("{}\n")
            import os
            os.utime(old, (1000, 1000))
            os.utime(new, (2000, 2000))
            found = sc.find_main_transcript(None, d)
        self.assertEqual(found, new)

    def test_find_missing_dir(self):
        self.assertIsNone(sc.find_main_transcript("x", "/no/such/dir/at/all"))

    def test_discover_task_dirs(self):
        with TemporaryDirectory() as d:
            base = Path(d)
            good = base / "claude-777" / "someslug" / "SID123" / "tasks"
            good.mkdir(parents=True)
            (base / "claude-777" / "someslug" / "OTHER" / "tasks").mkdir(parents=True)
            hits = sc.discover_task_dirs("SID123", bases=[str(base)])
            self.assertEqual([h.resolve() for h in hits], [good.resolve()])
            self.assertEqual(sc.discover_task_dirs("nomatch", bases=[str(base)]), [])


class GatherFilesTests(unittest.TestCase):
    def test_main_plus_taskdir_globs_output(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            main = root / "main.jsonl"
            main.write_text("{}\n")
            tasks = root / "tasks"
            tasks.mkdir()
            (tasks / "a.output").write_text("{}\n")
            (tasks / "b.output").write_text("{}\n")
            (tasks / "ignore.txt").write_text("{}\n")
            files = sc.gather_files(main, [tasks], [])
        names = [f.name for f in files]
        self.assertEqual(names, ["main.jsonl", "a.output", "b.output"])


class MainE2ETests(unittest.TestCase):
    def _make_session(self, root):
        proj = root / "slug"
        proj.mkdir()
        (proj / "SESS.jsonl").write_text("\n".join([
            _line("fake-opus", "m1", out=1000),
            _line("fake-frontier", "m2", out=1000),
        ]) + "\n")
        tasks = root / "tasks"
        tasks.mkdir()
        (tasks / "impl.output").write_text(_line("fake-mid", "m3", out=500) + "\n")
        (tasks / "check.output").write_text(_line("fake-cheap", "m4", out=100) + "\n")
        return proj, tasks

    def _run(self, argv):
        buf = io.StringIO()
        with mock.patch.object(sc.cr, "load_pricing", return_value=FIXTURE):
            with redirect_stdout(buf):
                sc.main(argv)
        return buf.getvalue()

    def test_json_with_subagents(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            _proj, tasks = self._make_session(root)
            out = self._run(["--session", "SESS", "--projects-dir", str(root),
                             "--tasks-dir", str(tasks), "--json"])
        obj = json.loads(out)
        self.assertEqual(obj["sources"]["subagent_transcripts"], 2)
        self.assertEqual(obj["counterfactual_model"]["display"], "Fake Frontier")
        # actual = 1000*25 + 1000*50 + 500*10 + 100*5 all /1e6
        self.assertAlmostEqual(obj["totals"]["actual_usd"], 0.0805, places=9)
        # counterfactual = 2600 output * 50 /1e6
        self.assertAlmostEqual(obj["totals"]["counterfactual_usd"], 0.13, places=9)

    def test_no_subagents_excludes_task_tokens(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            _proj, tasks = self._make_session(root)
            out = self._run(["--session", "SESS", "--projects-dir", str(root),
                             "--tasks-dir", str(tasks), "--no-subagents", "--json"])
        obj = json.loads(out)
        self.assertEqual(obj["sources"]["subagent_transcripts"], 0)
        # only the two main records: 1000*25 + 1000*50 /1e6
        self.assertAlmostEqual(obj["totals"]["actual_usd"], 0.075, places=9)

    def test_vs_flag_changes_target(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            _proj, tasks = self._make_session(root)
            out = self._run(["--session", "SESS", "--projects-dir", str(root),
                             "--tasks-dir", str(tasks), "--vs", "fake-mid", "--json"])
        obj = json.loads(out)
        self.assertEqual(obj["counterfactual_model"]["key"], "fake-mid")

    def test_markdown_smoke(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            _proj, tasks = self._make_session(root)
            out = self._run(["--session", "SESS", "--projects-dir", str(root),
                             "--tasks-dir", str(tasks)])
        self.assertIn("# Session cost — SESS", out)
        self.assertIn("Fake Frontier", out)
        self.assertIn("cheaper than", out)
        self.assertIn("API-equivalent", out)  # subscription-mode note

    def test_missing_session_exits(self):
        with TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                self._run(["--session", "NOPE", "--projects-dir", str(d), "--json"])

    def test_read_only_no_mutation(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            _proj, tasks = self._make_session(root)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self._run(["--session", "SESS", "--projects-dir", str(root),
                       "--tasks-dir", str(tasks), "--json"])
            after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)  # same files, same bytes — nothing written


class DefaultProjectsDirTests(unittest.TestCase):
    """The default --projects-dir honors CLAUDE_CONFIG_DIR (Claude Code's config-home
    override), else falls back to ~/.claude/projects. Real home never read — Path.home
    is patched to a fake path so the safety contract holds."""

    def test_honors_claude_config_dir_when_set(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/cfg/home"}, clear=False):
            self.assertEqual(sc._default_projects_dir(), Path("/cfg/home") / "projects")

    def test_blank_config_dir_falls_back_to_claude_home(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "   "}, clear=False), \
                mock.patch.object(sc.Path, "home", return_value=Path("/fake/home")):
            self.assertEqual(sc._default_projects_dir(), Path("/fake/home/.claude/projects"))

    def test_falls_back_to_claude_home_when_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(sc.Path, "home", return_value=Path("/fake/home")):
            self.assertEqual(sc._default_projects_dir(), Path("/fake/home/.claude/projects"))


if __name__ == "__main__":
    unittest.main()
