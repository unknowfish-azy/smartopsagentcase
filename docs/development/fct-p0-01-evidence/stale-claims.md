# FCT-P0-01 过期主张清单（自动生成，只检测不改文）

> 扫描范围：`docs/competition/**`、`docs/audit/**`、`docs/*.md`（对外材料）；`docs/development/**` 是工作报告，不参与核对。
> 只做扫描与分类，**不修改任何文档**。分类规则：能绑定到本快照指标且数值不同 → `needs_correction`；
> 命中历史措辞 → `historical_reference`；命中当前措辞 → `current_claim`；其余 → `needs_review`。
> “N 张表”绑定的是**离线 migration 定义去重数**，不是运行库表数（后者为 null，未核验）；
> “N 个接口”绑定的是静态解析出的 (HTTP方法, 路径) 去重数，常量拼接路径未计入并在 `unresolved_annotation_n` 单列。

| 分类 | 条数 | 含义 |
|---|---:|---|
| needs_correction | 0 | 与本次冻结指标冲突，必须人工改写 |
| needs_review | 20 | 无法自动判定，需按上下文人工确认 |
| historical_reference | 3 | 明确写为历史/旧稿，可保留 |
| current_claim | 0 | 与本次指标一致，视为当前主张 |

## needs_correction（0）

无。

## needs_review（20）

