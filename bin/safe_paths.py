#!/usr/bin/env python3
"""The one place this repo decides whether a path is safe to write, read, or delete.

WHY ONE PLACE. Several engines write into a caller-selected root -- a kit's marker directory,
the memory store, the telemetry store, an install destination. Each had grown its own idea of
what a destination is, and none of them checked the same things, so the same class of bug
(a symlink at the leaf, a symlink in a parent, a `..` in an identifier) had to be found and
fixed separately in every one. A guard implemented in five places is a guard that will
eventually be checked five different ways.

THE CHECK-THEN-USE RACE. `resolve()` followed by `open()` is two operations on a name, and
anything may replace that name in between. Every function here walks the path
DIRECTORY-RELATIVE instead: each component is opened through `dir_fd` with `O_NOFOLLOW`, so
the check and the use are the same operation and a link swapped in afterwards has nothing left
to redirect. Where that is unavailable the functions REFUSE rather than falling back to the
racy form -- see `dir_fd_supported`.

WHAT IS AND IS NOT PROMISED. This bounds a path to a root. It says nothing about who may run
the process, and it is not a substitute for the execution boundary in `bin/exec_policy.py`: a
process with the same uid and no confinement can still reach the root itself. Containment of
NAMES is the property here.
"""

import os
import re
import stat
import tempfile
from pathlib import Path, PurePosixPath


class SafePathError(ValueError):
    """A path, identifier, or destination that this module refuses to act on."""


class SafePathExists(SafePathError):
    """A destination that had to be ABSENT is not.

    Distinct from `SafePathError` because it is the one refusal a caller routinely wants to
    catch and report rather than treat as a bug: an installer whose plan said "absent" and
    whose apply found a file has a STALE PLAN, not a broken path.
    """


#: Directory-relative operations needed to resolve a path without a check-then-use race.
#: Every one takes `dir_fd` on Linux and macOS.
_DIR_FD_OPS = (os.open, os.mkdir, os.unlink, os.stat, os.rename)


def dir_fd_supported():
    """True when this runtime can walk a path without a check-then-use race."""
    return all(op in os.supports_dir_fd for op in _DIR_FD_OPS)


def _require_dir_fd(what):
    if not dir_fd_supported():
        raise SafePathError(
            f"{what}: this runtime lacks directory-relative file operations "
            f"(os.supports_dir_fd), so a link swapped in mid-operation cannot be excluded; "
            f"refusing rather than acting on an unchecked path"
        )


#: A safe identifier used to DERIVE a filename: one path component, no traversal, no
#: separators, no drive syntax, not starting with a dot. Deliberately narrow -- these ids come
#: from a kit's TASKS.md and are turned into filenames, and the set of ids anyone legitimately
#: writes is far smaller than the set a filesystem would accept.
SAFE_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def validate_id(value, what="identifier"):
    """`value` as a safe filename component, or SafePathError.

    Rejects the empty string, absolute paths, `/` and `\\` separators, `.`/`..` traversal,
    Windows drive syntax, and leading dots. Returns the validated string so callers can use
    the return value rather than the input they were about to trust.
    """
    text = "" if value is None else str(value)
    if not SAFE_ID_RE.match(text):
        raise SafePathError(
            f"{what}: {value!r} is not a safe identifier -- expected one component matching "
            f"{SAFE_ID_RE.pattern} (no separators, no traversal, no drive letter, no leading "
            f"dot). Identifiers become filenames, so an id that can name a path can leave the "
            f"directory it was supposed to stay in."
        )
    return text


def safe_parts(rel_path, what="path"):
    """`rel_path` as safe components under a root, or SafePathError."""
    text = str(rel_path)
    if not text.strip():
        raise SafePathError(f"{what}: empty path")
    if text.startswith(("/", "\\")):
        raise SafePathError(f"{what}: refusing an absolute path {text!r}")
    if re.match(r"\A[A-Za-z]:", text):
        raise SafePathError(f"{what}: refusing a drive-qualified path {text!r}")
    parts = list(PurePosixPath(text).parts)
    if not parts:
        raise SafePathError(f"{what}: {text!r} has no path components")
    if any(part == ".." for part in parts):
        raise SafePathError(f"{what}: refusing traversal in {text!r}")
    return parts


def _descend(root, parts, what, create):
    """Open the directory holding `parts[-1]`, relative to `root`, following no links.

    Returns an open dir fd the caller must close.
    """
    dir_fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=dir_fd)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise SafePathError(f"{what}: cannot create {part!r}: {exc}") from exc
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd
                )
            except OSError as exc:
                raise SafePathError(
                    f"{what}: {'/'.join(parts)!r} traverses {part!r}, which is not a directory "
                    f"this can enter without following a link ({exc.strerror})"
                ) from exc
            os.close(dir_fd)
            dir_fd = child
        return dir_fd
    except BaseException:
        os.close(dir_fd)
        raise


