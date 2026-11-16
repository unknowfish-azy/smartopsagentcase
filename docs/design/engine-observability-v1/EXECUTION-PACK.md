# 引擎可观测大屏 · 执行包（T37–T40）

> 配套 `DESIGN.md`（唯一口径）。执行前先读 DESIGN.md 三条铁律。
> 本包默认由实现模型执行；每工作包附验收门禁，逐包过关再进下一个。
> 立项 2026-11-16。

---

## 全局约束

- **零侵入**：不改任何现有 poller/Service 的业务逻辑，不改 DB 表结构，不新增 `@Scheduled`。
- **全真实**：页面每个数字可追到真实表字段；无事件静默；training 恒为 NOT_RUN 灰卡。
- **省赛封版材料零改动**（D6）：不动 technical-document / 介绍稿 / 合订本 / demo-script。
- 鉴权沿用 `internalTokenAuthenticationFilter` + 登录态，不新开无鉴权端点。

---

## T37 · 后端状态判定纯函数 + 单测

**目标**：把"心跳超时判定"做成可独立测试的无副作用纯函数，先把诚实性内核锁死。

**新增文件**
- `backend/src/main/java/com/smartops/observability/EngineCatalog.java`
  - 常量 Map：6 条引擎的 `id/name/expectedPeriodSec/eventSource/NOT_RUN 标记`。training 显式标 NOT_RUN。
- `backend/src/main/java/com/smartops/observability/EngineStateClassifier.java`
  - `EngineState classify(EngineFacts facts, long nowEpochSec)`
  - `EngineFacts = { id, lastEventAtSec, eventCount, lastEventKind, lastEventSuccess }`
  - `EngineState = { id, name, status, ageSec, expectedPeriodSec, eventCount, lastEventSummary, detail }`
  - 状态枚举 `NO_DATA / RUNNING / STALLED / ERROR / NOT_RUN`
  - 规则严格按 DESIGN.md §3：ERROR 优先；`age<=period` RUNNING；`period<age<=5×period` STALLED（detail 带超时倍数）；`>5×` STALLED 标"长期无心跳"；count=0 → NO_DATA；catalog 标 NOT_RUN → NOT_RUN。

**单测** `backend/src/test/java/com/smartops/observability/EngineStateClassifierTest.java`
- 覆盖：无数据 / 新鲜 / 边界=period / period+1 / 5×period 边界 / 5×+1 / 最近失败→ERROR / NOT_RUN / ERROR 覆盖 RUNNING。至少 9 个断言。

**门禁**：`mvn -q -Dtest=EngineStateClassifierTest test` 全绿。

---

## T38 · 后端只读聚合 Controller + Micrometer

**目标**：把 6 张真实表聚合成快照与事件流，暴露只读 API。

**新增文件**
- `backend/src/main/java/com/smartops/observability/EngineSnapshotService.java`
  - 注入 `JdbcTemplate`，对每张表执行 `MAX(时间列)`、`COUNT(*)`、最近一条摘要（`ORDER BY 时间 DESC LIMIT 1`）——**只聚合，不写库**。
  - `EngineFacts collect(String engineId)`：按 catalog 的表/列映射取事实，training 直接返回 NOT_RUN facts。
  - `List<EngineEvent> eventStream(String engineId, int limit)`：真实事件倒序，`kind` 取真实列。
  - SQL 全部参数化写死在 catalog 映射里，禁止拼接外部输入。
- `backend/src/main/java/com/smartops/observability/EngineObservabilityController.java`
  - `@RequestMapping("/api/engine-observability")`
  - `GET /snapshot`、`GET /event-stream?engine=&limit=50`
  - 调用 classifier + snapshotService，返回统一响应结构（沿用项目 `Result`/`code,data` 约定）。
  - `engine` 参数白名单校验（只能是 catalog 的 6 个 id），非法返回 400。
- `backend/src/main/java/com/smartops/observability/EngineObservabilityMetrics.java`
  - 仿 `WebResearchMetrics`：`snapshotRequested()` counter、`snapshotDuration(Duration)` timer。仅绑真实调用。

**表/列映射（来自盘点，勿臆造）**
| id | 表 | 时间列 | 成功判定列 |
|---|---|---|---|
| sentinel-poll | `sentinel_task` | `last_seen_at` | `last_status` |
| sentinel-guardian | `sentinel_alert_event` | `at` | `kind` |
| web-research | `web_research_task` | `finished_at` | `error_code` |
| inspector | `inspector_event` | `created_at` | `status` |
| decision-loop | `agent_decision_loop` | `created_at` | `outcome` |
| operation-run | `operation_run_record` | `ended_at` | `status` |
| training | — | — | 恒 NOT_RUN |

