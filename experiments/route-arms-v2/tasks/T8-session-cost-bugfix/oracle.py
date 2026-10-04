"""Hidden oracle for T8-session-cost-bugfix.

The expected prices are recomputed from the sandbox's own data/pricing.json. No
Claude model id, price, multiplier, or cached date is embedded here.
"""

import contextlib
import importlib.util
import io
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PRICING = json.loads((ROOT / "data" / "pricing.json").read_text(encoding="utf-8"))
MODEL_KEYS = list(PRICING["models"])
if not MODEL_KEYS:
    raise RuntimeError("pricing.json has no models")
MODEL = MODEL_KEYS[0]
OTHER_MODEL = MODEL_KEYS[1] if len(MODEL_KEYS) > 1 else MODEL_KEYS[0]
UNKNOWN = "oracle_unknown_model"
PLACEHOLDER = "<oracle-placeholder>"
SCRATCH_ROOT = ROOT / "tests" / "_session_cost_bugfix_oracle_scratch"


def _load():
    spec = importlib.util.spec_from_file_location("route_oracle_session_cost",
                                                  ROOT / "bin" / "session_cost.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sc = _load()


def usage(inp=0, out=0, cache_read=0, cache_write=0, **overrides):
    data = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_write,
    }
    data.update(overrides)
    return data


def line(model=MODEL, mid="m", use=None, timestamp=None):
    msg = {"id": mid, "model": model, "usage": usage(out=11) if use is None else use}
    obj = {"message": msg}
    if timestamp is not None:
        obj["timestamp"] = timestamp
    return json.dumps(obj)


def expected_price(key, buckets):
    model = PRICING["models"][key]
    inp = model["input_per_mtok"]
    outp = model["output_per_mtok"]
    read_mult = model.get("cache_read_multiplier", PRICING["cache_read_multiplier"])
    write_mult = PRICING["cache_write_multiplier_5m"]
    return (
        buckets.get("input", 0) * inp
        + buckets.get("output", 0) * outp
        + buckets.get("cache_read", 0) * inp * read_mult
        + buckets.get("cache_write", 0) * inp * write_mult
    ) / 1_000_000


class ScratchCase(unittest.TestCase):
    def setUp(self):
        self.scratch = SCRATCH_ROOT / self.__class__.__name__ / self._testMethodName
        if self.scratch.exists():
            shutil.rmtree(self.scratch)
        self.scratch.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)
        for parent in [self.scratch.parent, SCRATCH_ROOT]:
            try:
                parent.rmdir()
            except OSError:
                pass

    def write_jsonl(self, name, records):
        path = self.scratch / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(records) + "\n", encoding="utf-8")
        return path

    def collect_lines(self, *records):
        return sc.collect([self.write_jsonl("session.jsonl", records)], PRICING)

    def make_session_tree(self, main_records, task_records=(), include_records=()):
        projects = self.scratch / "projects"
        session_dir = projects / "project-slug"
        session_dir.mkdir(parents=True)
        main = session_dir / "SESS.jsonl"
        main.write_text("\n".join(main_records) + "\n", encoding="utf-8")
        tasks = self.scratch / "tasks"
        tasks.mkdir()
        for index, record in enumerate(task_records):
            (tasks / f"task{index}.output").write_text(record + "\n", encoding="utf-8")
        includes = []
        for index, record in enumerate(include_records):
            path = self.scratch / "includes" / f"include{index}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(record + "\n", encoding="utf-8")
            includes.append(path)
        return projects, tasks, includes

    def call_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with mock.patch.object(sc.cr, "load_pricing", return_value=PRICING):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    sc.main(list(argv))
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
        return code, out.getvalue(), err.getvalue()


