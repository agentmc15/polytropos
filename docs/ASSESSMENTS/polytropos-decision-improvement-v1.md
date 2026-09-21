# Whole-repository assessment: the decision and improvement work, release 1

- **Assessed revision:** `fd41902a7d0185a0681c23293d72bdc34baf2fcd`
- **Generated at:** 2026-09-20T03:40:14Z
- **Branch:** `codex/decision-improvement-plan`, 39 commits ahead of `main` (`8d1b7be`). **HEAD is not merged**, so nothing here describes a released artifact.
- **Working tree at generation, excluding this report's own files:** `M .claude/kits/decision-improvement-v1/TASKS.md` — the kit's execution status document, owned by the executor. **No finding below depends on its uncommitted content.** This report's own untracked output at generation was `?? docs/ASSESSMENTS/`, named separately so it is not read as pre-existing state.
- **What this document is:** an authored assessment, written by reading this tree and running offline commands against it. It is **not** an attempt record, a telemetry envelope, an evaluation result or a ledger line. Nothing in it was captured by a running engine, and nothing in it should be read as machine-captured evidence.

## How to read a claim's label

Three kinds of statement appear below and they are not interchangeable.

- A statement about **HEAD** is true of the committed revision named above. Almost every finding is one of these, and each evidence row says `read at fd41902` or names the command that was run.
- A statement about **this branch** is true of `codex/decision-improvement-plan` and not of `main`. The entire decision and improvement work is in this class: 39 commits that `main` does not have. An unlabelled branch fact would read as a repository fact, so every finding about work this kit added is a branch fact by construction.
- A statement about **uncommitted state** concerns the 1 working-tree entry named above, outside this report's own output. It is not code, and no finding rests on it.

## Scope and posture

- **Question assessed:** what is the current state of the decision and improvement work across the shared runtime, the four harnesses, the card-and-context surface, and evaluation and release — and is there a bounded next step worth taking?
- **Surfaces included:** `claude`, `codex`, `copilot`, `cursor`, `evaluation_release`, `runtime`, `skills_context`.
- **Surfaces excluded:** generated published pages (human-facing, never model-loaded, and cited nowhere here); any live, paid or networked probe; the full test suite, which this assessment did not run; and any host other than the one these commands ran on.
- **Read-only evidence used:** the tracked tree, plus offline commands that spend nothing — `exec_policy check`, `release_gate check`, `harness_update check`, the three generated-mirror checks, `workflow_eval` read-only verbs against temporary directories, and `improvement_loop demo`. No model CLI was invoked.
- **Evidence not available:** whether any model follows the card's prose; whether a confining, ledgered dispatch would work, there being no such path to run; whether the Cursor, Codex and Copilot hosts discover what the bundles install; and any quality or resource figure for a canary, none having run.
- **Decision requested from this report:** defer activation, and prioritise the two smallest evidence-gathering briefs named at the end.

## Readiness and gain are separated, and only one of them is populated

Readiness is what could be tried next. Gain is what a trial measured. **This report contains readiness statements only.**

What is ready, observed: the canary transition is reachable in code, machine-refuses, and names its own blocker; one bounded command exercises three public symbols of the five decision modules; an OS execution boundary is enforced on this host.

What was gained: **nothing is reported, and nothing is inferred.** No canary has run, no model was dispatched under any of this work, and every quality, resource, intervention or defect figure these functions could assemble today is synthetic-fixture input or an explicit unknown. A mechanism that refuses correctly is not a result. The kit's own records label their evidence `fixture-proves-mechanics-not-safety` and `mechanics-not-performance`; this report does not launder either into achievement.

## Nothing is activated, and this report activates nothing

`bin/workflow_eval.py`'s `CONFINED_DISPATCH_WIRED` is `False`. It is read at call time by the eligibility verdict, whose value is a conjunction over rows one of which reads the flag directly, so no supplied document can make promotion eligible. Observed, not read: `python3 bin/workflow_eval.py activation --prefs-dir <temp>` exits 0 and reports `confining, ledgered dispatch wired: False` with no pointer for any scope. There is no command-line verb that activates anything; the `activation` verb is read-only and says so.

## Baseline and authorities

