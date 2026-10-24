# SmartOpsAgent Training Readiness Report

- Status: **BLOCKED**
- Created: `2026-09-18T08:16:01.371407+00:00`
- Training started: `NO`
- Secrets included: `NO`

## Checks

| Check | Status | Reason |
|---|---|---|
| requirements | PARTIAL | optional training packages are missing |
| model | PARTIAL | Mock provider is configured; it is not a REAL model baseline |
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
