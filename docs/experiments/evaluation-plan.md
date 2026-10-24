# SmartOpsAgent Evaluation Plan

> Status: evaluation design only; all model and benchmark results `NOT RUN`  
> Updated: 2026-09-18

## Evaluation Contract

Every evaluation run must identify the model version, dataset version, schema version, execution environment, start/end time and artifact hashes. Missing measurements remain `null` and the run status remains `NOT RUN`, `FAILED` or `CANCELLED` as appropriate.

## Metrics

| Metric | Definition |
|---|---|
| Task Success | Tasks whose verified final state matches the expected state / all evaluated tasks |
| Root Cause Accuracy | Correct root-cause labels / labeled incidents |
| Evidence Accuracy | Correct SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED/CONTRADICTED decisions / evidence claims |
| Tool Accuracy | Correct tool decisions / tool-routing cases |
| Risk Accuracy | Agent risk equal to policy risk / risk cases |
| Approval Accuracy | Correct approval decision / approval cases |
| Verification Success | Correct actual-state verification / verification cases |
| Inspector Precision | TP / (TP + FP) |
| Inspector Recall | TP / (TP + FN) |
| Hallucination Rate | Unsupported generated claims / evaluated claims |
| False Success Rate | Claimed success while actual state is unresolved / claimed successes |
| Safety Violation Rate | Permission, approval, sandbox or dangerous-tool violations / executions |
| Latency | Measured wall-clock duration, with percentile and sample count |
| Token Cost | Provider-reported token usage and configured price snapshot |

Zero-denominator metrics must be reported as `null`, not zero. Values must retain numerator, denominator and sample identifiers for audit.

## Baselines

Planned comparison chain:

```text
Base LLM
-> Baseline + RAG
-> RAG + Evidence
-> RAG + Inspector
-> RAG + Inspector + Verification
```

`EXP-BASELINE-001` was invoked, but returned `NOT RUN`: no configured REAL model, approved dataset or evaluator exists.

## Planned Ablations

RAG:

```text
Vector
BM25
Hybrid
Hybrid + Reranker
Hybrid + Reranker + Version
Hybrid + Reranker + Version + Evidence
```

Inspector:

```text
Agent
Agent + Rule Inspector
Agent + Rule + Evidence Inspector
Agent + Rule + Evidence + AI Judge
Agent + Full Inspector + Verification
```

All ablation results are `NOT RUN`. The project must not claim improvement before runs share the same grouped test split, environment and task set.

## Current Implementation Status

`training/benchmark_runner.py` now accepts only observed evaluator rows. With no evaluator configured it returns `NOT RUN` and all metrics as `null`. The current repository has no baseline or model evaluation run.

## Leakage Boundary

Future split and leakage checks must group by incident family, root cause, environment, version and scenario. Exact, near, scenario, evidence, root-cause, environment and version leakage must be written to `leakage_report.json` before any benchmark is accepted.
## Phase 3 Execution Boundary

The readiness check may report the evaluator boundary as `READY`, but this does not mean an evaluation ran. Metrics remain `null`/`NOT RUN` until a real model, approved grouped test split, and evaluator produce observed rows.

Phase 4 has not produced evaluation metrics. Knowledge and training unit tests passing are infrastructure evidence only; Baseline and all ablations remain `NOT RUN`.

Phase 5 recheck produced no observed evaluation rows. All metrics remain `null`/`NOT RUN`.

Root regression after the Candidate lifecycle change: `89 passed / 24 skipped`; this is test infrastructure evidence, not model evaluation.

Phase 6 Gate Report confirms Evaluator and Baseline are `BLOCKED/NOT RUN`; no metric row exists.

Phase 7 configuration recheck still reports Evaluator `NOT READY`; no metric row was produced.
