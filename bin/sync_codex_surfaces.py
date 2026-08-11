#!/usr/bin/env python3
"""Build/check deprecated Codex prompt mirrors from canonical skills and agents."""

import argparse
import json
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_STEMS = (
    "architect",
    "effort",
    "escalate",
    "frontier-check",
    "journal",
    "route",
    "usage",
)
AGENT_PROMPTS = {
    "implementer": "kit-implementer",
    "reviewer": "phase-reviewer",
    "verifier": "kit-verifier",
}
EXPECTED_PROMPTS = set(SKILL_STEMS) | set(AGENT_PROMPTS)
PLACEHOLDER = "{{POLYTROPOS_ROOT}}"
DOCTOR_REMEDY = "python3 bin/harness_select.py doctor --harness codex"


def _frontmatter(path):
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"missing frontmatter anchor: {path}")
    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"missing closing frontmatter anchor: {path}") from exc
    fields = {}
    for line in lines[1:closing]:
        if not line.startswith((" ", "\t")) and ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"\'')
    return fields, "".join(lines[closing + 1 :]).lstrip("\n")


def _prompt(description, target, body):
    deprecated = f"Deprecated compatibility prompt; prefer {target}."
    return (
        "---\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"> {deprecated}\n\n"
        f"{body.rstrip()}\n"
    ).encode("utf-8")


def expected_prompts(repo_root=REPO_ROOT):
    root = Path(repo_root)
    expected = {}
    for stem in SKILL_STEMS:
        path = root / "codex" / "skills" / stem / "SKILL.md"
        fields, body = _frontmatter(path)
        if fields.get("name") != stem or not fields.get("description"):
            raise ValueError(f"malformed canonical skill frontmatter: {path}")
        expected[f"{stem}.md"] = _prompt(fields["description"], f"`${stem}`", body)

    if tomllib is None:
        raise RuntimeError("Python 3.11+ tomllib is required to generate agent prompt mirrors")
    for prompt_stem, agent_stem in AGENT_PROMPTS.items():
        path = root / "codex" / "agents" / f"{agent_stem}.toml"
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"malformed canonical agent TOML: {path}") from exc
        required = ("name", "description", "developer_instructions")
        if payload.get("name") != agent_stem or any(not payload.get(key) for key in required):
            raise ValueError(f"malformed canonical agent fields: {path}")
        expected[f"{prompt_stem}.md"] = _prompt(
            payload["description"],
            f"the `{agent_stem}` custom agent",
            payload["developer_instructions"],
        )
    return dict(sorted(expected.items()))


def sync(repo_root=REPO_ROOT, mode="check"):
    root = Path(repo_root)
    prompt_dir = root / "codex" / "prompts"
    expected = expected_prompts(root)
    actual_names = {path.name for path in prompt_dir.glob("*.md")} if prompt_dir.is_dir() else set()
    unknown = sorted(actual_names - EXPECTED_PROMPTS_NAMES)
    if unknown:
        raise ValueError(f"unknown Codex prompt file(s): {', '.join(unknown)}")
    drift = []
    for name, payload in expected.items():
        path = prompt_dir / name
        if not path.is_file() or path.read_bytes() != payload:
            drift.append(name)
    missing = sorted(EXPECTED_PROMPTS_NAMES - actual_names)
    drift = sorted(set(drift) | set(missing))
    if mode == "check":
        return drift
    if mode != "build":
        raise ValueError("mode must be build or check")
    prompt_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in expected.items():
        (prompt_dir / name).write_bytes(payload)
    return drift


EXPECTED_PROMPTS_NAMES = {f"{stem}.md" for stem in EXPECTED_PROMPTS}


def resolve_skill_root(skill_path, required_engine, installed_root=None):
    """Prove a plugin or managed-copy root using both pricing and engine sentinels."""
    path = Path(skill_path).resolve()
    if installed_root is None or str(installed_root) == PLACEHOLDER:
        if len(path.parents) < 4 or path.parents[1].name != "skills" or path.parents[2].name != "codex":
            raise RuntimeError(f"cannot prove plugin root; run `{DOCTOR_REMEDY}`")
        root = path.parents[3]
    else:
        root = Path(installed_root).resolve()
    pricing = root / "data" / "pricing.codex.json"
    engine = root / "bin" / required_engine
    if not pricing.is_file() or not engine.is_file():
        raise RuntimeError(f"stale or incomplete plugin root; run `{DOCTOR_REMEDY}`")
    return root


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "check"))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        drift = sync(args.repo_root, args.mode)
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.mode == "check" and drift:
        print("Codex prompt mirrors are stale: " + ", ".join(drift), file=sys.stderr)
        return 1
    if args.mode == "build":
        print("built Codex prompt mirrors" + (": " + ", ".join(drift) if drift else ""))
    else:
        print("Codex prompt mirrors are up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
