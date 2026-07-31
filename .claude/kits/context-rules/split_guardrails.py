#!/usr/bin/env python3
"""One-time migration tool: split CLAUDE.md's 19 kit-scoped guardrail fences
out into `.claude/kits/<slug>/GUARDRAILS.md`, verbatim.

Kit-local on purpose (see PLAN.md D1/D2 in this kit) — this is NOT a `bin/`
engine and must never be promoted there. Stdlib only: no network, no
subprocess, no Path.home().

Subcommands: plan | apply | check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXPECTED_SLUGS = (
    "harden-plugin", "aesop-bridge", "copilot-harness", "copilot-workflow",
    "copilot-costviz", "daily-journal", "fusion-tier1", "fusion-tier2",
    "routing-history", "per-task-dollars", "crossrepo-trend", "codex-harness",
    "journal-augment", "next-day-runbook", "harness-parity", "memory-skill",
    "effort-dial", "copilot-skills-parity", "copilot-model-prefs",
)

SLIM_TAIL = """  Each kit's own fences live in `.claude/kits/<slug>/GUARDRAILS.md` — read it together with
  that kit's PLAN.md before starting any of its tasks. Those fences are kit-scoped law: they
  bind only while that kit's tasks run and never generalize to other work. The Invariants
  above are the only always-on rules.
"""

HEADER_TEMPLATE = """# {slug} — kit guardrails

Relocated verbatim from the global CLAUDE.md by the context-rules kit (2026-07-24).
Kit-scoped: these fences bind this kit's tasks only. Global invariants live in CLAUDE.md.

