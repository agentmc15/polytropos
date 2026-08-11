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
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.11+ in supported Codex environments
    tomllib = None

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_AGENTS = REPO_ROOT / "copilot" / ".github" / "agents"
BUNDLE_SKILLS = REPO_ROOT / "copilot" / ".github" / "skills"
BUNDLE_CODEX_PROMPTS = REPO_ROOT / "codex" / "prompts"
BUNDLE_CODEX_AGENTS_MD = REPO_ROOT / "codex" / "AGENTS.md"
BUNDLE_CODEX_SKILLS = REPO_ROOT / "codex" / "skills"
BUNDLE_CODEX_AGENTS = REPO_ROOT / "codex" / "agents"
CODEX_PLUGIN_MANIFEST = REPO_ROOT / ".codex-plugin" / "plugin.json"
CODEX_MARKETPLACE = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
PLACEHOLDER = "{{POLYTROPOS_ROOT}}"
CODEX_COMPONENTS = ("plugin", "agents", "skills", "prompts", "guidance")
OWNERSHIP_RELATIVE = Path("polytropos") / "install-manifest.json"
OWNERSHIP_VERSION = 1

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


# ---- modern Codex setup engine ------------------------------------------------------------

def _sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def _read_bytes(path):
    return Path(path).read_bytes()


def _resolved_bytes(source, repo_root):
    raw = _read_bytes(source)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return text.replace(PLACEHOLDER, str(Path(repo_root).resolve())).encode("utf-8")


def _normalized_source_bytes(source):
    """Hashable source form: checked-in placeholder retained, line endings normalized."""
    raw = _read_bytes(source)
    try:
        return raw.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    except UnicodeDecodeError:
        return raw


def _normalized_legacy_bytes(payload, source, repo_root):
    """Return canonical placeholder form for a recognized legacy copy, else ``None``.

    Recognition is deliberately strict: a candidate must differ from the current source only
    by one absolute repository prefix occupying the source placeholder positions.
    """
    canonical = _normalized_source_bytes(source)
    if PLACEHOLDER.encode() not in canonical:
        return None
    try:
        text = payload.decode("utf-8").replace("\r\n", "\n")
        expected = canonical.decode("utf-8")
    except UnicodeDecodeError:
        return None
    candidates = {str(Path(repo_root).resolve())}
    candidates.update(re.findall(r'POLYTROPOS_ROOT="(/[^"\n]+)"', text))
    candidates.update(
        re.findall(
            r"(?:/Users/[^\s`'\"<>]+|/home/[^\s`'\"<>]+)(?=/(?:bin|data|codex)(?:/|\b))",
            text,
        )
    )
    matches = []
    for candidate in sorted(candidates):
        if text.replace(candidate, PLACEHOLDER) == expected:
            matches.append(expected.encode("utf-8"))
    return matches[0] if len(matches) == 1 else None


def parse_codex_components(raw):
    """Parse a comma list without filesystem or home-directory access."""
    if raw is None:
        return ("plugin", "agents")
    values = [value.strip() for value in raw.split(",")]
    if not values or any(not value for value in values):
        raise ValueError("--components must be a non-empty comma-separated list")
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate component(s): {', '.join(duplicates)}")
    unknown = sorted(set(values) - set(CODEX_COMPONENTS))
    if unknown:
        raise ValueError(f"unknown component(s): {', '.join(unknown)}")
    return tuple(value for value in CODEX_COMPONENTS if value in values)


