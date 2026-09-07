#!/usr/bin/env python3
"""The one place this repo starts an external process and decides when it must stop.

WHY ONE PLACE. Every dispatch and every verify command in this repo used a bare
`subprocess.run(argv, capture_output=True)`. That call has four failure modes this engine
cannot afford, and each call site had to remember all four:

1. IT REPORTS A FINISHED COMMAND AS A TIMEOUT. `subprocess.run(capture_output=True,
   timeout=T)` waits for the PIPES to close, not for the command to exit. A grandchild -- a
   test runner's worker, a language server the verify line started -- inherits those pipes and
   holds them open, so a command that succeeds in a second raises `TimeoutExpired` after the
   full T and its output is thrown away. Measured here: a script that echoes and returns
   instantly, having backgrounded one `sleep`, times out after exactly T. At this repo's
   1800-second default that is a half-hour stall ending in a false verdict. It also leaves the
   grandchild running.
2. IT CANNOT BOUND OUTPUT. `capture_output=True` accumulates everything before anyone gets a
   chance to truncate it. A runaway process printing megabytes a second exhausts memory long
   before a length check on the finished string ever runs.
3. IT INHERITS THE LAUNCH DIRECTORY. `cwd=None` means "wherever the user happened to be", so
   the same task verified different trees depending on where the driver was started.
4. ITS FAILURES ARE INDISTINGUISHABLE. A missing executable raises out of the runner and
   strands the task; a timeout and a command that chose to exit 124 are the same integer.

WHAT THIS PROMISES. A run ends when the COMMAND ends. Its pipes get a short drain window
afterwards so nothing it actually wrote is lost, and whatever still holds them after that is
terminated as the leftover it is. A process started here runs in its own session, so that
termination reaches the whole tree rather than one process. Output is drained continuously and bounded as it arrives,
keeping a head and a tail so the end of a log -- usually where the error is -- survives
truncation. The working directory is validated before anything starts. Every way a run can end
gets its own named outcome, and no way of ending raises out of `run()`.

WHAT IT DOES NOT. It does not promise exactly-once execution: a process killed here may have
already had its external effect, and after a crash this module knows nothing about what ran.
Reconciling that is durable-lifecycle work, not lifecycle-bounding work. It also does not
confine anything -- `bin/exec_policy.py` is the OS boundary, and this runs whatever argv it is
given, sandbox wrapper or not.
"""

import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

#: Wall-clock ceiling for one process. Generous: a real test suite is the common case.
DEFAULT_TIMEOUT_SECONDS = 1800

#: Combined stdout+stderr bytes retained. Beyond it the pipes are still drained -- the process
#: must never block on a full pipe just because we stopped caring about the content.
DEFAULT_OUTPUT_LIMIT = 8 * 1024 * 1024

#: How long a terminated tree gets to exit on SIGTERM before SIGKILL.
TERM_GRACE_SECONDS = 5

#: How long to keep reading after the command itself has exited. A command's last writes can
#: still be in the pipe when it exits, so stopping the instant it does would lose them. Anything
#: still holding the pipes after this is not the command -- it is something the command left
#: behind, and waiting on it is what turns a finished run into a reported timeout.
POST_EXIT_DRAIN_SECONDS = 2.0

#: Named outcomes. `rc` cannot carry these: a 124 from a timeout and a 124 the command chose to
#: return are the same integer, and a missing executable has no rc at all.
OUTCOME_OK = "ok"
OUTCOME_FAILED = "failed"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_CANCELLED = "cancelled"
OUTCOME_MISSING_EXECUTABLE = "missing-executable"
OUTCOME_NOT_PERMITTED = "not-permitted"
OUTCOME_BAD_WORKDIR = "bad-workdir"
OUTCOME_START_FAILED = "start-failed"

#: Outcomes where the process ran to completion and its rc means what it says. Everything else
#: is infrastructure: the command did not get to render a verdict, so its rc is not one.
TERMINAL_OUTCOMES = (OUTCOME_OK, OUTCOME_FAILED)

#: rc reported for a run that never produced one. 124 matches `timeout(1)`'s convention; the
#: `outcome` field, not this, is what callers should branch on.
INFRASTRUCTURE_RC = 124

