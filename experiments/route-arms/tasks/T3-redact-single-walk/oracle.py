"""Hidden oracle for T3 (one pattern walk in redact.py). Never shown to a candidate.

Differential: the base commit's `scan`/`redact` are embedded below and compared against the
candidate's on a fixed corpus. Structural: the module holds exactly one loop over the patterns,
and neither `scan` nor `redact` holds one of its own.
"""

import ast
import contextlib
import importlib.util
import io
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "bin" / "redact.py"


def _load():
    spec = importlib.util.spec_from_file_location("route_oracle_redact", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rd = _load()


def base_scan(text, patterns):
    found = {}
    remaining = text or ""
    for kind, pattern in patterns:
        matches = pattern.findall(remaining)
        if matches:
            found[kind] = found.get(kind, 0) + len(matches)
            remaining = pattern.sub(rd.PLACEHOLDER.format(kind=kind), remaining)
    return found


def base_redact(text, limit, patterns):
    original = text or ""
    result = original
    redactions = {}
    for kind, pattern in patterns:
        result, count = pattern.subn(rd.PLACEHOLDER.format(kind=kind), result)
        if count:
            redactions[kind] = redactions.get(kind, 0) + count
    truncated = False
    if limit is not None and len(result) > limit:
        dropped = len(result) - limit
        result = result[:limit] + rd.TRUNCATION_NOTE.format(dropped=dropped)
        truncated = True
    return {"text": result, "redactions": redactions, "truncated": truncated,
            "original_length": len(original)}


# Synthetic shapes only -- none of these is a real credential.
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
GH = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2"
OAI = "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz0123"
ANT = "sk-ant-" + "api03-abcdefghijklmnopqrstuv"
JWT = "eyJ" + "hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
_DASHES = "-" * 5
PEM = (f"{_DASHES}BEGIN RSA PRIVATE KEY{_DASHES}\nSYNTHETICxNOTxAxKEYxAAAA\n"
       f"{_DASHES}END RSA PRIVATE KEY{_DASHES}")

CORPUS = [
    None, "", " ", "plain words only", "password", "db_password = hunter2",
    f"key {AWS} and {AWS}", f"token {GH}", f"{OAI} then {ANT}", f"auth: Bearer {'x' * 30}",
    JWT, PEM, PEM.split("\n")[0], f"https://user:pa55w0rd@example.test/path",
    f"api_key={OAI}", f"secret: {GH} {AWS} {JWT}", "xoxb-" + "1234567890-abcdef",
    "AIza" + "B" * 35, f"{AWS}{AWS}", "client_secret=abc\nACCESS_KEY: def\ntoken=ghi",
    ("filler " * 200) + GH, GH + (" tail" * 200), "é ü — ✓ " + AWS,
]
LIMITS = (None, 0, 1, 10, 40, 500, 10_000)


class Differential(unittest.TestCase):
    def test_scan_matches_base(self):
        for text in CORPUS:
            self.assertEqual(rd.scan(text), base_scan(text, rd.PATTERNS), text)

    def test_redact_matches_base_for_every_limit(self):
        for text in CORPUS:
            for limit in LIMITS:
                self.assertEqual(rd.redact(text, limit=limit),
                                 base_redact(text, limit, rd.PATTERNS), (text, limit))

    def test_default_limit_unchanged(self):
        long_text = "x" * (rd.DEFAULT_FIELD_LIMIT + 25)
        self.assertEqual(rd.redact(long_text),
                         base_redact(long_text, rd.DEFAULT_FIELD_LIMIT, rd.PATTERNS))

    def test_custom_patterns_argument(self):
        custom = (("digits", re.compile(r"\d+")), ("vowel", re.compile(r"[aeiou]")))
        for text in ("abc 123 def 45", "", None, "zzz"):
            self.assertEqual(rd.scan(text, patterns=custom), base_scan(text, custom))
            self.assertEqual(rd.redact(text, limit=5, patterns=custom),
                             base_redact(text, 5, custom))
        self.assertEqual(rd.scan("abc", patterns=()), {})

    def test_redact_all_and_describe(self):
        texts, report = rd.redact_all(CORPUS[:12], limit=30)
        expected = [base_redact(t, 30, rd.PATTERNS)["text"] for t in CORPUS[:12]]
        self.assertEqual(texts, expected)
        totals = {}
        for t in CORPUS[:12]:
            for k, v in base_redact(t, 30, rd.PATTERNS)["redactions"].items():
                totals[k] = totals.get(k, 0) + v
        self.assertEqual(report["redactions"], totals)
        self.assertIn("cannot prove no secret remains", rd.describe(report))

    def test_cli_output_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "in.txt"
            path.write_text(f"hello {GH}\n{AWS}\n", encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = rd._cli([str(path)])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(),
                         base_redact(f"hello {GH}\n{AWS}\n", None, rd.PATTERNS)["text"])
        self.assertIn("github-token", err.getvalue())

    def test_public_surface(self):
        public = {n for n in vars(rd) if not n.startswith("_")} - {"re"}
        self.assertEqual(public, {"PLACEHOLDER", "PATTERNS", "DEFAULT_FIELD_LIMIT",
                                  "TRUNCATION_NOTE", "scan", "redact", "redact_all",
                                  "describe"})


class OneWalk(unittest.TestCase):
    @staticmethod
    def _walks(node):
        """Loops/comprehensions iterating a bare `patterns`/`PATTERNS` name under `node`."""
        count = 0
        for sub in ast.walk(node):
            iters = []
            if isinstance(sub, (ast.For, ast.AsyncFor)):
                iters.append(sub.iter)
            elif isinstance(sub, ast.comprehension):
                iters.append(sub.iter)
            for it in iters:
                if isinstance(it, ast.Name) and it.id in ("patterns", "PATTERNS"):
                    count += 1
        return count

    def setUp(self):
        self.tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        self.funcs = {n.name: n for n in self.tree.body if isinstance(n, ast.FunctionDef)}

    def test_exactly_one_walk_in_module(self):
        self.assertEqual(self._walks(self.tree), 1)

    def test_scan_and_redact_do_not_walk_themselves(self):
        self.assertEqual(self._walks(self.funcs["scan"]), 0)
        self.assertEqual(self._walks(self.funcs["redact"]), 0)


if __name__ == "__main__":
    unittest.main()
