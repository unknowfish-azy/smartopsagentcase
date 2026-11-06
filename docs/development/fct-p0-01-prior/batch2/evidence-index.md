# 恢复契约答辩证据索引

所有路径相对仓库根 `d:/SmartOpsAgent`。标注 `fixture` 为冻结样例，`loopback` 为 `127.0.0.1` 真实 HTTP，`real` 为真实平台链路（当前未执行）。

## 规范与设计

| 证据 | 路径 | 类型 |
|---|---|---|
| 七对象 schema | `docs/design/recovery-contract-v1/schema.json` | 设计冻结 |
| 语义（三值/窗口/预算/回放/谓词输入） | `docs/design/recovery-contract-v1/semantics.md` | 设计冻结 |
| 路由与证据来源 | `docs/design/recovery-contract-v1/routing-evidence.md` | 设计冻结 |
| 正例与 18 负例 | `docs/design/recovery-contract-v1/examples/` | fixture |
| 候选实现审阅与缺陷处置 | `docs/design/recovery-contract-v1/implementation-review.md` | 审阅记录 |

## 实现

| 模块 | 路径 | 备注 |
|---|---|---|
| 三值求值 + 窗口 | `agent/recovery_contracts/evaluator.py` | 纯函数；R-01/R-08 已修 |
| 只读探针 | `agent/recovery_contracts/probes.py` | 固定 `127.0.0.1`、GET、1s、4KiB |
| 补证调度 | `agent/recovery_contracts/scheduler.py` | 加权覆盖；run 级预算不重置 |
| 回执与失效 | `agent/recovery_contracts/receipts.py` | 非 VERIFIED 强制 `NOT_ISSUED` |
| 同证据回放 | `agent/recovery_contracts/replay.py` | 无网络/时钟/LLM |
| 前端三张卡 | `frontend/src/components/operations/recovery/` | 固定 schema，fixture 数据 |

## 运行与实验

| 证据 | 路径 | 类型 |
|---|---|---|
| N08 独立 oracle 实验（42 案例 / 5 判定器） | `scripts/research/recovery_contracts/{independent_oracle.py,run_experiments.py}` | fixture |
| N08 结果摘要 | `.runtime/n08/summary.md`、`.runtime/n08/report.json` | fixture |
| N08 报告 | `docs/evaluation/recovery-contracts/n08-report.md` | 报告 |
| HC-11 loopback 演示 | `scripts/research/recovery_contract_demo.py` | loopback |
| HC-11 运行证据 | `.runtime/hc-11/summary.md`、`.runtime/hc-11/run.json` | loopback |
| 后端测试 | `tests/recovery_contracts/` | 219 passed / 1 skipped |
| 前端组件测试 | `frontend/test/recovery/recoveryCards.test.mjs` | 9 pass |
| 集成审查记录 | `docs/development/原创创新实施记录.md` | 审查 |

## 平台与门禁（未通过项）

| 证据 | 路径 | 状态 |
|---|---|---|
| 平台接入映射 | `docs/design/recovery-contract-v1/platform-integration.md` | BLOCKED |
| 安全审计 | `docs/security/audit-20261105/` | 仅审计，未修 |
| 质量门禁 | `docs/release/quality-gates-20261105/` | 设计 |
| 基线盘点 | `docs/audit/20261105/` | DONE |
