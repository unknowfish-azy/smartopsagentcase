# PROBE-P1-01：有预算的只读补证调度

日期：2026-11-05  
任务 ID：`PROBE-P1-01`（任务书 `docs/development/路演短板优化与多模型实施任务书-20261105.md` L112-L120）  
规范来源：`docs/design/recovery-contract-v1/schema.json` + `semantics.md` §4/§5/§6/§8.1（N01 冻结，本任务只消费）  
依赖：`VER-P0-01`（N01/N02/N04 产物，已 DONE）

## 0. 状态账

| 维度 | 状态 | 说明 |
|---|---|---|
| plan_status | `DONE` | 按 N01 冻结的 §4.3 预算常量与 §5 调度规则实现；未改 schema、未改 semantics |
| implementation_status | `DONE` | 探针登记/有界执行器（N03）、调度器与固定顺序基线、真实 loopback transport 全部落地 |
| verification_status | `DONE` | 局部 205 passed / 1 skipped；全量 523 passed / 24 skipped（跳过均为环境缺失，不伪装 PASS） |

### 0.1 边界冻结

本次严格遵守：

- ✅ 只消费 `recovery-contract/v1`；`ProbeDecision` 字段与 schema 一致（decision/selected_probe_id/next_eligible_at/stop_reason/budget_before/budget_after 条件必填）
- ✅ 过滤顺序固定：`UNREGISTERED → IDENTITY → SCOPE → TARGET_ALLOWLIST → TOOL_PERMISSION → READ_ONLY → QUOTA → DEADLINE → COST → DUPLICATE`
- ✅ 每次只发一个探针，收到结果后重算；`WAIT` 不扣调用次数但受总 deadline；`STOP` 不是恢复结论
- ✅ 机制原型仅 loopback：固定 `127.0.0.1` + 登记端口、固定 GET、固定路径集（`/health` `/ready` `/api/health`）；禁任意 URL/代理/重定向；响应 ≤4KiB；1 秒绝对时限含连接+完整读取+解析
- ✅ 新轮次不重置 run 预算与 deadline；重试同样计费；重启只恢复持久化 ISO deadline，不比较旧单调时钟
- ❌ 不做任意主机/写操作/代理/重定向跟随；不把探针传输成功当恢复证据
- ❌ 不承诺贪心全局最优；对照实验只报告同预算同停止机会下的事件差异
- ❌ 未接生产 SLO；12 次/30 秒/1 秒/4KiB 均为原型参数

## 1. 交付文件

| 文件 | 行数 | 职责 |
|---|---:|---|
| `agent/recovery_contracts/probes.py` | 446 | 不可变探针登记（`Probe`/`ProbeRegistry`）+ 有界 GET 执行器（`ProbeExecutor`，transport/clock 注入）；§8.1 error/payload 分离 |
| `agent/recovery_contracts/scheduler.py` | 504 | `RunBudget` 持久化账本 + `choose_next` 纯函数（SELECTED/WAIT/STOP）+ `choose_next_fixed_order` 同预算基线 + `minimum_calls_for_round` |
| `agent/recovery_contracts/collector.py` | 132 | 机制原型真实 socket transport（`loopback_transport`）+ `LoopbackProbeClient` |
| `agent/recovery_contracts/__init__.py` | 173 | 公开符号导出（新增 collector 三件与 `add_ms`） |
| `tests/recovery_contracts/test_probes.py` | 326 | 登记边界 + 注入 transport 的有界执行（不联网、不起服务） |
| `tests/recovery_contracts/test_scheduler.py` | 385 | 评分/同分排序/过滤顺序/WAIT/各 STOP 原因/预算/轮次/基线 |
| `tests/recovery_contracts/test_probe_driver.py` | 379 | 自持有 loopback 服务真实 socket 端到端（见 §3） |
| `scripts/compare_probe_strategies.py` | 253 | 对照实验（可重跑，输出证据 JSON） |
| `docs/development/probe-p1-01-evidence/compare-weighted-vs-fixed-order.json` | 证据 | 两策略两场景全事件轨迹（含全部 STOP/候选过滤理由） |

## 2. 任务书判据 → 实现映射

