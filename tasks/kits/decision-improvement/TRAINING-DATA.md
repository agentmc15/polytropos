# Training-data preparation — Release 1 infrastructure

## Purpose and authority

D31–D34 set up collection and export for a future small open-weights specialist. They are mandatory V1 infrastructure tasks, not a model-training job. Begin with failure classification. Snapshot capture can be used in eligible authorized runs once implemented; enabling capture must have a declared collection scope and retention policy. Do not silently backfill private transcripts or upload data to a provider. Building the feature does not authorize a training run, paid collection, Jev calls or deployment. Existing explicit authorization applies to its actual scope.

These tasks run before the V1 handoff and before the first live improvement experiment. Keep the original D01–D30 IDs stable; appended IDs D31–D34 are scheduled by dependencies, not numeric order. The native Claude TASKS.md owns execution status. Synthetic fixtures prove mechanics, not model quality or data sufficiency.

## Minimum example contract

Every record has an example ID, schema version, source attempt/decision references, task/defect group, repository revision and capture boundary. Preserve data already owned by attempt_ledger, runtime_data, decision contracts and partition/exposure storage through references; do not introduce a competing execution ledger. Use an optional bin/training_data.py for validation, adjudication and derived dataset exports, with immutable bounded artifacts owned by the existing private-store authority. Raw transcript logging is not required.

| Record | Required fields and semantics |
| --- | --- |
| Decision-time input | Timestamp and sequence/event boundary; bounded task statement, relevant code/context, observed error and tool state, available constraints; field provenance and evidence artifact hashes; exact decision question and schema/taxonomy version |
| Cause target | Reviewed label or explicitly unresolved/unknown/multiple-cause status; primary and contributing causes when supported; evidence references, label method, reviewer identity, disagreement and resolution history |
| Subsequent action/outcome | Action actually attempted, permitted alternatives if known, verification evidence, success/failure/unknown, retries and human intervention; distinguish observed outcome from an optimal-action label |
| Reproducibility | Harness, requested/dispatched/observed model identity, prompt/policy/code versions, capture and labeling tooling versions; absent old fields stay unknown |
| Resources | Existing usage records and basis, elapsed time, review effort and completeness; preserve estimates, measured use, subscription proxies and unknowns separately |
| Eligibility | Owner-approved collection/use scope, permitted training/export purpose, source/license restrictions, redaction status, retention/expiry and revocation state; unknown eligibility excludes export |
| Dataset placement | Related-task group, development/calibration/promotion/final-audit partition identity and version, exposure history, dataset membership and split-assignment version |

Input and label are different artifacts. Later reproduction or review may establish a cause, but cannot alter the historical input snapshot. Never place a later successful patch, reviewer diagnosis, future test result or reference answer in the deployed model's training input if unavailable at decision time. Missing historical snapshots are not reconstructed as exact observations. Exclude unsafe examples or explicitly segregate them from fine-tuning-ready exports.

## Labeling and collection behavior

Start with a versioned taxonomy: environment/infrastructure, missing context, implementation error, configuration/permission, multiple causes and unknown. D31 must reconcile overlap with existing failure classes; keep root cause distinct from symptoms such as a nonzero test exit. Define inclusion rules, counterexamples and an abstention policy before labeling. Preserve the original operational classification as an observation, not an adjudicated target.

Review disputed causes, record correction history, and exclude unresolved disagreements from supervised targets unless the selected task explicitly models ambiguity. A model or Jev suggestion is a candidate label, never independently verified truth. Use real evidence such as reproduction, tool failure stage and independent review. Successful attempts may provide negative/no-failure examples only under a compatible explicitly defined question; do not force them into a failure-cause taxonomy.

Retain eligible failures, successful recoveries, abstentions, censored outcomes and human corrections. Capture selection/sampling policy and counts for included, dropped, redacted and unlabeled examples, including exclusions by cause. Avoid success-only training or equating untried proposals with failures. A recovery that succeeded is not proof it was the best recovery; learning action choice requires controlled alternative trials or appropriately qualified evidence. Experiment-ranking labels require observed experiment outcomes and full cost, not the proposer’s enthusiasm.

## Partition, privacy and export rules

Use V1 grouped immutable partitions and exposure records. All retries, near-duplicate snippets, related defects and derivative/synthetic variants share an assigned group; record detection method and unresolved grouping uncertainty. Dataset construction only reads authorized development material; keep calibration, promotion and final audit inaccessible to training exporters. A future protocol may use explicitly separate development validation splits, but must never relabel final-audit material as training while preserving an independent-audit claim. Record feedback exposure as well as raw access.

Redact before persistence, use bounded allowlisted fields, and fail closed when content cannot be retained safely. Keep artifacts outside commits, docs, packages and public telemetry under private-store controls. Export only with explicit purpose/destination eligibility. Withdrawal or expiry excludes future exports, invalidates affected manifests, and identifies downstream training artifacts; deleting a file does not prove removal from already trained weights. Preserve only permitted minimal revocation provenance, never secrets in tombstones. No external transfer is part of V1.

Create deterministic local JSONL examples and a versioned manifest: input and target schema, example/content hashes, source IDs, label versions, permitted-use metadata, grouping/split versions, exclusions, dataset statistics, exporter version and parent dataset. Keep label rationale/provenance out of model inputs. Separate training payload from audit metadata and protected evaluators. The manifest identifies content; it does not establish access enforcement. Refuse missing sources, stale labels, revoked eligibility, ambiguous groups crossing splits and future-information leakage.

## Readiness and later training

Produce a data-readiness report with label agreement, category coverage, unknown/exclusion rates, sampling bias, duplication, partition/exposure checks, provenance completeness and resource coverage. Do not invent a minimum sample count or claim training readiness from fixture counts. Use a pilot and learning curves on separate development validation to choose a collection target; preserve protected final evaluation.

The operator handoff must show a local example from authorized synthetic data: capture → label/review → assign eligible development group → validate → export → inspect manifest → revoke and refuse re-export. Document feature-disabled behavior and commands for enabling scoped capture in future authorized runs. No credentials, model downloads, training, deployment or real private-data collection are required for this demonstration.

Later training must bind parent checkpoint, dataset manifest, training recipe/software/seed, compute budget and outcome to RSI generation lineage. V1 prepares this interface but does not implement a trainer or assert gains. Context ranking, recovery choice and experiment selection require separately validated targets; failure-classification data cannot silently become labels for those jobs.
