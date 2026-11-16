# 引擎可观测大屏 · 设计口径 v1（ENGINE OBSERVABILITY）

> 立项 2026-11-16。来源：小红书「AI量化引擎怎么全自动运行？Opus直接给你看」的功能蒸馏。
> **蒸馏的是功能内核，不是量化交易**：原文痛点是"想知道每天引擎在干嘛？有没有摸鱼？"——一句话让 AI 生成一套把引擎每时每刻运行状态摊开的可视化监控。
> 本方案是该项目口径的唯一定义。执行包见 `EXECUTION-PACK.md`。

---

## 0. 三条铁律（违反即验收不通过）

1. **全真实事件**：大屏每一个状态、每一根心跳、每一条事件都来自真实表/真实 poller 的真实写入。**无事件即静默**，绝不伪造繁忙、不合成心跳、不编造进度。
2. **零侵入**：不改造任何现有 poller/Service 的业务逻辑，不新增定时任务，不改数据库表结构。大屏只是一个**只读聚合视图**，把已经存在的真实事件读出来展示。
3. **摸鱼=心跳超时，可解释**：引擎 STALLED 的判定只能基于"距最后一次真实事件的时间 > 该引擎声明的预期周期"，界面必须同时显示"距上次心跳 Xs / 阈值 Ys / 最后事件是什么"，让人能自己判断。禁止用动画"假装它在工作"。

---

## 1. 目标与非目标

**目标**：新增一个全局页面 `/engine-observability`，把项目里 6 条真实运行的引擎流水线的"活着吗 / 在干嘛 / 多久没动了 / 最近做了什么"一屏摊开，让评委和运营在 10 秒内判断系统健康度。

**非目标**（明确不做，避免跑偏）：
- ❌ 不做股票/加密货币量化交易、行情、K线、收益率——项目无真实行情数据，做了就是伪造，触碰红线。
- ❌ 不给预测面补 MLP+GRU 真模型（那是另一条候选线，本方案不碰）。
- ❌ 不新增 `@Scheduled` 任务（引擎本来就在跑，大屏只观测不驱动）。
- ❌ 不改任何省赛封版材料/文档口径（D6 延续）。

---

## 2. 六条引擎的真实事件源（全部只读）

盘点是本方案的事实基础。每条引擎映射一张真实表 + 一个真实周期声明：

| 引擎 id | 名称 | 真实事件源表 | 时间字段 | 预期周期(阈值) | 数据来源 Service |
|---|---|---|---|---|---|
| `sentinel-poll` | 哨兵巡检 | `sentinel_task` | `last_seen_at` | 30s（poller 20-30s） | `SentinelService.pollDueTasks()` |
| `sentinel-guardian` | 守护 Agent | `sentinel_task`(guardian 类) 或 `sentinel_alert_event` | `last_seen_at` / `at` | 60s（collectEvidence 45s） | `SentinelGuardianService` |
| `web-research` | 联网研究 | `web_research_task` + `web_research_page` | `finished_at` / `fetched_at` | 90s（radar 30s + 宽限） | `KnowledgeCrawlService.runDueMonitor()` |
| `inspector` | 纠察 | `inspector_event` | `created_at` | 300s（事件驱动，非周期） | `InspectorController` 写入链 |
| `decision-loop` | 决策闭环 | `agent_decision_loop` | `created_at`/`updated_at` | 300s | `DecisionLoopService` |
| `operation-run` | 运维执行 | `operation_run_record` | `started_at`/`ended_at` | 300s | `JdbcOperationRunRecorder` |

**training 明确标 `NOT_RUN`**：`training_pipeline.py` 的 `dry_run()` 返回 `"status":"NOT RUN"`，无真实训练事件表 → 大屏该卡显示"未运行 / 无事件源"，**不造假、不给绿灯**。这是诚实性的体现，也是评审加分点。

**阈值统一放在后端一个常量 Map 里**（`EngineCatalog`），前端不硬编码——前端只消费后端下发的 `expectedPeriodSec`。

---

## 3. 状态判定（纯函数，可单测）

对每条引擎，取"最后事件时间" `lastEventAt`，计算 `ageSec = now - lastEventAt`：

```
NO_DATA    : 表存在但从无事件（count=0）        → 灰色"无数据"
RUNNING    : ageSec <= expectedPeriodSec        → 绿色"运行中"
STALLED    : expectedPeriodSec < ageSec <= 5×period → 琥珀"疑似停摆"（显示超时倍数）
ERROR      : 最近一条真实事件带 error/failure 标记 → 红色"异常"
NOT_RUN    : 显式声明无事件源（training）        → 灰色"未运行"
```

- 阈值分档：`< period` 健康；`period ~ 5×` 疑似停摆；`> 5×` 也归 STALLED 但标注"长期无心跳"。
- ERROR 优先于 RUNNING：若最近事件本身是失败（`last_status='FAILURE'` / `error_code` 非空 / `exit_code!=0`），即使时间新也标 ERROR。
- 判定函数写成**无副作用的纯函数** `classifyEngine(EngineFacts, now): EngineState`，独立单测覆盖：无数据、新鲜、超时、失败、NOT_RUN、边界值。

