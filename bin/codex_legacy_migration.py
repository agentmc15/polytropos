#!/usr/bin/env python3
"""Plan, apply, and restore proven Codex legacy copies safely."""

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath

MANIFEST_NAME = "retirement-manifest.json"
FORMAT_VERSION = 1


def _sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def _lexical(path):
    return Path(os.path.abspath(os.fspath(path)))


def _inside(path, root):
    try:
        _lexical(path).relative_to(_lexical(root))
        return True
    except ValueError:
        return False


def _reject_symlinks(path, boundary):
    path = _lexical(path)
    boundary = _lexical(boundary)
    if not _inside(path, boundary):
        raise ValueError(f"path escapes approved root: {path}")
    cursor = path
    while True:
        if cursor.is_symlink():
            raise ValueError(f"symlinked path is not allowed: {cursor}")
        if cursor == boundary:
            return
        cursor = cursor.parent


def _roots(repo_root, codex_home, backup_root):
    lexical_roots = tuple(_lexical(path) for path in (repo_root, codex_home, backup_root))
    for root in lexical_roots:
        if root.is_symlink():
            raise ValueError(f"symlinked root is not allowed: {root}")
    # Resolve existing parent aliases before comparing roots.  This accepts ordinary system
    # aliases such as /tmp while preventing a user-created parent link from hiding that the
    # requested backup actually lands inside a discovery root.
    repo, home, backup = (root.resolve(strict=False) for root in lexical_roots)
    discovery_roots = (
        repo,
        home,
        repo / ".agents" / "skills",
        home.parent / ".agents" / "skills",
    )
    if any(_inside(backup, root) or _inside(root, backup) for root in discovery_roots):
        raise ValueError("backup root must be outside every supplied discovery root")
    return repo, home, backup


