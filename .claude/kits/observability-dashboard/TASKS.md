# TASKS — observability-dashboard

Repo root: the polytropos checkout you were dispatched in (`git rev-parse --show-toplevel`).
Run every verify command from there. Read `PLAN.md` (D1–D16, the out-of-scope fence,
R1–R12) and `GUARDRAILS.md` (same directory) first — they are binding for every task.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch notes for the orchestrator: pass each task's `model` as the Agent tool's `model`
parameter when dispatching `observability-dashboard-implementer`. **Warm-cluster hints:**
T4 → T5 → T6 → T7 are strictly serial (same primary files `bin/dashboard.py` +
`tests/test_dashboard.py`, same `sonnet` pin) — one continued implementer may serve the
chain. T2 → T3 share the same files but change pin (opus → sonnet), so T3 is a fresh
dispatch. T10 → T11 are both opus and serial. Nothing in this kit is marked `independent:`
— every task edits `bin/dashboard.py`, a generated surface, or a snapshot test, and
parallel edits to those collide. The declared roles (`red-team` per task after the
verifier, `security-auditor` per phase beside the reviewer) are sequenced by the
interactive execute skill; a headless driver refuses or discloses them.

**T11 is gated (PLAN D12, amended 2026-09-27).** Before dispatching T11, run the gate command
in its brief — it is `ast`-only and executes nothing. On exit 3, set T11's `- status:` to
`blocked`, append ONE plain prose line to `NOTES.md` naming the gate and the date (no ledger
token at column one — nothing was dispatched, so no `outcome:` line), report the kit as
complete except T11, and stop. Re-run execute after `feat/rsi-evidence-foundation` merges to
`main`. When the gate passes, flip `- status:` to `pending` and dispatch T11 as one task
(opus); its red-team follows the verifier as for every task, and Phase 4's reviewer and
security-auditor run again at its end, since T11 changes what the page executes.

Standing rules for every task:

- Stdlib only; `unittest` only. Every test module isolates the data home with
  `setUpModule` + `mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": tmp})` (copy the
  idiom from `tests/test_copilot_execute.py`), builds synthetic namespaces in temp dirs,
  and passes `--out-dir`, `--projects-dir <empty temp dir>` and `--no-git` to every `build`.
  Zero `Path.home()` in anything you write. No task's verify block runs a real build.
- The full suite is always run as
  `POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v`.
- Never invoke the real `claude`/`codex`/`copilot`/`agent` CLI. The engine's only
  subprocesses are read-only git verbs through `bin/proc_runner.py`.
- Reuse owners by import through the sibling loader; never copy an owner's logic and never
  edit an owner. If an owner's signature, key or label differs from a brief, the owner is
  authoritative: adapt the dashboard's adapter layer, keep the brief's semantics, record the
  delta in `NOTES.md`, and continue; if the semantics cannot be kept, stop and report.
- Sanctioned structural vocabulary for this kit: `BUILD_SCHEMA_VERSION = 1`, the CSP string
  `default-src 'none'; style-src 'unsafe-inline'; img-src data:`, `RESIDUE_NAMESPACE_RE`
  (grammar `^tmp[a-z0-9_]{8}-[0-9a-f]{8}$`), the store name `dashboard`, the file names
  `index.html` / `build.json` / `config.json`, the namespace classes `mapped | unmapped |
  residue`, and fixture-local synthetic values. Prices, model ids, pricing dates and
  contract-version strings are never written into code, tests or docs — read them from
  the owning module at run time; fixtures use obviously synthetic values.
- When quoting ledger grammar in `NOTES.md` prose, backtick the tokens (`outcome:`,
  `agent:`, `reroute:`, `session:`, `reviewer:`, `defect:`) — unbackticked column-one grammar
  parses as data.
- Verify blocks use `python3 - <<'PY'` heredoc probes; never `producer | python3 -`
  (redirect the producer to a file first). Do not commit or push.

## Phase 1 — Store, enumeration and the page shell

### T1 — Register the `dashboard` store and carry its documentation consequences
- id: T1
- title: Register the `dashboard` store and carry its documentation consequences
- status: done
- model: sonnet
- depends: (none)

**Brief.** PLAN D6. The page needs a store of its own because every existing store is
written by exactly one engine. Files: `bin/runtime_data.py` (one tuple append, nothing
else), `.gitignore`, `docs/PRIVACY.md`, `docs/REFERENCE.md`, `SECURITY.md`, and the
generated `docs/RELEASE.md` block + `docs-site/deep-dives/*` via their generators.

1. In `bin/runtime_data.py` change only the `STORES` tuple: append `"dashboard"` as its
   LAST element. No other line of that file changes.
2. In `.gitignore`, directly after the `/training/` block, append exactly:

   ```
   # observability dashboard output (one offline HTML page over the personal stores: dollar
   # figures, task titles, repo paths, namespace digests — never committed; its default home
   # is the per-user data root, this entry covers a legacy in-tree store only)
   /dashboard/
   ```

   The leading slash is load-bearing (root-anchored — the `/memory/` precedent).
3. `docs/PRIVACY.md`: add a table row after the `training/` row:
   `| `dashboard/` | the built observability page (`index.html`) and its receipt (`build.json`): dollar figures, task titles, repo paths, namespace digests |`;
   extend the "Zero files under any of these have ever been committed" paragraph with the
   date you verified it for `dashboard/` (run `git log --all --diff-filter=A -- dashboard/`
   and state what it returned — it should return nothing, because the store did not exist
   before this kit); add `dashboard` to the `runtime_data.STORES` name list in the
   "Standing rules this creates" bullet and to the `rm -rf` line in the bump-and-prune
   runbook (step 5) beside the other store names. Change nothing else in that file.
4. `docs/REFERENCE.md`: the census row `| Runtime stores, all outside the tree | 9 |` becomes
   `10`; the paragraph opening `**Nine stores, all outside the tree.**` becomes
   `**Ten stores, all outside the tree.**` and its backticked list gains `dashboard` after
   `training`. Change nothing else.
5. `SECURITY.md`: the bullet opening `**Personal data stays local and gitignored.**` names
   "The memory, telemetry, journal, benchmark, and training stores" — add "dashboard" to
   that list. Change nothing else.
6. Run `python3 bin/release_gate.py build` (the private-store table in `docs/RELEASE.md`'s
   generated block is derived from `STORES` and the ignore rules) and then
   `python3 bin/docs_build.py build` (the deep-dive mirrors of `docs/PRIVACY.md`,
   `docs/REFERENCE.md`, `docs/RELEASE.md`). Never hand-edit anything under `docs-site/` or
   inside the marked block of `docs/RELEASE.md`.

Gotcha: `tests/test_privacy_layout.py` derives its list from `runtime_data.STORES`, so the
suite is red between step 1 and step 2 — do both before running anything. The generated
block of `docs/RELEASE.md` is also edited by Codex's `feat/rsi-evidence-foundation`; a
later merge conflict there is resolved by regenerating, never by hand (PLAN R2).

**Acceptance.** `runtime_data.STORES[-1] == "dashboard"` and the tuple is otherwise
unchanged; `git check-ignore dashboard/probe/x.json` reports the path ignored;
`python3 bin/runtime_data.py where` prints a `dashboard` row; the four prose docs carry the
exact additions above and nothing else changed in them (`git diff --stat` shows only the
files named in this brief plus generated mirrors); `python3 bin/release_gate.py check` and
`python3 bin/docs_build.py check` exit 0; full suite green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("rd", "bin/runtime_data.py")
rd = importlib.util.module_from_spec(spec); spec.loader.exec_module(rd)
assert rd.STORES[-1] == "dashboard", rd.STORES
assert rd.STORES[:-1] == ("memory", "telemetry", "journal", "benchruns", "prefs", "trends",
                          "attempts", "evals", "training"), rd.STORES
print("T1 STORES OK")
PY
git check-ignore -q dashboard/probe/x.json
grep -qx '/dashboard/' .gitignore
grep -q '`dashboard/`' docs/PRIVACY.md
grep -q 'Ten stores, all outside the tree' docs/REFERENCE.md
grep -q '| Runtime stores, all outside the tree | 10 |' docs/REFERENCE.md
grep -q 'dashboard' SECURITY.md
python3 bin/release_gate.py check
python3 bin/docs_build.py check
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_privacy_layout.py' -v
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

### T2 — `bin/dashboard.py` core: namespace enumeration, checkout discovery, private writer, page shell
- id: T2
- title: `bin/dashboard.py` core: namespace enumeration, checkout discovery, private writer, page shell
- status: done
- model: opus
- depends: T1

**Brief.** PLAN D1, D2, D4, D5, D6, D8, D9, D15. Files: NEW `bin/dashboard.py`, NEW
`tests/test_dashboard.py`. This is the keystone: everything later tasks render hangs off
the model, the writer and the bounds built here, and a wrong micro-decision here is a
privacy defect, not a bug.

1. **Module preamble.** A docstring stating what the engine is (a read-only consumer and
   presentation layer over the stores the owning engines write), what it refuses (never a
   second analysis authority: it prices, sums, ranks and classifies nothing; never reaches
   the network; writes only its own store; never opens a residue namespace beyond one
   listing; never deletes), and the residue heuristic with its limit. Constants, each with a
   one-line comment saying why the number: `BUILD_SCHEMA_VERSION = 1`, `PAGE_NAME =
   "index.html"`, `RECEIPT_NAME = "build.json"`, `CONFIG_NAME = "config.json"`, `CSP =
   "default-src 'none'; style-src 'unsafe-inline'; img-src data:"`, `RESIDUE_NAMESPACE_RE =
   re.compile(r"^tmp[a-z0-9_]{8}-[0-9a-f]{8}$")`, `MAX_NAMESPACES_LISTED = 5000`,
   `MAX_NAMESPACES_READ = 32`, `MAX_LEDGER_BYTES = 8 * 1024 * 1024`, `MAX_KITS_PER_DIR =
   100`, `MAX_EVAL_RUNS_RENDERED = 10`, `MAX_JOURNAL_DAYS = 60`,
   `MAX_TELEMETRY_ENVELOPES_PER_SOURCE = 120`, `GIT_TIMEOUT_SECONDS = 20`, `PLUGIN_ROOT =
   Path(__file__).resolve().parents[1]`. Caps are passed around as a dict so tests can lower
   them. Sibling loader `_mod(name)` with a cache (the `bin/telemetry_snapshot.py` shape).
   The strings `Path.home`, `subprocess`, `urlopen` and `http.client` must not appear
   anywhere in this file, comments included (the verify greps for them; phrase prose as
   "spawns nothing but the git verbs of D4 through proc_runner").
2. **Primary checkout and candidates** — `discover_checkouts(cwd, flags=(), config=(),
   git=True, runner=None) -> (checkouts, notes)`. The PRIMARY checkout is the git toplevel
   of `cwd` when `git` is on and `runner(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
   timeout=GIT_TIMEOUT_SECONDS, name="git rev-parse")` returns `outcome == "ok"`; otherwise
   `cwd` itself, with a note. `PLUGIN_ROOT` is NEVER a candidate on its own — when the
   engine runs from the plugin cache, that directory is not a checkout and must not own a
   store (PLAN D6). Candidates in order: primary, each `--checkout` flag, each config entry,
   then the worktrees of every candidate so far from `runner(["git", "worktree", "list",
   "--porcelain"], cwd=<candidate>, …)` (`worktree <path>` lines). `runner` defaults to
   `proc_runner.run`; a non-`ok` outcome or a non-directory candidate is a note, never an
   error; dedupe by `os.path.realpath`; `git=False` skips both verbs.
