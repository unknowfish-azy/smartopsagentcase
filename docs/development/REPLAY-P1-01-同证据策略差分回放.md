# REPLAY-P1-01：同证据的策略差分回放

日期：2026-11-05（北京时间）  
任务 ID：`REPLAY-P1-01`（任务书 `docs/development/路演短板优化与多模型实施任务书-20261105.md`，映射 N05）  
规范来源：`docs/design/recovery-contract-v1/schema.json`（`ReplayBundle`）、`semantics.md` §2 / §2.1 / §9（N01 冻结，本任务只消费）  
依赖：`VER-P0-01`（N01/N02/N04）、`PROBE-P1-01`（N03），均已 DONE

## 0. 状态账

| 维度 | 状态 | 说明 |
|---|---|---|
| plan_status | `DONE` | 按 §9 `replay(bundle, policy_version) -> COMPLETE\|REPLAY_INCOMPLETE + structured_decision` 实现；未改 schema/semantics |
| implementation_status | `DONE` | `agent/recovery_contracts/replay.py`：冻结包解析、完整性校验、确定性重算、变形包、缺口报错 |
| verification_status | `DONE` | `test_replay.py` 21 passed；`tests/recovery_contracts` 208 passed / 1 skipped；全量 526 passed / 24 skipped |

### 0.1 边界冻结（有意不做）

- ✅ 回放为纯函数：不联网（测试注入 `socket.connect` 抛错断言）、不调用 LLM、不读当前墙钟（测试把模块内 `datetime` 换成 `now()` 抛错的子类）
- ✅ 判定时钟只来自 `bundle.decision_clock`；观测顺序只来自 `bundle.observation_order`
- ✅ 冻结输入以 bundle 为准；`contract`/`claim` 参数仅作调用方视图传入，不替代冻结副本
- ✅ 未录制探针 → `REPLAY_INCOMPLETE` + `MISSING_RECORDED_PROBE`，不补探、不默认 TRUE、不臆测成本
- ✅ 未实现策略版本 → `REPLAY_INCOMPLETE` + `UNSUPPORTED_POLICY_VERSION`，不伪造结论
- ✅ 变形包必须新 `bundle_id`/`digest`/`parent_bundle_id`/`mutation_diff` 且 `is_historical_fact=false`；历史原包不改写
- ❌ 不预测未执行修复的因果效果；不称“数字孪生”
- ❌ 不写在线审批/回执状态；停用回放不影响在线审批

## 1. 交付文件

| 文件 | 行数 | 职责 |
|---|---:|---|
| `agent/recovery_contracts/replay.py` | 550 | `ReplayBundle` 冻结包解析 + `replay()` 状态机 + `ReplayResult`/`ObligationDiff`/`MissingProbe` |
| `tests/recovery_contracts/test_replay.py` | 541 | 18 个原有用例 + 本轮新增 3 个用例 |

`__init__.py` 已导出 `replay`、`ReplayBundle`、`REPLAY_STATES`、`MissingProbe`、`ObligationDiff` 等符号，本轮无需改动。

## 2. 任务书判据 → 实现映射

| 任务书要求 | 实现位置 | 可复现证据（`test_replay.py`） |
|---|---|---|
| 冻结契约、声明、观测、来源、策略/配置版本、显式判定时钟、预算及事件顺序 | `ReplayBundle.from_dict`（19 字段白名单，含 `source_mapping`/`policy_config`/`decision_clock`/`observation_order`/`prerecorded_probe_map`/`budget`/`run_event_refs`/`dependency_versions`） | `test_complete_replay_reproduces_recorded_receipt` |
| 离线运行旧/新策略，逐义务解释差异 | 用冻结输入重算 `verify()`，与录制回执逐义务比对，输出 `verdict` + `obligation_diffs` + `diff_reason_codes` | `test_variant_expected_revision_flips_verified_to_insufficient`（TRUE→UNKNOWN，`WRONG_REVISION`） |
| 不联网、不调用模型、不改用回放当天墙钟 | 模块无网络/LLM 依赖；`datetime` 仅供类型注解与解析 | `test_replay_never_reads_system_clock`、`test_complete_replay_reproduces_recorded_receipt`（含 `_forbid_network`） |
| 同包重复 100 次确定性输出摘要一致 | 无随机源、无 `uuid`、无墙钟；回执 id/run/round 取自录制回执 | `test_replay_is_byte_identical_over_100_runs`（100 次 `canonical_json` 去重后仅 1 个） |
| 摘要校验依赖外部受信 expected digest | `expected_bundle_digest` 与内部自洽摘要独立比对 | `test_external_expected_digest_match_replays_completely`（通过）、`test_external_expected_digest_mismatch_is_stale`（拒绝） |
| 篡改拒绝 | 分层校验：未冻结字段 → bundle 摘要 → contract 摘要 → 证据摘要 → probe 映射 → 顺序 → 变形不变式 | `UNFROZEN_FIELD` / `BUNDLE_DIGEST_MISMATCH` / `CONTRACT_DIGEST_MISMATCH` / `EVIDENCE_DIGEST_MISMATCH` / `PROBE_REFERENCE_MISMATCH` / `OBSERVATION_ORDER_MISMATCH` / `CLAIM_DIGEST_MISMATCH`（`STALE`）/ `MUTATION_DIFF_INCONSISTENT` 各 1 例 |
| 新策略选到未录制探针 → `REPLAY_INCOMPLETE`，不补造结果 | `required_probes` 缺口检查，命中即返回缺口清单（`probe_id` + 义务） | `test_missing_required_probe_is_incomplete`（`missing_probes=[("probe-c", ("obl-business-health"))]`，`verdict=None`、`recomputed=None`） |
| 未实现策略版本不得假装成功 | `policy_version != recovery-eval/v1` → `UNSUPPORTED_POLICY_VERSION` | `test_unsupported_policy_version_is_incomplete` |
| 删证据变形 → 新包带 parent/新 digest，原包不变 | `_make_bundle` 派生 + 断言父包摘要/观测不变 | `test_variant_deleted_evidence_flips_verified_to_insufficient`、`test_derived_bundle_keeps_parent_replay_unchanged` |
| 增加反例变形 → 同上 | 新增反例观测（`payload.recovery_status=false`，摘要按 `payload_digest` 重算） | `test_variant_added_counterexample_flips_verified_to_contradicted`（`VERIFIED→CONTRADICTED`，`NEW_COUNTEREXAMPLE` 入 diff） |
| 观测数组乱序不得改变结论 | 重算沿用求值器 `_ordered` 的确定性排序 | `test_reversed_observation_order_keeps_same_decision_digest`（recomputed digest 与原回执一致） |

