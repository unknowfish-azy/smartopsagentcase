# N08：独立 oracle × 强基线可证伪实验报告

## 1. 目的

验证 `agent/recovery_contracts` 的三值恢复判定是否只靠“HTTP 成功 / 自检 passed / 有观测”就会产生假恢复，并检查实现与一个**不依赖实现代码**的 oracle 在同一批案例上的差异。

本实验不修改 `agent/recovery_contracts` 下任何文件，不新增依赖，不联网，不启动平台服务，不运行 git 写操作。

## 2. 方法

### 2.1 独立 oracle

位置：`scripts/research/recovery_contracts/independent_oracle.py`

- 只 import 标准库（`json`、`hashlib`、`dataclasses`、`datetime`、`re`、`typing`）与仓库内的 schema/semantics 常量。
- 不 import `evaluator`、`receipts`、`probes`、`scheduler`、`replay`；不引用 `PREDICATE_REGISTRY`。
- 自行实现：canonical JSON / digest、三值求值、资格判定（目标 / 版本 / 新鲜度 / 轮次 / 来源组 / scope / 采集器注册 / 重复 ID）、空义务拒绝、反例优先、采样窗口。
- 输出逐义务 verdict、整体 verdict、原因码、窗口原因与拒绝证据，字段与实现可比。

### 2.2 五个判定器

同一批冻结证据上运行：

1. `independent_oracle`：本报告第 2.1 节。
2. `implementation`：`agent.recovery_contracts` 的 `RecoveryContract` + `evaluate`。
3. `baseline_any_200`：任意一条观测 payload 带 HTTP 200 即判 VERIFIED。
4. `baseline_passed_true`：任意一条观测 payload 的 `passed=true` 或 `state_verifier_passed=true` 即判 VERIFIED。
5. `baseline_any_observation`：每个必需义务只要出现任意一条同来源组观测即视为满足，忽略 target / scope / round / revision / payload 值 / 时效 / 窗口。

说明：第 3、4 节把“强基线”理解为“工程上常见、但语义很弱的放行规则”；它们不是经过调优的正式判定器。

### 2.3 案例构成

- 总数：**42**
- 来自 `docs/design/recovery-contract-v1/examples/`：**19**（18 个 negative + 1 个 positive）
- 构造案例：**23**（200+passed+业务 false、过期、旧 binding、r17/r16、错目标、跨 scope、重复 ID、缺采样组、TTL / 偏斜 / 间隔闭区间边界、空义务、可选义务 false、多 target 窗口等）

执行顺序固定：先按文件名排序的 examples，再按代码中固定顺序追加构造案例；无随机数。

对 7 个使用占位谓词或占位 digest 的样例，实验只做**可执行化**：把 `PRED-A-BUSINESS-SELFCHECK` / `PRED-B-TRANSACTION-PROBE` 映射为 `business_health_flag(field=predicate_result)`（空义务样例没有谓词，只重算 digest），并按 schema 规范重算 contract / claim / artifact 摘要。缺陷语义（时间、轮次、scope、来源组、重复 ID、错误码）不改。

## 3. 指标（全部为分子/分母）

| 判定器 | 假 VERIFIED / 总数 | 假 VERIFIED / oracle 非 VERIFIED | 漏判 CONTRADICTED / oracle CONTRADICTED | 与 oracle verdict 一致 | 原因码集合一致 | 探针调用 |
|---|---:|---:|---:|---:|---:|---:|
| independent_oracle | 0 / 42 | 0 / 35 | 0 / 6 | 42 / 42 | 42 / 42 | 0 / 42 |
| implementation（修复前） | 1 / 42 | 1 / 35 | 0 / 6 | 40 / 42 | 37 / 42 | 0 / 42 |
| implementation（修复后） | 0 / 42 | 0 / 35 | 0 / 6 | 42 / 42 | 39 / 42 | 0 / 42 |
| baseline_any_200 | 21 / 42 | 21 / 35 | 6 / 6 | 15 / 42 | 11 / 42 | 0 / 42 |
| baseline_passed_true | 17 / 42 | 17 / 35 | 6 / 6 | 19 / 42 | 11 / 42 | 0 / 42 |
| baseline_any_observation | 33 / 42 | 33 / 35 | 6 / 6 | 9 / 42 | 11 / 42 | 0 / 42 |