**集成测试** `EngineObservabilityControllerTest`：用 `@JdbcTest` 或 H2 建最小表插入真实形态数据，断言 snapshot 状态分类正确、event-stream 倒序、非法 engine 返回 400、training 为 NOT_RUN。

**门禁**：`mvn test` 全绿（含 T37 单测）；`/actuator/health` 仍 UP。

---

## T39 · 前端大屏视图 + 导航接入

**目标**：新增 `/sentinel/observability` 页面，三态取数，复用现有壳。

**新增文件**
- `frontend/src/composables/useEngineObservability.js`
  - 照 `useForecastSeries.js` 范式：`state=loading|live|offline`；`GET /api/engine-observability/snapshot` 30s 轮询；失败→offline 空态+retry，**不自动 fallback demo**；`eventStream(engineId)` 单独取。
- `frontend/src/views/sentinel/EngineObservabilityView.vue`
  - 顶部 6 张引擎状态卡（Bento 网格）：状态灯 + "距上次心跳 Xs / 阈值 Ys" + 最近事件摘要；STALLED 克制呼吸描边（reduced-motion 关）。
  - 中部真实事件时间轴：复用 `DeskAxis.vue` Canvas 时间轴思路（或 `@xterm` 无关的手绘 Canvas），颜色=引擎、形状=状态，悬停显示摘要；无数据显示"当前窗口无真实事件"。
  - 底部事件表格 + 跳转原生页面链接（告警中心/运行记录等，只读联动）。
  - 复用 `SentinelDashboardView.vue` 的深色 shell + `CanvasAmbientField`、`--ds-*` 令牌、深浅主题；接 `motionScheduler`/`visualMode` 降级；窄屏单列。
  - training 卡固定灰卡"未运行 / 无事件源"。

**修改文件（锚点已确认）**
- `frontend/src/router/index.js`：在 `sentinel/forecast` 行附近加
  `{ path: 'sentinel/observability', name: 'EngineObservability', component: () => import('../views/sentinel/EngineObservabilityView.vue'), meta: { ...routeMetaFor('EngineObservability'), section: 'ENGINE OBSERVABILITY / 引擎可观测' } }`
- `frontend/src/navigation/personalSystemNavigation.js`：`sentinel.children` 数组末尾加
  `{ label: 'OBSERVABILITY', cn: '引擎可观测', routeName: 'EngineObservability', to: '/sentinel/observability' }`
- `frontend/src/navigation/routeMetadata.js`：登记 `EngineObservability → personalGroup:'sentinel'`（与 ForecastPlane 同款）。

**门禁**：`npm run typecheck` 0；`npm run lint` 0 error；两个路由/导航项可见（浏览器实测）。

---

## T40 · 浏览器实测 + 全量门禁 + 交付

**新增** `frontend/test/engine-observability.browser.mjs`（照 `forecast-plane.browser.mjs` 结构）
- mock 两组：`mockLive`（6 引擎，含 1 STALLED、1 ERROR、1 NOT_RUN、1 NO_DATA、2 RUNNING）+ `mockOffline`（snapshot 503）。
- 断言：①6 张卡渲染；②STALLED 卡显示"距上次心跳 Xs / 阈值 Ys"与超时文案；③ERROR 卡红灯；④training 卡 NOT_RUN 灰态；⑤时间轴画出真实事件点、空态文案正确；⑥offline 显示空态且**未自动 fallback**；⑦0 pageError；⑧无横向溢出；⑨reduced-motion 下背景静帧；⑩轮询调用发生。
- 截图到 `.runtime/engine-observability/browser/`。

**全量门禁**
- 后端 `mvn test`；前端 `node --test test/**/*.test.mjs`；`typecheck`；`lint`；`vite build` + `vite build --config vite.config.admin.mjs`。
- 真实性核查表：逐条列页面数字 → 真实表字段映射，附在 PR 描述。
- 省赛封版材料 git diff 为空确认。

**门禁全绿后**：commit + push origin/main；更新 `.workbuddy/memory/`。

---

## 执行顺序与依赖

```
T37（纯函数+单测）→ T38（Controller 聚合，依赖 T37 的 classifier）
                          ↓
                    T39（前端，依赖 T38 的 API 契约）
                          ↓
                    T40（实测+门禁+交付）
```

每个工作包完成后先跑本包门禁，再进下一个。任一门禁不过 → 停在该包修复，不带病前进。