#: True when this host can signal a whole process group. Without it, termination reaches the
#: direct child only and the result says so rather than implying a clean tree.
_HAS_PROCESS_GROUPS = hasattr(os, "killpg") and hasattr(os, "getpgid") and os.name == "posix"

#: Environment every child needs regardless of what it is: where to find binaries, who it is,
#: how to talk through a corporate proxy, and which CA bundle to trust. None of these are
#: credentials, and dropping them breaks ordinary hosts rather than protecting them.
BASE_ENV_ALLOWLIST = (
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR",
    "LANG", "LC_ALL", "LC_CTYPE", "TZ",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "no_proxy", "all_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
)

#: Name prefixes every child gets: locale and the XDG config-location family. Both say WHERE to
#: look for things, never what to authenticate with.
BASE_ENV_PREFIXES = ("LC_", "XDG_")

#: Name PREFIXES each provider's CLI may legitimately need. A dispatch to one provider carries
#: its own and the base set, and nothing else -- so handing `codex` the machine's Anthropic key,
#: or either of them the machine's AWS credentials, stops being something that happens by
#: default. This filters by NAME. It says nothing about what a CLI reads from disk: subscription
#: auth lives under HOME, which every dispatch still gets.
PROVIDER_ENV_PREFIXES = {
    "claude": ("ANTHROPIC_", "CLAUDE_"),
    "copilot": ("GH_", "GITHUB_", "COPILOT_"),
    "codex": ("OPENAI_", "CODEX_"),
}

#: Escape hatch, because an allowlist that cannot be widened is one a user cannot recover from.
#: Comma-separated variable NAMES (not values) to carry through in addition.
EXTRA_ENV_VAR = "POLYTROPOS_DISPATCH_ENV"


class WorkdirError(ValueError):
    """A working directory this runner will not start a process in."""


def validate_workdir(cwd, within=None, what="working directory"):
    """The directory a process may start in, or `WorkdirError` naming what is wrong.

    `cwd` is REQUIRED by every caller here on purpose. `subprocess`'s own default -- inherit
    whatever directory the user launched from -- is how the same task came to verify different
    trees on different runs.

    `within` additionally binds it to a root, compared after resolving symlinks, so a
    workspace reached through a link out of the repository is refused rather than used.
    """
    if cwd is None:
        raise WorkdirError(f"{what}: required; a process must not inherit the launch directory")
    path = Path(cwd)
    if not path.exists():
        raise WorkdirError(f"{what}: {str(path)!r} does not exist")
    if not path.is_dir():
        raise WorkdirError(f"{what}: {str(path)!r} is not a directory")
    resolved = os.path.realpath(str(path))
    if within is not None:
        root = os.path.realpath(str(within))
        if resolved != root and not resolved.startswith(root.rstrip(os.sep) + os.sep):
            raise WorkdirError(
                f"{what}: {str(path)!r} resolves to {resolved!r}, outside {root!r}"
            )
    return resolved


def dispatch_env(provider, base=None, extra=None):
    """The environment a dispatch to `provider` carries: base + that provider's own, nothing else.

    An unknown provider gets the base set only, which is the safe direction to be wrong in.
    `POLYTROPOS_DISPATCH_ENV` (comma-separated NAMES) widens it for a host whose CLI needs a
    variable this list has not learned about yet.
    """
    source = os.environ if base is None else base
    prefixes = PROVIDER_ENV_PREFIXES.get(provider, ())
    names = set(BASE_ENV_ALLOWLIST)
    names.update(name for name in source if name.startswith(BASE_ENV_PREFIXES))
    if prefixes:
        names.update(name for name in source if name.startswith(prefixes))
    for raw in (source.get(EXTRA_ENV_VAR) or "").split(","):
        if raw.strip():
            names.add(raw.strip())
    for name in extra or ():
        names.add(name)
    return {name: source[name] for name in sorted(names) if name in source}


def _trim_partial_tail(buf):
    """`buf` without a trailing incomplete UTF-8 sequence."""
    for back in range(1, min(4, len(buf)) + 1):
        byte = buf[-back]
        if byte < 0x80:
            return bytes(buf)
        if byte >= 0xC0:
            need = 2 if byte < 0xE0 else (3 if byte < 0xF0 else 4)
            return bytes(buf) if need == back else bytes(buf[: len(buf) - back])
    return bytes(buf)