补充：

- 实现与 oracle 逐义务值一致：**43 / 44**。
- 三条基线不产生原因码，因此它们的“原因码集合一致”主要统计 oracle 原因为空的案例，不能与实现的 39/42 直接横向比较。
- R-12/R-13（绑定与授权收紧）后，verdict 与 oracle 完全一致（42/42），但原因码粒度在 3 个案例上不同：实现用 `STALE`/`MISSING` 表示“归属不可确认”，oracle 用上层的 `CONFLICT`/`MISSING` 组合。
- oracle 与样例/构造标签 verdict 一致：**42 / 42**；样例给出的原因码在 oracle 原因码（含窗口原因）中出现：**31 / 31**。构造案例的 expected_verdict 是本实验按语义写下的预期，不是人为标注语料。
- “探针调用”在本实验恒为 0：四者均为冻结证据回放，不调度真实探针。该列不能用于评价在线探针成本。

## 4. 发现的假恢复与差异

### 4.1 实现：多 target 窗口被判成有效 A/B（R-08，已修复）

案例：`divergence-multi-target-window`

- 契约 `target=service:edge-nginx`，`source_groups=[sg-a, sg-b]`。
- 义务 A 只采集 `sg-a`，target 为 `service:edge-nginx`；义务 B 只采集 `sg-b`，target 为 `service:b`。
- 两个义务各有 3 条业务 TRUE 观测，时间偏斜满足窗口。
- 修复前实现：窗口按 source_group 直接配对，**未检查同组 A/B 的 target 是否相同**，因此把两个无关服务的观测当成 A/B 窗口，输出 **VERIFIED**。
- 独立 oracle：按 `semantics.md` §4.2“同组 A/B 同 target”，`service:b` 观测不能进入 `service:edge-nginx` 的契约窗口，输出 **INSUFFICIENT / MISSING**。

这是本批案例中实现相对 oracle 产生的**唯一 1 个假 VERIFIED**（1/42，1/35）。

处置（R-08，P0）：

- `agent/recovery_contracts/evaluator.py::evaluate_window` 增加同组 target 一致性检查，不一致的候选组不进入有效窗口。
- 同步修复窗口原因码不可见：`Evaluation.reason_codes()` 在 verdict 为 `INSUFFICIENT` 且窗口未满足时并入 `window.reasons`（见 §4.3）。
- 回归测试：`tests/recovery_contracts/test_independent_oracle.py::test_multi_target_window_is_rejected` 断言实现判 `INSUFFICIENT`、窗口不满足且原因码含 `MISSING`。
- 修复后复测：实现假 VERIFIED **0/42（0/35）**，与 oracle verdict 一致 **42/42**；原因码集合一致 **39/42**（差异集中在“归属不可确认”的表达粒度）。

### 4.2 实现：单来源组内部冲突被直接判 CONTRADICTED

案例：`negative-source-conflict`

- 同一来源组内同时出现 `predicate_result=true` 与 `predicate_result=false`，且样例 `context` 注明 `source_identity_confirmed=false`。
- oracle 用“义务只要求一个来源组”作为“没有独立来源可确认反例”的保守代理，判 **INSUFFICIENT / CONFLICT**。
- R-09 修复前，实现没有“身份未确认”的输入通道，直接按反例优先判 **CONTRADICTED**。
- R-09 修复后（身份/来源未确认的矛盾只构成 UNKNOWN），实现同样判 **INSUFFICIENT**，与 oracle 收敛；差异仅剩原因码粒度（实现 `MISSING`、oracle `CONFLICT`）。

这不是假恢复；V1 schema 仍没有承载“来源身份是否已确认”的字段，原因码对齐需要该字段落地。

### 4.3 窗口原因码已并入结论（R-08 附带修复）

`boundary-skew-1251`、`boundary-gap-4001`、`boundary-next-gap-1999`、`divergence-multi-target-window` 四个案例：