def _atomic_write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _exclusive_write(path, payload, root):
    path = _lexical(path)
    _reject_symlinks(path.parent, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlinks(path.parent, root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _plain_file(path, root):
    try:
        _reject_symlinks(path, root)
    except ValueError:
        return False
    return Path(path).is_file()


def _skill_extras(home, inventory):
    skill_root = home / "skills"
    canonical = {destination for component, _, destination in inventory if component == "skills"}
    extras = []
    if not skill_root.is_dir() or skill_root.is_symlink():
        return extras
    for skill_dir in skill_root.iterdir():
        if not skill_dir.is_dir() or skill_dir.is_symlink():
            continue
        known = {path for path in canonical if _inside(path, skill_dir)}
        actual = {path for path in skill_dir.rglob("*") if path.is_file() or path.is_symlink()}
        if known:
            extras.extend(sorted(actual - known))
    return extras


def plan_retirement(
    repo_root,
    codex_home,
    backup_root,
    components=("prompts",),
    native_skills_confirmed=False,
):
    """Build a byte-read-only retirement plan from explicit roots."""
    import harness_select as hs

    repo, home, backup = _roots(repo_root, codex_home, backup_root)
    components = tuple(components)
    if not components or set(components) - {"prompts", "skills"}:
        raise ValueError("components must be prompts and/or skills")
    if len(set(components)) != len(components):
        raise ValueError("components must be unique")

    ownership = hs._load_ownership(home)
    if ownership.get("invalid"):
        raise ValueError("ownership manifest is invalid; retirement cannot safely merge it")
    owned = {
        record.get("destination"): record
        for record in ownership.get("files", [])
        if isinstance(record, dict)
    }
    inventory = hs._source_inventory(repo, home, components, "project")
    conflicts = [str(path) for path in _skill_extras(home, inventory)]
    actions = []
    for component, source, destination in inventory:
        if not destination.exists() and not destination.is_symlink():
            continue
        key = hs._ownership_key(component, destination, home, repo)
        action = {
            "component": component,
            "source": str(source),
            "destination": str(destination),
            "ownership_key": key,
        }
        if not _plain_file(destination, home):
            action.update(state="conflict", reason="destination is symlinked, non-file, or escaped")
            conflicts.append(str(destination))
        else:
            payload = destination.read_bytes()
            digest = _sha256(payload)
            record = owned.get(key)
            exact = payload == hs._resolved_bytes(source, repo)
            ownership_proof = bool(record and record.get("installed_hash") == digest)
            if exact or ownership_proof:
                relative = destination.relative_to(home).as_posix()
                action.update(
                    state="eligible",
                    reason="exact current bundle content" if exact else "ownership hash matches",
                    digest=digest,
                    relative=relative,
                    backup=str(backup / "files" / relative),
                    ownership_record=dict(record) if ownership_proof else None,
                )
            else:
                action.update(state="conflict", reason="ownership is not proven", digest=digest)
                conflicts.append(str(destination))
        actions.append(action)
    return {
        "version": FORMAT_VERSION,
        "repo_root": str(repo),
        "codex_home": str(home),
        "backup_root": str(backup),
        "components": list(components),
        "native_skills_confirmed": bool(native_skills_confirmed),
        "actions": actions,
        "conflicts": sorted(set(conflicts)),
        "blocked": bool(conflicts),
    }


def _manifest_entry(action):
    return {
        "component": action["component"],
        "destination": action["destination"],
        "relative": action["relative"],
        "hash": action["digest"],
        "backup": action["backup"],
        "ownership_record": action.get("ownership_record"),
    }


def _validate_relative(component, raw):
    if not isinstance(raw, str):
        raise ValueError("manifest relative path must be a string")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        raise ValueError(f"invalid manifest relative path: {raw}")
    expected_prefix = "prompts" if component == "prompts" else "skills"
    if component not in {"prompts", "skills"} or not relative.parts or relative.parts[0] != expected_prefix:
        raise ValueError(f"manifest component/path mismatch: {component} {raw}")
    return Path(*relative.parts)


def _validated_manifest_entry(entry, home, backup):
    if not isinstance(entry, dict):
        raise ValueError("invalid retirement manifest entry")
    relative = _validate_relative(entry.get("component"), entry.get("relative"))
    if not isinstance(entry.get("destination"), str) or not isinstance(entry.get("backup"), str):
        raise ValueError("manifest paths must be strings")
    if not isinstance(entry.get("hash"), str) or len(entry["hash"]) != 64:
        raise ValueError("manifest hash is invalid")
    destination = home / relative
    payload_path = backup / "files" / relative
    if _lexical(entry.get("destination")) != destination:
        raise ValueError("manifest destination does not match its relative path")
    if _lexical(entry.get("backup")) != payload_path:
        raise ValueError("manifest backup does not match its relative path")
    record = entry.get("ownership_record")
    if record is not None:
        expected_key = f"home:{relative.as_posix()}"
        if not isinstance(record, dict) or record.get("destination") != expected_key:
            raise ValueError("manifest ownership record does not match its destination")
        if record.get("component") != entry.get("component"):
            raise ValueError("manifest ownership record component mismatch")
    return relative, destination, payload_path


def _matching_completed_manifest(plan, manifest):
    if manifest.get("repo_root") != plan["repo_root"]:
        return False
    if manifest.get("codex_home") != plan["codex_home"]:
        return False
    if manifest.get("components") != plan["components"]:
        return False
    intended = [_manifest_entry(action) for action in plan["actions"] if action["state"] == "eligible"]
    if intended:
        return manifest.get("files") == intended
    import harness_select as hs

    repo = Path(plan["repo_root"])
    home = Path(plan["codex_home"])
    canonical = {
        destination.relative_to(home).as_posix()
        for _, _, destination in hs._source_inventory(
            repo, home, tuple(plan["components"]), "project"
        )
    }
    recorded = {
        entry.get("relative")
        for entry in manifest.get("files", [])
        if isinstance(entry, dict)
    }
    return bool(recorded) and recorded.issubset(canonical)


def apply_retirement(plan, fail_after=None, fail_manifest=False, before_archive=None):
    """Apply one conservative batch, rolling back without overwriting concurrent edits."""
    import harness_select as hs

    if plan.get("blocked"):
        raise ValueError("retirement batch contains conflicts; nothing retired")
    if not plan.get("native_skills_confirmed"):
        raise ValueError("--native-skills-confirmed is required for apply; it records operator evidence")
    repo, home, backup = _roots(plan["repo_root"], plan["codex_home"], plan["backup_root"])
    _reject_symlinks(backup, backup)
    manifest_path = backup / MANIFEST_NAME
    eligible = [action for action in plan["actions"] if action["state"] == "eligible"]

    if manifest_path.exists() or manifest_path.is_symlink():
        if manifest_path.is_symlink():
            raise ValueError("backup manifest may not be a symlink")
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not _matching_completed_manifest(plan, existing):
            raise FileExistsError(f"backup manifest collision: {manifest_path}")
        for entry in existing.get("files", []):
            _, destination, payload_path = _validated_manifest_entry(entry, home, backup)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"retired destination has been recreated: {destination}")
            if not _plain_file(payload_path, backup):
                raise ValueError(f"backup payload is unsafe: {payload_path}")
            if _sha256(payload_path.read_bytes()) != entry["hash"]:
                raise ValueError(f"backup payload was tampered: {payload_path}")
        return existing

    if _skill_extras(home, hs._source_inventory(repo, home, plan["components"], "project")):
        raise ValueError("skill directory changed since preview; nothing retired")
    owner_path = home / hs.OWNERSHIP_RELATIVE
    _reject_symlinks(owner_path, home)
    prior_owner = owner_path.read_bytes() if owner_path.is_file() else None
    written_owner_digest = None
    written_backups = []
    removed = []
    try:
        for index, action in enumerate(eligible, 1):
            destination = Path(action["destination"])
            payload_path = Path(action["backup"])
            if before_archive is not None:
                before_archive(index, action)
            if not _plain_file(destination, home):
                raise ValueError(f"destination changed since preview: {destination}")
            payload = destination.read_bytes()
            if _sha256(payload) != action["digest"]:
                raise ValueError(f"destination changed since preview: {destination}")
            _reject_symlinks(payload_path.parent, backup)
            if payload_path.exists() or payload_path.is_symlink():
                raise FileExistsError(f"backup collision: {payload_path}")
            _exclusive_write(payload_path, payload, backup)
            written_backups.append((destination, payload_path))
            if not _plain_file(destination, home) or _sha256(destination.read_bytes()) != action["digest"]:
                raise ValueError(f"destination changed during retirement: {destination}")
            destination.unlink()
            removed.append((destination, payload))
            if fail_after is not None and index >= fail_after:
                raise RuntimeError("simulated retirement failure")

        owner = hs._load_ownership(home)
        keys = {action["ownership_key"] for action in eligible}
        owner["files"] = [
            record for record in owner.get("files", []) if record.get("destination") not in keys
        ]
        retired = owner.get("retired", [])
        retired = retired if isinstance(retired, list) else []
        retired.extend(
            {
                "component": action["component"],
                "destination": action["ownership_key"],
                "hash": action["digest"],
                "backup_manifest": str(manifest_path),
            }
            for action in eligible
        )
        owner["retired"] = sorted(
            {record["destination"]: record for record in retired}.values(),
            key=lambda record: record["destination"],
        )
        owner["version"] = hs.OWNERSHIP_VERSION
        _reject_symlinks(owner_path.parent, home)
        owner_payload = (json.dumps(owner, indent=2, sort_keys=True) + "\n").encode()
        _atomic_write(owner_path, owner_payload)
        written_owner_digest = _sha256(owner_payload)

        manifest = {
            "version": FORMAT_VERSION,
            "repo_root": str(repo),
            "codex_home": str(home),
            "components": plan["components"],
            "native_skills_confirmed": True,
            "files": [_manifest_entry(action) for action in eligible],
        }
        if fail_manifest:
            raise RuntimeError("simulated manifest failure")
        _reject_symlinks(manifest_path.parent, backup)
        _exclusive_write(
            manifest_path,
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
            backup,
        )
        for directory in sorted(
            {Path(action["destination"]).parent for action in eligible if action["component"] == "skills"},
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            cursor = directory
            while cursor != home / "skills" and _inside(cursor, home / "skills"):
                try:
                    cursor.rmdir()
                except OSError:
                    break
                cursor = cursor.parent
        return manifest
    except BaseException as original_error:
        restored_destinations = set()
        retained_backups = []
        for destination, payload in reversed(removed):
            if destination.exists() or destination.is_symlink():
                matching = [backup_path for archived, backup_path in written_backups if archived == destination]
                retained_backups.extend(matching)
                continue
            try:
                _exclusive_write(destination, payload, home)
                restored_destinations.add(destination)
            except BaseException:
                matching = [backup_path for archived, backup_path in written_backups if archived == destination]
                retained_backups.extend(matching)
        removed_destinations = {destination for destination, _ in removed}
        for destination, payload_path in reversed(written_backups):
            if destination not in removed_destinations:
                retained_backups.append(payload_path)
                continue
            if destination in restored_destinations and payload_path.is_file():
                payload_path.unlink()
        owner_is_ours = (
            written_owner_digest is not None
            and owner_path.is_file()
            and _sha256(owner_path.read_bytes()) == written_owner_digest
        )
        if owner_is_ours:
            if prior_owner is None:
                owner_path.unlink(missing_ok=True)
            else:
                _atomic_write(owner_path, prior_owner)
        if retained_backups:
            locations = ", ".join(str(path) for path in sorted(set(retained_backups)))
            raise RuntimeError(
                f"retirement failed; original payload retained at: {locations}"
            ) from original_error
        raise


def restore_legacy(repo_root, codex_home, backup_root, fail_after=None, before_restore=None):
    """Restore one manifest without overwriting later files or following symlinks."""
    import harness_select as hs

    repo, home, backup = _roots(repo_root, codex_home, backup_root)
    manifest_path = backup / MANIFEST_NAME
    _reject_symlinks(manifest_path, backup)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("repo_root") != str(repo) or manifest.get("codex_home") != str(home):
        raise ValueError("manifest roots do not match")

    checked = []
    for entry in manifest.get("files", []):
        _, destination, payload_path = _validated_manifest_entry(entry, home, backup)
        _reject_symlinks(destination.parent, home)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"restore destination is occupied: {destination}")
        if not _plain_file(payload_path, backup):
            raise ValueError(f"backup payload is unsafe: {payload_path}")
        payload = payload_path.read_bytes()
        if _sha256(payload) != entry["hash"]:
            raise ValueError(f"backup payload was tampered: {payload_path}")
        checked.append((entry, destination, payload))

    owner_path = home / hs.OWNERSHIP_RELATIVE
    _reject_symlinks(owner_path, home)
    current_owner = hs._load_ownership(home)
    if current_owner.get("invalid"):
        raise ValueError("ownership manifest is invalid; restore cannot safely merge it")
    prior_owner = owner_path.read_bytes() if owner_path.is_file() else None
    written_owner_digest = None
    restored = []
    try:
        for index, (entry, destination, payload) in enumerate(checked, 1):
            if before_restore is not None:
                before_restore(index, entry)
            _reject_symlinks(destination.parent, home)
            _exclusive_write(destination, payload, home)
            restored.append((destination, _sha256(payload)))
            if fail_after is not None and index >= fail_after:
                raise RuntimeError("simulated restore failure")

        owner = hs._load_ownership(home)
        keys = {f"home:{Path(entry['relative']).as_posix()}" for entry, _, _ in checked}
        owner["retired"] = [
            record for record in owner.get("retired", []) if record.get("destination") not in keys
        ]
        records = {
            record.get("destination"): record
            for record in owner.get("files", [])
            if isinstance(record, dict)
        }
        for entry, _, _ in checked:
            record = entry.get("ownership_record")
            if record is not None:
                records[record["destination"]] = record
        owner["files"] = sorted(records.values(), key=lambda record: record["destination"])
        owner_payload = (json.dumps(owner, indent=2, sort_keys=True) + "\n").encode()
        _atomic_write(owner_path, owner_payload)
        written_owner_digest = _sha256(owner_payload)
        return manifest
    except BaseException:
        for destination, digest in reversed(restored):
            if destination.is_file() and _sha256(destination.read_bytes()) == digest:
                destination.unlink()
        owner_is_ours = (
            written_owner_digest is not None
            and owner_path.is_file()
            and _sha256(owner_path.read_bytes()) == written_owner_digest
        )
        if owner_is_ours:
            if prior_owner is None:
                owner_path.unlink(missing_ok=True)
            else:
                _atomic_write(owner_path, prior_owner)
        raise


def render_plan(plan):
    lines = [
        "legacy retirement preview",
        f"native replacement attested: {str(plan['native_skills_confirmed']).lower()}",
    ]
    lines.extend(
        f"{action['component']}: {action['state']} — {action['destination']} ({action['reason']})"
        for action in plan["actions"]
    )
    lines.extend(f"conflict: {path}" for path in plan.get("conflicts", []))
    lines.append(
        "apply blocked by conflicts"
        if plan["blocked"]
        else "preview only; --apply also requires --native-skills-confirmed"
    )
    return "\n".join(lines)