3. **Namespace roots and classes** — `namespace_roots(checkout) -> [(root, kind)]` returns
   `(checkout, "checkout")` and `(checkout / "tasks" / "kits", "codex-kits")` (because
   `attempt_ledger.kit_repo_root` maps a `tasks/kits/<slug>` kit to `tasks/kits`).
   `classify_namespaces(data_home, checkouts, caps) -> (classes, notes)` scans the data home
   with `os.scandir`, bounded by `MAX_NAMESPACES_LISTED` (a note when exceeded); an entry
   that is not a directory without following links (`entry.is_dir(follow_symlinks=False)`)
   is skipped with a note; an absent data home, or one that is a file, is a note and empty
   classes. Expected namespaces are `runtime_data.project_namespace(root)` for every root of
   every checkout → class `mapped` with its checkout and kind; otherwise the residue test
   (name matches `RESIDUE_NAMESPACE_RE` AND one `os.listdir` of the namespace is a subset of
   `{"attempts"}`) → `residue`, counted with a 3-name sample and never opened again;
   otherwise `unmapped`. Result shape: `{"mapped": [{"namespace", "checkout", "kind",
   "stores": [names present]}], "unmapped": [{"namespace", "stores"}], "residue":
   {"count", "sample"}}`. For each mapped checkout also note any `runtime_data.resolve_store
   (name, checkout)` whose `origin == "legacy-in-tree"` as "legacy in-tree store <name> at
   ~/… — not scanned by the dashboard".
4. **Scrubbing** — `scrub(text, home)` replaces the `home` prefix (and its realpath, when
   different) with `~` in a string; applied by the render layer to every path. `home` is
   resolved once in `main` via `os.path.expanduser("~")` and threaded through as a
   parameter; pure functions never resolve it themselves.
5. **Model, page shell, receipt** — `build_model(data_home, checkouts, opts, caps) -> dict`
   returns the JSON-serializable model: `schema_version`, `built_at` (UTC ISO seconds),
   `primary_checkout`, `checkouts`, `data_home`, `classes`, `panels` (a list; later tasks
   append), `caps` (each cap, its value, and whether it was hit), `notes`. A `PANELS`
   registry (list of `(id, title, builder)`) is consumed in order. The panel ids are
   PINNED for the whole kit, in this page order — later tasks register their builders
   under exactly these ids and the verify blocks assert them: `namespaces` (T2),
   `attempts` (T4), `scorecard` (T5), `kits` (T5), `telemetry` (T6), `journal` (T6),
   `evals` (T7), `training` (T7), `rsi` (T10), `bounds` (T2, always last). T2 registers
   `namespaces` (table: namespace, class, checkout/kind or "—", stores present) and
   `bounds` (every cap with hit/not hit and the notes). `render_page(model, home) -> str`
   emits `<!doctype html>`, `<html lang="en">`, `<head>` with `<meta charset="utf-8">`, THEN
   the CSP meta exactly `<meta http-equiv="Content-Security-Policy" content="default-src
   'none'; style-src 'unsafe-inline'; img-src data:">`, then the viewport meta, `<title>`,
   one `<style>` block (T2 ships the minimal stylesheet: `:root` custom properties for
   `--bg`, `--fg`, `--muted`, `--accent`, `--line`; the same properties redefined under
   `@media (prefers-color-scheme: dark)`; `body { background: var(--bg); color: var(--fg);
   font-family: <system stack>; }`; a `.wrap` column with `max-width` and `padding: 0 16px`;
   `.table-wrap { overflow-x: auto; }`), and a `<body>` with a header (page title, built-at
   on a line carrying `data-built-at`, primary checkout scrubbed, data home scrubbed), an
   anchor nav over the registered panels, and one `<section id="<panel id>">` per panel.
   Every string that reaches the page goes through `html.escape(s, quote=True)`. No
   `<script>`, no `src=`, no `href` to anything but `#<id>`.
6. **Writer and config** — `write_page(out_dir, html, receipt) -> {"page": path, "receipt":
   path}`: `runtime_data.ensure_private(out_dir)` then
   `safe_paths.confined_replace(out_dir, PAGE_NAME, html.encode("utf-8"), what="dashboard
   page", mode=0o600)` and the same for `RECEIPT_NAME` with `json.dumps(receipt, indent=2,
   sort_keys=True) + "\n"`. `default_out_dir(primary_checkout)` returns
   `runtime_data.store_path("dashboard", primary_checkout)` and is called INSIDE `main` at
   call time, never at import (a parse-time default captures the wrong environment — the
   `cost_report` `PROJECTS_DIR` lesson). `read_config(out_dir) -> (checkouts, notes)` reads
   `CONFIG_NAME` through `safe_paths.confined_read_bytes(..., missing_ok=True)`; the file
   must be a JSON object whose `checkouts` is a list of strings; anything else, a path
   containing `..`, or a path that is not a directory is a note and is skipped.
