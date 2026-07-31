# GUARDRAILS — telemetry-store (kit-scoped fences; read with PLAN.md before any task)

Absolute rules (money / live tooling / evidence integrity — no judgment calls):

- **NEVER invoke the real `copilot`/`codex`/`claude` CLI from any task, test, or verify
  command** — the snapshot tool imports sibling modules and calls their builders; it shells
  out to NOTHING, ever. Anything that could spend AI Credits or hit the network is a wrong
  change even if it "works".
- **Tests and verify probes never touch the real `~/.claude`/`~/.codex`/`~/.copilot` or the
  real `telemetry/`** — fixtures live in temp dirs passed through `--store-dir` /
  `--projects-dir` / `--codex-home` / `--copilot-home` / `--kits-dir` / direct function
  args. The ONE sanctioned exception is task T9's first real capture, which reads the real
  home dirs strictly read-only and writes ONLY under the repo's gitignored `telemetry/`;
  no other task may do either.
- **The store is written by `bin/telemetry_snapshot.py` only.** No other code — no test
  helper, no journal script, no skill snippet — ever creates or mutates a file under a
  telemetry store dir. Analytics tools stay read-only over their sources.
- **Never fabricate or backdate evidence** (PLAN D5): no hand-authored envelopes, no
  envelope reconstructed from prose/README/NOTES.md, no filename date other than the run
  date, no flag that backdates one. Late capture of a still-existing source is sanctioned;
  reconstruction of an evaporated one is forbidden forever.
- **The store carries aggregates and metadata only — never transcript text** (journal
  digest precedent). A payload embedding message bodies is a defect, whatever it enables.
- **Untouchable files:** `bin/bench_routing.py`, `tests/test_bench_routing.py`,
  `skills/bench-routing/SKILL.md`, `bin/context_weight.py`, `bin/journal_*.py`, every
  pricing file, every skill's YAML frontmatter, every existing kit's NOTES.md. If a change
  appears to require touching one, STOP and report.
- Do not commit or push.

Principles with the signal to read (judgment expected, drift is the failure mode):

- **Parsers degrade, they never guess.** Every degraded read path — missing store dir,
  rogue filename, undecodable JSON, non-dict envelope, unknown source subdir — ends in a
  skip-plus-note or `None`-plus-note, matching `routing_scorecard.read_snapshots`' style.
  The signal you've drifted: an `or 0`, a fabricated `0%`, or an absent source rendered as
  "found nothing" instead of "recorded: absent". Absence of evidence is written down AS
  absence, never as a zero measurement.
- **A snapshot is never more authoritative than the live output it captured.** Envelope
  `labels` are lifted from payload fields, never authored at capture time; `est.`,
  unpriced, API-equivalent, and partial-coverage caveats must survive the round trip into
  the store and back out of `--list`.
- **Additive means a pre-change invocation is undisturbed.** Every existing flag, exit
  code, and byte of markdown/JSON output of the four touched tools must be identical for
  existing invocations; new behavior hangs off new flags and new functions only. The
  signal: any existing test needing an expectation change that is not explicitly sanctioned
  by the task brief.
- **The three harnesses' dollars never merge.** No envelope, summary line, or `--list`
  column ever sums Claude, Codex, and Copilot dollars — one harness, one pricing file, one
  column, and Codex/Copilot dollar figures keep their proxy/estimate labels wherever they
  appear.
- **Verify commands must be able to fail.** Before claiming done, name the concrete repo
  state that would make each verify clause exit non-zero; if there is none, it is
  decoration — replace it with a content assertion. Never write
  `producer | python3 - <<'PY'` (pipe and heredoc both claim stdin): redirect producer
  output to a file first, then probe the file.
