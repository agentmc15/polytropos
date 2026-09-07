#!/usr/bin/env python3
"""The OS-enforced execution boundary for every stage of a run that executes code.

WHY THIS EXISTS, precisely. The drivers confine the MODEL: codex gets `--sandbox
workspace-write`, claude gets a permission flag, copilot gets a tool grant. Then verification
runs the code that model just wrote -- `python3 -m unittest discover -s tests` imports the
modules it edited -- through `subprocess.run(cmd, shell=True)` in the PARENT process, with the
parent's full filesystem access, the parent's credentials, and the parent's network. A worker
restricted to its workspace had its code executed by a process that was not restricted at all.

Changing `shell=True` to an argv list does not touch this. The command was never the problem;
the privileges of the process running it were. So the shell stays -- verify commands are
repo-authored shell lines and that is a legitimate contract -- and it runs INSIDE the boundary.

WHAT A BOUNDARY IS HERE. An `ExecPolicy` declares a writable workspace, a run-scoped scratch
directory, paths whose contents must not be readable, whether network is permitted, and the
environment variables that survive. Everything else is read-only, and nothing is inherited by
default: the environment is an ALLOWLIST, so a credential reaches a child only when something
declared it.

FAIL CLOSED. `mode="enforced"` requires a backend and raises `SandboxUnavailable` when there
is none. There is no quiet downgrade and no unsandboxed retry, because a boundary that
disappears under load is not a boundary. The escape hatch is explicit, named, and reported:
`mode="trusted-host"` runs with no OS boundary and says so in `confinement`, so a caller can
never mistake one for the other.

BACKENDS. macOS uses `sandbox-exec` (Seatbelt) with an inline profile -- no profile file, so
there is no profile path for a worker to race. Linux would use bubblewrap; it is NOT
implemented here, and that is deliberate: an untested confinement path that reports success is
worse than an honest refusal, so every non-Darwin platform reports no backend and `enforced`
refuses. Record that as an unsupported combination rather than reading it as "sandboxing is on".

WHAT THIS DOES NOT DO. It bounds what an executed stage can reach. It does not make the files
it writes authoritative, and it is not a claim about a vendor CLI's own internal sandbox.

WHY THE MODEL DISPATCH ITSELF IS NOT CONFINED. Measured on macOS, 2026-09-06, under a one-off
user authorisation to invoke a real CLI: `sandbox-exec` blocks Keychain access. The same
`security find-generic-password` lookup succeeds unconfined and fails confined, and Claude Code
stores subscription credentials in the Keychain rather than in a file under `~/.claude`. A
confined `claude -p` therefore reports "Not logged in", and no profile rule fixes it --
`mach-lookup`, `authorization-right-obtain` and write access to `~/Library/Keychains` were all
granted and it still failed, because Keychain access is gated by entitlements rather than by
profile rules.

So dispatch confinement is not offered here. It would work for API-KEY authentication, where
the credential is an environment variable this module can pass deliberately -- but that is a
different billing mode, and a boundary that silently depends on how the user happens to be
logged in is worse than an absent one. Verification is unaffected: a verify command
authenticates to nothing, which is exactly why it is the stage this module does confine.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

#: Environment variables a confined stage may inherit. An ALLOWLIST, so a credential that
#: nobody declared cannot arrive by accident -- which is the usual way they arrive.
DEFAULT_ENV_ALLOWLIST = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "USER", "SHELL")

#: Device files a normal process needs to run at all. Narrower than "all of /dev".
_DEV_WRITES = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/dtracehelper", "/dev/urandom",
               "/dev/random", "/dev/zero", "/dev/tty", "/dev/fd")

#: Distinguishes "caller did not specify a backend" from "caller says there is none". `or`
#: cannot express the second, which made the fail-closed path unreachable by its own callers.
_UNSET = object()

_PROC_RUNNER = None


def _pr():
    """Lazy-load `bin/proc_runner.py` -- the repo's ONE process-lifecycle helper.

    By file path and cached, for the same reason the other sibling loaders are: `bin/` is not a
    package and is not reliably importable when this module is loaded by path.
    """
    global _PROC_RUNNER
    if _PROC_RUNNER is None:
        path = Path(__file__).resolve().parent / "proc_runner.py"
        spec = importlib.util.spec_from_file_location("proc_runner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _PROC_RUNNER = module
    return _PROC_RUNNER


DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_OUTPUT_LIMIT = 8 * 1024 * 1024


class SandboxUnavailable(RuntimeError):
    """Raised when `enforced` confinement was required and no backend can provide it."""


def detect_backend(platform=None):
    """The confinement backend for this host, or None.

    None is a real answer and callers must handle it: on a host with no backend, `enforced`
    refuses rather than running the stage unconfined.
    """
    platform = platform or sys.platform
    if platform == "darwin" and os.path.exists("/usr/bin/sandbox-exec"):
        return "sandbox-exec"
    # Linux (bubblewrap) is intentionally not implemented -- see the module docstring.
    return None


def _sbpl_string(path):
    """One SBPL string literal. Backslash and quote are the only escapes SBPL needs."""
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _real(path):
    return os.path.realpath(str(path))


class ExecPolicy:
    """What one executed stage may reach.

    `workspace`   -- the one tree it may write (its own working directory).
    `scratch`     -- a run-scoped writable temp dir, exported as TMPDIR. NOT the host's whole
                     temp tree: allowing that re-opens the boundary, because everything else
                     using mkdtemp lands there too, including the run's own control state.
    `read_only`   -- extra trees it may read. Reads are broadly allowed by default (an
                     interpreter needs its stdlib); this documents the ones that matter.
    `deny_read`   -- trees whose CONTENTS must not be readable, for confidentiality: withheld
                     tests, reference answers, credentials, unrelated project data.
    `allow_network` -- default False. A verification run that needs the network is declaring
                     something, and should have to declare it.
    `env`         -- extra environment beyond `DEFAULT_ENV_ALLOWLIST`, by explicit name.
    """

    def __init__(self, workspace, scratch=None, read_only=(), deny_read=(),
                 allow_network=False, env=None, env_allowlist=DEFAULT_ENV_ALLOWLIST,
                 name="stage"):
        self.workspace = _real(workspace)
        self.scratch = _real(scratch) if scratch else None
        self.read_only = tuple(_real(p) for p in read_only)
        self.deny_read = tuple(_real(p) for p in deny_read)
        self.allow_network = bool(allow_network)
        self.env = dict(env or {})
        self.env_allowlist = tuple(env_allowlist)
        self.name = name

    # -- description -------------------------------------------------------------------

    def describe(self):
        """What this policy actually enforces, for logs and honest reporting."""
        return {
            "name": self.name,
            "workspace": self.workspace,
            "scratch": self.scratch,
            "read_only": list(self.read_only),
            "deny_read": list(self.deny_read),
            "network": "allowed" if self.allow_network else "denied",
            "env_allowlist": list(self.env_allowlist) + sorted(self.env),
        }

    def is_at_most(self, other):
        """True when this policy grants no more than `other`.

        The step-05 rule in one predicate: verification must not gain broader write, network,
        or credential access than the worker whose files it runs. It MAY hold read-only inputs
        the worker cannot see, so `read_only`/`deny_read` are deliberately not compared.
        """
        if self.allow_network and not other.allow_network:
            return False
        if not _within_any(self.workspace, (other.workspace,) + ((other.scratch,) if other.scratch else ())):
            return False
        if self.scratch and not _within_any(
            self.scratch, (other.workspace,) + ((other.scratch,) if other.scratch else ())
        ):
            return False
        extra_env = (set(self.env_allowlist) | set(self.env)) - (
            set(other.env_allowlist) | set(other.env)
        )
        return not extra_env

    # -- backend rendering -------------------------------------------------------------

    def sbpl(self):
        """The Seatbelt profile for this policy.

        Rule order is load-bearing: SBPL takes the LAST matching rule, so every `deny` sits
        after the `allow` it narrows. `file-read*` is allowed broadly because an interpreter
        needs its own installation; the `deny_read` subpaths then carve out what must stay
        unreadable.
        """
        writable = [self.workspace] + ([self.scratch] if self.scratch else [])
        lines = [
            "(version 1)",
            "(deny default)",
            "(allow process-exec* process-fork signal)",
            "(allow sysctl-read mach-lookup ipc-posix-shm)",
            "(allow file-read-metadata)",
            "(allow file-read*)",
        ]
        for path in self.deny_read:
            lines.append(f"(deny file-read* (subpath {_sbpl_string(path)}))")
        write_targets = " ".join(f"(subpath {_sbpl_string(p)})" for p in writable)
        dev_targets = " ".join(f"(literal {_sbpl_string(d)})" for d in _DEV_WRITES)
        lines.append(f"(allow file-write* {write_targets} {dev_targets})")
        lines.append("(allow network*)" if self.allow_network else "(deny network*)")
        return "\n".join(lines)

    def environment(self):
        """The environment a confined stage receives: the allowlist, plus declared extras."""
        env = {k: os.environ[k] for k in self.env_allowlist if k in os.environ}
        if self.scratch:
            env["TMPDIR"] = self.scratch
        env.update(self.env)
        return env


def _within_any(path, roots):
    path = _real(path)
    for root in roots:
        if not root:
            continue
        root = _real(root)
        if path == root or path.startswith(root.rstrip("/") + "/"):
            return True
    return False


def wrap_argv(argv, policy, backend=_UNSET):
    """`argv` rewritten to run under `policy`, or ValueError for an unknown backend."""
    backend = detect_backend() if backend is _UNSET else backend
    if backend == "sandbox-exec":
        return ["/usr/bin/sandbox-exec", "-p", policy.sbpl(), *argv]
    raise ValueError(f"no confinement rendering for backend {backend!r}")


def shell_argv(command):
    """A repo-authored shell verify line as argv, so the SHELL runs inside the boundary.

    Verify commands are shell lines by contract and this does not change that. It changes
    which process interprets them.
    """
    return ["/bin/sh", "-c", command]


def run_confined(argv, policy, cwd=None, mode="enforced", timeout=DEFAULT_TIMEOUT_SECONDS,
                 output_limit=DEFAULT_OUTPUT_LIMIT, backend=_UNSET):
    """Run `argv` under `policy` -> `{rc, output, confinement, backend, timed_out}`.

    `mode="enforced"` requires a backend and raises `SandboxUnavailable` without one -- no
    silent downgrade, no unsandboxed retry. `mode="trusted-host"` is the named opt-out: it
    runs with no OS boundary and reports `confinement="trusted-host"`, so nothing downstream
    can read it as enforcement.
    """
    if mode not in ("enforced", "trusted-host"):
        raise ValueError(f"unknown execution mode {mode!r}")

    backend = detect_backend() if backend is _UNSET else backend
    if mode == "enforced":
        if backend is None:
            raise SandboxUnavailable(
                f"{policy.name}: no OS confinement backend on this host "
                f"(sys.platform={sys.platform!r}); refusing to execute unconfined. Re-run with "
                f"the explicit trusted-host mode if this host is trusted -- that runs with NO "
                f"filesystem, network, or credential boundary and is reported as such."
            )
        run_argv = wrap_argv(argv, policy, backend=backend)
        confinement = backend
    else:
        run_argv = list(argv)
        confinement = "trusted-host"

    # Lifetime, output, and working directory are `bin/proc_runner.py`'s job; confinement is
    # this module's. Keeping them apart is what lets a call site bound a process it does not
    # sandbox (a git read, a summary dispatch) and sandbox a process it does bound.
    result = _pr().run(
        run_argv,
        cwd=cwd if cwd is not None else policy.workspace,
        # Bound to the workspace: a verify command must not be run against whatever tree the
        # user happened to be standing in when they started the driver.
        within=policy.workspace,
        env=policy.environment(),
        timeout=timeout,
        output_limit=output_limit,
        name=policy.name,
    )
    output = result["output"]
    if result["detail"] and not result["terminal"]:
        output = f"{output}\n{result['detail']}" if output else result["detail"]
    return dict(
        result,
        output=output,
        confinement=confinement,
        backend=backend,
        policy=policy.describe(),
    )


def run_verify(command, policy, cwd=None, mode="enforced", **kwargs):
    """One repo-authored shell verify line, inside the boundary -> the same result dict."""
    return run_confined(shell_argv(command), policy, cwd=cwd, mode=mode, **kwargs)


#: Paths whose CONTENTS a verify command has no business reading. Credential stores and the
#: harness homes this repo itself reads elsewhere: a verify line is repo-authored, but it runs
#: code the model just wrote, and "the test suite" is a fine place to hide an exfiltration.
#: Only the ones that exist are declared, so the profile never names a path that is not there.
_CONFIDENTIAL_HOME_PATHS = (
    ".ssh", ".aws", ".gnupg", ".netrc", ".config/gh", ".docker",
    ".claude", ".codex", ".copilot",
)


def default_deny_read(home=None):
    """The confidential paths present on this host, as absolute paths."""
    home = Path(home) if home is not None else Path.home()
    return tuple(str(home / rel) for rel in _CONFIDENTIAL_HOME_PATHS if (home / rel).exists())


def verify_runner(workspace, mode="enforced", deny_read=None, timeout=DEFAULT_TIMEOUT_SECONDS,
                  on_result=None):
    """A `runner(cmd) -> (rc, output)` that runs one verify line inside the boundary.

    The shape the drivers already inject, so wiring it in is a one-line change at each call
    site rather than a new execution path. Each call gets a fresh run-scoped scratch directory,
    exported as TMPDIR and discarded afterwards, so a verify command's temp files are writable
    without the whole host temp tree being writable.
    """
    deny = default_deny_read() if deny_read is None else tuple(deny_read)

    def runner(cmd):
        with tempfile.TemporaryDirectory(prefix="polytropos-verify-") as scratch:
            policy = ExecPolicy(workspace, scratch=scratch, deny_read=deny, name="verify")
            result = run_verify(cmd, policy, mode=mode, timeout=timeout)
            if on_result is not None:
                on_result(result)
            return result["rc"], result["output"]

    return runner


def _cli(argv=None):
    """`exec_policy.py describe|check` -- what this host can actually enforce."""
    argv = list(sys.argv[1:] if argv is None else argv)
    verb = argv[0] if argv else "check"
    backend = detect_backend()
    if verb == "check":
        if backend is None:
            print(f"no OS confinement backend on {sys.platform} — `enforced` mode will refuse; "
                  f"only the explicit trusted-host mode can run here")
            return 3
        print(f"confinement backend: {backend} ({sys.platform})")
        return 0
    if verb == "describe":
        workspace = argv[1] if len(argv) > 1 else os.getcwd()
        policy = ExecPolicy(workspace, name="describe")
        print(f"backend: {backend}")
        print(f"profile:\n{policy.sbpl()}")
        print(f"env: {sorted(policy.environment())}")
        return 0
    print(f"usage: exec_policy.py [check|describe [workspace]]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