| 文件:行 | 命中数字 | 绑定指标 | 原文（截断） |
|---|---|---|---|
| docs/audit/20261105/status-baseline.md:9 | 81 | - | \| HEAD \| `48b8af47603e3d7e2b04b7bae81c667c588328dc` \| `git rev-parse HEAD` \| |
| docs/audit/20261105/status-baseline.md:20 | 83 | - | \| SCORE-01 尚未修复 \| CONFIRMED \| `training/evaluator.py` hash = `83a0d44c…`、`benchmark_runner.py` hash = `f1a9b97b…`，与交接书第 6.1 节记录的"当时源码 hash"完全一致 \| |
| docs/audit/20261105/test-matrix.md:19 | 80 | - | \| Agent pytest \| `pytest tests/agent -v --tb=no` \| — \| 80 passed \| NOT_RUN \| 覆盖 Inspector/Executor 定向回归 \| |
| docs/competition/adjustment-plan.md:44 | 80 | migrations.offline_distinct_table_n | - [x] **D1 数据库 schema 自愈**：新增 `AssistantWorkspaceConfig`，启动时幂等补齐 `chat_conversation` / `chat_message` / `chat_attachment` / `vision_event` / `operator_memory` / `personal_knowledge |
| docs/competition/recovery-contracts/evidence-index.md:35 | 219 | - | \| 后端测试 \| `tests/recovery_contracts/` \| 219 passed / 1 skipped \| |
| docs/competition/四件套万全之策-打印版.html:74 | 79 | - | .callout { background:#fffdf4; border:0.8pt solid #eadfc0; border-left:3pt solid #c79a2e; |
| docs/competition/答辩材料-打印合订本.html:59 | 135 | - | margin:6mm 0 10mm; background:linear-gradient(135deg,#0f2b46,#1f6feb); color:#fff; } |
| docs/competition/答辩知识手册-打印版.html:74 | 79 | - | .callout { background:#fffdf4; border:0.8pt solid #eadfc0; border-left:3pt solid #c79a2e; |
| docs/competition/答辩知识手册-打印版.html:191 | 89 | - | <p><strong>③ 融合</strong>（<code>retrieval/hybrid.py:89-101</code>）</p> |
| docs/competition/答辩知识手册-打印版.html:215 | 428 | - | <ul><li>双入口：用户层 5173 / 管理员层 5174，共用 <code>vite.shared.mjs</code>（代理 <code>/api</code> <code>/ws</code>，<code>/ai</code> 单独转发 8001）</li><li>手动分包：three / zrender / echarts / xterm /  |
| docs/competition/项目知识要点手册.md:95 | 89 | - | **③ 融合**（`retrieval/hybrid.py:89-101`） |
| docs/competition/项目知识要点手册.md:163 | 428 | - | - 错误处理：`request.ts`（498 行）统一拦截，覆盖 400/401/403/404/409/**428 人机验证**/429/422/500/502-504；401 派发 `smartops:unauthorized` 事件由路由清会话跳登录 |
| docs/human-verification-deployment.md:34 | 428, 428, 428 | - | 实测结果：`provider=local`、`targets∈{1,2}`、`tolerance=18`；`scene` 无 `data-*`/注释/脚本/外部引用；点选后状态变为「已通过」并成功登录 `portal=admin`；同一挑战二次兑换返回 **428**；点错返回 **428「没有点中正确图形，请重试（本次挑战还剩 2 次机会）」**；非法坐标 |
| docs/human-verification-deployment.md:95 | 428 | - | - HTTP 428：缺少、过期、重放、跨用途或跨会话验证；客户端重新取得策略和挑战。 |
| docs/OBSERVABILITY_SETUP.md:27 | 80, 80, 00111 | - | 发布地址分别是 `https://github.com/prometheus/prometheus/releases/tag/v3.5.0`、`https://github.com/grafana/loki/releases/tag/v3.5.0` 和 `https://github.com/prometheus-community/windows_expo |
| docs/OPTIMIZATION-CHANGES.md:344 | 89 | - | \| `python -m pytest -q` \| PASS：89 passed，24 skipped，1 个 pytest cache warning \| |
| docs/PROJECT-AUDIT-2026-11-04.md:55 | 79 | - | **现象**：[hash_embedding.py](file:///d:/SmartOpsAgent/knowledge/embedding/hash_embedding.py#L29-L79) 用 sha256 把 token 映射到 256 维做计数，本质是**词袋哈希**。中文还做了单字 + bigram 展开，所以能工作，但与 BM25 高度同源。 |
| docs/PROJECT-AUDIT-2026-11-04.md:214 | 79 | - | \| P1-PERF-02 大块拆分和长会话治理 \| 已完成 \| ECharts/Knowledge 懒加载核验：ECharts 四组件均为 `echarts/core` 模块导入且仅被懒加载路由视图引用（ModelAnalyticsView/Dashboard），knowledgeCatalog 30+ 领域模块仅被 KnowledgeView/QuizVi |
| docs/PROJECT-AUDIT-2026-11-04.md:215 | 80 | - | \| P1-PERF-01 前端性能基线 \| 已完成（fixture 边界） \| 新增 [performance-baseline.browser.mjs](file:///d:/SmartOpsAgent/frontend/test/performance-baseline.browser.mjs) + `npm run perf:baseline`；本机  |
| docs/smartops-companion-phase1.md:19 | 80 | - | - `npm test`: 80 tests passed. |

## historical_reference（3）

| 文件:行 | 命中数字 | 绑定指标 | 原文（截断） |
|---|---|---|---|
| docs/competition/答辩知识手册-打印版.html:219 | 113, 135 | - | <p class="note">注：模块拆分（13/36/20/18/5/6/15）是上一轮 <code>tests/</code> 113 用例口径，加上当时 ai-service 22 个合计 135；与上方 610 全量收集数不是同一快照；对外只引用 610 / 600 / 10。</p> |
| docs/competition/项目知识要点手册.md:186 | 113, 135 | - | > 注：模块拆分（13/36/20/18/5/6/15）是上一轮 `tests/` 113 用例口径，加上当时 ai-service 22 个合计 135；与上方 610 全量收集数不是同一快照；对外只引用 610 / 600 / 10。 |
| docs/OPTIMIZATION-CHANGES.md:397 | 89 | - | \| `python -m pytest -q` \| 上一轮真实结果：89 passed / 24 skipped \| |

## current_claim（0）

无。