7. **CLI** — `main(argv=None)` with subcommands `build`, `where`, `demo`; exits through
   `raise SystemExit(main())`. `build` flags: `--data-home` (default: `runtime_data.
   user_data_home()`, which honours `POLYTROPOS_DATA_HOME`), `--out-dir` (default:
   `default_out_dir(primary)`), `--checkout` (repeatable), `--projects-dir` (default: the
   scorecard's own default, resolved in `main`; consumed by T5), `--no-transcripts`
   (consumed by T5), `--no-git`, `--json`. `build` prints a one-screen summary — the page
   path (scrubbed), namespace counts by class, then one line per panel (T4+ fill these),
   caps hit, notes count — or the receipt as JSON with `--json`; exit 0 when the page was
   written (notes are not failures), 2 when the out dir cannot be written
   (`safe_paths.SafePathError` / `OSError`, message on stderr). `where` prints the resolved
   out dir (scrubbed) and its origin (`--json` for the dict). `demo` builds
   `synthetic_world` (below) inside a `tempfile.TemporaryDirectory`, runs the same build
   path with `git=False` and an empty temp projects dir, prints the summary and the page's
   temp path, removes everything, exits 0.
8. **`synthetic_world(root) -> dict`** — the ONE fixture builder shared by `demo` and the
   tests (later tasks extend it). Creates `root/data-home` and `root/checkout` (a directory
   with `.claude/kits/demo-kit/TASKS.md` + `NOTES.md` in the shape
   `tests/test_telemetry_snapshot.py`'s `_write_kit` uses, and an empty `tasks/kits/`),
   computes the mapped namespace with `runtime_data.project_namespace`, writes a ledger via
   `attempt_ledger.AttemptLedger(<ns>/attempts, "demo-kit")` using `record_started`,
   `record_finished`, `record_verify`, `record_projected` plus one started-but-unfinished
   attempt (the `attempt_ledger._demo` idiom), creates 30 residue namespaces
   (`tmp<8 chars>-<8 hex>` each holding only `attempts/kit/events.jsonl` with one valid
   event line) and one `unmapped-cafef00d` namespace with a ledger. Returns the paths.
9. **Tests** (`tests/test_dashboard.py`, the importlib `_load` idiom and the data-home
   `setUpModule` patch): classification counts over `synthetic_world` (1 mapped, 1 unmapped,
   30 residue) and residue never opened (make one residue `events.jsonl` unreadable with
   `chmod 0` and assert no note mentions it — restore the mode in `addCleanup`); a symlink
   entry skipped with a note; absent data home → note, empty classes; `discover_checkouts`
   with an injected `runner` returning porcelain text, and with one returning `{"outcome":
   "missing-executable"}` → note and primary = cwd; `read_config` with a `..` path and a
   non-list → notes; `write_page` leaves `0700` dir / `0600` files (`stat.S_IMODE`); an
   `--out-dir` whose leaf `index.html` is a symlink is refused (exit 2); the page's first
   `<meta http-equiv` is the exact CSP; no `<script`, `src=`, `href="http`, `href="//`,
   `@import`, `url(` in the page; the fixture's fake home path (`HOME` in the patched env)
   never appears in the page while `~/` does; `where` prints a path under the patched data
   home; `demo` exits 0 and leaves nothing behind (patch `tempfile.tempdir` to a temp dir
   and assert it is empty afterwards); two builds of the same world are byte-identical after
   dropping the line containing `data-built-at`; source introspection: none of `Path.home`,
   `subprocess`, `urlopen`, `http.client` appears in `bin/dashboard.py`.

**Acceptance.** All nine items present with the pinned names; every degraded path is a
note, never an exception; the residue count over a 1,500-residue fixture (build one inside
the test with the caps at defaults) is exact and the build completes in single-digit
seconds; `demo` is self-contained; the page shell satisfies D9's head order; tests green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
grep -cE "Path\.home|subprocess|urlopen|http\.client" bin/dashboard.py | grep -qx 0
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 bin/dashboard.py demo > "$(mktemp -d)/demo.txt"
python3 - <<'PY'
import importlib.util, json, os, re, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("dashboard", "bin/dashboard.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    world = db.synthetic_world(root)
    out = root / "out"; proj = root / "proj"; proj.mkdir()
    os.environ["POLYTROPOS_DATA_HOME"] = str(world["data_home"])
    rc = db.main(["build", "--data-home", str(world["data_home"]), "--out-dir", str(out),
                  "--checkout", str(world["checkout"]), "--projects-dir", str(proj),
                  "--no-git", "--json"])
    assert rc == 0, rc
    page = (out / "index.html").read_text()
    assert page.index('content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:"') < page.index("<body"), "CSP missing or late"
    for bad in ("<script", "src=", 'href="http', 'href="//', "@import", "url("):
        assert bad not in page, bad
    assert oct(os.stat(out / "index.html").st_mode & 0o777) == "0o600"
    receipt = json.loads((out / "build.json").read_text())
    assert receipt["schema_version"] == 1 and receipt["classes"]["residue"]["count"] == 30, receipt["classes"]
print("T2 probe OK")
PY
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

### T3 — Rendering toolkit: tables, SVG charts with table twins, panel chrome, light/dark, phone width
- id: T3
- title: Rendering toolkit: tables, SVG charts with table twins, panel chrome, light/dark, phone width
- status: done
- model: sonnet
- depends: T2

**Brief.** PLAN D7(c–f), D9. Files: `bin/dashboard.py`, `tests/test_dashboard.py` (extend).
The toolkit every panel builds with, so that honesty rendering is written once.

1. `esc(value)` → `html.escape(str(value), quote=True)`; `None` → the literal text
   `unknown` wrapped in `<span class="unknown">`.
2. `fmt_count(v)` (ints; `None` → `unknown`), `fmt_usd(v, basis_label)` (`None` → `unknown`;
   a number → `$` with two decimals followed by the basis label in a `<span class="label">`
   — the label is REQUIRED, never optional, so a dollar can never appear without its
   basis), `fmt_credits(v)`, `fmt_seconds(v)`, `fmt_date(v)`, `age_days(observed, today)`
   (`None` when either is missing; parses `YYYY-MM-DD` and ISO timestamps).
3. `html_table(headers, rows, caption=None, details=False)`: rows are lists of cell values
   passed through `esc`; wrapped in `<div class="table-wrap">`; `details=True` wraps it in
   `<details><summary>caption (N rows)</summary>…</details>` for long tables.
4. `svg_bars(rows, title, desc, label_key, value_key)` and `svg_sparkline(points, title,
   desc)`: return one `<figure>` holding an inline `<svg viewBox="0 0 W H" role="img"
   aria-labelledby="<title id> <desc id>">` with `<title>` and `<desc>` as the first two
   children, drawn with `<rect>`/`<polyline>`/`<text>` from the rows, and — in the SAME
   figure, as its `<figcaption>` — an `html_table` of the same rows. A `None` value is
   drawn as no bar/point and shows `unknown` in the table. `svg { width: 100%; height:
   auto; }` in the stylesheet keeps charts phone-width.
5. `panel(pid, title, source, observed, age, notes, body_html, refresh_hint=None)`: the
   `<section id=…>` chrome: `<h2>`, a `<p class="meta">` line `source: <source> ·
   observed: <date or "never captured"> · age: <N day(s) or "n/a">`, the optional refresh
   hint, a `<ul class="notes">` (rendered even when empty as "notes: none"), then the body.
   `nav(panels)` renders `<nav>` anchors for every registered panel id.
6. Stylesheet completion: `.label` (monospace, muted), `.unknown` (italic, muted — never
   hidden), `.notes`, `.meta`, `figure`, `figcaption`, `details`, `table` borders using
   `--line`, `th`/`td` padding, and the dark override for every colour property.
7. Tests: every `<svg` in a fixture-built page has `<title>` and `<desc>` as its first
   children and is followed within its `<figure>` by a `<table`; a cell containing
   `<script>&"` and an emoji renders escaped; `fmt_usd(None, "est.")` → contains `unknown`
   and no `$`; `fmt_usd(1.5, "est.")` → contains both `$1.50` and `est.`; `age_days`
   cases; `prefers-color-scheme: dark` present exactly once; every `<nav>` anchor target
   exists as an `id` in the page; no `url(`, `@import`, `<link`.

**Acceptance.** Every number on the page can be traced to a table cell; no chart is the
only carrier of a value; `unknown` is rendered text, never a hidden cell; light and dark
both define `body` background; tests green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
python3 - <<'PY'
import importlib.util, re
spec = importlib.util.spec_from_file_location("dashboard", "bin/dashboard.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
fig = db.svg_bars([{"label": "a", "value": 2}, {"label": "b", "value": None}], "T", "D", "label", "value")
assert fig.index("<title") < fig.index("<rect") and "<desc" in fig and "<table" in fig, fig[:300]
assert "unknown" in fig
u = db.fmt_usd(None, "est.")
assert "unknown" in u and "$" not in u, u
assert "$1.50" in db.fmt_usd(1.5, "est.") and "est." in db.fmt_usd(1.5, "est.")
print("T3 probe OK")
PY
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

## Phase 2 — Panels over the sources that exist today

### T4 — Attempts panel: the ledger and its history projection, through the owners
- id: T4
- title: Attempts panel: the ledger and its history projection, through the owners
- status: done
- model: sonnet
- depends: T3

**Brief.** PLAN D2, D3 (row 1), D7(a–c). Files: `bin/dashboard.py`, `tests/test_dashboard.py`.
Owners: `bin/attempt_history.py` (`join_kits`, `summarize`, `COST_BASES`,
`DURATION_BASES`) and `bin/attempt_ledger.py` (`AttemptLedger.events`, `.open_attempts`,
`.corrupt`). Read both before writing a line.

1. **History projection per mapped checkout.** For each mapped namespace of kind
   `checkout` whose checkout has a `.claude/kits` dir, and each of kind `codex-kits` whose
   root `tasks/kits` exists: `records, notes, coverage = attempt_history.join_kits(kits_dir,
   store=<data_home>/<namespace>/attempts)` — the store is the namespace's own `attempts`
   root, so a mapped checkout's ledger is read where it actually lives (`kit_contract.
   open_ledger` derives the ledger namespace from the kit dir name). Then `card =
   attempt_history.summarize(records, notes, coverage)`. Wrap each call in `try/except
   Exception as exc` → a note `f"attempt history unavailable for {label}: {type(exc).
   __name__}"` (type only, never the message — a message can carry a path).
2. **Render the card, verbatim fields only:** the `records` / `by_source` line; `coverage`
   (kits, with ledger, with notes, with role-use); `by_harness` × tier table with each
   tier's `results` dict rendered as `result: n` pairs; the `unknown` table (every key,
   including the four provenance refs — an unknown count is a count, render it); the
   `failure_classes` table; **cost by basis**: one row per basis in
   `attempt_history.COST_BASES` (read the tuple, do not retype it) with `n`, `usd`, `credits`
   through `fmt_usd(value, basis)` / `fmt_credits` — `None` renders `unknown` — and the
   owner's `card["cost"]["note"]` printed verbatim beneath; **duration by basis** the same
   way over `DURATION_BASES`; `latest` as a `details` table (kit, task, result, run); the
   number of `lineage` entries; the card's `notes` list. A bar chart of records per
   `harness/tier` (counts only) with its table twin. There is NO total row anywhere, and
   `bin/dashboard.py` contains no `sum(` call at all — count with `len()` and loops, so
   the mechanical grep in the verify block is the fence (PLAN R4).
3. **Ledger facts per namespace** (owner: `AttemptLedger`), for mapped and unmapped
   namespaces up to `MAX_NAMESPACES_READ` (mapped first, then unmapped by name; a note
   when the cap cuts): for each `attempts/<ns>` subdir, `os.stat` the `events.jsonl`; if
   larger than `MAX_LEDGER_BYTES`, skip with a note naming the namespace and its size;
   otherwise `ledger = attempt_ledger.AttemptLedger(<attempts root>, ns)`, `events =
   ledger.events()`, then a row: namespace, ledger name, events, corrupt lines
   (`ledger.corrupt`), kind histogram (`kind: n` pairs), open attempts
   (`len(ledger.open_attempts())`), first and last `ts`, claim files present (`len(os.
   listdir(claims dir))` when it exists). A `safe_paths.SafePathError`, `LedgerError` or
   `OSError` is a note for that row. The ledger's `report`, `tail`, `prompt_sha`,
   `verify_sha` and `note` fields are never rendered.
4. **Residue line:** `"<count> residue namespaces (heuristic: tempfile-shaped name holding
   only an attempts store) — counted, not opened, excluded from every figure above"`.
5. `synthetic_world` extension: a second kit `notes-kit` with a `NOTES.md` carrying two
   `outcome:` lines (one `pass`, one `blocked`) so `notes`-source records exist; a ledger
   record whose finished event carries `cost` with basis `estimated` and one with no cost;
   an unmapped namespace ledger with one corrupt line and one over-size ledger (write
   `MAX_LEDGER_BYTES + 1` bytes of newline-terminated valid events? no — write a single
   file of that size once, in the test only, not in `demo`).
6. Tests: a record with no cost renders `unknown` in the cost table; every basis in
   `COST_BASES` has a row and the string `card["cost"]["note"]` is on the page; no cell
   contains a sum of two bases (assert the page has no row labelled `total`); `open
   attempts` = 1 for the demo kit; the corrupt line is counted; the over-size ledger is
   skipped with a note and never read (assert via the note and by making the file
   unreadable); residue namespaces contribute nothing to `records`; the `MAX_NAMESPACES_READ`
   cap lowered to 1 produces the cap note on the page and in the receipt.

**Acceptance.** The attempts panel renders from the owners' return values only; per-basis
rows and the owner's never-summed note are present; unknown is text; bounds and residue are
visible; tests green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
grep -cE "^\s*[^#]*\bsum\(" bin/dashboard.py | grep -qx 0
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
python3 - <<'PY'
import importlib.util, os, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("dashboard", "bin/dashboard.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
ah_spec = importlib.util.spec_from_file_location("attempt_history", "bin/attempt_history.py")
ah = importlib.util.module_from_spec(ah_spec); ah_spec.loader.exec_module(ah)
with tempfile.TemporaryDirectory() as td:
    root = Path(td); world = db.synthetic_world(root)
    out = root / "out"; proj = root / "proj"; proj.mkdir()
    os.environ["POLYTROPOS_DATA_HOME"] = str(world["data_home"])
    assert db.main(["build", "--data-home", str(world["data_home"]), "--out-dir", str(out),
                    "--checkout", str(world["checkout"]), "--projects-dir", str(proj), "--no-git"]) == 0
    page = (out / "index.html").read_text()
    for basis in ah.COST_BASES:
        assert basis in page, basis
    assert "bases are separate facts and are never summed together" in page
    assert "unknown" in page and "residue namespaces" in page
    section = page.split('id="attempts"', 1)[1].split("<section", 1)[0]
    assert "total" not in section.lower(), "a total row appeared in the attempts panel"
print("T4 probe OK")
PY
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

### T5 — Routing scorecard panel and kits in flight
- id: T5
- title: Routing scorecard panel and kits in flight
- status: done
- model: sonnet
- depends: T4

**Brief.** PLAN D2, D3 (rows 2 and 6), D7, D15. Files: `bin/dashboard.py`,
`tests/test_dashboard.py`. Owners: `bin/routing_scorecard.py` (`assemble_history_card`,
`scan_kits`, `build_roles_card`, `resolve_kits_dirs`, `_LABEL_RE`, `DEFAULT_PROJECTS_DIR`
via `sc`) and `bin/kit_contract.py` (`parse_tasks`, `validate_graph`, `graph_state`). Read
`run_history`, `run_roles` and `assemble_history_card`'s docstring first; the card's key
names are the owner's, and the brief below names them as observed on 2026-09-25 — the
owner wins on any difference.

1. **Tokens.** For every discovered checkout, the kits dirs that EXIST: `<checkout>/.claude/
   kits` labelled with the checkout's basename and `<checkout>/tasks/kits` labelled
   `<basename>-codex`; each label must match `routing_scorecard._LABEL_RE` (read the regex;
   sanitise with the same character class) and each token is `f"{label}={path}"`. No
   existing kits dir at all → the panel body is the sentence "no kits directories found in
   the discovered checkouts" and the rest is skipped.
2. **History card.** `card = routing_scorecard.assemble_history_card(tokens,
   projects_dir=str(projects_dir))` inside `try/except ValueError` → note. `projects_dir`
   is the `--projects-dir` flag when given, else the scorecard's own default; with
   `--no-transcripts` it is an empty temp directory created for the build and removed after,
   plus the note "transcript pricing skipped (--no-transcripts): dollars render as the
   owner's quality-only label". Render: a headline from the card's own fields; the
   `tiers` table with every key each tier dict carries, rendered as-is — on 2026-09-25 each
   tier dict carries `pinned`, `with_outcome`, `first_try`, `retry_pass`, `escalated_pass`,
   `blocked`, `reroutes`, `first_try_rate` and `escalation_rate`, so the rates are the
   OWNER's values and render verbatim; if a future card carries only counts, render counts
   and add the note "rates: see `python3 bin/routing_scorecard.py --history`" (the
   dashboard never divides);
   the `kits` table (kit, tasks, with_outcome, first_try_pass, retry_pass, escalated_pass,
   blocked, sessions count, cost → `fmt_usd(cost, "actual, priced sessions")` or
   `unknown`); the `dollars` block — when `None`, the owner's note from `card["notes"]` that
   explains why; otherwise `actual_usd`, `counterfactual_usd` beside
   `counterfactual_model["display"]`, `delta_usd`, `ratio`, `coverage`,
   `kits_with_sessions`/`kits_total`, `sessions_priced`/`sessions_found`, `pricing_cached`,
   each through the formatters, with the label "actual vs all-frontier counterfactual over
   priced sessions only — coverage <coverage>"; `roles` (the card's role-quality block:
   render each sub-table it carries, including the architect brief-defect kinds);
   `reroutes`; the card's `notes`. One bar chart: per tier, first-try / retry / escalated /
   blocked counts, with its table twin.
3. **Roles value card**, once per kits dir (the `run_roles` bare shape): `records, notes =
   routing_scorecard.scan_kits(kits_dir)`; `roles_card = routing_scorecard.build_roles_card
   (records, kits_dir, extra_notes=notes)`; render `aggregate` as a table whose cells are
   the owner's values verbatim (they may be strings such as "insufficient sample" or
   "n/a" — never coerced), `min_dispatches`, and `notes`. The per-kit sections are rendered
   as a `details` table (kit, roster label, roster size).
4. **Kits in flight**, per kits dir, up to `MAX_KITS_PER_DIR` kit dirs (sorted by name; a
   note when cut): read `TASKS.md` (skip a dir without one), `tasks = kit_contract.
   parse_tasks(text)` (a `ValueError` → note naming the kit), status counts over
   `kit_contract.STATUSES`, and `state = kit_contract.graph_state(tasks, kit_contract.
   validate_graph(tasks))["state"]` if that is the owner's shape (read `graph_state`; render
   whatever state word it returns). Table: checkout label, kit, pending/in-progress/done/
   blocked counts, graph state.