| Surface | Current owner | Posture at this revision |
| --- | --- | --- |
| `claude` | the skills/ tree is the roster; .claude-plugin/plugin.json declares none. | the card is native. Confined dispatch is recorded verified-unsupported on this harness. |
| `codex` | .codex-plugin/plugin.json points at a directory; the roster is frozen in tests/test_codex_bundle.py. | the card is absent. The manifest cannot disagree with the tree, so manifest validity is not coverage. |
| `copilot` | copilot/aesop.toml primitives.skills, pinned equal to the bundle tree. | the card is absent, by a recorded scope decision rather than a measurement. |
| `cursor` | bin/cursor_adapter.py BUNDLE, applied by bin/harness_select.py. | the card ships. The host-side discovery it depends on is verified-unknown, and Cursor carries the most unknown rows in the registry. |
| `evaluation_release` | bin/workflow_eval.py owns evaluation persistence, proposals, approvals and activation pointers; bin/release_gate.py owns the release surface. | the arms, partitions and approval lifecycle exist as mechanism. No live outcome has been observed, promotion eligibility can never be true at this revision, and the release gate reads the new modules only for version strings. |
| `runtime` | bin/kit_contract.py for the task contract; bin/attempt_ledger.py and bin/attempt_history.py for attempt evidence; bin/safe_paths.py, bin/exec_policy.py and bin/proc_runner.py for the path, boundary and process seams; bin/runtime_data.py for store location. | unchanged and intact. The kit added library modules beside these owners and created no competing authority. |
| `skills_context` | skills/assess-improvement/SKILL.md and its template for the card's own rules; bin/graph_ground.py for the graph seam; bin/docs_build.py for published pages. | the card's vocabulary is closed and parsed from the shipped prose at call time. Graph output stays advisory. The publication surface understates the card's reach. |

No finding below proposes a new authority, and nothing in this report is an engine record.

## Findings, with contradicting evidence held beside each one

### `claude`

*Which behaviour is native, adapted, documented-only, runtime-verified or unsupported here?*

**F07 — The assess-improvement card ships on the Claude surface, and the Claude plugin manifest carries no skill roster -- the skills/ tree is the roster.**

- *Status:* `observed`. *Scope:* skills/, .claude-plugin/plugin.json.
- *Contradicting evidence, or the limit of the claim:* Everything asserted about this card is structural. No test in the repository asserts that a model follows its prose, and the kit's own record says so.
- *Evidence:*
    - `skills/assess-improvement/SKILL.md` — `name: assess-improvement`. read at this revision; one of 15 directories under skills/, counted directly.
    - `.claude-plugin/plugin.json` — `(key set)`. parsed at this revision; its key set is exactly name, description, version, author -- no `skills` key.
    - `tests/test_assessment_skill.py` — `SkillPackagingTests`. read, not run, by this assessment; the roster equality guard that pins the card to exactly the harnesses whose roster lists it.

**F08 — The single blocker holding the activation transition shut has an independently recorded reason on this harness, not merely unfinished wiring: confined dispatch is recorded verified-unsupported for Claude, measured on macOS, because subscription credentials live in a keychain the profile blocks.**

- *Status:* `observed`. *Scope:* primitives/harness-capabilities.json, claude-code only.
- *Contradicting evidence, or the limit of the claim:* The two facts are about different things and must not be merged. The registry row is about dispatching a model under the boundary; the kit's flag is about whether any confining, ledgered dispatch path exists in this repository. Neither implies the other, and the row's date precedes this kit.
- *Evidence:*
    - `primitives/harness-capabilities.json` — `harnesses.claude-code.capabilities.confined_dispatch`. parsed at this revision; product/implemented/verified all `unsupported`, source 'measured on macOS', verified_on 2026-09-06.
    - `primitives/harness-capabilities.json` — `unknown_is_valid`. parsed at this revision; the file's own instruction that a caller needing certainty treats unknown as no.

### `codex`

*Same question, asked separately; no claim transfers from another harness.*

**F09 — The card is absent from the Codex surface. Its roster lives in a test constant rather than in the plugin manifest, which points at a directory, so adding a card there is a test edit in a file the staging task did not own.**