def confined_write_bytes(root, rel_path, data, what="confined write", mode=0o600,
                         create_parents=True):
    """Write `data` at `rel_path` under `root`, refusing to leave `root` by any route.

    The leaf is unlinked if it is anything but a regular file, so bytes are never written
    THROUGH a link -- the link is removed and a real file takes its place. A DIRECTORY at the
    leaf is a genuine conflict and raises rather than being deleted.

    No link is traversed, including a legitimate one. A store whose subdirectory is a symlink
    gets an explicit error naming the component, not a silent write outside the root.
    """
    parts = safe_parts(rel_path, what)
    _require_dir_fd(what)
    if isinstance(data, str):
        data = data.encode()
    dir_fd = _descend(root, parts, what, create=create_parents)
    try:
        leaf = parts[-1]
        try:
            st = os.stat(leaf, dir_fd=dir_fd, follow_symlinks=False)
        except FileNotFoundError:
            st = None
        except OSError as exc:
            raise SafePathError(f"{what}: cannot inspect {rel_path!r}: {exc}") from exc
        if st is not None and stat.S_ISDIR(st.st_mode):
            raise SafePathError(f"{what}: {rel_path!r} is a directory")
        if st is not None and not stat.S_ISREG(st.st_mode):
            os.unlink(leaf, dir_fd=dir_fd)
        try:
            fd = os.open(
                leaf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, mode, dir_fd=dir_fd
            )
        except OSError as exc:
            raise SafePathError(
                f"{what}: cannot open {rel_path!r} without following a link: {exc}"
            ) from exc
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    finally:
        os.close(dir_fd)


def confined_create_bytes(root, rel_path, data, what="confined create", mode=0o600,
                          create_parents=True):
    """Create `rel_path` under `root` ONLY if nothing is there, in a single unlosable step.

    `confined_write_bytes` answers "put these bytes here"; this answers "put these bytes here
    IF this name is still free" -- and answers it with `O_EXCL`, so the question and the write
    are one kernel operation. A caller that instead checks `exists()` and then writes has a
    window in which someone else creates the file, and the write destroys it.

    That window is exactly the stale-plan bug this exists for: a plan computed one moment and
    applied the next must not overwrite a destination that appeared in between. `O_EXCL` also
    treats a SYMLINK at the leaf as existing (it refuses rather than following it), which is
    the outcome we want -- an unexpected link is a thing to report, not to write through.

    Raises `SafePathExists` when the name is taken.
    """
    parts = safe_parts(rel_path, what)
    _require_dir_fd(what)
    if isinstance(data, str):
        data = data.encode()
    dir_fd = _descend(root, parts, what, create=create_parents)
    try:
        try:
            fd = os.open(
                parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode,
                dir_fd=dir_fd,
            )
        except FileExistsError as exc:
            raise SafePathExists(
                f"{what}: {rel_path!r} already exists; refusing to create over it"
            ) from exc
        except OSError as exc:
            raise SafePathError(f"{what}: cannot create {rel_path!r}: {exc}") from exc
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    finally:
        os.close(dir_fd)


def confined_read_bytes(root, rel_path, what="confined read", missing_ok=False):
    """Read `rel_path` under `root` without following a link at any component.

    `missing_ok` returns None for an absent file. A link AT the leaf is refused rather than
    followed: reading through one is how a store hands back a file from outside itself.
    """
    parts = safe_parts(rel_path, what)
    _require_dir_fd(what)
    try:
        dir_fd = _descend(root, parts, what, create=False)
    except SafePathError:
        if missing_ok and not Path(root, *parts).exists():
            return None
        raise
    try:
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise SafePathError(f"{what}: {rel_path!r} does not exist")
        except OSError as exc:
            raise SafePathError(
                f"{what}: cannot read {rel_path!r} without following a link: {exc}"
            ) from exc
        with os.fdopen(fd, "rb") as fh:
            return fh.read()
    finally:
        os.close(dir_fd)


def confined_unlink(root, rel_path, what="confined delete", missing_ok=True):
    """Delete `rel_path` under `root`, following no link at any component.

    Deletion is the operation where an unchecked path is least recoverable, so it gets the
    same no-follow walk as a write: a link in a parent must not make this remove a file
    somewhere else.
    """
    parts = safe_parts(rel_path, what)
    _require_dir_fd(what)
    try:
        dir_fd = _descend(root, parts, what, create=False)
    except SafePathError:
        if missing_ok:
            return False
        raise
    try:
        try:
            os.unlink(parts[-1], dir_fd=dir_fd)
            return True
        except FileNotFoundError:
            if missing_ok:
                return False
            raise SafePathError(f"{what}: {rel_path!r} does not exist")
        except OSError as exc:
            raise SafePathError(f"{what}: cannot delete {rel_path!r}: {exc}") from exc
    finally:
        os.close(dir_fd)


def confined_replace(root, rel_path, data, what="confined replace", mode=0o600):
    """Atomically put `data` at `rel_path` under `root`: write a sibling temp, then rename.

    Atomic REPLACEMENT, so a reader sees either the old bytes or the new ones and never a
    half-written file. The temp file is created in the same confined directory (a rename is
    only atomic within one filesystem) and is removed if the rename fails.
    """
    parts = safe_parts(rel_path, what)
    _require_dir_fd(what)
    if isinstance(data, str):
        data = data.encode()
    dir_fd = _descend(root, parts, what, create=True)
    tmp_name = None
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=f".{parts[-1]}.", dir=os.getcwd())
        os.close(fd)
        os.unlink(tmp_path)
        tmp_name = os.path.basename(tmp_path)
        fd = os.open(
            tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=dir_fd
        )
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.rename(tmp_name, parts[-1], src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        tmp_name = None
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=dir_fd)
            except OSError:
                pass
        os.close(dir_fd)


def leaf_is_regular(root, rel_path):
    """True when `rel_path` under `root` exists and is a REGULAR file, following no links.

    The question a store has to ask before treating an existing destination as something it
    may read back and reason about. A dangling or redirecting link is not a fact file.
    """
    parts = safe_parts(rel_path, "inspect")
    _require_dir_fd("inspect")
    try:
        dir_fd = _descend(root, parts, "inspect", create=False)
    except SafePathError:
        return False
    try:
        st = os.stat(parts[-1], dir_fd=dir_fd, follow_symlinks=False)
        return stat.S_ISREG(st.st_mode)
    except OSError:
        return False
    finally:
        os.close(dir_fd)
