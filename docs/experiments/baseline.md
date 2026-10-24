# Baseline Evaluation

## Status

`EXP-BASELINE-001` was invoked through the baseline boundary. It returned `NOT RUN` because the repository has no configured REAL model, approved dataset or evaluator.

No baseline accuracy, latency, token cost or capability claim is made.

Phase 3 readiness confirms the baseline remains `NOT RUN`: there is no configured REAL model, approved dataset, or evaluator input. The readiness evidence is recorded in `training/readiness-report.json` and `training/readiness-report.md`.

Phase 5 rechecked the same gate. Provider is `mock`, all Dataset manifests are `DRAFT` with `approved_count=0`, so Prompt Baseline and REAL Baseline remain `NOT RUN`.

Phase 6 unified gate report: `training/training-gate-report.json` and `.md`; `training_allowed=false`.

Phase 7 recheck confirms the same boundary. Configuration check reports LLM `MISSING`; Prompt Baseline and Real Baseline remain `NOT RUN`.

## Required Inputs

```text
REAL or explicitly labeled evaluation dataset
model/provider configuration
evaluator adapter
grouped test split
Inspector and Verification result contract
```

Once these exist, the runner must record model, dataset version, schema version, environment, start/end time, artifact hashes and all metric denominators.