- *Status:* `observed`. *Scope:* codex/skills/, .codex-plugin/plugin.json, tests/test_codex_bundle.py.
- *Contradicting evidence, or the limit of the claim:* The manifest side cannot disagree with the tree, because it names a directory rather than a list. So `Codex plugin valid` is satisfied while the card is absent -- the manifest is not evidence of coverage either way.
- *Evidence:*
    - `.codex-plugin/plugin.json` — `skills`. parsed at this revision; `skills` is the string './codex/skills/', a directory pointer, so discovery grows with the tree.
    - `tests/test_codex_bundle.py` — `EXPECTED_SKILL_STEMS`. read, not run; the frozen roster set, which does not contain assess-improvement. Directory listing of codex/skills/ at this revision: 12 entries, none of them the card.

### `copilot`

*Same question, asked separately; no claim transfers from another harness.*

**F10 — The card is absent from the Copilot surface, whose roster is pinned by an exact set equality between the bundle manifest and the skills tree.**

- *Status:* `observed`. *Scope:* copilot/aesop.toml, copilot/.github/skills/, tests/test_copilot_bundle.py.
- *Contradicting evidence, or the limit of the claim:* Absence here is a scope decision the staging task recorded, not an oversight and not a capability judgement. Nothing was measured about whether the card would work on Copilot.
- *Evidence:*
    - `copilot/aesop.toml` — `primitives.skills`. read at this revision; 13 skill names, none of them assess-improvement, and the tree under copilot/.github/skills/ has the same 13.
    - `tests/test_copilot_bundle.py` — `ManifestSkillsMatchBundleTests`. read, not run; the manifest-equals-tree guard that makes a one-sided addition fail.

### `cursor`

*Same question, asked separately; no claim transfers from another harness.*

**F11 — The card ships on the Cursor surface through the ownership-aware installer, and the very product capability it relies on -- Cursor reading an installed skill file -- is recorded verified-unknown.**

- *Status:* `observed`. *Scope:* cursor/skills/, bin/cursor_adapter.py, primitives/harness-capabilities.json.
- *Contradicting evidence, or the limit of the claim:* Unknown is not unsupported. The row's product and implemented axes both read supported, and the installer's behaviour is well covered; what is unverified is the host's own discovery of the file.
- *Evidence:*
    - `cursor/skills/assess-improvement/SKILL.md` — `name: assess-improvement`. read at this revision; one of exactly 2 directories under cursor/skills/.
    - `bin/cursor_adapter.py` — `BUNDLE`. read at fd41902; a 5-tuple of (source, destination) pairs, two of which are the card and its template.
    - `primitives/harness-capabilities.json` — `harnesses.cursor.capabilities.skill_files`. parsed at this revision; product supported, implemented supported, verified unknown, with the note that discovery by the product is not verified here.

**F12 — Cursor carries the most unknown capability rows of any harness in the registry: 13 of its 19 are verified-unknown, against 4 of 11 for Claude.**

- *Status:* `observed`. *Scope:* primitives/harness-capabilities.json.
- *Contradicting evidence, or the limit of the claim:* A larger unknown count partly reflects a larger declared surface, not a worse one -- Cursor declares 19 capabilities where Copilot declares 9. A ratio across unequal vocabularies is not a ranking.
- *Evidence:*
    - `primitives/harness-capabilities.json` — `harnesses.cursor.capabilities`. parsed and tallied at this revision across all five harness entries.

### `evaluation_release`

*Are baseline, control, candidate, partitions, labels, release claims, rollback and the supported-environment matrix separately evidenced?*

**F16 — The release gate couples to the new modules through one version string each. It executes four of them and calls no function in any, so the gate would still pass with every function in one of them deleted, provided its version constant survived.**

- *Status:* `observed`. *Scope:* bin/release_gate.py.
- *Contradicting evidence, or the limit of the claim:* The coupling is real in one direction the kit proved: bumping a registered constant moves `release_gate check` from 0 to 3, and an import-time error in an executed module breaks the gate. That is genuine coupling to the modules' loadability, just not to their behaviour.
- *Evidence:*
    - `bin/release_gate.py` — `VERSION_SOURCES`. read at fd41902; eight rows name decision_contract, decision_provider, decision_eval and decision_context, each for one constant. decision_policy and improvement_loop have no row.
    - `bin/release_gate.py` — `run_check`. exercised: `python3 bin/release_gate.py check` exited 0 at this revision and reported findings: none.

**F17 — Exactly three public symbols of the five decision modules are reached by a runnable command in this repository. That is readiness to try, and it is not a measured outcome of any kind.**