def _load_ownership(codex_home):
    path = Path(codex_home) / OWNERSHIP_RELATIVE
    if not path.is_file():
        return {"version": OWNERSHIP_VERSION, "bundle_version": None, "files": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": None, "bundle_version": None, "files": [], "invalid": True}
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
        return {"version": None, "bundle_version": None, "files": [], "invalid": True}
    return payload


def _bundle_version(repo_root):
    try:
        payload = json.loads(
            (Path(repo_root) / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        return payload.get("version") if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _ownership_key(component, destination, codex_home, repo_root):
    destination = Path(destination)
    for label, base in (("home", Path(codex_home)), ("project", Path(repo_root))):
        try:
            return f"{label}:{destination.relative_to(base).as_posix()}"
        except ValueError:
            continue
    raise ValueError(f"destination escapes approved roots: {destination}")


def _source_inventory(repo_root, codex_home, components, agent_scope):
    root = Path(repo_root)
    home = Path(codex_home)
    inventory = []
    if "agents" in components:
        destination_root = root / ".codex" / "agents" if agent_scope == "project" else home / "agents"
        for source in sorted((root / "codex" / "agents").glob("*.toml")):
            inventory.append(("agents", source, destination_root / source.name))
    if "skills" in components:
        skill_root = root / "codex" / "skills"
        for source in sorted(path for path in skill_root.rglob("*") if path.is_file()):
            inventory.append(("skills", source, home / "skills" / source.relative_to(skill_root)))
    if "prompts" in components:
        prompt_root = root / "codex" / "prompts"
        for source in sorted(prompt_root.glob("*.md")):
            inventory.append(("prompts", source, home / "prompts" / source.name))
    if "guidance" in components:
        source = root / "codex" / "AGENTS.md"
        if source.is_file():
            inventory.append(("guidance", source, home / "AGENTS.md"))
    return inventory


def _validate_plugin_metadata(repo_root):
    root = Path(repo_root).resolve()
    manifest_path = root / ".codex-plugin" / "plugin.json"
    marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        skills_raw = manifest["skills"]
        plugin = marketplace["plugins"][0]
        source_raw = plugin["source"]["path"]
        if manifest.get("name") != "polytropos" or plugin.get("name") != "polytropos":
            raise ValueError("plugin identity mismatch")
        for raw, base in ((skills_raw, root), (source_raw, root)):
            if not isinstance(raw, str) or not raw.startswith("./"):
                raise ValueError("plugin paths must begin with ./")
            resolved = (base / raw).resolve()
            if not resolved.is_relative_to(root) or not resolved.exists():
                raise ValueError("plugin path is missing or escapes the repository")
    except (OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return False, str(exc)
    return True, "repo marketplace and skills path are ready"


def _validate_agent_sources(repo_root):
    expected = {"kit-implementer", "kit-verifier", "phase-reviewer", "repo-explorer"}
    paths = sorted((Path(repo_root) / "codex" / "agents").glob("*.toml"))
    if {path.stem for path in paths} != expected:
        return False, "canonical agent roster is missing or has drifted"
    if tomllib is None:
        return True, "canonical agent roster is present (schema parser unavailable)"
    try:
        for path in paths:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
            if set(payload) != {"name", "description", "developer_instructions"}:
                raise ValueError(f"unexpected fields in {path.name}")
            if payload["name"] != path.stem:
                raise ValueError(f"name mismatch in {path.name}")
            if not payload["description"].strip() or not payload["developer_instructions"].strip():
                raise ValueError(f"empty required field in {path.name}")
    except (OSError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        return False, str(exc)
    return True, "canonical agent schema is valid"


def plan_codex_setup(
    repo_root,
    codex_home,
    components=("plugin", "agents"),
    agent_scope="project",
    legacy_copy=False,
    refresh_managed=False,
):
    """Build a deterministic setup plan using only the explicitly supplied roots."""
    if repo_root is None:
        raise ValueError("a repository root is required")
    if codex_home is None:
        raise ValueError("an explicit Codex home is required")
    components = tuple(components)
    unknown = set(components) - set(CODEX_COMPONENTS)
    if unknown or len(set(components)) != len(components):
        raise ValueError("components must be unique members of the supported component set")
    copied = {"skills", "prompts", "guidance"} & set(components)
    if copied and not legacy_copy:
        raise ValueError("skills, prompts, and guidance copies require --legacy-copy")
    if agent_scope not in {"project", "user"}:
        raise ValueError("agent scope must be project or user")

    root = Path(repo_root).resolve()
    home = Path(codex_home).resolve()
    ownership = _load_ownership(home)
    owned = {
        entry.get("destination"): entry
        for entry in ownership.get("files", [])
        if isinstance(entry, dict) and isinstance(entry.get("destination"), str)
    }
    actions = []

    if "plugin" in components:
        valid, reason = _validate_plugin_metadata(root)
        actions.append(
            {
                "component": "plugin",
                "source": str(root / ".agents" / "plugins" / "marketplace.json"),
                "destination": "Codex /plugins",
                "state": "up-to-date" if valid else "conflict",
                "reason": reason if valid else f"plugin metadata invalid: {reason}",
                "source_digest": None,
                "destination_digest": None,
            }
        )

    if "agents" in components:
        valid, reason = _validate_agent_sources(root)
        if not valid:
            actions.append(
                {
                    "component": "agents",
                    "source": str(root / "codex" / "agents"),
                    "destination": str(
                        root / ".codex" / "agents"
                        if agent_scope == "project"
                        else home / "agents"
                    ),
                    "state": "conflict",
                    "reason": f"canonical agents invalid: {reason}",
                    "source_digest": None,
                    "destination_digest": None,
                }
            )

    for component, source, destination in _source_inventory(
        root, home, components, agent_scope
    ):
        source_normalized = _normalized_source_bytes(source)
        source_digest = _sha256_bytes(source_normalized)
        installed = _resolved_bytes(source, root)
        installed_digest = _sha256_bytes(installed)
        key = _ownership_key(component, destination, home, root)
        record = owned.get(key)
        destination_digest = None
        state = "install"
        reason = "destination is absent"
        if destination.exists():
            if not destination.is_file():
                state, reason = "conflict", "destination exists but is not a file"
            else:
                current = _read_bytes(destination)
                destination_digest = _sha256_bytes(current)
                if current == installed:
                    state, reason = "up-to-date", "destination matches the current bundle"
                elif PLACEHOLDER.encode("utf-8") in current:
                    state, reason = "conflict", "destination contains an unresolved literal placeholder"
                elif record and record.get("installed_hash") == destination_digest:
                    if refresh_managed:
                        state, reason = "managed-update", "unchanged managed copy can be refreshed"
                    else:
                        state, reason = "unmanaged", "managed copy is stale; rerun with --refresh-managed"
                elif record:
                    state, reason = "conflict", "managed destination was edited; preserving user changes"
                elif _normalized_legacy_bytes(current, source, root) is not None:
                    state = "managed-update" if refresh_managed else "unmanaged"
                    reason = (
                        "recognized legacy copy can be adopted and refreshed"
                        if refresh_managed
                        else "recognized legacy copy; rerun with --refresh-managed to adopt"
                    )
                else:
                    state, reason = "conflict", "unmanaged destination differs"
        action = {
            "component": component,
            "source": str(source),
            "destination": str(destination),
            "state": state,
            "reason": reason,
            "source_digest": source_digest,
            "destination_digest": destination_digest,
            "_installed_digest": installed_digest,
            "_content": installed,
            "_ownership_key": key,
        }
        actions.append(action)

    actions.sort(key=lambda action: (CODEX_COMPONENTS.index(action["component"]), action["destination"]))
    return {
        "version": OWNERSHIP_VERSION,
        "bundle_version": _bundle_version(root),
        "repo_root": str(root),
        "codex_home": str(home),
        "agent_scope": agent_scope,
        "components": list(components),
        "actions": actions,
    }


def _public_plan(plan):
    return {
        key: value
        for key, value in plan.items()
        if key != "actions"
    } | {
        "actions": [
            {key: value for key, value in action.items() if not key.startswith("_")}
            for action in plan["actions"]
        ]
    }


def _atomic_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def apply_codex_plan(plan, fail_after=None):
    """Apply writable actions atomically as a group; ownership is always written last."""
    blocking = [
        action for action in plan["actions"] if action["state"] in {"conflict", "unmanaged"}
    ]
    if blocking:
        raise ValueError("setup plan contains conflicts or unmanaged destinations; nothing written")
    writable = [
        action for action in plan["actions"] if action["state"] in {"install", "managed-update"}
    ]
    backups = {}
    ownership_path = Path(plan["codex_home"]) / OWNERSHIP_RELATIVE
    prior_manifest = ownership_path.read_bytes() if ownership_path.is_file() else None
    try:
        for index, action in enumerate(writable, start=1):
            destination = Path(action["destination"])
            backups[destination] = destination.read_bytes() if destination.is_file() else None
            _atomic_write(destination, action["_content"])
            if fail_after is not None and index >= fail_after:
                raise RuntimeError("simulated setup write failure")

        records = []
        for action in plan["actions"]:
            if action["component"] == "plugin" or action["state"] in {"conflict", "unmanaged", "skip"}:
                continue
            destination = Path(action["destination"])
            if not destination.is_file():
                continue
            records.append(
                {
                    "component": action["component"],
                    "destination": action["_ownership_key"],
                    "bundle_version": plan["bundle_version"],
                    "source_hash": action["source_digest"],
                    "installed_hash": _sha256_bytes(destination.read_bytes()),
                }
            )
        manifest = {
            "version": OWNERSHIP_VERSION,
            "bundle_version": plan["bundle_version"],
            "files": sorted(records, key=lambda record: record["destination"]),
        }
        if records:
            manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
            if prior_manifest != manifest_bytes:
                _atomic_write(ownership_path, manifest_bytes)
    except BaseException:
        for destination, prior in reversed(list(backups.items())):
            if prior is None:
                destination.unlink(missing_ok=True)
            else:
                _atomic_write(destination, prior)
        if prior_manifest is None:
            ownership_path.unlink(missing_ok=True)
        else:
            _atomic_write(ownership_path, prior_manifest)
        raise


def doctor_codex(repo_root, codex_home):
    """Read-only diagnostic plan covering every Codex surface."""
    plan = plan_codex_setup(
        repo_root,
        codex_home,
        components=CODEX_COMPONENTS,
        agent_scope="project",
        legacy_copy=True,
        refresh_managed=False,
    )
    ownership = _load_ownership(codex_home)
    checks = _public_plan(plan)
    destination_agents = Path(repo_root).resolve() / ".codex" / "agents"
    canonical = {path.name for path in (Path(repo_root) / "codex" / "agents").glob("*.toml")}
    if destination_agents.is_dir():
        for path in sorted(destination_agents.glob("*.toml")):
            if path.name in canonical:
                continue
            checks["actions"].append(
                {
                    "component": "agents",
                    "source": "",
                    "destination": str(path),
                    "state": "unmanaged",
                    "reason": "agent is outside the canonical bundle; preserved for manual review",
                    "source_digest": None,
                    "destination_digest": _sha256_bytes(path.read_bytes()),
                }
            )
    checks["actions"].sort(
        key=lambda action: (CODEX_COMPONENTS.index(action["component"]), action["destination"])
    )
    checks["ownership_manifest"] = (
        "invalid" if ownership.get("invalid") else "present" if ownership.get("files") else "absent"
    )
    checks["session_note"] = "Restart Codex or start a new session after enabling the plugin or changing agents."
    return checks


def render_codex_plan(plan, as_json=False):
    public = _public_plan(plan)
    if as_json:
        return json.dumps(public, indent=2, sort_keys=True)
    lines = []
    for action in public["actions"]:
        lines.append(
            f"{action['component']}: {action['state']} — {action['destination']} ({action['reason']})"
        )
    if "plugin" in public["components"]:
        lines.append("next: restart Codex, open /plugins, then install and enable Polytropos")
    return "\n".join(lines)


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
    codex_only_values = (
        args.repo_root,
        args.components,
        args.agent_scope,
        args.legacy_copy,
        args.refresh_managed,
        args.json,
    )
    if args.harness != "codex" and any(codex_only_values):
        raise SystemExit("Codex setup flags may be used only with --harness codex")

    if args.harness == "claude-code":
        print(f"claude-code: {CLAUDE_CODE_MESSAGE}")
        return

    if args.harness == "codex":
        modern = any(codex_only_values)
        home = Path(args.codex_home) if args.codex_home else (Path.home() / ".codex")
        if modern:
            if args.refresh_managed and args.codex_home is None:
                raise SystemExit("--refresh-managed requires an explicit --codex-home")
            try:
                components = parse_codex_components(args.components)
                plan = plan_codex_setup(
                    Path(args.repo_root) if args.repo_root else REPO_ROOT,
                    home,
                    components=components,
                    agent_scope=args.agent_scope or "project",
                    legacy_copy=args.legacy_copy,
                    refresh_managed=args.refresh_managed,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            print(render_codex_plan(plan, as_json=args.json))
            if args.dry_run:
                return
            if any(action["state"] == "conflict" for action in plan["actions"]):
                raise SystemExit(2)
            apply_codex_plan(plan)
            return

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


def cmd_doctor(args):
    if args.harness != "codex":
        raise SystemExit("doctor currently supports only --harness codex")
    root = Path(args.repo_root) if args.repo_root else REPO_ROOT
    home = Path(args.codex_home) if args.codex_home else (Path.home() / ".codex")
    try:
        report = doctor_codex(root, home)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    print(render_codex_plan(report))
    print(f"ownership: {report['ownership_manifest']}")
    print(report["session_note"])


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
    p_install.add_argument(
        "--repo-root", default=None,
        help="repository root containing the Codex bundle (Codex modern setup only)",
    )
    p_install.add_argument(
        "--components", default=None,
        help="comma-separated Codex components: plugin,agents,skills,prompts,guidance",
    )
    p_install.add_argument(
        "--agent-scope", choices=["project", "user"], default=None,
        help="install Codex agents for this project or the explicit user home",
    )
    p_install.add_argument(
        "--legacy-copy", action="store_true",
        help="allow deprecated copying of skills, prompts, or guidance",
    )
    p_install.add_argument(
        "--refresh-managed", action="store_true",
        help="refresh only destinations proven unchanged by the ownership manifest",
    )
    p_install.add_argument(
        "--json", action="store_true", help="machine-readable Codex setup plan",
    )
    p_install.set_defaults(func=cmd_install)

    p_doctor = sub.add_parser("doctor", help="diagnose Codex plugin, agents, and legacy copies")
    p_doctor.add_argument("--harness", choices=["codex"], required=True)
    p_doctor.add_argument("--repo-root", default=None)
    p_doctor.add_argument("--codex-home", default=None)
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.set_defaults(func=cmd_doctor)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
