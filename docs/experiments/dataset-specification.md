# Dataset Specification

## Status

Schema v1 is implemented and registered in `training/schemas/catalog.json`. The current `data/training/*/manifest.json` files are `DRAFT` with zero promoted samples.

## Common Envelope

Every approved sample must identify:

```text
sample_id
dataset_id
dataset_version
schema_version
dataset_type
task_type
instruction
environment
knowledge
evidence
agent_context
policy
expected_behavior
output
verification
inspector
source
quality
metadata
```

`source` must contain `source_type`, `source_ref`, `created_at` and `data_class`. `data_class` is one of `REAL`, `SYNTHETIC`, `DEMO`; it is never inferred from the text.

## Dataset Roles

| Dataset | Task role | Required decision surface |
|---|---|---|
| SFT | Ops Reasoner | diagnosis, evidence, plan, tool, risk, approval and verification |
| Preference | Preference Ranking | chosen, rejected, reason and principles |
| Evidence | Evidence Verifier | support label, reason, evidence references and confidence |
| Inspector | Inspector Judge | decision, category, severity, issues and recommendation |
| Tool Call | Tool Router | environment-aware tool selection and rejection |
| Safety | Safety Judge | permission, risk, approval and safe alternative |
| Verification | State Verifier | SUCCESS, FALSE_SUCCESS, FAILED or UNKNOWN |

## Promotion

Candidates remain `PENDING` until Schema, rule, safety, knowledge, deduplication, grouped split, leakage and human review gates pass. Only `APPROVED` samples may enter a READY manifest.
## Phase 5 Candidate Promotion Gate

Candidate 必须按以下状态顺序流转：

```text
CANDIDATE → VALIDATED → QUALITY_CHECKED → SAFE → REVIEW_PENDING → APPROVED
```

失败状态为 `INVALID`、`UNSAFE`、`DUPLICATE`、`LEAKAGE`、`REJECTED`。自动收集不会自动批准；`training/candidate_lifecycle.py` 仅在 Human Review 和样本 `quality.human_review` 同时为 `APPROVED` 时允许晋级。
