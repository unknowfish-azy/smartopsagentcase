# SmartOpsAgent Training Plan

> Status: Phase 1 Dataset Schema completed; model training `NOT RUN`  
> Updated: 2026-09-18

## Objective

The training system teaches evidence-based, version-aware, risk-controlled and verifiable operations behavior. It does not optimize ordinary conversational style and does not expose hidden Chain-of-Thought. Training outputs use concise, auditable reasoning summaries.

```text
Task -> Environment -> Knowledge -> Evidence -> Reasoning Summary
     -> Plan -> Tool -> Risk -> Approval -> Execution
     -> Verification -> Inspector -> Final Result
```

## Phase Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Dataset Schema | COMPLETED |
| 2 | Data Validator | COMPLETED (legacy-compatible + Schema v1 semantic gate) |
| 3 | Synthetic Incident | COMPLETED (candidate generator only) |
| 4 | SFT Dataset | COMPLETED (candidate builder) |
| 5 | Preference Dataset | COMPLETED (candidate builder) |
| 6 | Evidence / Inspector Dataset | COMPLETED (candidate builders) |
| 7 | Train / Validation / Test Split | COMPLETED (deterministic grouped splitter) |
| 8 | Leakage Check | COMPLETED (report-only checker) |
| 9 | Benchmark Runner | COMPLETED (observed-results boundary) |
| 10 | Baseline Evaluation | NOT RUN (no model evaluator configured) |
| 11 | SFT Training | NOT RUN (dry-run config only) |
| 12 | Preference Optimization | NOT RUN (dry-run config only) |
| 13 | Inspector Evaluation | NOT RUN |
| 14 | OpsBench | NOT RUN |
| 15 | Model Registry | COMPLETED (PLANNED/NOT RUN lifecycle guard) |
| 16 | Agent Integration | NOT RUN |
| 17 | Ablation Study | COMPLETED (matrix declared; execution NOT RUN) |

## Phase 1 Artifacts

- `training/schemas/smartops-training-sample.schema.json`: unified sample envelope and task-specific structured outputs.
- `training/schemas/dataset-manifest.schema.json`: dataset identity, version, source, sample count, hash and split metadata.
- `training/schemas/catalog.json`: stable registry for schemas, dataset types and source types.
- `training/schema_registry.py`: read-only loader with catalog lookup and path traversal protection.

Schema version `1.0.0` requires every sample to carry:

- stable sample and dataset identity;
- task type and dataset type;
- environment, knowledge and evidence context;
- policy, expected behavior, structured output, verification and inspector fields;
- source provenance and `REAL` / `SYNTHETIC` / `DEMO` classification;
- quality state and grouped-split metadata keys.

## Training Roles

| Role | Primary dataset task |
|---|---|
| Ops Reasoner | `OPS_REASONING` |
| Evidence Verifier | `EVIDENCE_VERIFICATION` |
| Tool Router | `TOOL_SELECTION` |
| Inspector Judge | `INSPECTION` |

One model is not assumed to perform every role. Role-specific training and evaluation remain separate until real experiments justify combination.

## Hardware And Dependencies

Phase 1 uses Python's standard library only. Transformers, Datasets, PEFT, TRL and PyTorch are not installed by this phase. CPU/CUDA/GPU training parameters will be introduced only with an approved real training run. No GPU availability, loss, duration or trained artifact is claimed.

## Data Promotion Rule

```text
Generator -> Schema Validation -> Rule Validation -> Knowledge Validation
          -> Deduplication -> Safety Validation -> Inspector
          -> Human Sampling -> Versioned Dataset
```

A schema-valid sample is still `DRAFT` or `PENDING`; it is not automatically trainable.

## Implemented Foundations

- `training/dataset_validator.py`: legacy formats plus Schema v1 semantic checks for provenance, evidence ranges, risk/approval consistency and REAL/SYNTHETIC/DEMO separation.
- `training/synthetic_incidents.py`: ten deterministic incident families with hard cases; candidates remain in memory.
- `training/dataset_builders.py`: SFT, Preference, Evidence and Inspector candidate conversion with pending quality status.
- `training/dataset_splitter.py`: deterministic grouped splits.
- `training/leakage_checker.py`: exact, scenario, evidence, root-cause, environment and version leakage report.
- `training/benchmark_runner.py`: observed-result-only metric computation; no evaluator means `NOT RUN`.
- `training/training_pipeline.py`: CPU/CUDA/GPU config validation and dry-run only.
- `training/model_registry.py`: a model cannot become `TRAINED` without an artifact and completed evaluation.
- `training/ablation.py`: RAG and Inspector ablation matrices with `NOT RUN` metrics.

The current repository contains no promoted training dataset, trained model artifact, baseline result, benchmark result, loss, accuracy, GPU run or model capability claim.
## Phase 3 Readiness Gate（2026-09-18）

已实现 `training/readiness/` 检查入口：

```powershell
python -m training.readiness
```

当前真实报告为 `BLOCKED`：7 个 Dataset 均 `DRAFT`、`approved_count=0`；`.env` 配置的是 Mock 而非 REAL 模型；PyTorch 可用但 Transformers/Datasets/PEFT/TRL 缺失；CUDA/GPU 不可用。报告文件为 `training/readiness-report.json` 和 `training/readiness-report.md`。

## Phase 4 Test Infrastructure

Knowledge 单元测试现已建立并通过 `13 passed`。训练测试通过项目内 `tmp_path` 夹具规避受限 Windows 系统临时目录，当前 `tests/training` 为 `33 passed`。这只表示数据/训练基础设施测试通过，不代表 Baseline 或模型训练已执行。

SFT Gate 必须同时满足 Dataset READY、Model READY、Leakage PASS、Safety PASS 和 Split READY；本次未启动训练。

## Phase 6 Training Gate

统一门禁报告由 `python -m training.gate_report` 生成，当前为 `BLOCKED`，`training_allowed=false`。该命令只汇总现有报告，不会创建或批准样本，也不会调用模型。

## Phase 7 Gate Recheck

首轮复核仍为 `BLOCKED`：7 个 Dataset 均 `DRAFT`、Approved Samples=0、Split=0/0/0；当前 Provider 为 Mock，Evaluator 未就绪，训练依赖不完整，CUDA/GPU 不可用。训练和 Knowledge 测试分别为 `36 passed` 与 `13 passed`。在真实数据、人工审核和真实模型配置完成前，不进入 Baseline。
