#!/usr/bin/env python3
"""Plan, diagnose, and explicitly apply Polytropos policy to Codex app state."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import tempfile
import tomllib
from pathlib import Path


def _load_policy_module():
    path = Path(__file__).resolve().with_name("codex_policy.py")
    spec = importlib.util.spec_from_file_location("codex_policy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


POLICY = _load_policy_module()
MANAGED_ROLES = ("repo-explorer", "phase-reviewer", "kit-verifier", "kit-implementer")
PINNED_ROLE_KIND = {"phase-reviewer": "verifier", "kit-verifier": "verifier"}


class AppPolicyError(RuntimeError):
    pass


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _reject_symlinks_below(base, destination):
    """Reject a destination or intermediate component below a trusted direct root."""
    try:
        relative = destination.relative_to(base)
    except ValueError:
        raise AppPolicyError(f"destination escapes managed root: {destination}")
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise AppPolicyError(f"refusing symlinked app-policy path: {current}")


def _reject_raw_symlink_chain(path, label):
    """Reject caller-supplied symlink components before canonicalization.

    macOS exposes /var and /tmp themselves as fixed system aliases; those two roots are
    tolerated so normal TemporaryDirectory paths remain usable, while descendants are not.
    """
    tolerated = {Path("/var"), Path("/tmp")}
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate in tolerated:
            continue
        if candidate.is_symlink():
            raise AppPolicyError(f"{label} contains a symlink component: {candidate}")


def _set_toml_value(text, section, key, value):
    """Surgically set one scalar while preserving unrelated TOML bytes and tables."""
    rendered = json.dumps(value)
    lines = text.splitlines(keepends=True)
    section_start = 0
    section_end = next(
        (idx for idx, line in enumerate(lines) if re.match(r"^\s*\[", line)), len(lines)
    )
    if section:
        header = f"[{section}]"
        found = None
        for idx, line in enumerate(lines):
            if line.strip() == header:
                found = idx
                break
        if found is None:
            suffix = "" if not text or text.endswith("\n") else "\n"
            return text + suffix + f"\n{header}\n{key} = {rendered}\n"
        section_start = found + 1
        section_end = len(lines)
        for idx in range(section_start, len(lines)):
            if re.match(r"^\s*\[", lines[idx]):
                section_end = idx
                break
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*).*$")
    for idx in range(section_start, section_end):
        raw = lines[idx].rstrip("\r\n")
        match = pattern.match(raw)
        if match:
            ending = "\n" if lines[idx].endswith("\n") else ""
            lines[idx] = f"{match.group(1)}{rendered}{ending}"
            return "".join(lines)
    lines.insert(section_end, f"{key} = {rendered}\n")
    return "".join(lines)


def _role_bytes(repo_root, pricing, name):
    source = Path(repo_root) / "codex" / "agents" / f"{name}.toml"
    if not source.is_file():
        raise AppPolicyError(f"missing canonical Codex role: {source}")
    text = source.read_text(encoding="utf-8")
    role = PINNED_ROLE_KIND.get(name)
    if role:
        model = POLICY.resolve_assignment(pricing, role=role)["model_id"]
        text = _set_toml_value(text, "", "model", model)
        text = _set_toml_value(text, "", "sandbox_mode", "read-only")
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise AppPolicyError(f"generated role {name} is invalid TOML: {exc}")
    return text.encode("utf-8")


def _load_runtime_ids(path):
    if path is None:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise AppPolicyError("runtime model snapshot must contain a data list")
    return {row.get("id") for row in rows if isinstance(row, dict) and row.get("id")}


def _installer_owned_files(home, repo):
    """Read the existing harness ownership ledger for proven project-agent copies."""
    path = home / "polytropos" / "install-manifest.json"
    if not path.is_file():
        return {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AppPolicyError(f"invalid Codex install ownership manifest: {path}: {exc}")
    rows = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(rows, list):
        raise AppPolicyError(f"invalid Codex install ownership records: {path}")
    owned = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("destination"), str)
            or not isinstance(row.get("installed_hash"), str)
        ):
            raise AppPolicyError(f"invalid Codex install ownership record: {path}")
        destination = row["destination"]
        if destination.startswith("project:"):
            owned[str(repo / destination.removeprefix("project:"))] = row.get("installed_hash")
    return owned


def plan_app_policy(repo_root, codex_home, backup_root, runtime_models=None):
    raw_repo, raw_home, raw_backup = map(Path, (repo_root, codex_home, backup_root))
    for path, label in ((raw_repo, "repository"), (raw_home, "Codex home"), (raw_backup, "backup root")):
        _reject_raw_symlink_chain(path, label)
    repo, home, backup = raw_repo.resolve(), raw_home.resolve(), raw_backup.resolve()
    for protected, label in ((repo, "repository"), (home, "Codex home")):
        try:
            backup.relative_to(protected)
        except ValueError:
            pass
        else:
            raise AppPolicyError(f"backup root must be outside the {label}")
    pricing = json.loads((repo / "data" / "pricing.codex.json").read_text(encoding="utf-8"))
    status = POLICY.policy_status(pricing)
    if not status["ready"]:
        raise AppPolicyError(status["error"])
    runtime_ids = _load_runtime_ids(runtime_models)
    required = {status["orchestrator_model"], *status["worker_models"]}
    missing = sorted(required - runtime_ids) if runtime_ids is not None else []
    if missing:
        raise AppPolicyError(f"runtime model snapshot is missing required policy models: {', '.join(missing)}")

    config_path = home / "config.toml"
    original_or_none = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    original = original_or_none or ""
    try:
        tomllib.loads(original)
    except tomllib.TOMLDecodeError as exc:
        raise AppPolicyError(f"invalid Codex config TOML: {exc}")
    desired = _set_toml_value(original, "", "model", status["orchestrator_model"])
    default_worker = POLICY.resolve_assignment(pricing)["model_id"]
    desired = _set_toml_value(desired, "agents", "default_subagent_model", default_worker)
    try:
        parsed = tomllib.loads(desired)
    except tomllib.TOMLDecodeError as exc:
        raise AppPolicyError(f"policy would produce invalid Codex config TOML: {exc}")
    if parsed.get("model") != status["orchestrator_model"] or parsed.get("agents", {}).get("default_subagent_model") != default_worker:
        raise AppPolicyError("Codex config uses an unsupported quoted or dotted table layout")
    actions = [{
        "component": "config", "destination": str(config_path),
        "state": "up-to-date" if desired == original else ("install" if original_or_none is None else "managed-update"),
        "desired": desired.encode("utf-8"), "original": None if original_or_none is None else original.encode("utf-8"),
        "scope": "home",
    }]
    guidance_path = home / "AGENTS.md"
    guidance_or_none = guidance_path.read_text(encoding="utf-8") if guidance_path.exists() else None
    guidance_original = guidance_or_none or ""
    start_marker = "<!-- polytropos-app-policy:start -->"
    end_marker = "<!-- polytropos-app-policy:end -->"
    managed_guidance = (
        f"{start_marker}\n"
        "Polytropos reserves the configured frontier orchestrator for planning, coordination, "
        "integration decisions, final acceptance, and evidence-gated recovery. Ordinary "
        "implementation uses the configured worker tiers; routine and independent verification "
        "use the configured verification worker. A preference for the best model is not recovery "
        "evidence. After recovery, return later implementation to the cheapest sufficient worker.\n"
        f"{end_marker}"
    )
    marker_pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker), re.DOTALL
    )
    existing_managed_block = marker_pattern.search(guidance_original)
    if existing_managed_block:
        guidance_desired = marker_pattern.sub(managed_guidance, guidance_original)
    else:
        separator = "" if not guidance_original else ("\n" if guidance_original.endswith("\n") else "\n\n")
        guidance_desired = guidance_original + separator + managed_guidance + "\n"
    actions.append({
        "component": "guidance", "destination": str(guidance_path),
        "state": "up-to-date" if guidance_desired == guidance_original else ("install" if guidance_or_none is None else "managed-update"),
        "desired": guidance_desired.encode(), "original": None if guidance_or_none is None else guidance_original.encode(),
        "scope": "home", "existing_managed_block": bool(existing_managed_block),
    })

    manifest_path = home / "polytropos" / "app-policy-manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise AppPolicyError(f"invalid app-policy ownership manifest: {manifest_path}")
    if not isinstance(manifest, dict):
        raise AppPolicyError(f"invalid app-policy ownership manifest object: {manifest_path}")
    if not isinstance(manifest.get("files", {}), dict):
        raise AppPolicyError(f"invalid app-policy ownership manifest files: {manifest_path}")
    owned = manifest.get("files", {})
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in owned.items()):
        raise AppPolicyError(f"invalid app-policy ownership manifest hashes: {manifest_path}")
    installer_owned = _installer_owned_files(home, repo)
    guidance_action = actions[-1]
    if guidance_action["existing_managed_block"] and owned.get(str(guidance_path)) != _digest(guidance_action["original"]):
        guidance_action["state"] = "conflict"
    for name in MANAGED_ROLES:
        destination = home / "agents" / f"{name}.toml"
        desired_bytes = _role_bytes(repo, pricing, name)
        current = destination.read_bytes() if destination.is_file() else None
        if current == desired_bytes:
            state = "up-to-date"
        elif current is None:
            state = "install"
        elif owned.get(str(destination)) == _digest(current):
            state = "managed-update"
        else:
            state = "conflict"
        actions.append({
            "component": "agent", "role": name, "destination": str(destination),
            "state": state, "desired": desired_bytes, "original": current, "scope": "home",
        })
        project_destination = repo / ".codex" / "agents" / f"{name}.toml"
        project_current = project_destination.read_bytes() if project_destination.is_file() else None
        canonical = (repo / "codex" / "agents" / f"{name}.toml").read_bytes()
        if project_current == desired_bytes:
            project_state = "up-to-date"
        elif (
            project_current == canonical
            or owned.get(str(project_destination)) == _digest(project_current or b"")
            or installer_owned.get(str(project_destination)) == _digest(project_current or b"")
        ):
            project_state = "managed-update" if project_current is not None else "install"
        elif project_current is None:
            project_state = "install"
        else:
            project_state = "conflict"
        actions.append({
            "component": "agent", "role": name, "destination": str(project_destination),
            "state": project_state, "desired": desired_bytes, "original": project_current,
            "scope": "project",
        })
    return {
        "ready": runtime_ids is not None,
        "runtime_models": "validated" if runtime_ids is not None else "unknown",
        "orchestrator_pool": "reserved",
        "orchestrator_model": status["orchestrator_model"],
        "default_subagent_model": default_worker,
        "actions": actions,
        "backup_root": str(backup),
        "manifest_path": str(manifest_path),
    }


def _public(plan):
    return {**{k: v for k, v in plan.items() if k != "actions"}, "actions": [
        {k: v for k, v in action.items() if k not in {"desired", "original"}}
        for action in plan["actions"]
    ]}


def apply_app_policy(plan):
    if plan["runtime_models"] != "validated":
        raise AppPolicyError("apply requires a validated runtime model snapshot")
    conflicts = [a["destination"] for a in plan["actions"] if a["state"] == "conflict"]
    if conflicts:
        raise AppPolicyError("refusing to overwrite unmanaged or edited roles: " + ", ".join(conflicts))
    backup = Path(plan["backup_root"])
    if backup.exists() and (not backup.is_dir() or any(backup.iterdir())):
        raise AppPolicyError(f"backup root must be new or empty: {backup}")
    backup.mkdir(parents=True, exist_ok=True)
    changed = [a for a in plan["actions"] if a["state"] in {"install", "managed-update"}]
    manifest_path = Path(plan["manifest_path"])
    manifest_original = manifest_path.read_bytes() if manifest_path.is_file() else None
    for action in changed:
        destination = Path(action["destination"])
        base = Path(plan["manifest_path"]).parents[1] if action.get("scope") == "home" else Path(action["destination"])
        if action.get("scope") == "project":
            # Project actions always live below the repository; infer it from /.codex/agents/.
            base = destination.parents[2]
        _reject_symlinks_below(base, destination)
        current = destination.read_bytes() if destination.is_file() else None
        if current != action["original"]:
            raise AppPolicyError(f"destination changed after plan; re-plan before apply: {destination}")
    applied = []
    files = {
        a["destination"]: _digest(a["desired"])
        for a in plan["actions"] if a["component"] in {"agent", "guidance"}
    }
    manifest = {
        "schema_version": 1, "orchestrator_pool": "reserved",
        "orchestrator_model": plan["orchestrator_model"], "files": files,
    }
    manifest_desired = (json.dumps(manifest, indent=2) + "\n").encode()
    try:
        for action in changed:
            original = action["original"]
            if original is not None:
                target = backup / action.get("scope", "home") / action["component"] / Path(action["destination"]).name
                if target.exists():
                    raise AppPolicyError(f"backup destination already exists: {target}")
                _atomic_write(target, original)
            _atomic_write(Path(action["destination"]), action["desired"])
            applied.append(action)
        if manifest_original is not None:
            _atomic_write(backup / "home/manifest/app-policy-manifest.json", manifest_original)
        _reject_symlinks_below(manifest_path.parents[1], manifest_path)
        _atomic_write(manifest_path, manifest_desired)
    except Exception:
        for action in reversed(applied):
            destination = Path(action["destination"])
            if destination.is_file() and destination.read_bytes() == action["desired"]:
                if action["original"] is None:
                    destination.unlink()
                else:
                    _atomic_write(destination, action["original"])
        if manifest_path.is_file() and manifest_path.read_bytes() == manifest_desired:
            if manifest_original is None:
                manifest_path.unlink()
            else:
                _atomic_write(manifest_path, manifest_original)
        raise
    return _public(plan)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "status", "apply"))
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--codex-home", required=True)
    parser.add_argument("--backup-root", required=True)
    parser.add_argument("--runtime-models")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    plan = plan_app_policy(args.repo_root, args.codex_home, args.backup_root, args.runtime_models)
    result = apply_app_policy(plan) if args.command == "apply" else _public(plan)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"runtime models: {result['runtime_models']}")
        print(f"orchestrator: {result['orchestrator_model']} ({result['orchestrator_pool']})")
        print(f"default subagent: {result['default_subagent_model']}")
        for action in result["actions"]:
            print(f"{action['component']}: {action['state']} — {action['destination']}")


if __name__ == "__main__":
    main()
