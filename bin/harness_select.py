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

What `install --harness codex` does by default: it validates and prepares the checked-in plugin
metadata and may install the selected optional agent roles. It does not call `codex`, register
or enable a plugin, refresh the host cache, or copy skills, prompts, or global guidance.
Use `codex plugin marketplace add <repo-root>` and `codex plugin add
polytropos@polytropos-local` for the host-side installation. The plan reports package readiness
separately from runtime activation, which remains unknown without host evidence.

`--legacy-copy` is the explicit compatibility path for copying skills, prompts, or guidance into
an explicitly supplied Codex home. It is ownership-aware and preserves differing user files.
The legacy `install_codex()` helper retains that behavior for callers; new normal installs and
updates use the native planner. Tests and verification always pass temporary homes, never a real
Codex home.

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

    All destinations are no-clobber. Prompt destinations now use the same absent/matching/differing
    classification as guidance: matching files remain untouched and differing files are skipped.
    `~/.codex/AGENTS.md` is a single shared file that may hold the
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
        text = src.read_text().replace(PLACEHOLDER, str(repo_root))
        if dest.exists():
            if dest.is_file() and dest.read_text() == text:
                results.append((dest, "up-to-date"))
            else:
                results.append((dest, "skip-differs"))
            continue
        results.append((dest, "install"))
        if not dry_run:
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