- *Status:* `observed`. *Scope:* bin/improvement_loop.py, bin/workflow_eval.py, the five decision modules.
- *Contradicting evidence, or the limit of the claim:* The kit's Phase 4 review measured this island as having zero in-edges from the running system. That is no longer accurate: the bounded-draft command reaches two modules. But three exercised symbols out of roughly seventy public ones is a small fraction, and the reached path spends nothing and dispatches nothing.
- *Evidence:*
    - `bin/improvement_loop.py` — `main`. exercised and traced: `improvement_loop demo` exits 0, and instrumenting the module loader shows it reaching decision_contract.parse_bundle, decision_contract.parse_proposal and decision_policy.bundle_ref, plus four contract constants -- three functions in total.
    - `bin/workflow_eval.py` — `build_parser`. traced: none of the five offline verbs demo, activation, policy, approvals or list loads any decision module; the contract is reached only through the bounded-draft path.
    - `bin/decision_provider.py` — `evaluate`. read at fd41902; its three public symbols are reached by nothing in bin/ except the release gate's read of one constant.

**F18 — Two gates disagree on this same tree: the release gate exits 0 while the harness freshness card exits 3. The release gate does not consult installed harness freshness.**

- *Status:* `observed`. *Scope:* bin/release_gate.py, bin/harness_update.py.
- *Contradicting evidence, or the limit of the claim:* This is not a contradiction. They answer different questions, and the exit 3 is pre-existing installed-home staleness the kit's own record attributes to state outside the repository, reproduced against a clean extract of a committed tree.
- *Evidence:*
    - `bin/harness_update.py` — `main`. exercised: `python3 bin/harness_update.py check` exited 3 at this revision, reporting drift for claude, copilot and codex installs with pricing and generated mirrors up to date.
    - `.claude/kits/decision-improvement-v1/NOTES.md` — `D07 -- Protected profile sentinels`. the kit's D07 entry records the exit 3 as pre-existing, proven against a clean archive extract of the committed tree.

**F19 — Whether a whole-task study gates a move to `active` is an open architect decision. The live-run requirement list carries it; the activation gate's own requirements do not.**

- *Status:* `documented`. *Scope:* bin/workflow_eval.py.
- *Contradicting evidence, or the limit of the claim:* Recorded as `documented` rather than `observed` because the gap is plain in the two vocabularies but the resolution is a scope decision nobody has taken. Note also that whichever task takes it, the row stays a caller's assertion: nothing offline can re-derive that a study ran.
- *Evidence:*
    - `bin/workflow_eval.py` — `ACTIVATION_OWN_REQUIREMENTS`. read at fd41902; two requirements, current-evaluation-manifest and predeclared-trial-plan, with no whole-task-study row.
    - `bin/workflow_eval.py` — `live_requirements (line 2692)`. line verified at this revision: the live-requirement row whose owner reads 'a prospective study, separately run'.

**F20 — No policy-bundle store exists. Every seam that takes a bundle reference accepts a well-formed pointer whose target nothing opens, so bundle references carry no origin evidence anywhere.**

- *Status:* `observed`. *Scope:* bin/workflow_eval.py, bin/decision_policy.py.
- *Contradicting evidence, or the limit of the claim:* One neighbouring path does re-derive its digest at the moment the pointer is taken -- the manifest reference read through the command line refuses a rewritten file. So the absence is specific to bundles, not general to references.
- *Evidence:*
    - `bin/workflow_eval.py` — `build_proposal`. read at fd41902; the proposal builder's bundle_ref parameter, which the kit's record states has no caller because there is no bundle store.
    - `bin/workflow_eval.py` — `activation_entry`. read at fd41902; the activation minting function requires a bundle_ref and opens nothing to check it.
    - `bin/decision_policy.py` — `bundle_ref`. read at fd41902; builds the reference; proves shape, never origin.

**F21 — The repository's own no-gain-claim authority refuses this assessment. Exactly one token spelling is responsible, it is the one this kit is named for, and no occurrence of it anywhere in either artifact is a statement about performance. The authority's docstring predicts exactly this outcome.**

