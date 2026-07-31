#!/usr/bin/env python3
"""Count REAL `Path.home()` call sites via the AST. Kit-local verification helper.

Why this exists instead of `grep -c 'Path.home()'`:

    `tests/test_context_weight.py` carries a docstring documenting the zero-`Path.home()`
    contract. grep counts that PROSE and reports 1, which reads as a guardrail violation
    when the count of actual calls is 0. The Phase-1 review confirmed the false failure,
    and the same trap recurred four more times this run in other forms — a file that
    DOCUMENTS a contract will contain the string that contract forbids.

    The rule this encodes: never judge code by substring presence. Parse it.

Counts only `Call(func=Attribute(value=Name("Path"), attr="home"))` — a genuine
`Path.home()` invocation. A bare mention, a comment, a docstring, or the attribute
without a call all correctly count 0.

Usage:
    python3 _home_check.py FILE [FILE ...]          # every file must have 0 calls
    python3 _home_check.py --expect 3 FILE          # sanctioned-count file (the engine)

Exit 0 when every file matches its expected count, 1 otherwise, 2 on a bad argument
or unparseable file. Read-only: never writes, never imports the file under test.
"""
import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def path_home_call_lines(path: Path) -> list[int]:
    """Line numbers of real `Path.home()` calls in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "home"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "Path"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Count real Path.home() call sites via the AST (grep gives false positives)."
    )
    ap.add_argument("files", nargs="+", help="Python files to check (relative to repo root or absolute)")
    ap.add_argument(
        "--expect",
        type=int,
        default=0,
        help="Expected number of calls per file (default 0; the engine's sanctioned count is 3)",
    )
    args = ap.parse_args(argv)

    failed = False
    for name in args.files:
        path = Path(name)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            print(f"{name}: MISSING — no such file", file=sys.stderr)
            return 2
        try:
            lines = path_home_call_lines(path)
        except SyntaxError as exc:
            print(f"{name}: UNPARSEABLE — {exc}", file=sys.stderr)
            return 2
        status = "ok" if len(lines) == args.expect else "FAIL"
        where = f" at line(s) {', '.join(str(n) for n in lines)}" if lines else ""
        print(f"{name}: {len(lines)} Path.home() call(s), expected {args.expect} — {status}{where}")
        if len(lines) != args.expect:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