def parse_retirement_components(raw):
    values = tuple(value.strip() for value in (raw or "prompts").split(","))
    if not values or any(not value for value in values) or len(set(values)) != len(values):
        raise ValueError("--components must contain unique prompts and optionally skills")
    if set(values) - {"prompts", "skills"}:
        raise ValueError("retirement supports only prompts and skills")
    return tuple(value for value in ("prompts", "skills") if value in values)


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
    package_valid, package_reason = _validate_plugin_metadata(root)

    if "plugin" in components:
        actions.append(
            {
                "component": "plugin",
                "source": str(root / ".agents" / "plugins" / "marketplace.json"),
                "destination": "Codex /plugins",
                # Preserve the installer action-state contract.  Package readiness below is
                # the diagnostic truth; this state does not assert host installation.
                "state": "up-to-date" if package_valid else "conflict",
                "reason": (
                    package_reason
                    if package_valid
                    else f"plugin metadata invalid: {package_reason}"
                ),
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
        "legacy_copy": bool(legacy_copy),
        "package_readiness": {
            "state": "ready" if package_valid else "invalid",
            "reason": package_reason,
        },
        "activation": {
            "state": "unknown",
            "reason": "installation, enablement, and loaded skills require host runtime evidence",
        },
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

        # Merge selected actions into the prior manifest. Component-scoped native setup must
        # not discard ownership for legacy components (or later migration metadata) that the
        # current plan did not select.
        prior_ownership = _load_ownership(plan["codex_home"])
        manifest = dict(prior_ownership) if isinstance(prior_ownership, dict) else {}
        manifest.pop("invalid", None)
        records_by_destination = {
            record.get("destination"): dict(record)
            for record in manifest.get("files", [])
            if isinstance(record, dict) and isinstance(record.get("destination"), str)
        }
        for action in plan["actions"]:
            if action["component"] == "plugin" or action["state"] in {"conflict", "unmanaged", "skip"}:
                continue
            destination = Path(action["destination"])
            if not destination.is_file():
                continue
            records_by_destination[action["_ownership_key"]] = {
                "component": action["component"],
                "destination": action["_ownership_key"],
                "bundle_version": plan["bundle_version"],
                "source_hash": action["source_digest"],
                "installed_hash": _sha256_bytes(destination.read_bytes()),
            }
        manifest.update({
            "version": OWNERSHIP_VERSION,
            "bundle_version": plan["bundle_version"],
            "files": sorted(records_by_destination.values(), key=lambda record: record["destination"]),
        })
        if plan.get("legacy_copy") and isinstance(manifest.get("retired"), list):
            recreated = {
                action.get("_ownership_key") for action in plan["actions"]
                if action["component"] in {"skills", "prompts"}
                and action["state"] not in {"conflict", "unmanaged", "skip"}
            }
            manifest["retired"] = [
                record for record in manifest["retired"]
                if record.get("destination") not in recreated
            ]
        records = manifest["files"]
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
    optional_components = {"skills", "prompts", "guidance"}
    for action in checks["actions"]:
        if action["component"] in optional_components and action["state"] == "install":
            action["state"] = "absent"
            action["reason"] = "optional legacy copy is absent"
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
    home = Path(codex_home).resolve()
    legacy_surfaces = {}
    for component, relative in (
        ("skills", Path("skills")),
        ("prompts", Path("prompts")),
        ("guidance", Path("AGENTS.md")),
    ):
        component_actions = [
            action for action in checks["actions"] if action["component"] == component
        ]
        present = [action for action in component_actions if action["state"] != "absent"]
        legacy_surfaces[component] = {
            "state": "present" if present else "absent",
            "optional": True,
            "path": str(home / relative),
            "counts": {
                state: sum(action["state"] == state for action in component_actions)
                for state in sorted({action["state"] for action in component_actions})
            },
        }
    checks["legacy_surfaces"] = legacy_surfaces

    canonical_names = {
        path.name for path in (Path(repo_root) / "codex" / "skills").iterdir() if path.is_dir()
    } if (Path(repo_root) / "codex" / "skills").is_dir() else set()
    duplicate_surfaces = {}
    for action in checks["actions"]:
        if action["state"] == "absent" or action["component"] not in {"skills", "prompts"}:
            continue
        destination = Path(action["destination"])
        if action["component"] == "skills":
            try:
                name = destination.relative_to(home / "skills").parts[0]
            except (ValueError, IndexError):
                continue
        else:
            name = destination.stem
        if name not in canonical_names:
            continue
        duplicate_surfaces.setdefault(name, {"plugin-package"}).add(
            f"legacy-{action['component'][:-1]}-copy"
        )
    checks["potential_duplicate_names"] = [
        {"name": name, "surfaces": sorted(surfaces)}
        for name, surfaces in sorted(duplicate_surfaces.items())
    ]
    checks["session_note"] = "Restart Codex or start a new session after enabling the plugin or changing agents."
    return checks


def render_codex_plan(plan, as_json=False):
    public = _public_plan(plan)
    if as_json:
        return json.dumps(public, indent=2, sort_keys=True)
    lines = []
    readiness = public.get("package_readiness", {})
    activation = public.get("activation", {})
    lines.append(
        f"package readiness: {readiness.get('state', 'unknown')}"
        f" ({readiness.get('reason', 'no evidence')})"
    )
    lines.append(
        f"runtime activation: {activation.get('state', 'unknown')}"
        f" ({activation.get('reason', 'no runtime evidence')})"
    )
    for action in public["actions"]:
        label = "plugin package metadata" if action["component"] == "plugin" else action["component"]
        lines.append(
            f"{label}: {action['state']} — {action['destination']} ({action['reason']})"
        )
    if "plugin" in public["components"]:
        lines.append("next: open /plugins, install and enable Polytropos, then start a new session")
    for duplicate in public.get("potential_duplicate_names", []):
        lines.append(
            f"potential duplicate: {duplicate['name']} — {', '.join(duplicate['surfaces'])}"
        )
    for name, surface in sorted(public.get("legacy_surfaces", {}).items()):
        lines.append(f"optional legacy {name}: {surface['state']} — {surface['path']}")
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
        home = Path(args.codex_home) if args.codex_home else (Path.home() / ".codex")
        try:
            if args.refresh_managed and args.codex_home is None:
                raise SystemExit("--refresh-managed requires an explicit --codex-home")
            if args.legacy_copy and args.components is None:
                raise SystemExit("--legacy-copy requires explicit --components")
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
        if any(action["state"] in {"conflict", "unmanaged"} for action in plan["actions"]):
            raise SystemExit(2)
        apply_codex_plan(plan)
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


def cmd_retire_legacy(args):
    import codex_legacy_migration as migration
    try:
        components = parse_retirement_components(args.components)
        plan = migration.plan_retirement(
            args.repo_root, args.codex_home, args.backup_root, components,
            native_skills_confirmed=args.native_skills_confirmed,
        )
        print(json.dumps(plan, indent=2, sort_keys=True) if args.json else migration.render_plan(plan))
        if args.apply:
            migration.apply_retirement(plan)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


def cmd_restore_legacy(args):
    import codex_legacy_migration as migration
    try:
        result = migration.restore_legacy(args.repo_root, args.codex_home, args.backup_root)
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"restored {len(result['files'])} legacy files")
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


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

    for command, function, help_text in (
        ("retire-legacy", cmd_retire_legacy, "preview or apply reversible Codex legacy retirement"),
        ("restore-legacy", cmd_restore_legacy, "restore a retired Codex legacy batch"),
    ):
        parser = sub.add_parser(command, help=help_text)
        parser.add_argument("--harness", choices=["codex"], required=True)
        parser.add_argument("--repo-root", required=True)
        parser.add_argument("--codex-home", required=True)
        parser.add_argument("--backup-root", required=True)
        parser.add_argument("--json", action="store_true")
        if command == "retire-legacy":
            parser.add_argument("--components", default="prompts")
            parser.add_argument("--native-skills-confirmed", action="store_true",
                                help="record operator evidence that native replacement skills work")
            parser.add_argument("--apply", action="store_true")
        parser.set_defaults(func=function)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