"""

BLOCK_RE = re.compile(r"^  For `([a-z0-9-]+)` specifically:")


def get_root() -> Path:
    # script sits at .claude/kits/context-rules/split_guardrails.py, three
    # levels below the repo root.
    root = Path(__file__).resolve().parents[3]
    assert (root / "CLAUDE.md").is_file(), (
        f"sanity check failed: {root / 'CLAUDE.md'} is not a file "
        f"(computed root={root})"
    )
    return root


class Block:
    __slots__ = ("slug", "start_line", "end_line", "lines")

    def __init__(self, slug, start_line, end_line, lines):
        self.slug = slug
        self.start_line = start_line
        self.end_line = end_line
        self.lines = lines  # list of lines (with their original line endings)

    @property
    def text(self) -> str:
        return "".join(self.lines)

    @property
    def nbytes(self) -> int:
        return len(self.text.encode("utf-8"))


def parse_claude_md(text: str):
    """Split `text` into (head_lines, blocks). Lines keep their endings."""
    lines = text.splitlines(keepends=True)
    first_match_idx = None
    for i, line in enumerate(lines):
        if BLOCK_RE.match(line):
            first_match_idx = i
            break

    if first_match_idx is None:
        return lines, []

    head_lines = lines[:first_match_idx]

    # Find the index (in `lines`) of every block-start line.
    starts = []
    for i, line in enumerate(lines):
        if BLOCK_RE.match(line):
            starts.append(i)

    blocks = []
    for bi, start_idx in enumerate(starts):
        end_idx = starts[bi + 1] if bi + 1 < len(starts) else len(lines)
        slug = BLOCK_RE.match(lines[start_idx]).group(1)
        block_lines = lines[start_idx:end_idx]
        # 1-based line numbers for human-readable reporting.
        blocks.append(Block(slug, start_idx + 1, end_idx, block_lines))

    return head_lines, blocks


def validate_blocks(blocks, root: Path):
    """Returns list of error strings; empty means valid."""
    errors = []
    found_slugs = tuple(b.slug for b in blocks)
    if found_slugs != EXPECTED_SLUGS:
        errors.append(
            "slug mismatch:\n"
            f"  expected: {EXPECTED_SLUGS}\n"
            f"  found:    {found_slugs}"
        )
    for slug in found_slugs:
        kit_dir = root / ".claude" / "kits" / slug
        if not kit_dir.is_dir():
            errors.append(f"missing kit dir: {kit_dir}")
    return errors


def cmd_plan(root: Path, args) -> int:
    claude_md = root / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8")
    head_lines, blocks = parse_claude_md(text)

    head_bytes = len("".join(head_lines).encode("utf-8"))
    blocks_bytes = sum(b.nbytes for b in blocks)
    total = len(text.encode("utf-8"))

    for b in blocks:
        print(f"{b.slug}  {b.start_line}  {b.end_line}  {b.nbytes}")
    print(
        f"head_bytes={head_bytes} blocks={len(blocks)} "
        f"blocks_bytes={blocks_bytes} total={total}"
    )

    errors = validate_blocks(blocks, root)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_apply(root: Path, args) -> int:
    claude_md = root / "CLAUDE.md"
    text = claude_md.read_text(encoding="utf-8")
    head_lines, blocks = parse_claude_md(text)

    if not blocks:
        print("nothing to do")
        return 0

    errors = validate_blocks(blocks, root)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    backup_path = root / ".claude" / "kits" / "context-rules" / "CLAUDE.md.orig"
    if backup_path.exists() and not args.force:
        print(
            f"ERROR: backup already exists at {backup_path} "
            "(pass --force to overwrite)",
            file=sys.stderr,
        )
        return 1
    backup_path.write_text(text, encoding="utf-8")

    for b in blocks:
        guardrails_path = root / ".claude" / "kits" / b.slug / "GUARDRAILS.md"
        content = HEADER_TEMPLATE.format(slug=b.slug) + b.text
        guardrails_path.write_text(content, encoding="utf-8")

    new_claude_md = "".join(head_lines) + SLIM_TAIL
    claude_md.write_text(new_claude_md, encoding="utf-8")

    print(f"wrote {len(blocks)} GUARDRAILS.md files, backup at {backup_path}")
    return 0


def cmd_check(root: Path, args) -> int:
    claude_md = root / "CLAUDE.md"
    backup_path = root / ".claude" / "kits" / "context-rules" / "CLAUDE.md.orig"

    if not backup_path.is_file():
        print(f"ERROR: backup not found at {backup_path}", file=sys.stderr)
        return 2

    backup_text = backup_path.read_text(encoding="utf-8")
    head_lines, blocks = parse_claude_md(backup_text)
    current_text = claude_md.read_text(encoding="utf-8")

    failures = []

    # (a) each kit's GUARDRAILS.md content == header + original block bytes.
    for b in blocks:
        guardrails_path = root / ".claude" / "kits" / b.slug / "GUARDRAILS.md"
        expected = HEADER_TEMPLATE.format(slug=b.slug) + b.text
        if not guardrails_path.is_file():
            failures.append(f"missing {guardrails_path}")
            continue
        actual = guardrails_path.read_text(encoding="utf-8")
        if actual != expected:
            failures.append(f"content mismatch: {guardrails_path}")

    # (b) current CLAUDE.md contains no line matching the block regex.
    for line in current_text.splitlines(keepends=True):
        if BLOCK_RE.match(line):
            failures.append(
                "current CLAUDE.md still contains a block-start line: "
                f"{line!r}"
            )
            break

    # (c) SLIM_TAIL appears verbatim in current CLAUDE.md.
    if SLIM_TAIL not in current_text:
        failures.append("SLIM_TAIL not found verbatim in current CLAUDE.md")

    # (d) byte accounting.
    backup_total = len(backup_text.encode("utf-8"))
    head_bytes = len("".join(head_lines).encode("utf-8"))
    blocks_bytes = sum(b.nbytes for b in blocks)
    if blocks_bytes != backup_total - head_bytes:
        failures.append(
            "byte accounting mismatch: "
            f"blocks_bytes={blocks_bytes} != "
            f"backup_total({backup_total}) - head_bytes({head_bytes}) "
            f"= {backup_total - head_bytes}"
        )

    if args.strict:
        expected_current = "".join(head_lines) + SLIM_TAIL
        if current_text != expected_current:
            failures.append(
                "--strict: current CLAUDE.md != backup HEAD + SLIM_TAIL "
                "byte-identical"
            )

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1

    print("check ok")
    return 0


def main(argv) -> int:
    parser = argparse.ArgumentParser(
        prog="split_guardrails.py",
        description=(
            "Migration tool: split CLAUDE.md's kit-scoped guardrail fences "
            "into per-kit GUARDRAILS.md files."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan", help="parse only, write nothing")

    apply_p = sub.add_parser("apply", help="perform the migration")
    apply_p.add_argument(
        "--force", action="store_true",
        help="overwrite an existing CLAUDE.md.orig backup",
    )

    check_p = sub.add_parser("check", help="prove byte-level content survival")
    check_p.add_argument(
        "--strict", action="store_true",
        help="also assert current CLAUDE.md == backup HEAD + SLIM_TAIL exactly",
    )

    args = parser.parse_args(argv)
    root = get_root()

    if args.command == "plan":
        return cmd_plan(root, args)
    if args.command == "apply":
        return cmd_apply(root, args)
    if args.command == "check":
        return cmd_check(root, args)

    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
