# Data Leakage Controls

The splitter and checker are deterministic and report-only. Random split is not the only strategy and is not used by default.

## Group Keys

Datasets can be grouped by incident family, root cause, environment, version or scenario. A group remains in one split.

## Checks

`training/leakage_checker.py` reports exact duplicate, scenario duplicate, evidence duplicate, root-cause leakage, environment leakage and version leakage. Near-duplicate token analysis remains a planned extension and must be added before a large benchmark is accepted.

No leakage report is currently accepted as a clean benchmark result because no promoted dataset exists. Current status: `NOT RUN`.
## Phase 4 Gate Status

Leakage checking remains `NOT RUN` for the empty datasets. A passing unit-test suite does not constitute a leakage pass.

Phase 7 remains `NOT RUN` because there are no promoted samples or grouped splits to inspect.