class UsageValidationTests(ScratchCase):
    def test_missing_buckets_default_to_zero_when_output_present(self):
        data = self.collect_lines(line(use={"output_tokens": 17}))
        self.assertEqual(data["grand"], {"input": 0, "output": 17, "cache_read": 0, "cache_write": 0})
        self.assertEqual(data["unique_messages"], 1)

    def test_none_bucket_defaults_to_zero(self):
        data = self.collect_lines(line(use=usage(inp=None, out=19)))
        self.assertEqual(data["grand"]["input"], 0)
        self.assertEqual(data["grand"]["output"], 19)
        self.assertEqual(data["unique_messages"], 1)

    def test_all_zero_usage_is_still_ignored(self):
        data = self.collect_lines(line(use={}))
        self.assertEqual(data["grand"], {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0})
        self.assertEqual(data["unique_messages"], 0)

    def test_string_token_skips_whole_record_without_crashing(self):
        data = self.collect_lines(line(use=usage(out="7")))
        self.assertEqual(data["by_model"], {})
        self.assertEqual(data["unique_messages"], 0)

    def test_float_token_skips_whole_record_without_crashing(self):
        data = self.collect_lines(line(use=usage(out=7.5)))
        self.assertEqual(data["grand"]["output"], 0)
        self.assertEqual(data["unique_messages"], 0)

    def test_boolean_token_skips_whole_record_without_crashing(self):
        data = self.collect_lines(line(use=usage(out=True)))
        self.assertEqual(data["by_model"], {})
        self.assertEqual(data["unique_messages"], 0)

    def test_negative_input_skips_whole_record(self):
        data = self.collect_lines(line(use=usage(inp=-1, out=23)))
        self.assertEqual(data["grand"]["output"], 0)
        self.assertEqual(data["unique_messages"], 0)

    def test_negative_cache_write_skips_whole_record(self):
        data = self.collect_lines(line(use=usage(out=23, cache_write=-4)))
        self.assertEqual(data["by_model"], {})
        self.assertEqual(data["unique_messages"], 0)

    def test_invalid_unknown_usage_is_not_added_to_unpriced(self):
        data = self.collect_lines(line(model=UNKNOWN, use=usage(out="9")))
        self.assertEqual(data["unpriced"], {})
        self.assertEqual(data["unique_messages"], 0)

    def test_valid_cache_read_and_write_are_priced_from_pricing(self):
        buckets = {"input": 13, "output": 29, "cache_read": 31, "cache_write": 37}
        data = self.collect_lines(line(use=usage(inp=13, out=29, cache_read=31, cache_write=37)))
        actual = data["by_model"][MODEL]["cost"]
        self.assertAlmostEqual(actual, expected_price(MODEL, buckets), places=12)
        self.assertEqual(data["grand"], buckets)


class UnknownModelTests(ScratchCase):
    def test_unknown_string_model_accumulates_unpriced_tokens(self):
        data = self.collect_lines(line(model=UNKNOWN, use=usage(inp=2, out=3, cache_read=5, cache_write=7)))
        self.assertEqual(data["unpriced"], {UNKNOWN: 17})
        self.assertEqual(data["unique_messages"], 0)

    def test_placeholder_unknown_model_is_ignored(self):
        data = self.collect_lines(line(model=PLACEHOLDER, use=usage(out=41)))
        self.assertEqual(data["unpriced"], {})
        self.assertEqual(data["unique_messages"], 0)

    def test_numeric_model_label_is_stringified_without_crashing(self):
        data = self.collect_lines(line(model=8675309, use=usage(out=43)))
        self.assertEqual(data["unpriced"], {"8675309": 43})
        self.assertEqual(data["unique_messages"], 0)

    def test_list_model_label_is_stringified_without_crashing(self):
        raw_model = ["oracle", "unknown"]
        data = self.collect_lines(line(model=raw_model, use=usage(out=47)))
        self.assertEqual(data["unpriced"], {str(raw_model): 47})
        self.assertEqual(data["unique_messages"], 0)

    def test_unknown_before_priced_duplicate_does_not_mask_valid_record(self):
        data = self.collect_lines(
            line(model=UNKNOWN, mid="dup", use=usage(out=53)),
            line(model=MODEL, mid="dup", use=usage(out=59)),
        )
        self.assertEqual(data["grand"]["output"], 59)
        self.assertEqual(data["unpriced"], {UNKNOWN: 53})
        self.assertEqual(data["unique_messages"], 1)

    def test_placeholder_before_priced_duplicate_does_not_mask_valid_record(self):
        data = self.collect_lines(
            line(model=PLACEHOLDER, mid="dup", use=usage(out=61)),
            line(model=MODEL, mid="dup", use=usage(out=67)),
        )
        self.assertEqual(data["grand"]["output"], 67)
        self.assertEqual(data["unique_messages"], 1)

    def test_unknown_models_do_not_increment_unique_messages(self):
        data = self.collect_lines(
            line(model=UNKNOWN, mid="u1", use=usage(out=71)),
            line(model=MODEL, mid="p1", use=usage(out=73)),
        )
        self.assertEqual(data["unique_messages"], 1)
        self.assertEqual(data["grand"]["output"], 73)