5. `synthetic_world` extension: the checkout's `.claude/kits` gains a kit whose `NOTES.md`
   carries three `outcome:` lines across two tiers so the tiers table has data, and a
   `tasks/kits/codex-demo` kit with one task and one `outcome:` line so the `-codex` label
   appears.
6. Tests: the tokens list contains both labels and every label matches `_LABEL_RE`; a
   missing kits dir is never passed (assemble would raise); with an empty projects dir the
   dollars block carries the owner's quality-only wording (assert on the substring the owner
   emits — read `telemetry_snapshot._DOLLARS_QUALITY_ONLY_NOTE` for the note's exact text);
   `--no-transcripts` adds the skip note; the roles aggregate table is present and contains
   the owner's below-floor wording when the fixture is small; the kits-in-flight table
   shows the demo kits with correct counts; the page contains no computed rate string
   unless the card carries one (assert the `rates: see` note appears iff no tier dict
   carries a rate key).

**Acceptance.** Every figure in the panel is a card field; dollars carry coverage and
counterfactual labels; the roles card cells are verbatim; kits in flight come from
`kit_contract`; tests green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
python3 - <<'PY'
import importlib.util, os, re, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("dashboard", "bin/dashboard.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
with tempfile.TemporaryDirectory() as td:
    root = Path(td); world = db.synthetic_world(root)
    out = root / "out"; proj = root / "proj"; proj.mkdir()
    os.environ["POLYTROPOS_DATA_HOME"] = str(world["data_home"])
    assert db.main(["build", "--data-home", str(world["data_home"]), "--out-dir", str(out),
                    "--checkout", str(world["checkout"]), "--projects-dir", str(proj), "--no-git"]) == 0
    page = (out / "index.html").read_text()
    assert 'id="scorecard"' in page and 'id="kits"' in page, "panel ids missing"
    assert "coverage" in page and "-codex" in page
    assert "insufficient sample" in page or "n/a" in page
print("T5 probe OK")
PY
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

### T6 — Telemetry snapshots and journal digests panel
- id: T6
- title: Telemetry snapshots and journal digests panel
- status: done
- model: sonnet
- depends: T5

**Brief.** PLAN D3 (rows 3 and 4), D7(d, g), D8. Files: `bin/dashboard.py`,
`tests/test_dashboard.py`. Owners: `bin/telemetry_snapshot.py` (`SOURCES`,
`build_list_summary`, `read_source_snapshots`, `build_envelope` for fixtures) and
`bin/journal_collect.py` (`SCHEMA_VERSION`, read as data; no reader exists, so the digest
adapter below is one of the three sanctioned thin adapters).

1. **Telemetry**, per read namespace (mapped first; a namespace without a `telemetry` dir
   renders "never captured — run `python3 bin/telemetry_snapshot.py` to capture"): `summary,
   notes = telemetry_snapshot.build_list_summary(store_dir)`; the per-source table from
   `summary["sources"]` (source, registered, count, first, last, latest status, latest
   labels verbatim). Then for each registered source in `telemetry_snapshot.SOURCES` (read
   the tuple): `dated, src_notes = read_source_snapshots(store_dir, source)`; keep at most
   the last `MAX_TELEMETRY_ENVELOPES_PER_SOURCE` (a note when cut); the latest envelope
   renders `capture_date`, `period`, `status`, `labels`, `notes` and — only for `status ==
   "ok"` with a dict payload — the HEADLINE allowlist of PLAN D7(g), each missing field as
   `unknown`; an unregistered source renders labels only. Age = `age_days(capture_date,
   today)`; a header refresh hint names `python3 bin/telemetry_snapshot.py`. One sparkline
   per namespace of `cost_report` `payload["totals"]["usd"]` across the kept envelopes,
   labelled with the latest envelope's own labels (the billing-mode and est. labels come
   from the owner — never write "estimate" yourself), with its table twin.
2. **Journal digests** (thin adapter), per read namespace with a `journal` dir: candidate
   days are the subdirectory names matching `^\d{4}-\d{2}-\d{2}$`, sorted descending,
   bounded by `MAX_JOURNAL_DAYS`; each `digest.json` is read with `safe_paths.
   confined_read_bytes(journal_dir, f"{day}/digest.json", missing_ok=True)`; a decode
   error, a non-object, or `schema_version != journal_collect.SCHEMA_VERSION` (read from the
   module) is the note `f"{day}: unknown digest version, not rendered"` / "undecodable, not
   rendered". Render per day: `totals.usd_priced` through `fmt_usd(v, "journal's own priced
   total: est., priced sources only")`, `totals.sessions`, `sources_active`,
   `unpriced_sources`; a sparkline of `usd_priced` by day with its table twin; for the
   latest day a per-source table (`available`, `priced`, `sessions`, `usd` → `fmt_usd(v,
   "est.")` when `priced` else the text "unpriced"). Nothing else from the digest is read:
   not `inbox`, not `signals`, not any narrative file — the panel says so in one line.
3. `synthetic_world` extension: two dated envelopes per registered source built with
   `telemetry_snapshot.build_envelope` (synthetic payloads carrying the headline fields
   with obviously fake numbers and a `labels` list), one rogue file `notes.json`, one
   unregistered source dir `mystery/2026-01-01.json`; two journal days with schema-1
   digests, one day with `schema_version` 99, and one digest whose `inbox` list holds the
   canary string `CANARY-INBOX-TEXT-DO-NOT-RENDER`.
4. Tests: the rogue-file and unregistered-source notes from the owner appear; the latest
   envelope's labels appear verbatim; a headline field absent from a payload renders
   `unknown`; the schema-99 day is noted and none of its numbers render; the canary string
   is absent from the page; an absent `telemetry` dir renders the never-captured line; the
   sparkline figure carries a table twin with one row per kept envelope; the
   `MAX_JOURNAL_DAYS` cap lowered to 1 leaves a note.

**Acceptance.** Usage numbers come only from envelopes, with the owners' labels beside
them; digests are version-gated and free text never renders; staleness and refresh hints
are visible; tests green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
python3 - <<'PY'
import importlib.util, os, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("dashboard", "bin/dashboard.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
with tempfile.TemporaryDirectory() as td:
    root = Path(td); world = db.synthetic_world(root)
    out = root / "out"; proj = root / "proj"; proj.mkdir()
    os.environ["POLYTROPOS_DATA_HOME"] = str(world["data_home"])
    assert db.main(["build", "--data-home", str(world["data_home"]), "--out-dir", str(out),
                    "--checkout", str(world["checkout"]), "--projects-dir", str(proj), "--no-git"]) == 0
    page = (out / "index.html").read_text()
    assert "CANARY-INBOX-TEXT-DO-NOT-RENDER" not in page
    assert "unknown digest version" in page and "telemetry_snapshot.py" in page
    assert 'id="telemetry"' in page and 'id="journal"' in page
print("T6 probe OK")
PY
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

### T7 — Evals, policy, activation and training panel; the demo renders every panel
- id: T7
- title: Evals, policy, activation and training panel; the demo renders every panel
- status: done
- model: sonnet
- depends: T6

**Brief.** PLAN D3 (row 5), D7(e). Files: `bin/dashboard.py`, `tests/test_dashboard.py`.
Owners: `bin/workflow_eval.py` (`EVAL_VERSION`, `list_runs`, `read_envelope`, `build_card`,
`policy_report`, `approval_report`, `activation_report`, `MANIFEST_DIR`, `NOT_A_RANKING`) and
`bin/training_data.py` (`status`). Read `build_card` and `_variant_summary` to learn which
trial and variant keys a minimal envelope needs; the fixture is the smallest envelope the
owner's own `build_card` accepts.

1. **Evaluation runs**, per read namespace with an `evals` dir: `rows, notes =
   workflow_eval.list_runs(store_dir)` → the runs table (run id, harness, repo scrubbed,
   trials, `spent_usd` → `fmt_usd(v, "as the evaluation recorded it")` or `unknown`,
   labels verbatim) plus the owner's notes (an unknown-version run is one of them —
   render it, and render nothing else about that run). For the latest
   `MAX_EVAL_RUNS_RENDERED` runs (by run id descending; a note when cut): `card =
   workflow_eval.build_card(workflow_eval.read_envelope(store_dir, run_id))` in `try/except
   (OSError, ValueError, KeyError, TypeError)` → note; render `variants` as a table of
   every key each summary carries (`None` → `unknown`), `below_floor` as text, `spend`
   and `totals` dicts as key/value tables through the formatters (a spend key that names a
   basis keeps that basis word in its label), `sample`, `labels` verbatim and in full,
   `ranking` ONLY when it is not `None` (otherwise the line "ranking: none — the owner did
   not rank"), `adjudications`, `escaped_defects_total`, `untested_claims` as a `details`
   list, `notes`. Manifests: the count of `*.json` names under `store_dir/MANIFEST_DIR`
   (names only, never opened).
2. **Policy, approvals, activation**, per read namespace (`prefs_dir = <ns>/prefs`, which
   may be absent — the owners tolerate it): `policy_report(prefs_dir)` → in force (version
   and `defaults`) or "none in force", `history_versions`, proposals table (id, status,
   run, decisions), `consumption`, `review_authority` verbatim; `approval_report` → table
   (id, state, granted, by, refusals) + its `labels`; `activation_report` → scopes table
   (scope key, generation, state, unreadable, strays), `confined_dispatch_wired`,
   `unproven` codes and `labels` verbatim. Each in `try/except Exception` → note with the
   exception type.
3. **Training**, per discovered checkout: `training_data.status(repo_root=checkout)` →
   `collection_enabled`, `capture_wired`, `store_path` scrubbed, `store_origin`,
   `store_exists`, `eligible_to_persist`, `to_enable` list, `notes` verbatim.
4. `synthetic_world` extension: one evals run whose `results.json` carries `"v":
   workflow_eval.EVAL_VERSION` (read from the module at fixture-build time) and the minimal
   trial/variant fields `build_card` needs, with a synthetic `labels` list; one run dir
   whose `results.json` carries `"v": "polytropos.workflow-eval/99"`; one dir that is not a
   run; an empty `prefs` dir. `demo` now renders every panel and its summary prints one
   line per panel.
5. Tests: the version-99 run appears only through the owner's note; `NOT_A_RANKING` (read
   from the module) appears on the page for a single-repeat run; `ranking: none` appears
   and no ranking list does; a variant with `below_floor` renders the owner's below-floor
   label; `spent_usd` `None` renders `unknown`; training switches render `False` /
   `False`; approvals absent renders the owner's empty shape without error; `demo` output
   names every panel id.