- *Status:* `observed`. *Scope:* this report and its JSON, swept through bin/workflow_eval.py.
- *Contradicting evidence, or the limit of the claim:* A returning sweep would not have meant this report claims no gain, and a refusing sweep does not mean it claims one. The check is a token match over spellings and cannot establish absence; it names the spellings it misses, including outperform, uplift, lift, beat the baseline and better than. Those were avoided by authoring, which is a weaker guarantee than a check. Note also that the checkout directory this tree sits in is itself named for the token, so any absolute path quoted in this worktree carries it -- the collision is wider than the kit's own naming.
- *Evidence:*
    - `bin/workflow_eval.py` — `assert_no_gain_claim`. exercised against this report's own text and JSON at this revision; it raised, naming one token. A per-string pass through the same public function then classified every carrying string, each read in context: most carry it only inside an identifier, and the handful that carry it as a bare word either name the body of work assessed or quote a search pattern given as provenance. The figures are in the report's closing section.
    - `bin/workflow_eval.py` — `NO_GAIN_CLAIM`. read at fd41902; the constant that states what a returning sweep does not prove and lists the spellings it does not catch.

### `runtime`

*Which component is authoritative for task lifecycle, admission, budgets, policy identity, evidence, readiness and acceptance?*

**F01 — The canary/active transition refuses, and the refusal is re-derived from this repository's own code at each point that matters rather than read out of a stored verdict.**

- *Status:* `observed`. *Scope:* bin/workflow_eval.py at fd41902; no harness, no host.
- *Contradicting evidence, or the limit of the claim:* A fixture can make every named gate pass, and the kit's tests do exactly that to show each gate is individually reachable. That shows a gate reads what it claims to read; it certifies no host isolation and no model quality. The refusal survives such a fixture only because one row reads the flag directly.
- *Evidence:*
    - `bin/workflow_eval.py` — `CONFINED_DISPATCH_WIRED`. read at this revision, and exercised: `python3 bin/workflow_eval.py activation --prefs-dir <temp>` exited 0 and printed 'confining, ledgered dispatch wired: False' with no pointer for any scope.
    - `bin/workflow_eval.py` — `promotion_eligibility`. read at this revision; the eligibility verdict is a conjunction over rows and one row's re_derived_by names the flag, so no supplied document can make it True.
    - `tests/test_decision_activation.py` — `ProtectedActivationGateTests`. the kit's own positive control: it asserts each named gate is satisfiable and that the transition still refuses. Read, not run, by this assessment.

**F02 — The context-repair policy admits exactly one failure class, and the repository's dispatch classifier cannot emit it. The only route to that class is a driver's NOTES prose projection, not a trusted ledger event.**

- *Status:* `observed`. *Scope:* bin/decision_policy.py, bin/attempt_ledger.py, bin/attempt_history.py.
- *Contradicting evidence, or the limit of the claim:* `attempt_ledger.CLASSES` declares both `model` and `verification`, so the vocabulary looks complete when read on its own. The gap is visible only by reading the classifier's returns.
- *Evidence:*
    - `bin/decision_policy.py` — `REPAIRABLE_FAILURE_CLASSES`. read at fd41902; the tuple is one element, `verification`.
    - `bin/attempt_ledger.py` — `classify_dispatch`. read at fd41902; its returns are infrastructure, None, auth, config, permission, unknown -- never `verification`, never `model`.
    - `bin/attempt_history.py` — `observe (line 296)`. line verified at this revision: it reads `failure_class=failure_class or pairs.get("failure")`, where pairs['failure'] is the driver's NOTES outcome-line string.

**F03 — The field whose whole job is to name how trustworthy a failure class is reports `trusted-event` for a class that arrived through the NOTES prose projection.**

- *Status:* `observed`. *Scope:* bin/decision_eval.py, one expression.
- *Contradicting evidence, or the limit of the claim:* Nothing in production calls this function, so no operator reads the label today. It is a latent defect, not an active one.
- *Evidence:*
    - `bin/decision_eval.py` — `(line 528)`. line verified at this revision: `"failure_class_basis": "trusted-event" if cls else None`, set unconditionally on the presence of a class rather than on its origin.
    - `.claude/kits/decision-improvement-v1/NOTES.md` — `Phase 5 review -- adjudications`. the kit's Phase 5 review recorded this adjacent overclaim and left it to whichever task takes the trigger question; still open at this revision.

