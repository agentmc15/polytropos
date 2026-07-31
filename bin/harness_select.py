#!/usr/bin/env python3
"""Detect and install the harness CLIs this monorepo supports.

Per PLAN.md D7, each harness already auto-loads its own native config, so "selecting the
harness" is just two things: (1) detect which harness CLIs are on PATH and say what (if
anything) needs to happen, and (2) for Copilot, materialize the bundle authored under
`copilot/.github/` into a Copilot home directory.

What `install --harness copilot` does: for every `*.agent.md` file under
`copilot/.github/agents/`, it copies the text into `<copilot-home>/agents/<same filename>`,
replacing every occurrence of the `{{POLYTROPOS_ROOT}}` placeholder with this repo's
absolute path. It also materializes every file under `copilot/.github/skills/` into
`<copilot-home>/skills/<same relative path>`, with the same placeholder resolution — a
missing or empty skills directory is tolerated (agents remain the required core). Copilot
has no `${CLAUDE_PLUGIN_ROOT}`-style variable to resolve a bundle's own location at run
time, so the placeholder has to become a literal absolute path at install time instead —
the Copilot analogue of this plugin's one standing absolute-path exception (the statusline
command written into `~/.claude/settings.json`, per CLAUDE.md, because that env var doesn't
exist outside plugin context either).

Claude Code needs NO install step: the plugin at this repo's root is already installed
live at user scope via the local marketplace (`.claude-plugin/marketplace.json`), so
`install --harness claude-code` writes nothing and just says so.

Home-dir precedence gotcha: Copilot CLI reads custom agents from both the repo's own
`.github/agents/` and the user-level `~/.copilot/agents/` (or `$COPILOT_HOME/agents/`), and
on a name collision the home-dir agent wins. Installing this bundle into a Copilot home
therefore makes it the one true `route` agent everywhere that home is active, silently
shadowing any same-named agent a project might keep in its own `.github/agents/`.

What `install --harness codex` does: it copies every `*.md` file under `codex/prompts/`
into `<codex-home>/prompts/<same filename>`, resolving `{{POLYTROPOS_ROOT}}` to this
repo's absolute path exactly as the Copilot install does. It then handles `codex/AGENTS.md`
→ `<codex-home>/AGENTS.md` under a NO-CLOBBER rule: write it if absent; if it already exists
byte-identical to the resolved text, leave it and report `up to date`; if it exists but
DIFFERS, never overwrite it — skip it and print a manual-merge warning. Rationale:
`~/.codex/AGENTS.md` is a single shared file that may hold the user's own global Codex
instructions, so overwriting is destructive — unlike Copilot's per-file namespaced
`agents/` directory. The installer NEVER touches `config.toml` (a live user file whose TOML
merging is invasive). `~/.codex` is only ever written at the user's explicit request via
this installer; every test and verify command passes a temp `--codex-home`, never the real
`~/.codex`.

The prompts cover the terminal `codex` CLI (which reads `<codex-home>/prompts/`). The
ChatGPT Codex desktop app uses a DIFFERENT surface — Agent Skills under
`<codex-home>/skills/<name>/` (its `/`-palette "Skills" section) — and does not read prompts
at all. So the codex install ALSO materializes every skill directory under `codex/skills/`
into `<codex-home>/skills/<name>/`, with the same placeholder resolution, under a per-skill
NO-CLOBBER rule (the AGENTS.md rule at directory granularity, matching Codex's own
skill-installer abort-if-exists safety): destination skill dir absent → install; present and
every file byte-identical → up-to-date; present but any file differs → skip-differs (never
overwrite a user's same-named personal skill; re-installing our own after a repo-side change
also reports skip-differs — remove the stale `<codex-home>/skills/<name>/` to refresh it). A
missing or empty `codex/skills/` dir is tolerated — prompts remain the required core, exactly
as the Copilot install tolerates a missing skills dir.

Nothing here writes outside an explicitly-passed home directory, and `detect()` does not
read or write anything under `~` — it only consults PATH via `shutil.which`.

Usage:
    harness_select.py detect [--json]
    harness_select.py install --harness {claude-code,copilot,codex} [--copilot-home PATH] [--codex-home PATH] [--dry-run]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_AGENTS = REPO_ROOT / "copilot" / ".github" / "agents"
BUNDLE_SKILLS = REPO_ROOT / "copilot" / ".github" / "skills"
BUNDLE_CODEX_PROMPTS = REPO_ROOT / "codex" / "prompts"
BUNDLE_CODEX_AGENTS_MD = REPO_ROOT / "codex" / "AGENTS.md"
BUNDLE_CODEX_SKILLS = REPO_ROOT / "codex" / "skills"
PLACEHOLDER = "{{POLYTROPOS_ROOT}}"

CLAUDE_CODE_MESSAGE = (
    "installed live from this repo via the local marketplace — nothing to install"
)
COPILOT_INSTALL_HINT = (
    "run: python3 bin/harness_select.py install --harness copilot "
    "(--copilot-home <dir> to override; defaults to ~/.copilot)"
)
CODEX_INSTALL_HINT = (
    "run: python3 bin/harness_select.py install --harness codex "
    "(--codex-home <dir> to override; defaults to ~/.codex)"
)


# ---- pure functions -----------------------------------------------------------------------

def detect():
    """Which harness CLIs are on PATH: {"claude-code": bool, "copilot": bool, "codex": bool}.

    Pure `shutil.which` lookups against PATH — no filesystem writes, and nothing under
    `~` is read (harness config directories are never touched here).
    """
    return {
        "claude-code": shutil.which("claude") is not None,
        "copilot": shutil.which("copilot") is not None,
        "codex": shutil.which("codex") is not None,
    }


def install_copilot(home, repo_root=None, dry_run=False):
    """Materialize `copilot/.github/agents/*.agent.md` into `<home>/agents/`, plus every
    file under `copilot/.github/skills/` into `<home>/skills/`.

    `repo_root` defaults to this repo (`REPO_ROOT`); every occurrence of the
    `{{POLYTROPOS_ROOT}}` placeholder in each file's text is replaced with
    `str(repo_root)` before being written to its destination (parent dirs are created as
    needed). Returns the list of destination paths in every case, including `dry_run=True`,
    which writes NOTHING (no files, no directories).

    Raises `FileNotFoundError` (message names the expected bundle path) if the bundle
    agents directory is missing or contains no `*.agent.md` files. Agents remain the
    required core: a missing or empty skills directory is NOT an error.
    """
    if repo_root is None:
        repo_root = REPO_ROOT
        bundle_agents = BUNDLE_AGENTS
        bundle_skills = BUNDLE_SKILLS
    else:
        repo_root = Path(repo_root)
        bundle_agents = repo_root / "copilot" / ".github" / "agents"
        bundle_skills = repo_root / "copilot" / ".github" / "skills"

    home = Path(home)
    agent_files = sorted(bundle_agents.glob("*.agent.md")) if bundle_agents.is_dir() else []
    if not agent_files:
        raise FileNotFoundError(
            f"no *.agent.md files found under {bundle_agents} — is the Copilot bundle "
            "(copilot/.github/agents/) present?"
        )

    dest_dir = home / "agents"
    dest_paths = []
    for src in agent_files:
        dest = dest_dir / src.name
        dest_paths.append(dest)
        if dry_run:
            continue
        text = src.read_text()
        text = text.replace(PLACEHOLDER, str(repo_root))
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)

    if bundle_skills.is_dir():
        skill_files = sorted(p for p in bundle_skills.rglob("*") if p.is_file())
        for src in skill_files:
            rel = src.relative_to(bundle_skills)
            dest = home / "skills" / rel
            dest_paths.append(dest)
            if dry_run:
                continue
            text = src.read_text()
            text = text.replace(PLACEHOLDER, str(repo_root))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text)

    return dest_paths


def install_codex(home, repo_root=None, dry_run=False):
    """Materialize `codex/prompts/*.md` into `<home>/prompts/`, plus `codex/AGENTS.md` into
    `<home>/AGENTS.md` under a NO-CLOBBER rule (PLAN.md D6).

    `repo_root` defaults to this repo (`REPO_ROOT`); every occurrence of the
    `{{POLYTROPOS_ROOT}}` placeholder in each file's text is replaced with
    `str(repo_root)` before being written to its destination (parent dirs are created as
    needed) — the exact Copilot mechanism.

    AGENTS.md no-clobber rule: `~/.codex/AGENTS.md` is a single shared file that may hold the
    user's own global Codex instructions, so — unlike Copilot's per-file namespaced `agents/`
    directory — overwriting it is destructive. Destination absent → write the resolved text;
    destination present and byte-identical to the resolved text → do NOT write, report
    up-to-date; destination present and DIFFERENT → NEVER overwrite: skip it (the caller
    prints a manual-merge warning). This installer NEVER touches `config.toml` (a live user
    file whose TOML merging is invasive).

    Returns a list of `(dest_path, action)` tuples in a stable order — prompt files in
    filename order, then `AGENTS.md`, then one entry per `codex/skills/<name>/` directory in
    name order (dest is the destination skill DIR). `action` is one of "install" (written, or
    would be written under `dry_run`), "up-to-date" (destination already byte-identical — left
    as is), or "skip-differs" (destination exists and differs — never overwritten). The
    returned list always includes the AGENTS.md entry so callers see the full intent
    regardless of action. `dry_run=True` writes NOTHING (no files, no directories) but returns
    the same tuple list.

    Skills → `<home>/skills/<name>/` cover the Codex desktop app's Agent-Skills surface, which
    (unlike the CLI's prompts) is what its `/`-palette reads. Per-skill NO-CLOBBER: dir absent
    → install every file; present and every file byte-identical to the resolved source →
    up-to-date; present but any file missing/differs → skip-differs (never overwrite a user's
    same-named skill). A missing or empty `codex/skills/` dir is tolerated (prompts are the
    required core).

    Raises `FileNotFoundError` (message names the expected prompts path) if the bundle prompts
    directory is missing or contains no `*.md` files.
    """
    if repo_root is None:
        repo_root = REPO_ROOT
        bundle_prompts = BUNDLE_CODEX_PROMPTS
        bundle_agents_md = BUNDLE_CODEX_AGENTS_MD
        bundle_skills = BUNDLE_CODEX_SKILLS
    else:
        repo_root = Path(repo_root)
        bundle_prompts = repo_root / "codex" / "prompts"
        bundle_agents_md = repo_root / "codex" / "AGENTS.md"
        bundle_skills = repo_root / "codex" / "skills"

    home = Path(home)
    prompt_files = sorted(bundle_prompts.glob("*.md")) if bundle_prompts.is_dir() else []
    if not prompt_files:
        raise FileNotFoundError(
            f"no *.md files found under {bundle_prompts} — is the Codex bundle "
            "(codex/prompts/) present?"
        )

    dest_dir = home / "prompts"
    results = []
    for src in prompt_files:
        dest = dest_dir / src.name
        results.append((dest, "install"))
        if dry_run:
            continue
        text = src.read_text()
        text = text.replace(PLACEHOLDER, str(repo_root))
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)

    if bundle_agents_md.is_file():
        agents_dest = home / "AGENTS.md"
        resolved = bundle_agents_md.read_text().replace(PLACEHOLDER, str(repo_root))
        if agents_dest.exists():
            if agents_dest.read_text() == resolved:
                results.append((agents_dest, "up-to-date"))
            else:
                # NEVER overwrite a differing user file.
                results.append((agents_dest, "skip-differs"))
        else:
            results.append((agents_dest, "install"))
            if not dry_run:
                agents_dest.parent.mkdir(parents=True, exist_ok=True)
                agents_dest.write_text(resolved)

    # Skills → <home>/skills/<name>/ for the Codex desktop app's Agent-Skills surface (the
    # `/`-palette Skills section), which — unlike the CLI — does NOT read prompts. Each skill
    # is a directory whose files carry the same {{POLYTROPOS_ROOT}} placeholder. Per-
    # skill NO-CLOBBER (mirrors the AGENTS.md rule at directory granularity, and the Codex
    # skill-installer's own abort-if-exists safety): destination skill dir absent → install
    # every file; present and every file byte-identical to the resolved source → up-to-date;
    # present but any file missing/differs → NEVER overwrite (a user's same-named personal
    # skill is protected — skip-differs). A missing or empty codex/skills/ dir is tolerated:
    # prompts remain the required core, exactly as Copilot tolerates a missing skills dir.
    if bundle_skills.is_dir():
        skill_dirs = sorted(p for p in bundle_skills.iterdir() if p.is_dir())
        for skill_dir in skill_dirs:
            src_files = sorted(p for p in skill_dir.rglob("*") if p.is_file())
            if not src_files:
                continue
            dest_skill_dir = home / "skills" / skill_dir.name

            def _resolved(src):
                return src.read_text().replace(PLACEHOLDER, str(repo_root))

            if not dest_skill_dir.exists():
                action = "install"
            else:
                identical = True
                for src in src_files:
                    dest_file = dest_skill_dir / src.relative_to(skill_dir)
                    if not dest_file.is_file() or dest_file.read_text() != _resolved(src):
                        identical = False
                        break
                action = "up-to-date" if identical else "skip-differs"

            results.append((dest_skill_dir, action))
            if action == "install" and not dry_run:
                for src in src_files:
                    dest_file = dest_skill_dir / src.relative_to(skill_dir)
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    dest_file.write_text(_resolved(src))

    return results


# ---- CLI ------------------------------------------------------------------------------------

def cmd_detect(args):
    result = detect()
    if args.json:
        print(json.dumps(result, indent=2))
        return

    if result["claude-code"]:
        print(f"claude-code: found — {CLAUDE_CODE_MESSAGE}")
    else:
        print(f"claude-code: not found — {CLAUDE_CODE_MESSAGE}")

    if result["copilot"]:
        print(f"copilot: found — {COPILOT_INSTALL_HINT}")
    else:
        print(f"copilot: not found — {COPILOT_INSTALL_HINT}")

    if result["codex"]:
        print(f"codex: found — {CODEX_INSTALL_HINT}")
    else:
        print(f"codex: not found — {CODEX_INSTALL_HINT}")


def cmd_install(args):
    if args.harness == "claude-code":
        print(f"claude-code: {CLAUDE_CODE_MESSAGE}")
        return

    if args.harness == "codex":
        home = Path(args.codex_home) if args.codex_home else (Path.home() / ".codex")
        try:
            results = install_codex(home, dry_run=args.dry_run)
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            sys.exit(2)

        for dest, action in results:
            if action == "up-to-date":
                verb = "up to date"
            elif action == "skip-differs":
                verb = "skipped (exists, differs)"
            else:  # "install"
                verb = "would install" if args.dry_run else "installed"
            print(f"{verb} {dest}")
        return

    home = Path(args.copilot_home) if args.copilot_home else (Path.home() / ".copilot")
    try:
        dest_paths = install_copilot(home, dry_run=args.dry_run)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    verb = "would install" if args.dry_run else "installed"
    for dest in dest_paths:
        print(f"{verb} {dest}")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="harness_select.py",
        description=(
            "Detect which harness CLIs (Claude Code, Copilot, Codex) are on PATH and install "
            "the Copilot or Codex bundle into a harness home directory."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser("detect", help="detect which harness CLIs are on PATH")
    p_detect.add_argument("--json", action="store_true", help="machine-readable output")
    p_detect.set_defaults(func=cmd_detect)

    p_install = sub.add_parser("install", help="materialize a harness's native config")
    p_install.add_argument(
        "--harness", choices=["claude-code", "copilot", "codex"], required=True,
        help="which harness to install",
    )
    p_install.add_argument(
        "--copilot-home", default=None,
        help="Copilot home directory to install into (default: ~/.copilot)",
    )
    p_install.add_argument(
        "--codex-home", default=None,
        help="Codex home directory to install into (default: ~/.codex)",
    )
    p_install.add_argument(
        "--dry-run", action="store_true", help="print what would be installed; write nothing",
    )
    p_install.set_defaults(func=cmd_install)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