def _trim_partial_head(buf):
    """`buf` without leading UTF-8 continuation bytes orphaned by a cut."""
    index = 0
    while index < len(buf) and index < 3 and 0x80 <= buf[index] < 0xC0:
        index += 1
    return bytes(buf[index:])


class _BoundedCapture:
    """Accumulate up to `limit` bytes, keeping a head and a tail rather than a prefix.

    Truncating from the front alone throws away the end of the log, which is where a failing
    command usually says why. This keeps three quarters from the start and one quarter from the
    end, and states in the middle how much it dropped.
    """

    def __init__(self, limit):
        self.limit = max(int(limit), 0)
        self._head_limit = (self.limit * 3) // 4
        self._tail_limit = self.limit - self._head_limit
        self._head = bytearray()
        self._tail = bytearray()
        self.dropped = 0
        self.total = 0

    def feed(self, chunk):
        self.total += len(chunk)
        if len(self._head) < self._head_limit:
            room = self._head_limit - len(self._head)
            self._head += chunk[:room]
            chunk = chunk[room:]
        if not chunk:
            return
        self._tail += chunk
        if len(self._tail) > self._tail_limit:
            excess = len(self._tail) - self._tail_limit
            del self._tail[:excess]
            self.dropped += excess

    @property
    def truncated(self):
        return self.dropped > 0

    def raw(self):
        if not self.truncated:
            # Byte-exact: untruncated output is handed back exactly as it arrived, because a
            # caller may be fingerprinting it or decoding it strictly.
            return bytes(self._head)
        note = f"\n[... {self.dropped} bytes dropped; head and tail kept ...]\n".encode()
        # Cutting mid-character would INVENT a decode error in output that was valid UTF-8,
        # and a caller that decodes strictly to detect real undecodable bytes could not tell
        # the two apart. Only reached when already truncated, so nothing byte-exact is at stake.
        return _trim_partial_tail(self._head) + note + _trim_partial_head(self._tail)

    def text(self):
        return self.raw().decode("utf-8", "replace")


def _terminate_tree(proc, pgid, grace=TERM_GRACE_SECONDS):
    """Stop the run's whole process group -> how thoroughly that was possible.

    SIGTERM to the group first so a well-behaved child can clean up, then SIGKILL to whatever
    is still there. Signalling the GROUP is the part that matters: signalling the child alone
    leaves its grandchildren running, which is the leak this exists to close.

    `pgid` is remembered from the moment the process started, not looked up now. By the time
    leftovers are cleaned up the direct child has usually been reaped, and a lookup through a
    reaped pid finds nothing -- which is how a first version of this reported success while the
    leftover kept running.

    This does not verify that the group emptied, because there is no portable way to ask:
    measured on macOS, signal 0 to a group whose leader has been reaped answers EPERM rather
    than ESRCH, so a probe cannot tell "gone" from "not allowed". Both are read here as
    "nothing signalable left", and the return value says what was SENT, not what died.
    """
    if pgid is None:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        return "direct-child-only"
    if pgid == os.getpgrp():
        # Unreachable while `start_new_session` holds, and catastrophic if it ever stopped.
        return "refused-own-group"
    delivered = False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
            delivered = True
        except (ProcessLookupError, PermissionError):
            break
        except OSError:
            return "process-group-unreachable"
        if proc.poll() is None:
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                continue
        else:
            time.sleep(0.05)
    return "process-group" if delivered else "no-such-group"


def _result(argv, cwd, outcome, rc, stdout, stderr, started, **extra):
    duration = time.monotonic() - started
    payload = {
        "argv": list(argv),
        "cwd": cwd,
        "outcome": outcome,
        "rc": rc,
        "stdout": stdout,
        "stderr": stderr,
        # Kept because every existing caller in this repo consumes one merged stream. stdout and
        # stderr stay separate above so a caller that parses structured events on stdout is not
        # handed diagnostics interleaved into them.
        "output": stdout + stderr,
        "terminal": outcome in TERMINAL_OUTCOMES,
        "timed_out": outcome == OUTCOME_TIMEOUT,
        "duration_s": round(duration, 3),
    }
    payload.update(extra)
    payload.setdefault("truncated", False)
    payload.setdefault("tree_cleanup", None)
    payload.setdefault("leftovers", False)
    payload.setdefault("detail", "")
    return payload