---

## 4. 后端 API（只读，沿用现有鉴权）

新增 Controller `EngineObservabilityController`，`@RequestMapping("/api/engine-observability")`：

- `GET /snapshot` → `{ generatedAt, engines: [EngineState] }`
  - `EngineState = { id, name, status, lastEventAt, ageSec, expectedPeriodSec, eventCount, lastEventSummary, detail }`
  - 服务端聚合 6 张真实表，每条只取 `MAX(时间)`、`COUNT(*)`、最近一条摘要，`LIMIT 1` 级查询，不做全表扫描。
- `GET /event-stream?engine=&limit=50` → 指定引擎最近 N 条真实事件（时间倒序），字段 `{ at, kind, summary }`。
  - `kind` 来自真实列（如 `sentinel_alert_event.kind`、`operation_run_record.status`），不臆造类型。

**鉴权**：项目内部接口走现有 `internalTokenAuthenticationFilter` + 登录态，与 `/api/sentinel/**` 一致，不新开无鉴权口子。

**性能**：6 条聚合 `UNION` 或并行单表 `MAX/COUNT`，总耗时目标 <500ms；结果可被前端 30s 轮询，无需后端缓存。

**Micrometer**：沿用 `WebResearchMetrics` 的写法新增 `EngineObservabilityMetrics`（仅记录快照被请求的次数/耗时，绑真实调用，无事件即零），不新增依赖。

---

## 5. 前端页面（复用现有壳，零新造型语言）

新增 `frontend/src/views/sentinel/EngineObservabilityView.vue`，路由 `name: 'EngineObservability'`，路径 `/sentinel/observability`，挂在 `personalSystemNavigation.js` 的 `sentinel.children`，`meta.section: 'ENGINE OBSERVABILITY / 引擎可观测'`；同步登记 `routeMetadata.js`。

**布局**（沿用 `SentinelDashboardView.vue` 的深色 shell + `CanvasAmbientField` 极光背景 + 状态栏骨架，`--ds-*` 令牌 + 深浅主题自适应）：

1. **顶部**：6 张引擎卡（Bento 网格）。每张卡：引擎名 + 状态灯（绿/琥珀/红/灰）+ "距上次心跳 Xs / 阈值 Ys" + 最近一条事件摘要。STALLED 卡片有克制呼吸描边（绑真实超时倍数，非假繁忙）。
2. **中部**：真实事件时间轴，复用 `DeskAxis.vue` 的 Canvas 共享时间轴思路。横轴时间，每条真实事件一个点（颜色=引擎，形状=状态），鼠标悬停显示摘要。有数据才画，无数据显示"当前窗口无真实事件"空态。
3. **底部**：选中某引擎后，列出其 `event-stream` 最近 N 条真实事件表格（时间/kind/摘要），点击可跳转到对应原生页面（如告警中心、运行记录）——**联动但只读**。

**三态取数**：严格照 `useForecastSeries.js` 范式——`loading/live/offline`。接口失败 → `offline` 空态 + 重试按钮，**绝不自动 fallback demo**（本页无 demo 数据，因为主题就是"真数据"）。缺字段显示 `—`，不补默认值。

**降级/动效**：接入 `motionScheduler.js`（共享 rAF、离屏暂停）+ `visualMode.js`（lightweight/reduced-motion 下关背景极光与呼吸描边，静态单帧）；`prefers-reduced-motion` 下禁用一切自动动画；窄屏（≤760）卡片单列、时间轴退化为列表。G5 四重降级沿用。

---

## 6. 验收门禁（缺一不可）

- 后端：纯函数单测（6 类状态 + 边界），Controller 集成测试（真实表只读）；`mvn test` 全绿。
- 前端：浏览器实测脚本 `engine-observability.browser.mjs` mock `live`（含一条 STALLED、一条 ERROR、一条 NOT_RUN）/`offline` 两态，断言状态灯、超时文案、"无真实事件"空态、不自动 fallback、0 pageError、无横向溢出。
- 工程：`typecheck` 0、`lint` 0 error、双 build（vite + admin）通过。
- 真实性核查：逐条确认页面每个数字都能追到一张真实表的一个真实字段；**training 卡必须为 NOT_RUN 灰卡**。
- 红线：省赛封版材料零改动；无金额/收益/准确率 9X% 文案。

---

## 7. 待裁决项（默认执行，用户可推翻）

- **D-ENG1**：页面入口默认放 `sentinel` 组还是新建顶级组？**默认：sentinel 组**（定位为"哨兵的可观测总览"，改动最小）。
- **D-ENG2**：`inspector`/`decision-loop` 预期周期是事件驱动非周期，阈值取 300s 是否合理？**默认：300s，界面标注"事件驱动·参考阈值"**。
- **D-ENG3**：是否给 STALLED 加声音/强提醒？**默认：不加**（控制台克制风格，仅视觉描边）。

工作包拆解与执行顺序见 `EXECUTION-PACK.md`。