class DedupeAndUniqueMessageTests(ScratchCase):
    def test_duplicate_priced_first_record_wins(self):
        data = self.collect_lines(
            line(model=MODEL, mid="dup", use=usage(out=79)),
            line(model=MODEL, mid="dup", use=usage(out=83)),
        )
        self.assertEqual(data["grand"]["output"], 79)
        self.assertEqual(data["unique_messages"], 1)

    def test_duplicate_priced_later_model_is_skipped(self):
        data = self.collect_lines(
            line(model=MODEL, mid="dup", use=usage(out=89)),
            line(model=OTHER_MODEL, mid="dup", use=usage(out=97)),
        )
        self.assertEqual(data["grand"]["output"], 89)
        self.assertEqual(data["unique_messages"], 1)
        self.assertEqual(sum(bucket["msgs"] for bucket in data["by_model"].values()), 1)

    def test_malformed_before_priced_duplicate_does_not_mask_valid_record(self):
        data = self.collect_lines(
            line(model=MODEL, mid="dup", use=usage(out="bad")),
            line(model=MODEL, mid="dup", use=usage(out=101)),
        )
        self.assertEqual(data["grand"]["output"], 101)
        self.assertEqual(data["unique_messages"], 1)

    def test_idless_priced_messages_are_all_counted_unique(self):
        data = self.collect_lines(
            line(model=MODEL, mid=None, use=usage(out=103)),
            line(model=MODEL, mid=None, use=usage(out=107)),
        )
        self.assertEqual(data["grand"]["output"], 210)
        self.assertEqual(data["unique_messages"], 2)

    def test_empty_string_ids_are_not_deduped_and_are_counted(self):
        data = self.collect_lines(
            line(model=MODEL, mid="", use=usage(out=109)),
            line(model=MODEL, mid="", use=usage(out=113)),
        )
        self.assertEqual(data["grand"]["output"], 222)
        self.assertEqual(data["unique_messages"], 2)

    def test_non_string_message_ids_are_not_deduped_or_crashing(self):
        data = self.collect_lines(
            line(model=MODEL, mid=["same"], use=usage(out=127)),
            line(model=MODEL, mid=["same"], use=usage(out=131)),
        )
        self.assertEqual(data["grand"]["output"], 258)
        self.assertEqual(data["unique_messages"], 2)


class GatherFilesTests(ScratchCase):
    def test_relative_glob_still_supported(self):
        main = self.write_jsonl("main.jsonl", ["{}"])
        rel = self.write_jsonl("rel/a.output", ["{}"])
        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(self.scratch)
            files = sc.gather_files(main, [], ["rel/*.output"])
            resolved = [p.resolve() for p in files]
        finally:
            os.chdir(old_cwd)
        self.assertEqual(resolved, [main.resolve(), rel.resolve()])

    def test_absolute_glob_supported_in_sorted_order(self):
        main = self.write_jsonl("main.jsonl", ["{}"])
        b = self.write_jsonl("glob/b.jsonl", ["{}"])
        a = self.write_jsonl("glob/a.jsonl", ["{}"])
        files = sc.gather_files(main, [], [str(self.scratch / "glob" / "*.jsonl")])
        self.assertEqual([p.resolve() for p in files], [main.resolve(), a.resolve(), b.resolve()])

    def test_absolute_glob_with_no_matches_adds_nothing(self):
        main = self.write_jsonl("main.jsonl", ["{}"])
        files = sc.gather_files(main, [], [str(self.scratch / "missing" / "*.jsonl")])
        self.assertEqual([p.resolve() for p in files], [main.resolve()])

    def test_absolute_glob_dedupes_explicit_same_file(self):
        main = self.write_jsonl("main.jsonl", ["{}"])
        extra = self.write_jsonl("glob/one.jsonl", ["{}"])
        files = sc.gather_files(main, [], [str(self.scratch / "glob" / "*.jsonl"), str(extra)])
        self.assertEqual([p.resolve() for p in files], [main.resolve(), extra.resolve()])

    def test_directory_include_still_uses_only_output_files(self):
        main = self.write_jsonl("main.jsonl", ["{}"])
        out = self.write_jsonl("inc/kept.output", ["{}"])
        self.write_jsonl("inc/ignored.jsonl", ["{}"])
        files = sc.gather_files(main, [], [str(self.scratch / "inc")])
        self.assertEqual([p.resolve() for p in files], [main.resolve(), out.resolve()])