def _render(capture, text):
    return capture.text() if text else capture.raw()


def _fail(argv, cwd, outcome, exc, started, text, detail):
    """An infrastructure outcome, rendered in whichever form the caller asked for."""
    empty = "" if text else b""
    stderr = str(exc) if text else str(exc).encode()
    return _result(argv, cwd, outcome, INFRASTRUCTURE_RC, empty, stderr, started, detail=detail)


def run(argv, cwd, env=None, timeout=DEFAULT_TIMEOUT_SECONDS,
        output_limit=DEFAULT_OUTPUT_LIMIT, input_text=None, within=None, name="process",
        grace=TERM_GRACE_SECONDS, text=True):
    """Run `argv` in `cwd` under a wall-clock and output bound -> a result dict.

    Never raises for anything the process does: a missing executable, a refused permission, a
    bad directory, a timeout, and a clean exit all come back as an `outcome`. The one exception
    is `KeyboardInterrupt`, which is re-raised AFTER the process tree is torn down -- swallowing
    it would take Ctrl-C away from the user, and letting it through without the teardown would
    leave the tree running. A caller that must record an interrupted task catches it around
    this call, where it has the task to record against.

    `text=False` returns `stdout`/`stderr`/`output` as BYTES. Decoding is lossy -- a binary
    `git diff` run through `errors="replace"` is not the diff any more -- so anything whose
    bytes are the point (a fingerprint, an archive) must ask for them.

    `env=None` inherits this process's environment. Callers dispatching to a provider should
    pass `dispatch_env(provider)` instead; verification should pass the reduced environment
    `bin/exec_policy.py` builds.
    """
    started = time.monotonic()
    argv = list(argv)
    try:
        cwd = validate_workdir(cwd, within=within, what=f"{name} working directory")
    except WorkdirError as exc:
        return _fail(argv, str(cwd), OUTCOME_BAD_WORKDIR, exc, started, text, str(exc))

    payload = input_text.encode() if isinstance(input_text, str) else input_text
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            close_fds=True,
            # Its own session, so termination can reach grandchildren. Without this a killed
            # child's children survive, keep the pipes open, and the wait never ends.
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return _fail(argv, cwd, OUTCOME_MISSING_EXECUTABLE, exc, started, text,
                     f"{name}: executable not found: {argv[0]!r}")
    except PermissionError as exc:
        return _fail(argv, cwd, OUTCOME_NOT_PERMITTED, exc, started, text,
                     f"{name}: not permitted to execute {argv[0]!r}")
    except OSError as exc:
        return _fail(argv, cwd, OUTCOME_START_FAILED, exc, started, text,
                     f"{name}: could not start {argv[0]!r}: {exc}")

    # `start_new_session` makes the child a session and group leader, so its pgid IS its pid.
    # Captured now because it stops being discoverable once the child is reaped.
    pgid = proc.pid if _HAS_PROCESS_GROUPS else None
    out = _BoundedCapture(output_limit)
    err = _BoundedCapture(output_limit)
    deadline = time.monotonic() + timeout if timeout else None
    tree_cleanup = None
    outcome = None

    leftovers = False
    try:
        leftovers = _pump(proc, payload, out, err, deadline) == "leftover"
    except _Deadline:
        tree_cleanup = _terminate_tree(proc, pgid, grace=grace)
        outcome = OUTCOME_TIMEOUT
    except KeyboardInterrupt:
        _terminate_tree(proc, pgid, grace=grace)
        raise
    finally:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass

    if outcome == OUTCOME_TIMEOUT:
        rc = INFRASTRUCTURE_RC
        detail = f"{name}: exceeded its {timeout}s wall-clock limit and was terminated"
    else:
        try:
            remaining = None if deadline is None else max(deadline - time.monotonic(), 0.0)
            rc = proc.wait(timeout=remaining if remaining is None else max(remaining, 1.0))
        except subprocess.TimeoutExpired:
            tree_cleanup = _terminate_tree(proc, pgid, grace=grace)
            return _result(argv, cwd, OUTCOME_TIMEOUT, INFRASTRUCTURE_RC,
                           _render(out, text), _render(err, text),
                           started, truncated=out.truncated or err.truncated,
                           tree_cleanup=tree_cleanup,
                           detail=f"{name}: exceeded its {timeout}s wall-clock limit")
        outcome = OUTCOME_OK if rc == 0 else OUTCOME_FAILED
        detail = ""
        if leftovers:
            # The command finished; something it started is still holding the pipes. Its
            # verdict stands -- the leftover is not evidence about the command -- but the
            # leftover does not get to outlive the run.
            tree_cleanup = _terminate_tree(proc, pgid, grace=grace)
            detail = (
                f"{name}: exited but left processes holding its output; they were terminated"
            )

    return _result(argv, cwd, outcome, rc, _render(out, text), _render(err, text), started,
                   truncated=out.truncated or err.truncated, tree_cleanup=tree_cleanup,
                   leftovers=leftovers, detail=detail)


