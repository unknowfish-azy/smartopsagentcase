# SmartOpsAgent Training Readiness Report

- Status: **BLOCKED**
- Created: `2026-11-04T13:33:52.725355+00:00`
- Training started: `NO`
- Secrets included: `NO`

## Checks

| Check | Status | Reason |
|---|---|---|
| requirements | PARTIAL | optional training packages are missing |
| model | PARTIAL | provider and model are configured; run training.scripts.check_model for live connectivity |
| dataset | BLOCKED | no dataset has approved samples and a passing leakage check |
| hardware | READY | storage is available; GPU availability is reported separately |

## Gates

| Gate | Status |
|---|---|
| dataset | BLOCKED |
| model | PARTIAL |
| evaluation | READY |
| sft | BLOCKED |
| preference_optimization | NOT_READY |

`BLOCKED`, `PARTIAL`, `NOT_READY` and `NOT RUN` are truthful environment states; no metric or training result is inferred.