- 两者 verdict 都是 INSUFFICIENT；
- oracle 在 `window.reasons` 报 `MISSING`；
- 修复前实现 `evaluation.reason_codes()` 返回空集合，因为窗口失败原因没有进入整体原因码；
- 修复后 `Evaluation.reason_codes()` 在 `INSUFFICIENT` 且窗口未满足时并入 `window.reasons`，实现与 oracle 的原因码集合一致率由 37/42 提升到 41/42。

该修复只影响结论层原因码展示，不改变逐义务三值，也不改变 `CONTRADICTED` 的主导地位（`CONTRADICTED` 时不追加窗口原因）。

### 4.4 弱基线的假恢复

- `baseline_any_200`：21/42 假 VERIFIED；能放行 `negative-different-round`、`negative-duplicate-observation-id`、`negative-window-missing-sample`、`negative-source-conflict` 等。
- `baseline_passed_true`：17/42 假 VERIFIED；能放行过期、旧 binding、r16 反例、错目标、跨 scope、缺采集器、重复 ID、窗口偏斜/间隔失败等。
- `baseline_any_observation`：33/42 假 VERIFIED；几乎只要“有观测”就放行，包括 malformed、timeout、future timestamp、反例和缺组。

三者在 oracle 判 CONTRADICTED 的 6 个案例上全部漏判（6/6）。

## 5. 可重复性与验证

```powershell
python scripts/research/recovery_contracts/run_experiments.py
python -m pytest tests/recovery_contracts -q -p no:cacheprovider --tb=short
```

- 实验脚本退出码：0。
- 产物：`.runtime/n08/report.json`、`.runtime/n08/summary.md`。
- 测试：`tests/recovery_contracts/test_independent_oracle.py` 共 11 项；其中 1 项为 R-08 回归（多 target 窗口应被拒绝），1 项仍为显式分歧记录（单来源组冲突）。
- 本机全量 recovery 测试：**219 passed / 1 skipped**。该数字包含本任务新增的 11 项；工作区存在并行改动，因此与交接书里的 205 passed / 1 skipped 不能直接相减对齐。

## 6. 局限与 UNKNOWN

1. **未做真实平台**：全部为冻结证据回放，没有启动 Inspector、StateVerifier 或任何平台服务；没有真实网络/探针证据。
2. **未做人为标注语料**：expected_verdict 来自 docs 样例标签与本实验构造时的语义预期；42/42 的一致不能当作“人工金标准”准确率。
3. `negative-missing-field` 的 defect 文本称“键缺失，不是 null”，但 JSON 实际写的是 `"observed_revision": null`。实验按 defect 文本删除键；若保留 null，按 semantics §3.2 会得到 UNDETERMINED/MISSING，而不是 MALFORMED。
4. `source_identity_confirmed` 只存在于样例 `context`，V1 schema 没有字段承载。oracle 的“单来源组冲突 → UNKNOWN”是保守代理，不是规范唯一解。
5. `observed_revision=null` 存在两种解读：本 oracle 采用“未报告 → UNDETERMINED/MISSING”；实现也采用该解读。另一种“null 不阻断业务谓词”的解读未在本批实验中展开。
6. 窗口 target 规则按 semantics §4.2 执行；R-08 已把该检查补入实现。如果未来规范允许一组 A/B 跨 target，多 target 窗口案例的结论需要重评。
7. 修复后实现与 oracle 的 verdict 已完全一致；剩余差异只在 3 个案例的原因码粒度，根因是 V1 schema 未承载“来源身份是否已确认”，不影响是否签发。
8. 弱基线是人为定义的稻草人，不代表任何已部署系统；它们的假恢复率不能外推到真实平台。
9. 42 个案例为定向构造，不是概率抽样；没有统计显著性结论。

## 7. 复现文件

- `scripts/research/recovery_contracts/independent_oracle.py`
- `scripts/research/recovery_contracts/run_experiments.py`
- `tests/recovery_contracts/test_independent_oracle.py`
- `.runtime/n08/report.json`
- `.runtime/n08/summary.md`
