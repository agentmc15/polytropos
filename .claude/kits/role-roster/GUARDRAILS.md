# role-roster — kit-scoped fences

These bind only while role-roster tasks run. The repo Invariants in CLAUDE.md apply on
top, always.

- **Extended roles are measured, never mandated.** Absent `roles:` line = the trio,
  today's behavior, in every kit ever written — nothing in this kit changes the default,
  auto-declares a role, or auto-applies a roster recommendation. Evidence advises; the
  human decides between kits, never mid-run.
- **The task-field contract is untouchable.** `roles:` is a PLAN.md line family exactly
  like `autonomy:`/`budget:`. No new task fields, no status-vocabulary change, no new
  NOTES.md line family (the six stay six — `marginal=` is a field on the existing
  `agent:` family, and every quoted grammar token in prose gets backticks).
- **Zero drift on locked surfaces.** The four scorecard byte-goldens, the three 9-key
  card locks, and the `--by-task` needle set must pass UNCHANGED by T1/T2. A failing
  golden means the seam leaked — stop and report; never update a golden to make the
  suite pass. The ONE sanctioned fence replacement is `test_agent_roles_untouched` →
  the new exact-tuple pin (PLAN D1's documented supersession), and the ONE sanctioned
  event-key-lock update is the tripwire case, recorded in NOTES when taken.
- **Honesty labels are load-bearing.** None-not-zero precision; absent-not-zero roles;
  "insufficient sample" below the floor; legacy lines are "marginal unmeasured", never
  marginal=0; dollars only from priced transcripts, bases never summed; escalation
  excluded from the value table; reviewer marginal stated unmeasured. Softening any of
  these is a defect even with green tests.
- **Deflationary adjudication is the law of `marginal=`.** Unsure = not marginal; no
  artifact = not confirmed = never marginal. The execute skill states these verbatim;
  weakening the wording is a defect.
- **Mission boundaries between roles are design, not decoration.** Red-team attacks
  beyond acceptance (never re-runs the verifier's job); security-auditor is fences and
  leaks only; second-verifier must carry a stated different lens; docs-editor writes
  docs only; test-author writes tests only, authored from the BRIEF not the
  implementation; synthesizer writes NOTES prose only and never a machine line. Template
  or skill text that blurs a boundary is a defect.
- **Contract-sensitive edits (T4/T5) are additive-only** — with exactly two sanctioned
  surgical amendments in execute's Agent-ledger section (the ad-hoc-scout sentence and
  the grammar line's role enumeration; fence text corrected at the closing review to
  match the P1-corrected brief, which always named both) — plus any closing-review
  remediation the orchestrator explicitly sanctions with the same surgical scoping —
  and both skills are rechecked against CLAUDE.md's shared-contract bullet after each
  edit, stated in the implementer's report.
- Stdlib-only, unittest only, no real-CLI invocation anywhere, temp fixtures only, no
  network, no hardcoded prices or model-id price claims.