**Acceptance.** The evals panel never ranks, prices or judges — every label and verdict is
the owner's; activation and training states are shown as the owners report them; the demo
is complete; tests green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 bin/dashboard.py demo > "$(mktemp -d)/demo.txt"
python3 - <<'PY'
import importlib.util, os, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("dashboard", "bin/dashboard.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
we_spec = importlib.util.spec_from_file_location("workflow_eval", "bin/workflow_eval.py")
we = importlib.util.module_from_spec(we_spec); we_spec.loader.exec_module(we)
with tempfile.TemporaryDirectory() as td:
    root = Path(td); world = db.synthetic_world(root)
    out = root / "out"; proj = root / "proj"; proj.mkdir()
    os.environ["POLYTROPOS_DATA_HOME"] = str(world["data_home"])
    assert db.main(["build", "--data-home", str(world["data_home"]), "--out-dir", str(out),
                    "--checkout", str(world["checkout"]), "--projects-dir", str(proj), "--no-git"]) == 0
    page = (out / "index.html").read_text()
    assert we.NOT_A_RANKING.split(":")[0] in page, "owner ranking label missing"
    assert "ranking: none" in page and 'id="evals"' in page and 'id="training"' in page
    assert "collection_enabled" in page or "collection enabled" in page
print("T7 probe OK")
PY
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

## Phase 3 — Skill and documentation

### T8 — The `/polytropos:dashboard` skill and its docs-site surfaces
- id: T8
- title: The `/polytropos:dashboard` skill and its docs-site surfaces
- status: done
- model: sonnet
- depends: T7

**Brief.** PLAN D11, D8. Files: NEW `skills/dashboard/SKILL.md`; NEW
`docs-src/fragments/skills/claude/dashboard.md`; `.claude/kits/docs-site/AUDIT.md`;
`mkdocs.yml`; `tests/test_docs_build.py`; `docs/REFERENCE.md`; generated `docs-site/**`
via `python3 bin/docs_build.py build`. All in this one task, because three tests pin the
roster (`tests/test_docs_audit.py`, `tests/test_docs_build.py` `LiveTreeInventoryTests`,
`tests/test_docs_site.py` nav coverage) and the tree is red between any two of these edits.

1. `skills/dashboard/SKILL.md` frontmatter — exactly three fields, in this order, no
   `model:` pin ever:

   ```yaml
   ---
   name: dashboard
   description: Build the local observability dashboard — one offline HTML page over the attempt ledger and history, the routing scorecard across every checkout, the telemetry snapshots and journal digests, and the evaluation, policy and training status — then report where it landed. Use when the user asks for the dashboard, an overview of what the ledger, scorecard or telemetry show, or to refresh the observability page. Not for analysis or routing changes; it renders what the owning engines report.
   allowed-tools: Bash
   ---
   ```

   Body, in this order: (a) engine resolution in the `skills/update/SKILL.md` wording —
   `python3 "${CLAUDE_PLUGIN_ROOT}/bin/dashboard.py" build --checkout "$(git rev-parse
   --show-toplevel)"`, with the `../../bin/dashboard.py`-relative-to-this-SKILL.md fallback
   resolved to an absolute path before shelling out, and why `--checkout` is passed (the
   plugin runs from its cache, which is not a checkout); (b) **the context-hygiene law,
   binding:** relay the page path and the one-screen summary the engine prints (or `--json`
   for the receipt); never `cat`, `Read`, `grep`, `head` or otherwise load `index.html` or
   `build.json` into the session; never paste, quote, publish, attach or upload the page or
   the receipt anywhere; never run `open`/`xdg-open` or any browser — opening the file is
   the user's action; (c) what the page holds, one paragraph per panel (namespaces,
   attempts, scorecard, kits, telemetry, journal, evals/policy/activation, training, RSI
   status) and the honesty rules in one paragraph (owners' labels verbatim, one row per
   cost basis and nothing summed, `unknown` is a word, absent is absent, bounds visible,
   residue counted not opened); (d) refresh guidance: the page is a file — rebuild to
   refresh; a stale telemetry panel means `python3 "${CLAUDE_PLUGIN_ROOT}/bin/
   telemetry_snapshot.py"` first, then rebuild; (e) flags — `--checkout` (repeatable),
   `--no-transcripts`, `--no-git`, `--out-dir`, `where`, `demo`; (f) what it cannot do — no
   analysis, no routing change, no network, no share path; (g) privacy: personal data,
   home paths rendered as `~`, keep it local. No absolute home path, no price, no model
   id, no cached date anywhere in the file.
2. `docs-src/fragments/skills/claude/dashboard.md` per `docs-src/fragments/TEMPLATE.md`:
   the six `###` sections in order, 150–550 `wc -w` with at most 450 words of prose, at
   least one real "not for" bullet, every command traced to the SKILL.md or
   `bin/dashboard.py`'s argparse, zero numbers that rot, links relative to
   `docs-site/skills/claude/` (`journal.md`, `cost-report.md`, `update.md`,
   `../../deep-dives/privacy.md`).
3. `.claude/kits/docs-site/AUDIT.md`: append a `### claude/dashboard` entry under the
   `## claude` section with the five fields in the pinned order (`verdict`, `skill-md`,
   `references`, `fragment-notes`, `sentinels`; read `tests/test_docs_audit.py` for the
   sanctioned verdict values and use the one that means "keep as written"), a body word
   count you measured, `references: none`, and a sentinels line naming
   `tests/test_docs_build.py`'s inventory count as the only test that notices the skill;
   update the `## Disposition summary` tally sentence so its `keep` count includes this
   entry (the test recounts it); label the entry as an addendum, like the
   `claude/assess-improvement` precedent.
4. `mkdocs.yml`: insert `      - dashboard: skills/claude/dashboard.md` in the Claude
   block between the `cost-report` and `escalate` lines (alphabetical, matching indent).
5. `tests/test_docs_build.py` `LiveTreeInventoryTests`: the Claude count becomes 16 and its
   comment gains "16 since the observability-dashboard kit added skills/dashboard".
6. `docs/REFERENCE.md`: census row `| Skills (Claude Code) | 15 |` → `16`; the heading
   `## Capabilities — the fifteen skills` and the two other "fifteen"/"Fifteen" mentions
   → sixteen; add a `**`/polytropos:dashboard`**` paragraph beside the other skill
   paragraphs in that section, in their register (what it runs, the hygiene law, what it
   never does), with no number that rots.
7. `python3 bin/docs_build.py build`; confirm `check` exits 0; `git status --porcelain`
   shows only the files above plus generated pages under `docs-site/skills/claude/` and
   `docs-site/skills/index.md`, `docs-site/deep-dives/reference.md`.

**Acceptance.** Frontmatter keys exactly `name`, `description`, `allowed-tools`;
description carries "Use when"; the hygiene law names `index.html` and the words never
read/paste/open; no `/Users/` or other absolute home path in the skill or fragment;
`docs_build.py check` 0; the full suite green (this is what proves the AUDIT roster, the
inventory count and the nav coverage).

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 - <<'PY'
import re
t = open("skills/dashboard/SKILL.md", encoding="utf-8").read()
fm = re.match(r"---\n(.*?)\n---\n", t, re.S); assert fm, "no frontmatter"
keys = [l.split(":")[0] for l in fm.group(1).splitlines() if ":" in l]
assert keys == ["name", "description", "allowed-tools"], keys
assert "Use when" in t and "CLAUDE_PLUGIN_ROOT" in t and "index.html" in t
assert "/Users/" not in t and "/home/" not in t, "home path leak"
low = t.lower()
assert "never" in low and "paste" in low and "open" in low
f = open("docs-src/fragments/skills/claude/dashboard.md", encoding="utf-8").read()
assert f.count("\n### ") + f.startswith("### ") == 6, "fragment must carry six ### sections"
print("T8 skill shape OK")
PY
grep -q 'dashboard: skills/claude/dashboard.md' mkdocs.yml
grep -q '### claude/dashboard' .claude/kits/docs-site/AUDIT.md
grep -q '| Skills (Claude Code) | 16 |' docs/REFERENCE.md
python3 bin/docs_build.py check
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

### T9 — Wiring: kit sentinel, engine documentation, census, and the generator checks
- id: T9
- title: Wiring: kit sentinel, engine documentation, census, and the generator checks
- status: done
- model: haiku
- depends: T8

**Brief.** PLAN D16 and the documentation consequences of a new engine. Files:
`tests/test_guardrails_layout.py`, `docs/HOW-IT-WORKS.md`, `docs/REFERENCE.md`, and the
generated `docs-site/deep-dives/*` via `python3 bin/docs_build.py build`. `CLAUDE.md` is
NOT edited — it sits at its byte ceiling; the run-line it would normally gain is deferred
(record that as unfinished in `NOTES.md`).

1. `tests/test_guardrails_layout.py` `KIT_SENTINELS` dict: add the entry
   `"observability-dashboard": "the page can never reach the network",` (that substring
   exists verbatim in `.claude/kits/observability-dashboard/GUARDRAILS.md`; do not edit
   GUARDRAILS.md).
2. `docs/HOW-IT-WORKS.md`: in the engine-family table of §4, add `dashboard` to the
   **Memory, lessons, telemetry** row's engine list and extend its description with one
   clause: "and one offline HTML page rendered over those stores by `dashboard`, which
   computes nothing the owners already report".
