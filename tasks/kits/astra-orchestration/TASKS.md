# Tasks — Astra orchestration

## Phase 1 — Policy and execution

### T1 — Central routing policy and Codex pricing

- id: T1
- title: Central routing policy and Codex pricing
- status: done
- model: strong
- depends: none
- independent: no

**Brief.** Create bin/codex_policy.py as the shared role-aware authority and integrate bin/codex_pricing.py and bin/bench_routing.py. Store orchestrator/worker roles, availability, efforts, screenshot-derived rates, cache categories, and request thresholds in data/pricing.codex.json. Ordinary and verification assignments must exclude the reserved orchestrator; legacy pins migrate safely; missing required models fail closed. Prove valid workers and evidence-only recovery eligibility with synthetic tests.

**Acceptance.** Central enforcement and relevant automated regression tests pass, with limitations stated honestly.

**Verify.**

```bash
python3 -m unittest discover -s tests -p "test_codex*.py"
```

### T2 — Execution, evidence-gated recovery, and actual-use records

- id: T2
- title: Execution, evidence-gated recovery, and actual-use records
- status: done
- model: strong
- depends: T1
- independent: no

**Brief.** Integrate the central policy into bin/codex_execute.py. Dispatch ordinary tasks to workers, retain dependency/budget checks, gate reserved recovery on driver-observed failure, and record each attempt plus evidence, correction scope, and verification. Preserve planned pins separately from requested and independently observed use. Sol reviews and Astra accepts current evidence read-only; later changes invalidate earlier acceptance. Test injected runners only; no live CLI model calls.

**Acceptance.** Central enforcement and relevant automated regression tests pass, with limitations stated honestly.

**Verify.**

```bash
python3 -m unittest discover -s tests -p "test_codex*.py"
```

### T3 — Independent harness pricing and usage consumers

- id: T3
- title: Independent harness pricing and usage consumers
- status: done
- model: strong
- depends: T1
- independent: no

**Brief.** Update the independently owned Codex/Copilot pricing and usage consumers plus journal/context adapters. Transcribe applicable screenshot rates separately into each harness source. Preserve inclusive observed input counts while pricing uncached, cached-read, and observed write categories without double counting. Apply long-context rates only when per-request size is known and expose aggregate limitations. Keep Claude rates unchanged and historical benchmark measurements intact.

**Acceptance.** Central enforcement and relevant automated regression tests pass, with limitations stated honestly.

**Verify.**

```bash
python3 -m unittest discover -s tests -p "test_codex*.py"
```

### T4 — Application integration and role-aware discovery

- id: T4
- title: Application integration and role-aware discovery
- status: done
- model: strong
- depends: T1, T2
- independent: no

**Brief.** Add bin/codex_app_policy.py plan/status/apply commands with explicit repository, Codex-home, backup, and observed runtime-model inputs. Preserve custom configuration; materialize runtime-derived defaults and verifier roles; protect ownership, symlinks, and rollback including the ownership manifest. Integrate existing harness diagnostics and reinstall handling so centrally owned pins remain intact. Test temporary homes and then read-only live management evidence without model dispatch.

**Acceptance.** Central enforcement and relevant automated regression tests pass, with limitations stated honestly.

**Verify.**

```bash
python3 -m unittest discover -s tests -p "test_codex*.py"
```

### T5 — Skill guidance, migration, examples, and generated documentation

- id: T5
- title: Skill guidance, migration, examples, and generated documentation
- status: done
- model: mid
- depends: T1, T2, T3, T4
- independent: no

**Brief.** Update native Codex skills, canonical agent instructions, migration guidance, examples, and generated mirrors for the central policy. Preserve existing documentation contracts and distinguish package readiness from observed runtime activation. Explain safe legacy pins, reserved recovery, planned/dispatched/observed records, costing provenance, and the direct-host enforcement boundary. Regenerate Codex and Copilot documentation using their respective sources and recorded generation preferences.

**Acceptance.** Central enforcement and relevant automated regression tests pass, with limitations stated honestly.

**Verify.**

```bash
python3 -m unittest discover -s tests -p "test_codex*.py"
```