## 3. 回放状态机（结构化 reason_code）

| 状态 | reason_code | 触发条件 |
|---|---|---|
| `MALFORMED` | `UNFROZEN_FIELD` / `BUNDLE_DIGEST_MISMATCH` / `CONTRACT_DIGEST_MISMATCH` / `EVIDENCE_DIGEST_MISMATCH` / `PROBE_REFERENCE_MISMATCH` / `OBSERVATION_ORDER_MISMATCH` / `MUTATION_DIFF_INCONSISTENT` / `CLAIM_CONTRACT_BINDING_MISMATCH` | 冻结输入结构、摘要或不变式被破坏 |
| `STALE` | `CLAIM_DIGEST_MISMATCH` / `EXPECTED_DIGEST_MISMATCH` | 声明与录制回执不一致；或与外部受信摘要不一致 |
| `REPLAY_INCOMPLETE` | `MISSING_RECORDED_PROBE` / `UNSUPPORTED_POLICY_VERSION` / `NO_RECORDED_RECEIPT` | 缺录制证据或缺策略实现：给出缺口，不给结论 |
| `COMPLETE` | — | 重算得到 verdict + 逐义务 diff + `VERDICT_UNCHANGED`/`VERDICT_FLIPPED` + 变形 `kind` |

说明：`REPLAY_INCOMPLETE` 下 `verdict`、`recomputed_receipt_digest` 均为 `null`，`obligation_results` 为空——不把“缺证据”渲染成“已恢复”。

## 4. 命令级证据

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/recovery_contracts/test_replay.py -q` | `PASS`：21 passed in 0.25s |
| `python -m pytest tests/recovery_contracts -q` | `PASS`：208 passed, 1 skipped in 9.96s |
| `python -m pytest tests -q` | `PASS`：526 passed, 24 skipped in 137.55s |

跳过项（`SKIP`，非 PASS）：`test_examples.py` 全量 Schema 校验（未安装 `jsonschema`）；Redis 集成（缺 `redis` 模块）；Spring Boot 集成（后端未启动）。

## 5. 未做 / 边界

- 未实现“旧/新两套求值策略”并行：仓库只有 `recovery-eval/v1` 一个已实现求值策略；未知版本按 `UNSUPPORTED_POLICY_VERSION` 拒绝，不伪造第二套结论。差分演示以**录制回执 vs 冻结输入重算**、以及 N03 的加权/固定顺序两套调度策略为对象。
- 回放未接入在线存储/事件流：`run_event_refs` 仅作为冻结引用记录，不读取外部事件。
- 回放不重放探针执行，只消费 `prerecorded_probe_map` 指向的已录制观测。
- 未提供长时间/大规模包的性能基线；当前样本为 6 条观测。

## 6. 环境偏差与说明

- **实现文件曾被本轮误覆盖后按测试契约重写**：`agent/recovery_contracts/replay.py` 在本轮初始状态下已存在（`__init__.py` 已引用其符号，`test_replay.py` 已冻结其 API），本轮重写为与 `test_replay.py` 一致的实现。`agent/recovery_contracts/` 整体处于未跟踪状态（`git status` 显示 `??`），无历史版本可对照，故以测试契约为准。
- `jsonschema` 未安装：Schema 全量校验记 `SKIP`（与 VER-P0-01 相同偏差）。
- Python 3.14.3。

## 7. 回滚

- 删除 `agent/recovery_contracts/replay.py` 并移除 `__init__.py` 中 11 个 replay 符号即可停用回放；`evaluate`/`verify`/`choose_next` 与在线审批路径不受影响。
- 回放是只读消费者：不签发回执、不写账本、不改历史 bundle。