**F04 — The decision replay store has no registered home. It is absent from the store registry and from .gitignore, so a caller passing a repository-relative directory would create a tracked store inside the distributed tree.**

- *Status:* `observed`. *Scope:* bin/runtime_data.py, .gitignore, bin/decision_provider.py.
- *Contradicting evidence, or the limit of the claim:* Not reachable today: every storage function takes an explicit caller-supplied store_dir, the module resolves no location and imports no store helper, and nothing in bin/ calls it. The hazard is latent and arrives with the first real caller.
- *Evidence:*
    - `bin/runtime_data.py` — `STORES`. read at fd41902; eight names -- memory, telemetry, journal, benchruns, prefs, trends, attempts, evals -- and no `replay`.
    - `.gitignore` — `(no /replay/ entry)`. searched at this revision for `replay`: zero matches, so a repository-root replay/ directory would be tracked.
    - `bin/decision_provider.py` — `record_result`. read at fd41902; the signature's first parameter is the caller's store_dir and the module never resolves a default.

**F05 — Strength. The repository's single-authority invariants hold across the new work: one path helper, one execution boundary, one process runner, one attempt ledger, and this host enforces a real OS boundary.**

- *Status:* `observed`. *Scope:* bin/safe_paths.py, bin/exec_policy.py, bin/proc_runner.py, bin/attempt_ledger.py.
- *Contradicting evidence, or the limit of the claim:* An enforced boundary is not a confined dispatch. The sentinel battery's own non-guarantee list says the model dispatch is not confined at all, stat on a denied path still succeeds, and nothing is claimed about any other host.
- *Evidence:*
    - `bin/exec_policy.py` — `DEFAULT_PROTECTED_PROFILE`. exercised: `python3 bin/exec_policy.py check` exited 0 on this host at this revision, so an OS execution boundary is enforced here.
    - `bin/exec_policy.py` — `SENTINEL_NOT_PROVEN`. read at fd41902; five named non-guarantees ride in every sentinel report, including that the model dispatch is not confined.
    - `bin/safe_paths.py` — `validate_id`. read at fd41902; the identifier validator the Phase 5 review's traversal finding added to the proposal/approval writers.

**F06 — Every cross-module edge the kit adds is a lazy file-path module load, not an import. A static import audit of bin/ sees no edges at all, so a renamed symbol inside a kit module fails at run time or in tests, never at import.**

- *Status:* `observed`. *Scope:* bin/decision_*.py, bin/improvement_loop.py, bin/workflow_eval.py, bin/release_gate.py.
- *Contradicting evidence, or the limit of the claim:* This is the repository's pre-existing sibling-load idiom, not something the kit invented; bin/ is not a package. The kit's own tests pin several of these reads by patching the owner, which is a stronger check than an import would give.
- *Evidence:*
    - `bin/workflow_eval.py` — `_dc`. derived: searched bin/ for `^\s*(import|from)\s+(decision|improvement)` at this revision and found zero static imports; the edges are accessor functions calling _sibling(...).
    - `bin/decision_policy.py` — `_sibling`. read at fd41902; loads bin/decision_context.py by file path through the same idiom.

### `skills_context`

*Is applicability explicit? Can a card be withheld for contradiction, staleness or no-fit? Are graph and context outputs advisory evidence rather than permission?*

**F13 — The card's report vocabulary is enforced by a checker that parses the shipped card and template at call time, so the rules cannot drift from the prose. The checker lives in a test module and has no production caller.**

- *Status:* `observed`. *Scope:* tests/test_assessment_skill.py, skills/assess-improvement/.
- *Contradicting evidence, or the limit of the claim:* This is a structural guard over an authored corpus and an authored oracle. It proves a report's shape against the card's own stated vocabulary; it observes no model and makes no claim about one.
- *Evidence:*
    - `tests/test_assessment_skill.py` — `review_assessment (line 773)`. read at this revision; defined in a test module, not under bin/, so nothing an engine runs reaches it.
    - `skills/assess-improvement/references/assessment-template.md` — `Evidence ledger`. read at this revision; the statuses, permitted assessments and ranking basis the checker parses out rather than copying.

**F14 — The documentation generator knows three harnesses, not four. Cursor has no generated pages, so the card is published as a Claude-only capability although it ships on two harnesses.**