class _Deadline(Exception):
    """Internal: the wall-clock limit passed while reading."""


def _pump(proc, payload, out, err, deadline, drain=POST_EXIT_DRAIN_SECONDS):
    """Drain both pipes (and feed stdin) until the COMMAND ends -> "closed" or "leftover".

    The stopping condition is the command's exit, not EOF on its pipes. Those are the same
    event only when nothing the command started outlives it; when something does, waiting for
    EOF waits for the leftover, which is how a finished run gets reported as a timeout. So once
    `poll()` says the command is gone, the pipes get `drain` seconds to hand over anything
    still buffered, and then this returns "leftover" and the caller cleans up what is holding
    them.

    Draining is not optional even after the output bound is reached: a process whose stdout
    pipe fills up blocks in `write`, and a blocked process never exits -- so a runner that
    stopped reading would deadlock precisely on the noisy processes the bound exists for.

    stdin is written through the same selector rather than up front, because a child that
    starts producing output before it has consumed a large prompt would otherwise fill its
    stdout pipe while this side is still blocked writing stdin -- each waiting on the other.

    Raises `_Deadline` if the wall-clock limit passes while the command is still running.
    """
    selector = selectors.DefaultSelector()
    capture = {}
    for stream, sink in ((proc.stdout, out), (proc.stderr, err)):
        if stream is not None:
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
            capture[stream.fileno()] = sink
    pending = payload
    if pending is not None and proc.stdin is not None:
        os.set_blocking(proc.stdin.fileno(), False)
        selector.register(proc.stdin, selectors.EVENT_WRITE)
    elif proc.stdin is not None:
        proc.stdin.close()

    drain_deadline = None
    try:
        while selector.get_map():
            now = time.monotonic()
            if drain_deadline is None and proc.poll() is not None:
                drain_deadline = now + drain
            if drain_deadline is not None and now >= drain_deadline:
                return "leftover"
            if deadline is not None and now >= deadline and drain_deadline is None:
                raise _Deadline()

            waits = [0.2]  # poll for the command's exit even while the pipes stay quiet
            if deadline is not None and drain_deadline is None:
                waits.append(max(deadline - now, 0.0))
            if drain_deadline is not None:
                waits.append(max(drain_deadline - now, 0.0))
            for key, _events in selector.select(timeout=min(waits)):
                if key.fileobj is proc.stdin:
                    try:
                        written = os.write(key.fd, pending)
                    except BlockingIOError:
                        continue
                    except OSError:
                        written = len(pending)
                    pending = pending[written:]
                    if not pending:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                    continue
                try:
                    chunk = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                except OSError:
                    chunk = b""
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                capture[key.fd].feed(chunk)
        return "closed"
    finally:
        selector.close()


def _cli(argv=None):
    """`proc_runner.py <cmd...>` -- run one command under the default bounds and report."""
    import json

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: proc_runner.py <command> [args...]", file=sys.stderr)
        return 2
    result = run(argv, cwd=os.getcwd(), name="cli")
    printable = {k: v for k, v in result.items() if k not in ("stdout", "stderr", "output")}
    print(json.dumps(printable, indent=2, sort_keys=True))
    return 0 if result["outcome"] == OUTCOME_OK else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