class MainSourceCountingTests(ScratchCase):
    def test_json_include_file_is_scanned_but_not_a_subagent(self):
        projects, _tasks, includes = self.make_session_tree(
            [line(model=MODEL, mid="main", use=usage(out=137))],
            include_records=[line(model=MODEL, mid="extra", use=usage(out=139))],
        )
        code, out, err = self.call_main([
            "--session", "SESS", "--projects-dir", str(projects),
            "--include", str(includes[0]), "--json",
        ])
        self.assertEqual(code, 0, err)
        obj = json.loads(out)
        self.assertEqual(obj["sources"]["files_scanned"], 2)
        self.assertEqual(obj["sources"]["subagent_transcripts"], 0)
        self.assertEqual(obj["sources"]["unique_messages"], 2)

    def test_markdown_include_file_still_says_main_session_only(self):
        projects, _tasks, includes = self.make_session_tree(
            [line(model=MODEL, mid="main", use=usage(out=149))],
            include_records=[line(model=MODEL, mid="extra", use=usage(out=151))],
        )
        code, out, err = self.call_main([
            "--session", "SESS", "--projects-dir", str(projects),
            "--include", str(includes[0]),
        ])
        self.assertEqual(code, 0, err)
        self.assertIn("main session only", out)
        self.assertNotIn("+ 1 subagent transcript", out)

    def test_tasks_dir_outputs_are_counted_as_subagents(self):
        projects, tasks, _includes = self.make_session_tree(
            [line(model=MODEL, mid="main", use=usage(out=157))],
            task_records=[line(model=MODEL, mid="task1", use=usage(out=163)),
                          line(model=MODEL, mid="task2", use=usage(out=167))],
        )
        code, out, err = self.call_main([
            "--session", "SESS", "--projects-dir", str(projects),
            "--tasks-dir", str(tasks), "--json",
        ])
        self.assertEqual(code, 0, err)
        obj = json.loads(out)
        self.assertEqual(obj["sources"]["subagent_transcripts"], 2)
        self.assertEqual(obj["sources"]["files_scanned"], 3)

    def test_no_subagents_still_scans_include_but_counts_zero_subagents(self):
        projects, tasks, includes = self.make_session_tree(
            [line(model=MODEL, mid="main", use=usage(out=173))],
            task_records=[line(model=MODEL, mid="task", use=usage(out=179))],
            include_records=[line(model=MODEL, mid="extra", use=usage(out=181))],
        )
        code, out, err = self.call_main([
            "--session", "SESS", "--projects-dir", str(projects),
            "--tasks-dir", str(tasks), "--include", str(includes[0]),
            "--no-subagents", "--json",
        ])
        self.assertEqual(code, 0, err)
        obj = json.loads(out)
        self.assertEqual(obj["sources"]["files_scanned"], 2)
        self.assertEqual(obj["sources"]["subagent_transcripts"], 0)
        self.assertEqual(obj["totals"]["grand_tokens"]["output"], 354)

    def test_files_scanned_includes_main_tasks_and_includes(self):
        projects, tasks, includes = self.make_session_tree(
            [line(model=MODEL, mid="main", use=usage(out=191))],
            task_records=[line(model=MODEL, mid="task", use=usage(out=193))],
            include_records=[line(model=MODEL, mid="extra", use=usage(out=197))],
        )
        code, out, err = self.call_main([
            "--session", "SESS", "--projects-dir", str(projects),
            "--tasks-dir", str(tasks), "--include", str(includes[0]),
            "--json",
        ])
        self.assertEqual(code, 0, err)
        obj = json.loads(out)
        self.assertEqual(obj["sources"]["files_scanned"], 3)
        self.assertEqual(obj["sources"]["subagent_transcripts"], 1)
        self.assertEqual(obj["sources"]["unique_messages"], 3)


if __name__ == "__main__":
    unittest.main()