- *Status:* `observed`. *Scope:* bin/docs_build.py.
- *Contradicting evidence, or the limit of the claim:* This is a publication gap, not a packaging gap: the installed bundle and the roster guards both carry the two-harness fact correctly. It misleads a reader of the published pages, not a caller of the installer.
- *Evidence:*
    - `bin/docs_build.py` — `_HARNESS_SKILL_ROOTS`. read at fd41902; the mapping has exactly three keys -- claude, copilot, codex -- and no cursor entry.
    - `bin/cursor_adapter.py` — `BUNDLE`. read at fd41902; the bundle that does ship the card to Cursor, which the generator does not read.

**F15 — The context-candidate module reads the graph seam rather than becoming a second graph reader, and no path in it invokes the external graph CLI.**

- *Status:* `observed`. *Scope:* bin/decision_context.py, bin/graph_ground.py.
- *Contradicting evidence, or the limit of the claim:* The module's own privacy prevention layer covers path prefixes only, so a credential-shaped suffix is read before its path is judged. What is guaranteed is that neither the path nor its bytes reach the manifest.
- *Evidence:*
    - `bin/decision_context.py` — `_sibling`. read at fd41902; loads bin/graph_ground.py by file path and states in its own header that the seam owns provenance, freshness, impact and search fallback.
    - `bin/decision_context.py` — `DEPENDENCY_TOKENS`. read at fd41902; the keys-only dependency fence, whose tokens include the parallel-safety spellings.

## Strengths, and where this work is a no-fit

**Strengths.** The single-authority invariants held under a large addition: one path helper, one execution boundary, one process runner, one attempt ledger, and no second evaluation writer. Honesty labels are carried as machine-readable codes on the records themselves rather than as prose a reader may skip, and they are unconditional — nothing in the activation or approval sections can discharge one. The no-gain-claim check moved from a test over one fixture into the product, which is the difference between a stated capability and an enforced one. The refusal that matters most is derived from code at three separate points rather than read out of a stored verdict.

**No-fit, stated rather than deferred.** Three things in scope for an assessment of this work are a no-fit for it as built:

1. **A cache of prior decisions is a no-fit.** The replay identity folds in a per-call correlation identifier, so a replay can hit only when a caller re-asks with the very same request object, never when the same situation recurs. That is conservative and safe — a narrower key can only miss — but a caller wiring it expecting a cache will find it abstains. Making it hit across recurring situations changes what identity means and is an architect decision, not an edit.
2. **Automatic recovery from a verification failure is a no-fit today.** The repair policy admits one failure class and the classifier cannot emit it (F02). Even were that closed, the retry capability draws down a budget line that no kit in this repository declares, so every kit would refuse.
3. **Any promotion claim is a no-fit.** There is no bundle store, so a bundle reference carries no origin evidence at any seam that takes one (F20), and promotion eligibility cannot be true (F01).

## Evaluation and release posture

| Item | State at this revision |
| --- | --- |
| Arms | Baseline, control and candidate exist as a specification with a frozen repair dimension. Nothing has run them. |
| Cohort and partitions | Four partition roles with the audit partition single-use; held-out material is refused when quarantine empties the target partition. |
| Labels | Human label sources are declared and read from their owner at call time. No label was collected. |
| Measures | Metric status is three-way, so a sparse sample reports `insufficient-evidence` with the sample count visible rather than a flattering zero. |
| Promotion | Cannot be eligible: the dispatch row re-derives `CONFINED_DISPATCH_WIRED`. |
| Rollback | Two unrelated things share the word. The policy-version restore is reachable from the command line; the activation-pointer rollback is reachable from nothing. Worth disambiguating before either is documented to an operator. |
| Release gate | Exits 0. It reads one version constant per new module and calls no function in any of them (F16). |
| Supported-environment matrix | 31 of 57 capability rows across 5 harness entries are `verified: unknown`, and the file instructs a caller needing certainty to treat unknown as no. Counted at this revision. |

## The next smallest experiment, and why its benefit is uncertain