| 任务书要求（L112-L120） | 实现位置 | 可复现证据 |
|---|---|---|
| 登记探针的加权缺口覆盖：`score = 尚缺必需义务权重和 / max(登记成本,1)` | `scheduler._candidate` + `_score` | `test_scheduler.py::test_selects_highest_uncovered_weight_per_cost` |
| 权限过滤后再评分；同分按成本、固定 probe_id | `_candidate` 过滤链 + `_decide` 排序键 `(-score, cost, probe_id)` | `test_tie_break_uses_probe_id_lexicographic_order`、`test_candidate_filters_cover_permission_executed_exhausted_and_coverage` |
| 每次取得结果后重算；每次只发一个 | `choose_next` 纯函数，调用方逐次传入最新 `ObligationResult` | `test_decision_is_deterministic_for_identical_inputs`；driver 端到端逐槽重算 |
| 时序槽未到输出 `WAIT(next_eligible_at)`，不扣调用次数，受总 deadline | `_decide` 的 WAIT 分支（slot 超过 deadline 则 `DEADLINE_EXCEEDED`） | `test_wait_until_next_slot_without_consuming_budget`、`test_slot_after_deadline_is_deadline_stop`；driver 中 WAIT 实测 |
| 到期/预算不足/无覆盖/静态不相容/无新信息 `STOP` | `_decide` 五个 STOP 分支 | `test_budget_exhausted_stops_with_reason_and_does_not_consume`、`test_deadline_exceeded_stops`、`test_static_incompatible_when_remaining_budget_cannot_finish_plan`、`test_all_required_obligations_true_stops_without_new_information`、`test_required_counterexample_stops_round` |
| 有效反例保持 CONTRADICTED，补证不能抵消 | FALSE 必需义务 → STOP + `stop_detail=COUNTEREXAMPLE` | `test_required_counterexample_stops_round` |
| 机制原型：自持有 loopback、固定 GET、登记端口；禁任意 URL/代理/重定向 | `probes._loopback_port`/`ALLOWED_PATHS` + `collector.loopback_transport` | `test_registration_rejects_invalid_probe`（16 组非法登记）；`test_execute_sends_only_bounded_get_to_loopback_path` |
| 连接+完整读取+解析共同受绝对 deadline | transport 内单调时钟预算逐段裁剪（connect→headers→body），slow-drip 无法续命 | `test_real_socket_slow_drip_hits_absolute_deadline`（服务端 2.1s 滴流，客户端 ~1s 停止）、`test_slow_drip_hits_absolute_timeout_even_if_status_is_200` |
| 响应体 ≤4KiB、限定格式 | transport 最多读 `max_bytes+1` 字节；超限/非 JSON 对象 → MALFORMED | `test_real_socket_oversized_body_is_rejected`、`test_oversized_body_is_blocked_before_parsing`、`test_non_json_object_is_rejected` |
| 非 2xx/3xx 只写 error；传输错误与业务失败分离 | `ProbeExecutor.execute` 的 status 分支 | `test_non_2xx_response_writes_error_and_never_payload`、参数化 4xx/5xx |
| 重定向不跟随、不当可达证据 | `http.client` 不跟随 + 执行器记 `REDIRECT_BLOCKED` | `test_real_socket_redirect_is_not_followed`、`test_redirect_with_location_is_blocked` |
| 慢速滴流/超大 body/重复 ID/错来源/超时/预算耗尽均有证据 | 前两者见上；重复 ID 与错来源沿用 VER-P0-01 冻结样例 | `negative-duplicate-observation-id`（INSUFFICIENT/MISSING）、`negative-source-conflict`（INSUFFICIENT/CONFLICT）、`negative-timeout`；预算耗尽 `test_budget_exhausted_*` |
| 重试计费；新轮次不重置 run 预算 | `RunBudget.record_call` 每次真实调用记账；`start_round` 只切轮次 | `test_retry_after_failure_charges_budget_again`（真实 loopback 两次失败调用 calls_used=2）、`test_new_round_does_not_reset_run_budget` |
| 重启后不比较旧单调时钟；新 run 继承持久预算 | `RunBudget` 持久化 `deadline_at`(ISO)/`calls_used`/`verification_round`；transport 单调时钟仅存活在单次调用内 | `test_restart_inherits_persisted_budget_and_deadline`（恢复后 SELECTED；deadline 已过则 DEADLINE_EXCEEDED） |
| 与同目录、同预算、同停止机会的固定顺序策略比较；失败/暂缓均入报告 | `choose_next_fixed_order` 共享过滤与 WAIT/STOP；`scripts/compare_probe_strategies.py` 两场景 | §4 对照实验；证据 JSON 含全事件轨迹 |
| 不承诺贪心全局最优 | S2 场景：贪心先选无信息高覆盖探针，比固定顺序多用 1 次调用 | 证据 JSON `S2-wide-no-progress`；本报告 §4 如实并列两场景 |
| 回滚：停用调度器仍可人工选择登记只读探针 | `ProbeRegistry`/`LoopbackProbeClient` 不依赖调度器；`ProbeExecutor` 可独立调用 | 结构约束（driver 直接按 probe_id 执行） |

## 3. 真实 loopback 端到端（test_probe_driver.py）

自持有 `ThreadingHTTPServer`（127.0.0.1 临时端口），走 `collector.loopback_transport` 真实 socket：