3. `docs/REFERENCE.md`: in the engine table (the section opening "`bin/` is one flat
   directory"), add a row `| `bin/dashboard.py` | One offline HTML page over the attempt
   ledger and history, the routing scorecard across checkouts, the telemetry snapshots,
   journal digests and evaluation/policy/training status — a consumer that renders the
   owners' labels verbatim, sums nothing, and writes only its own `dashboard` store |`
   beside the other store-reading engines; re-derive the census row `| Engines
   (`bin/*.py`) | N |` with `ls bin/*.py | wc -l` and write that number.
4. `python3 bin/docs_build.py build`; then confirm every generator's `check` exits 0.

**Acceptance.** Sentinel present in both files; the two docs carry the rows; the census
number equals the live count; `python3 bin/docs_build.py check`, `python3
bin/copilot_docs.py check`, `python3 bin/sync_codex_surfaces.py check`, `python3
bin/release_gate.py check` all exit 0; `CLAUDE.md` unchanged; full suite green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
grep -q '"observability-dashboard": "the page can never reach the network"' tests/test_guardrails_layout.py
grep -q 'the page can never reach the network' .claude/kits/observability-dashboard/GUARDRAILS.md
grep -q '`bin/dashboard.py`' docs/REFERENCE.md
grep -q 'dashboard' docs/HOW-IT-WORKS.md
python3 - <<'PY'
import glob, re
n = len(glob.glob("bin/*.py"))
t = open("docs/REFERENCE.md", encoding="utf-8").read()
m = re.search(r"\| Engines \(`bin/\*\.py`\) \| (\d+) \|", t)
assert m and int(m.group(1)) == n, (m and m.group(1), n)
print("census OK", n)
PY
git diff --quiet -- CLAUDE.md
python3 bin/docs_build.py check
python3 bin/copilot_docs.py check
python3 bin/sync_codex_surfaces.py check
python3 bin/release_gate.py check
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

## Phase 4 — RSI: what exists now, then the records when their read seam lands

### T10 — RSI status panel from what exists on `main` today
- id: T10
- title: RSI status panel from what exists on `main` today
- status: done
- model: opus
- depends: T7

**Brief.** PLAN D12, D3 (row 7), D10. Files: `bin/dashboard.py`, `tests/test_dashboard.py`.
On 2026-09-25 `bin/recursive_improvement.py` exists only on Codex's
`feat/rsi-evidence-foundation` (R01 done: versioned validators for generation / improver /
experiment / lineage / source-capture records, arms A/B/C, no store, no reader);
`tasks/kits/recursive-improvement/{PLAN,TASKS,NOTES}.md` exists on `main`. Never read or run
anything in the RSI worktree; the branch is inspected only through `git show
feat/rsi-evidence-foundation:<path>` and `git log main..feat/rsi-evidence-foundation`,
and only to confirm the shapes this brief describes — the panel renders what the EXECUTING
checkout holds.

1. **Engine presence probe** (a sanctioned thin adapter) — `rsi_status(checkout) -> dict`:
   `path = checkout / "bin" / "recursive_improvement.py"`; absent → `{"present": False}`
   and the panel line "RSI engine not present in this checkout (`bin/recursive_improvement.py`)".
   Present → load it with `importlib` inside `try/except Exception as exc` (failure →
   `{"present": True, "importable": False, "error": type(exc).__name__}` and a note — the
   exception message is never rendered); on success collect every module attribute whose
   name ends with `_VERSION` and whose value is a `str` (rendered as a table of contract
   names → versions, as DATA read at run time, never typed into the dashboard), the `ARMS`
   tuple when present, and `STORE` when present as a string: if `STORE` names an entry of
   `runtime_data.STORES` render its resolved path for the checkout (scrubbed) and whether
   it exists; otherwise the line "store kind unknown to runtime_data — not resolved". When
   there is no `STORE` and no attribute whose name contains `READ` or that is a function
   named `read_*`/`list_*`/`iter_*`, the panel says: "no RSI record store or reader is
   defined by this engine version; nothing to render — R02 (durable links and history
   projection) has not landed here".
2. **RSI kit progress**, per discovered checkout: `kit_dir = checkout / "tasks" / "kits" /
   "recursive-improvement"`; absent → "RSI kit not present in this checkout"; present →
   `kit_contract.parse_tasks(TASKS.md text)` → a table (id, title, status, model) and the
   status counts; the NOTES.md `outcome:` lines through `attempt_history.notes_records
   (kit, text, registry)` with `registry = model_registry.registry()` → a table (task,
   result, dispatched/observed model, run) — every field the record carries or `unknown`;
   the count of `actual-use:` and `routing:` lines (counted by prefix only, never parsed —
   their vocabulary belongs to the Codex driver). Link the reader to the attempts panel
   for the `kits-…` namespace ledger (the Codex kits' ledger root is `tasks/kits`, D4).
3. **Version guard** used by T11 — `rsi_record_kind(obj, known_versions) -> ("known" |
   "unknown" | "not-a-record", version_or_None)`: a dict whose `v` is a string starting
   with `polytropos.rsi-` is a record; known iff `v` is in the loaded module's version
   values; anything else is not a record. A renderer that meets `unknown` prints "unknown
   version, not rendered" and the version string. The literal prefix `polytropos.rsi-`
   appears EXACTLY once in `bin/dashboard.py` (this guard) and never as a full version
   string — the verify block counts it; keep it out of docstrings and comments.
4. `synthetic_world` extension: the demo checkout gains `tasks/kits/recursive-improvement/`
   with a TASKS.md of three tasks (`done`, `pending`, `pending`) and a NOTES.md with one
   `outcome:` line, an `actual-use:` line and a `routing:` line; NO engine file (the demo
   shows the absent state).
5. Tests: absent engine → the absent line; a temp checkout with a stub
   `bin/recursive_improvement.py` exposing `FIXTURE_A_VERSION = "polytropos.rsi-fixture-a/1"`,
   `FIXTURE_B_VERSION = "polytropos.rsi-fixture-b/1"` and `ARMS = ("A", "B", "C")` → both
   versions render as data and the "nothing to render" line appears; a stub that raises
   `RuntimeError` on import → importable False with the type name and no message text on
   the page; a stub exposing `STORE = "not-a-store"` → the unknown-store line; the kit
   progress tables from the synthetic kit; `rsi_record_kind` over a known, an unknown and a
   non-record object; the page never contains the string `Traceback`.

**Acceptance.** The panel renders every state the executing checkout can be in without
importing anything about the branch into the dashboard's code; contract versions are data;
unknown versions are named, never crashed on; tests green.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_dashboard.py' -v
grep -c "polytropos.rsi-" bin/dashboard.py | grep -qx 1
python3 - <<'PY'
import importlib.util, os, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("dashboard", "bin/dashboard.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
with tempfile.TemporaryDirectory() as td:
    root = Path(td); world = db.synthetic_world(root)
    out = root / "out"; proj = root / "proj"; proj.mkdir()
    os.environ["POLYTROPOS_DATA_HOME"] = str(world["data_home"])
    assert db.main(["build", "--data-home", str(world["data_home"]), "--out-dir", str(out),
                    "--checkout", str(world["checkout"]), "--projects-dir", str(proj), "--no-git"]) == 0
    page = (out / "index.html").read_text()
    assert 'id="rsi"' in page and "RSI engine not present" in page and "recursive-improvement" in page
    assert "Traceback" not in page
    kind, v = db.rsi_record_kind({"v": "polytropos.rsi-fixture/7"}, ("polytropos.rsi-fixture/1",))
    assert kind == "unknown" and v == "polytropos.rsi-fixture/7", (kind, v)
print("T10 probe OK")
PY
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```

### T11 — RSI projections through the installed plugin's own engine (GATED on R02 reaching `main`)
- id: T11
- title: RSI projections through the installed plugin's own engine (GATED on R02 reaching `main`)
- status: blocked
- model: opus
- depends: T10

**Re-planned 2026-09-27 (architect).** The original T11 brief was unexecutable under two
facts: the user's decision "parse, never import" (2026-09-26; the dashboard never runs a
checkout's code), and R02's actual design (no `STORE`, no stored records, no reader — two
projection functions over the attempt ledger). Its gate `exec`'d the engine and demanded a
`STORE` string, so it could never pass; its item (2) called readers on each checkout's
engine, which meant importing checkout code. Everything below replaces that brief.

**Brief.** PLAN D12 (as amended), D3 row 7, D2, D4, D7, D8, D10; R3, R4, R12. Files:
`bin/dashboard.py`, `tests/test_dashboard.py`, `skills/dashboard/SKILL.md` (its RSI
paragraph only — no frontmatter change), `.claude/kits/docs-site/AUDIT.md` (the word count in
the `### claude/dashboard` entry only, if the body's word count changes), then `python3
bin/docs_build.py build` for the generated mirror. Nothing else. T10's parse-only reading of
each checkout's engine is UNCHANGED.

**Gate — the orchestrator runs this from the checkout root BEFORE dispatching, and reads the
result. It parses; it never imports, `exec`s or runs the engine:**

```bash
cd "$(git rev-parse --show-toplevel)"
git cat-file -e main:bin/recursive_improvement.py || { echo "gate: bin/recursive_improvement.py is not on main"; exit 3; }
test -f bin/recursive_improvement.py || { echo "gate: bin/recursive_improvement.py absent from this checkout"; exit 3; }
python3 - <<'PY'
import ast
tree = ast.parse(open("bin/recursive_improvement.py", "rb").read(), filename="recursive_improvement.py")
defs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
strings = {t.id for n in tree.body if isinstance(n, ast.Assign)
           and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
           for t in n.targets if isinstance(t, ast.Name)}
def first_param(name):
    f = defs.get(name)
    return f.args.args[0].arg if f is not None and f.args.args else None
found = {name: first_param(name) for name in ("outcome_eligibility_inventory", "derived_lineage")}
versions = sorted(s for s in strings if s.endswith("_VERSION"))
ok = (all(param == "ledger" for param in found.values())
      and {"OUTCOME_INVENTORY_VERSION", "LINEAGE_VERSION"} <= strings)
print("gate:", "met" if ok else "UNMET", "| first params:", found, "| version constants:", versions)
raise SystemExit(0 if ok else 3)
PY
```

Exit 3 means the gate is UNMET: set this task's `- status:` to `blocked`, append one plain
prose line to `NOTES.md` — "T11 gated <date>: `bin/recursive_improvement.py` <not on main |
absent | present without both projection functions taking `ledger` first, or without both
version constants>; waiting on feat/rsi-evidence-foundation R02 to merge to main" — dispatch
nothing, write no `outcome:` line, and report the kit complete except T11. The gate is
mechanical only; there is no judgement clause. If the engine on `main` has the functions
under other names or shapes, that is a re-plan, not a dispatch.

**What R02's engine looks like, confirmed from the branch TEXT on 2026-09-27** (`git show
feat/rsi-evidence-foundation:bin/recursive_improvement.py`; line numbers are that blob's, and
the engine ON `main` at dispatch time is authoritative where it differs — D10, R12; record any
delta in `NOTES.md` and adapt only the dashboard's adapter). Never read, list or run anything
in the RSI worktree.

- Module docstring (lines 2–15): "deliberately a coordinator, not a second attempt ledger,
  proposal store, evaluator, or admission path". No `STORE` anywhere. It loads its own
  siblings (`attempt_ledger`, `proc_runner`, `decision_contract`, `workflow_eval`) from
  `Path(__file__).resolve().parent` with `spec_from_file_location` on EVERY call of `_al()`
  etc. (lines 43–64: no cache) — so when it is loaded from `plugin_root/bin` its siblings come
  from that same tree, and its per-event cost includes re-executing `attempt_ledger.py`. Its
  projection is also quadratic in events by inspection (`_terminal_for` scans every event per
  `attempt.started`, lines 1010–1105 and 1163). Both facts are why the caps in item 2 exist.
- Versions (lines 26–31), all module-scope string literals: `GENERATION_VERSION`,
  `IMPROVER_VERSION`, `EXPERIMENT_VERSION`, `LINEAGE_VERSION`, `SOURCE_CAPTURE_VERSION`,
  `OUTCOME_INVENTORY_VERSION`. `ARMS = ("A", "B", "C")` (line 33). Read these AS DATA off the
  loaded module at run time; never type a version string into `bin/dashboard.py` (the literal
  prefix `polytropos.rsi-` stays exactly once there, in `rsi_record_kind` — T10's verify counts
  it and still must pass).
- `outcome_eligibility_inventory(ledger, captures=(), *, declared_attempt_count=None)` (line
  1108). `ledger` must have `.events()` (else `TypeError`, line 1116); it reads
  `getattr(ledger, "corrupt", 0)` and, for a candidate row with source refs, calls
  `ledger.read_rsi_source(ref)` inside its own `try/except Exception` (lines 1204–1212), so a
  ledger without that method yields the owner's own `missing-source-artifact` reason, not a
  crash. `captures` is "an accepted compatibility argument … never evidence" (lines 1139–1141):
  pass nothing. `declared_attempt_count` is a claim the caller makes; the page makes none: pass
  nothing. Returns (lines 1308–1316) `{"v": OUTCOME_INVENTORY_VERSION, "rows": [...], "counts":
  {"recorded_dispatches", "candidates", "corroborated"}, "integrity_reasons": [...],
  "claim_gate": {"eligible": bool, "reason": str | None}}`. Each row (lines 1258–1268):
  `attempt`, `run`, `task` (strings or `None`), `dispatch` and `terminal` (a V1 ledger ref
  `{"id", "sha", "v"}` or `None`), `sources` (list of refs), `source_digest` (str or `None`),
  `candidate`, `corroborated` (bools), `label` (exactly one of `corroborated` | `candidate` |
  `excluded`), `exclusion_reasons` (sorted list of strings).
- Exclusion reasons the text emits, verbatim: `ambiguous-dispatch`, `invalid-dispatch-event`,
  `role-not-implementer`, `invalid-dispatch-source-fields`, `missing-terminal-outcome`,
  `ambiguous-task-projection`, `ambiguous-attempt-terminal`, `ambiguous-verify-terminal`,
  `invalid-terminal-event`, `invalid-terminal-order`, `invalid-cross-run-terminal`,
  `unresolved-task-projection-comparison`, `contradictory-task-projection`,
  `unresolved-terminal-outcome`, `invalid-terminal-outcome`, `missing-dispatch-source-link`,
  `invalid-dispatch-source-reference`, `legacy-source-capture-version`,
  `unsupported-source-capture-version`, `corrupt-source-artifact`, `stale-source-artifact`,
  `missing-source-artifact`, `source-after-dispatch`, `unresolved-dispatch-source-proof`,
  `missing-dispatch-source-digest`. Integrity reasons: `corrupt-ledger-event`,
  `malformed-ledger-event`, `orphan-terminal-event`, `mismatched-attempt-count`. Claim-gate
  reasons: the first integrity reason, `unresolved-inventory-row`, `no-corroborated-outcome`,
  or `None`. The page renders WHATEVER strings the owner returns — this list is so the
  implementer and the verifier can recognise them, not an allowlist, and none of them is
  typed into `bin/dashboard.py`.
- `derived_lineage(ledger, captures=())` (line 1319) calls the inventory again and returns
  `{"v": LINEAGE_VERSION, "records": [{"dispatch", "terminal", "sources", "source_digest"}
  for each corroborated row], "inventory": <the inventory dict>}`.
- On the branch `attempt_ledger.py` also gains `read_rsi_source`, `RSI_SOURCES_DIR` and a
  `_ri()` sibling load; on `main` today it has `LEDGER_VERSION`, `REF_FIELDS`,
  `REF_PART_CHARS`, `make_ref`, `read_ref`, `OUTCOME_UNKNOWN` and `AttemptLedger(root,
  namespace)` with `.events()`, `.corrupt` and `.open_attempts()` and a constructor that
  writes nothing. The engine's ledger dependencies arrive with the same merge; the dashboard
  constructs the ledger through the owner and never inspects which methods it has.

1. **The owner seam — `rsi_owner(plugin_root) -> dict`**, the ONE place the page loads
   `recursive_improvement`. It looks up `plugin_root/bin/recursive_improvement.py` with
   `_no_follow_walk` (a link anywhere in the path → not loaded); the leaf must be a regular
   file. Absent → `{"state": "absent"}`. A link or non-regular leaf → `{"state": "refused",
   "detail": <leaf kind>}`. Present → load it exactly as `_load` does (`spec_from_file_location`
   + `exec_module`) inside `try/except Exception as exc` → `{"state": "error", "detail":
   type(exc).__name__}` (message never rendered) or `{"state": "loaded", "module": m,
   "versions": [[name, value] …], "known_versions": [values]}` where `versions` is every
   module attribute whose name ends `_VERSION` and whose value is a `str`, in `sorted(dir(m))`
   order. Then the shape check, by `inspect.signature`: for each of
   `outcome_eligibility_inventory` and `derived_lineage`, the attribute must be callable and its
   first parameter must be named `ledger` and be positional; a miss → `{"state":
   "shape-mismatch", "detail": "<function name>: <missing | first parameter is '<name>'>"}`
   (parameter NAMES are safe to render; nothing else from the module is). The loaded module is
   held in the build `ctx` (key `rsi_owner`), resolved once per build in `build_model` from
   `opts["plugin_root"]` — the seam `assemble_build` already fills with `PLUGIN_ROOT` for
   `build`, the synthetic plugin root for `demo`, and whatever a test passes. It is NEVER put
   in `_MODULES` (that cache is keyed by name and bound to `PLUGIN_ROOT`; a fixture tree must
   not poison it) and NEVER resolved from a checkout, a flag, a config entry or a store.
   `demo`'s synthetic plugin root carries no engine, so the demo page shows the absent state
   (Done-means 1 unchanged, and `demo` still executes no file it wrote).
2. **Which ledgers are projected, and the caps.** A new sub-section of the RSI panel, "RSI
   projections (through the installed plugin's engine)", rendered after the per-checkout
   sections, inside its own `_guarded_section`. Its inputs are the MAPPED namespace rows of
   `read_namespaces(ctx, plugin_install=False)` with `kind` in `("checkout", "codex-kits")` —
   the same rows and order the attempts panel's ledger facts read, so the RSI kit's own ledger
   (the `kits-<digest>` namespace, PLAN D4) is included. Unmapped namespaces are never
   projected (D4: read through shallow stats only), residue never opened, and the plugin
   install's namespace never projected (it is not a checkout and holds no kit ledger by
   design). Per row, every `attempts/<ledger>` subdir passes the SAME regular-file and
   `MAX_LEDGER_BYTES` gate as `_ledger_fact_rows` — extract that stat/kind/size gate into one
   helper both call so the logic exists once (behaviour unchanged; the existing ledger-facts
   tests must stay green unmodified). Then two new caps, both in `CAP_NAMES` and
   `default_caps()`, each hit a `cap_note` on the panel, in bounds and in `build.json`:
   - `MAX_RSI_PROJECTED_LEDGER_BYTES` — a ledger whose `events.jsonl` is larger is NOT handed
     to the owner (note: "… bytes — not projected; the owner's projection is quadratic in
     events and reloads its siblings per event"). Set it from a MEASUREMENT at dispatch time:
     time `outcome_eligibility_inventory` + `derived_lineage` over synthetic ledgers written
     through `AttemptLedger.record_started`/`record_finished` in a temp dir at 25%, 50% and
     100% of the candidate cap, choose the cap so one ledger's two calls take about one second
     on this machine, and record the three timings, the machine, and the cap in `NOTES.md`.
     The comment beside the constant states the measured basis. Never truncate a ledger's
     events to fit: a truncated event list would manufacture `missing-terminal-outcome` rows
     the owner never emitted (R3/R4 in spirit — a fabricated exclusion is a fabricated figure).
   - `MAX_RSI_LEDGERS_PROJECTED` — how many ledgers across the build are handed to the owner
     (mapped order, checkout namespaces before `codex-kits`); the rest get one note naming how
     many were skipped.
   Each projected ledger is `al.AttemptLedger(attempts_root, ledger_name)` — the owner's own
   object, constructed exactly as `_one_ledger_fact` does. Each of the two owner calls is
   positional-`ledger`-only (`fn(ledger)`), inside `try/except Exception` per ledger → a note
   "RSI projection for <ns>/<ledger>: <function> raised (<TypeName>)" and the fixed line that
   this ledger's projection could not be built; the other ledgers still render.
3. **Rendering, verbatim and version-gated.** Each returned object goes through
   `rsi_record_kind(obj, owner["known_versions"])` first: `"known"` → render; `"unknown"` →
   render only the new constant `RSI_UNKNOWN_VERSION = "unknown version, not rendered"` plus
   the version string; `"not-a-record"` → the fixed line "the owner returned no versioned
   record (<type name>)". For a known inventory render: a two-column table of `counts` with
   the owner's KEY NAMES as row labels and `{"fmt": "count"}` cells (a missing key renders
   `unknown`, never 0); the `v`; `integrity_reasons` as a list, verbatim, with the empty text
   "integrity_reasons: none reported by the owner"; `claim_gate` as "eligible: true|false"
   and "reason: <string> | null (the owner set none)"; then a `<details>` table of `rows`
   with the owner's field names as headers — `attempt`, `run`, `task`, `label`,
   `exclusion_reasons` (joined with "; ", each string whole), `candidate`, `corroborated`
   (the words `true`/`false`), `dispatch` and `terminal` as their `id` (or `null`), `sources`
   as a count of refs (counting what you were handed is allowed, D2), `source_digest` whole or
   `null`. Rows are bounded by a third cap `MAX_RSI_INVENTORY_ROWS_RENDERED` (the `counts`
   table stays complete because the owner computed it). For a known lineage render: `v`, the
   count of `records`, and a `<details>` table of `records` under the same row cap with
   `dispatch.id`, `terminal.id`, sources count, `source_digest`; its embedded `inventory` is
   NOT rendered again (it is the same object). Nothing is scored, ranked, attributed, summed
   or re-labelled: if a figure the reader wants is not in the owner's output the page says the
   owner does not report it. Every string through `esc()` (the typed-cell path, once); every
   path through `scrub`. Honesty (D7): a `None` count is `unknown`; a `None` reason is `null`;
   booleans are words. The panel `summary` stays fixed words plus integers and gains one
   clause: "; projections read for J of K ledger(s) through the installed plugin's engine"
   or "; no projection — the installed plugin carries no RSI engine" (or "… engine not
   loaded" for `refused`/`error`/`shape-mismatch`). Nothing read out of the owner's output
   rides in the summary (P3 review M2).
4. **The states of the projections section**, each a fixed constant that names no plan
   state (the `test_no_rsi_line_names_plan_state` sweep must keep passing: no `R02`,
   `landed`, `main`, `PLAN`): `absent` → `RSI_OWNER_ABSENT`: "The installed plugin this page
   was built by carries no bin/recursive_improvement.py, so no RSI projection was read. A
   checkout's own engine is parsed as text above and never run."; `refused`/`error` → the
   fixed line that the plugin's engine was not loaded, plus a note with the leaf kind or the
   exception type; `shape-mismatch` → `RSI_OWNER_SHAPE_DIFFERS`: "The installed plugin's
   bin/recursive_improvement.py does not expose the projection functions in the shape this
   page binds to, so nothing was projected — see the notes above." plus the note with the
   detail; `loaded` with no eligible ledger → "no mapped ledger to project" (a fact, not a
   zero). Also reword T10's two sentences so they stay TRUE once projections exist:
   `RSI_NOTHING_TO_RENDER` ends "… This page does not call into this checkout's engine." and
   `RSI_RECORDS_NOT_READ` ends "… but this page does not call into this checkout's engine;
   any RSI projection on this page comes only from the installed plugin's own engine (see
   'RSI projections' below)." — the same facts T10 stated, minus the now-false "reads no RSI
   records". Update the `skills/dashboard/SKILL.md` RSI paragraph in the same task: its
   sentence "The panel reads no RSI records itself …" becomes a sentence saying the panel
   parses each checkout's engine as text and never runs it, and renders the outcome-eligibility
   inventory and derived lineage that the INSTALLED plugin's own engine projects from the
   attempt ledger, verbatim, computing nothing itself. Recount the body's words; if the count
   changes, update the number in `.claude/kits/docs-site/AUDIT.md`'s `### claude/dashboard`
   entry (T8 precedent — the audit test compares it). Run `python3 bin/docs_build.py build`
   and confirm `python3 bin/docs_build.py check` exits 0.
5. **Tests — `RsiRecordsTests` in `tests/test_dashboard.py`**, every build through
   `assemble_build(cwd, data_home=…, out_dir=…, git=False, projects_dir=<empty temp>,
   plugin_root=<fixture tree>)` (the module-level `setUpModule` data-home patch applies; zero
   `Path.home()`). The fixture tree is `<tmp>/plugin/bin/recursive_improvement.py`, a
   SYNTHETIC module in the owner's documented shape: `OUTCOME_INVENTORY_VERSION =
   "polytropos.rsi-fixture-inventory/1"`, `LINEAGE_VERSION = "polytropos.rsi-fixture-lineage/1"`,
   `ARMS`, `outcome_eligibility_inventory(ledger, captures=(), *, declared_attempt_count=None)`
   that asserts `hasattr(ledger, "events")`, calls `ledger.events()` and returns the branch's
   shape with deterministic rows whose reasons are fixture words (e.g.
   `fixture-reason-alpha`), and `derived_lineage(ledger, captures=())`. The data home holds a
   mapped checkout namespace and a `tasks/kits` namespace, each with a ledger written through
   `attempt_ledger.AttemptLedger`'s own writers (never hand-written JSONL — the owner's writer
   is the fixture), plus a checkout whose OWN `bin/recursive_improvement.py` writes a canary
   file and raises if executed. Assert at least: (a) the inventory's `counts` keys, values,
   `v`, every fixture reason and label, and `claim_gate` render verbatim and escaped; (b) a
   fixture whose inventory `v` is not among its `*_VERSION` values renders
   `RSI_UNKNOWN_VERSION` plus that version and none of its rows; (c) a fixture returning a
   list renders the not-a-record line; (d) a fixture whose `derived_lineage` raises
   `RuntimeError` yields the type name in a note, no message text, and the inventory still
   renders; (e) a fixture with `def outcome_eligibility_inventory(store, ...)` renders
   `RSI_OWNER_SHAPE_DIFFERS` with the parameter name in a note and calls nothing; (f) a fixture
   tree with no engine renders `RSI_OWNER_ABSENT`, and a tree whose `bin` is a symlink renders
   the not-loaded line; (g) the checkout's canary engine is never executed (no canary file;
   T10's parsed table still renders it) while the plugin fixture IS called — the ONLY module
   loaded is the plugin tree's; (h) a ledger over `MAX_RSI_PROJECTED_LEDGER_BYTES` (caps
   overridden to 1 through the caps seam, the T10 precedent) is not handed to the owner (a
   fixture counter proves zero calls) and the cap note appears on the panel, in bounds and in
   `build.json`; likewise `MAX_RSI_LEDGERS_PROJECTED` and `MAX_RSI_INVENTORY_ROWS_RENDERED`;
   (i) the unmapped and residue namespaces' ledgers and the plugin install's namespace are
   never handed to the owner; (j) no `sum(` over owner values, no `$`, no `Traceback`, no
   fake home path, no fixture canary string on the page; (k) `summary_lines` still relays a
   summary of fixed words and integers only, with the new clause. Add ONE more class,
   `RsiRealOwnerShapeTests`, decorated `@unittest.skipUnless((PLUGIN_ROOT / "bin" /
   "recursive_improvement.py").is_file(), "the RSI engine is not in this checkout")`: with
   `plugin_root=PLUGIN_ROOT` (this checkout — this repo's own code, the same trust every owner
   test extends) over a synthetic ledger written through the owner's writers, it asserts the
   section renders the inventory's `v` equal to the module's `OUTCOME_INVENTORY_VERSION`, the
   three `counts` keys, and the lineage's `v`; and that `rsi_owner(PLUGIN_ROOT)["state"] ==
   "loaded"`. That class is skipped on a tree without the engine and RUNS at T11's verify
   (the verify's `test -f` guarantees it is not skipped there). It never reads the branch.
6. **`NOTES.md` delta record.** Record: the engine's actual signatures and return keys on
   `main` at dispatch (from `inspect.signature` and one real call over a fixture ledger),
   every place they differed from this brief, the three cap timings and the machine, and the
   `_MODULES`/`ctx` decision as built.

**Acceptance.** Projections come ONLY from the plugin tree's own engine, over
`attempt_ledger.AttemptLedger` objects, and a checkout's engine is still never executed;
every count, label, reason and gate value is the owner's, verbatim, version-gated by
`rsi_record_kind`, with `RSI_UNKNOWN_VERSION` a named constant; unknown counts render
`unknown`, null reasons `null`, booleans as words; nothing is scored, summed, ranked or
re-labelled; every read is behind a named cap whose hit is visible in three places; the
owner's shape differing degrades to a fixed line plus a note, never a guess; T10's sentences
and the skill's RSI paragraph are true of the page as built; `RsiRecordsTests` and
`RsiRealOwnerShapeTests` green (the second not skipped); full suite green; `docs_build check`
exits 0; `NOTES.md` records the binding and the timings.

**Verify.**
```bash
cd "$(git rev-parse --show-toplevel)"
test -f bin/recursive_improvement.py
grep -c "polytropos.rsi-" bin/dashboard.py | grep -qx 1
grep -c 'RSI_UNKNOWN_VERSION = "unknown version, not rendered"' bin/dashboard.py | grep -qx 1
grep -q "RSI_OWNER_ABSENT" bin/dashboard.py && grep -q "RSI_OWNER_SHAPE_DIFFERS" bin/dashboard.py
grep -q "def rsi_owner(" bin/dashboard.py
for cap in MAX_RSI_PROJECTED_LEDGER_BYTES MAX_RSI_LEDGERS_PROJECTED MAX_RSI_INVENTORY_ROWS_RENDERED; do grep -q "\"$cap\"" bin/dashboard.py || exit 1; done
! grep -q "reads no RSI records" bin/dashboard.py skills/dashboard/SKILL.md
grep -q "class RsiRecordsTests" tests/test_dashboard.py && grep -q "class RsiRealOwnerShapeTests" tests/test_dashboard.py
t11_out="$(mktemp)"
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -p 'test_dashboard.py' -k RsiRecords -k RsiRealOwner -v > "$t11_out" 2>&1; rc=$?; tail -5 "$t11_out"; test $rc -eq 0
! grep -q "skipped=" "$t11_out"
python3 - <<'PY'
import importlib.util, tempfile, textwrap
from pathlib import Path
spec = importlib.util.spec_from_file_location("dashboard", "bin/dashboard.py")
db = importlib.util.module_from_spec(spec); spec.loader.exec_module(db)
# The real owner in THIS checkout loads and has the shape the page binds to.
owner = db.rsi_owner(db.PLUGIN_ROOT)
assert owner["state"] == "loaded", owner.get("state")
assert any(name == "OUTCOME_INVENTORY_VERSION" for name, _v in owner["versions"]), owner["versions"]
# A checkout engine that would write a canary is never executed; a fixture plugin tree is called.
with tempfile.TemporaryDirectory() as td:
    root = Path(td); world = db.synthetic_world(root)
    canary = root / "canary"
    eng = Path(world["checkout"]) / "bin"; eng.mkdir(exist_ok=True)
    (eng / "recursive_improvement.py").write_text(
        f"import pathlib\npathlib.Path({str(canary)!r}).write_text('ran')\nraise RuntimeError('executed')\n"
        "CHECKOUT_VERSION = 'polytropos.rsi-checkout/1'\n")
    plug = root / "plug" / "bin"; plug.mkdir(parents=True)
    (plug / "recursive_improvement.py").write_text(textwrap.dedent('''
        OUTCOME_INVENTORY_VERSION = "polytropos.rsi-fixture-inventory/1"
        LINEAGE_VERSION = "polytropos.rsi-fixture-lineage/1"
        def outcome_eligibility_inventory(ledger, captures=(), *, declared_attempt_count=None):
            assert hasattr(ledger, "events"); ledger.events()
            return {"v": OUTCOME_INVENTORY_VERSION, "rows": [],
                    "counts": {"recorded_dispatches": 3, "candidates": 1, "corroborated": 0},
                    "integrity_reasons": ["fixture-integrity-zeta"],
                    "claim_gate": {"eligible": False, "reason": "fixture-gate-omega"}}
        def derived_lineage(ledger, captures=()):
            return {"v": LINEAGE_VERSION, "records": [], "inventory": outcome_eligibility_inventory(ledger)}
    '''))
    out = root / "out"; proj = root / "proj"; proj.mkdir()
    _o, model, receipt, page = db.assemble_build(
        str(world["checkout"]), data_home=str(world["data_home"]), out_dir=str(out),
        flags=[str(world["checkout"])], git=False, projects_dir=str(proj),
        plugin_root=str(root / "plug"))
    assert not canary.exists(), "a checkout engine was executed"
    for needle in ("fixture-integrity-zeta", "fixture-gate-omega", "recorded_dispatches",
                   "polytropos.rsi-fixture-inventory/1", "polytropos.rsi-fixture-lineage/1",
                   "eligible: false"):
        assert needle in page, needle
    assert "Traceback" not in page and "executed" not in page
    rsi = next(p for p in model["panels"] if p["id"] == "rsi")
    assert "projections read for" in rsi["summary"] and "fixture" not in rsi["summary"], rsi["summary"]
print("T11 probe OK")
PY
python3 bin/docs_build.py check
POLYTROPOS_DATA_HOME="$(mktemp -d)" python3 -m unittest discover -s tests -v
```