**Candidate A — give the repair trigger a producer, or record that it has none.** *Hypothesis:* a dispatch that succeeds and whose verification fails can be distinguished from an unclassified failure by a trusted ledger event rather than by a driver's prose line. *Smallest falsifying step:* do not change the classifier. Instead assert, over a real ledger written by one existing driver in a temporary home, which class a verify-failure actually projects and from which source. If it projects `source="notes"` with no class, the trigger has no trusted producer and that is the finding; the honest remedy is then to correct `failure_class_basis` (F03) and to state the gap, not to widen a vocabulary. *Owner:* `bin/attempt_history.py` and `bin/attempt_ledger.py`, which already own classification and projection. *Uncertain benefit:* this buys a correct label and a closed question. It buys no recovery, because even a correct trigger still meets the undeclared budget line above. It is worth doing for the honesty of the record, and its value should not be argued on recovery grounds.

**Candidate B — register the replay store's home, or refuse the store.** *Hypothesis:* the absence of a `replay` entry in the store registry and in `.gitignore` is a latent invariant violation that the first real caller triggers. *Smallest falsifying step:* in a temporary directory, call the record writer with a repository-relative path and observe whether the result would be tracked. If it would, the choice is to register the store with the location helper or to make the writer refuse a path inside the tree. *Owner:* `bin/runtime_data.py` for the registry; `bin/decision_provider.py` for the refusal. *Uncertain benefit:* nothing calls this today, so the change prevents a fault nobody has hit. Its value is that the fault would be silent and would put personal data into a distributed tree, which is the class of defect this repository treats as not negotiable — but it is prevention, and no measurement will show it working.

**Neither candidate needs a provider, a network call, a paid dispatch or an optional dependency.** Both are deterministic and offline. Neither is a promotion, and neither licenses one.

## What this assessment could not assess

- **Whether any model follows the card.** No assertion in this repository is about a model's behaviour, and this report adds none. Every claim about the card is structural.
- **Whether a confined dispatch would work.** There is no such path to run. The registry records the capability verified-unsupported on Claude for a measured credential reason (F08), which is a different fact from the kit's flag and must not be merged with it.
- **Whether the non-Claude hosts discover what the bundles install.** Those rows are verified-unknown and stay unknown until someone runs them.
- **Anything about another host.** All commands ran on one machine.
- **The full test suite.** This assessment did not run it and reports no count from it.
- **Whether the fraction in F17 is stable.** It was measured by instrumenting a module loader on one command path; a verb behind absent state may reach further when that state exists.

## Decision and next handoff

**Decision: evidence collection needed — draft the two briefs above; defer activation.** No finding here supports a promotion, an activation or a policy change, and this report makes none. What would change the conclusion: a trusted producer for the repair trigger, a bundle store with origin evidence, and a dispatch path that both confines and is ledgered — in that order, and each separately evidenced.

## A note on this report's own honesty check

This report's text and its JSON were swept through this repository's own `bin/workflow_eval.py` `assert_no_gain_claim` rather than checked by eye. **The sweep refuses this report.** Exactly one token spelling is responsible: the one this kit, this file and one module under `bin/` are all named for.

A per-string pass through the same public function — deciding nothing itself, and keeping no copy of the token list — classified every string. Measured on this document as finally written:

| Swept strings | Carrying the token | Inside an identifier only | As a bare word | Distinct tokens found |
| --- | --- | --- | --- | --- |
| 945 | 42 | 37 | 5 | 1 |

The identifier occurrences are paths, the kit slug, the card name and a module filename. The bare-word occurrences are of exactly two kinds and no third — each one was read in context, not counted and waved through. Three of them name the body of work this report assesses, in the phrase this repository uses for it. The remaining two are one search pattern, quoted as the provenance of F06 and appearing once in each artifact. **None is a statement about performance.** The prose was written so that the disclaimer above does not need to spell the token in order to disclaim it, which is why no occurrence of that third kind remains to report.

The refusal is the behaviour the function's own docstring predicts: it says it will refuse an honest document whose relayed data happens to carry a token, and that refusing loudly is the direction to prefer over passing quietly. It is recorded as F21 rather than worked around, and nothing was renamed to make the check pass. One further collision is worth knowing: the checkout directory this tree sits in is itself named for the token, so any absolute path quoted from this worktree carries it.

Two limits follow and neither is softened. A returning sweep would not have meant this report claims no gain; shape-matching cannot establish absence. And the spellings the check does not catch — outperform, uplift, lift, beat the baseline, better than, ahead of, efficiency, reduction — were avoided by authoring, which is a weaker guarantee than a check and is stated as such.