| 用例 | 服务端行为 | 断言 |
|---|---|---|
| `test_real_loopback_three_group_window_verified` | A/B 两端口均 200 `{"recovery_status":true,"observed_revision":"r17"}` | 3 组 × 2 来源、组间隔 2200ms，闭环 `choose_next`（含 WAIT 实测不扣费）→ `VERIFIED`，calls_used=6 |
| `test_real_loopback_http200_business_false_is_contradicted` | 200 但 `recovery_status=false` | `CONTRADICTED`，义务 `FALSE` |
| `test_real_loopback_502_is_insufficient_not_success` | 502 | `INSUFFICIENT` + `MALFORMED`；error 与 payload 分离 |
| `test_real_socket_slow_drip_hits_absolute_deadline` | 每 0.7s 滴一段，共 2.1s | `TIMEOUT`，elapsed ≥1000ms，墙钟 <1900ms（不等服务端滴完） |
| `test_real_socket_oversized_body_is_rejected` | >4KiB body | `MALFORMED` + `truncated`，读取 ≤4097 字节 |
| `test_real_socket_redirect_is_not_followed` | 302 + Location | `REDIRECT_BLOCKED`，不跟随 |
| `test_retry_after_failure_charges_budget_again` | 502 ×2 | 重试两次 calls_used=2，后续决策 budget_before 反映 |
| `test_restart_inherits_persisted_budget_and_deadline` | — | 持久化字段重建 RunBudget：calls_used=6 保留；deadline 已过 → `DEADLINE_EXCEEDED` |

## 4. 对照实验（同登记表 / 同预算 / 同停止规则）

`python scripts/compare_probe_strategies.py` → `docs/development/probe-p1-01-evidence/compare-weighted-vs-fixed-order.json`。契约：3 个必需义务（权重 1/2/3）；登记表：`probe-wide`（覆盖全部，成本 1）、`probe-cheap-a/b/c`（各覆盖 1 项，成本 1）。两策略共享过滤与 WAIT/STOP，唯一差异是合格候选排序。

| 场景 | 加权覆盖策略 | 固定顺序基线 |
|---|---|---|
| S1 全部调用产生有效信息 | 1 次调用（先选 probe-wide）→ `NO_NEW_INFORMATION` | 3 次调用（cheap-a→b→c）→ `NO_NEW_INFORMATION` |
| S2 probe-wide 无新增有效信息 | 4 次调用（wide 记 exhausted 后再补 3 次）→ `NO_NEW_INFORMATION` | 3 次调用 → `NO_NEW_INFORMATION` |

结论按任务书口径如实陈述：S1 加权策略调用更少，S2 加权策略反而更多；差异只来自排序规则，**不构成"贪心更省调用"的全局主张**。全部决策、候选过滤理由与 STOP 事件均在证据 JSON 中。

## 5. 命令级证据

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/recovery_contracts/test_probe_driver.py -q` | `PASS`：8 passed in 9.64s |
| `python -m pytest tests/recovery_contracts -q` | `PASS`：205 passed, 1 skipped in 10.50s |
| `python -m pytest tests -q` | `PASS`：523 passed, 24 skipped in 166.42s |
| `python scripts/compare_probe_strategies.py` | `PASS`：S1 weighted=1/fixed=3；S2 weighted=4/fixed=3；证据 JSON 已写入 |

跳过项（`SKIP`，非 PASS）：`test_examples.py` Schema 全量校验（缺 `jsonschema`）；Redis/Spring Boot 集成（缺依赖/服务未启动）。

## 6. 未做 / 边界

- 未接生产探针：原型只允许 loopback 明文 HTTP；生产适配（mTLS、认证、SLO）不在本任务。
- 未实现"探针无新增有效信息达预定次数 STOP"的可配置计数器：当前由调用方以 `exhausted_probe_ids` 记账（S2 场景演示），计数阈值未冻结进 schema。
- `PROBE-P1-01` 不签发回执、不触发审批、不修改 `StateVerifier.passed` 原义。
- 采样槽计划时间由调用方传入（`next_slot_at`）；调度器自己不以计划时间冒充事实。

## 7. 环境偏差

- Python 3.14.3：`http.client.HTTPConnection.getresponse()` 会将 `connection.sock` 置 `None`，且 `HTTPResponse` 读完 body 后自动关闭底层 socket。`collector.loopback_transport` 已按此行为实现（连接时捕获 sock 引用、每轮读取前查 `isclosed()`）；旧版本 Python 未实测。
- `jsonschema` 未安装：Schema 全量校验记 `SKIP`（与 VER-P0-01 相同偏差）。
- Windows 时钟粒度：窗口测试组间隔取 2200ms（>2000ms 冻结下界），留余量防 sleep 欠冲；实测 8/8 通过。

## 8. 回滚

- 停用调度器：删除对 `choose_next` 的调用即可；`ProbeRegistry` + `LoopbackProbeClient` 仍可人工按 probe_id 选择登记只读探针（driver 已演示该路径）。
- 停用真实 transport：`ProbeExecutor` 继续接受注入 transport（test_probes.py 全部用例不依赖 socket）。
- 全部变更为新增文件（`probes.py`/`scheduler.py`/`collector.py`/测试/脚本/证据），未修改既有运行代码；`__init__.py` 仅追加导出，删除新增符号即可还原。
