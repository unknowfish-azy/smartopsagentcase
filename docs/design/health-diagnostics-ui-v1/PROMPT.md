# 实现提示词：重做健康诊断模块 UI

把下面整段发给 Trae（或任何能改本仓库的模型）。它要求仓库里已有 `docs/design/health-diagnostics-ui-v1/`。

---

## 你的任务

重做 `/health`（`HealthCenter`，健康诊断）的界面：把现在「巨标题 + 7 行平铺列表 + 3 个工具面板」改成「结论带 + 分组检查清单 + 能力边界 + 统一诊断结果面板」。

**先读、再计划、后实现。** 第一步只输出：现状问题复述 + 数据字段核对表 + 分阶段计划，等我确认后再动代码。

## 开工前必读

| 文件 | 从中拿到 |
| --- | --- |
| `docs/design/health-diagnostics-ui-v1/DESIGN.md` | 全案：三层信息架构、状态语义表、结论带、分组规则、证据完整性横幅、令牌、验收清单 |
| `docs/design/health-diagnostics-ui-v1/index.html` | 参考原型（播种真实字段），可直接读它的 CSS/结构 |
| `frontend/src/views/diagnostics/HealthCenterView.vue` | 现状：8 行，`<h1>` 文案「配置非证据」，页面下挂 3 个工具面板 |
| `frontend/src/components/diagnostics/HealthCheckList.vue` | 现状列表实现、`emit('policy')` 没人接 |
| `frontend/src/components/diagnostics/healthState.js` | `FIVE_MINUTES_MS`、`isFreshCheck`、`healthStateLabel`、`normalizeDiagnosticFailure` —— **这些是既成契约，不要改签名** |
| `backend/.../diagnostics/HealthDiagnosticService.java` | `Check{id,label,status,scope,checkKind,checkedAt,durationMs,summary,nextAction}`、`Summary{scope,checks,policy}` |
| `backend/.../diagnostics/{host,database,kubernetes,network}/*.java` | 四种诊断结果字段（`checks`/`layers`/`findings`/`blockedBy` + `unverified`/`truncated`/`permissionDenied`/`dataMissing`） |
| `design-system/MASTER.md` | 工具层契约：半径 4-8、1px 发丝线、零 `backdrop-filter`、状态色只用语义色 |

## 硬约束

1. **不动后端**。所有字段现有接口都有；缺什么先报告，不要自己加接口。
2. **`healthState.js` 只加不改**：新增导出（如 `groupOf(status)`、`severityRank(check)`），现有 `healthStateLabel` / `isFreshCheck` / `createDiagnosticState` / `normalizeDiagnosticFailure` 的签名与行为保持不变——有测试和其它调用方。
3. **状态只用语义色**：异常 `--ds-semantic-danger`、未配置 `--ds-semantic-warning`、缺证据/无权限 `--ds-semantic-neutral`、通过 `--ds-semantic-success`。**不许**给「未检查」用绿色或红色，**不许**发明新色相。
4. **状态不能只靠颜色**：每个状态必须有形状（实心/虚线空心/锁）+ 文字。
5. **`NOT_CHECKED` 与 `UNCONFIGURED` 必须视觉可分**：前者虚线空心（缺证据），后者实心琥珀（等你配置）。
6. **不做**：不弹庆祝动效、不用 `backdrop-filter`、不在列表里塞内联图表、不把 4 个工具做成 4 个弹窗。
7. **不要重写** `NetworkDiagnosticTool.vue` / `ConfigDiffTool.vue` 的内部逻辑，只按新的容器结构挂载它们。

## 分阶段执行（每阶段结束等我确认）

### 阶段 1：数据形状与分组逻辑（不碰 DOM）

- 新建 `components/diagnostics/healthGroups.js`：`groupOf(status)` → `action|config|unknown|pass|forbidden`；`rank(check)` → `ACTIVE_PROBE(0) < LOCAL_CHECK(1) < CONFIGURATION(2)`，同档按 `durationMs` 降序。
- 单测（沿用 `frontend/test/*.test.mjs` 的写法）：5 个状态各归到正确的组；排序稳定；`checkedAt=null` 不被当成新鲜。
- 验收：`node --test frontend/test/health-groups.test.mjs` 通过。

### 阶段 2：结论带 + 分组列表

- `ConclusionBar.vue`：三个计数（含 0 也显示，降饱和）+ 新鲜度环（用 `FIVE_MINUTES_MS`）+ 「重新检查」；`role="status" aria-live="polite"`。
- `CheckGroupList.vue` + `CheckRow.vue`：分组顺序 `需要处理 → 需要配置 → 缺证据 → 通过`，`通过` 默认折叠；行内三栏（状态+名称 / 证据摘要 / 硬度+耗时+时间）。
- `checkKind` 中文档位必须有 tooltip：`主动探测`=真的连了下游；`本地检查`=只证明请求链路活着；`配置读取`=只读了配置。
- 验收：1440 与 768 截图；把截图转灰度后仍能分辨五个语义组。

### 阶段 3：过期与失败

- 过期：整块降饱和 40% + 顶部提示条（「正在显示 HH:MM 的快照」），不只改某个 pill 的颜色。
- 诊断失败：只在结果面板内报错（用 `normalizeDiagnosticFailure` 的 category 文案），并**明确写「这不代表目标服务不健康」**；失败后旧结果立刻置 stale。
- 验收：手动把系统时间往前调 6 分钟，或把 `checkedAt` 改成过去，截图证明降饱和与提示都出现。

### 阶段 4：能力边界 + 工具条

- `PolicyPanel.vue`：并发、超时、响应上限、目标数、三个配置布尔。**只在 `admin` 范围渲染**（`GET /health` 无 `policy` 时整块隐藏，不显示「未知」）。
- `ToolBar.vue`：chips 一行（`主机/数据库/Kubernetes/网络路径/HTTP 探针/证书/配置差异`），选中后在下方原位展开面板。
- 从检查项的 `[去处理 →]` 进入时，自动选中对应工具并预填目标。
- 验收：`policy` 六项都在；非 admin 侧看不到这块。

### 阶段 5：统一诊断结果面板

- `DiagnosisResultPanel.vue`：四个工具共用（host/database/kubernetes/network），头部 = 目标 + 耗时 + 结论；主体 = 分层/分项可折叠列表（每项：名称 · 状态 · `command`（等宽）· `evidence`）；底部 = `findings` 按 severity 排序。
- `EvidenceBanner.vue`：`permissionDenied / dataMissing / unverified / truncated` **合并成一条**横幅，四个中文文案见 DESIGN §8.3；有任一为 true 就必须出现。
- `layers[].blockedBy` 渲染成「被阻断（不是故障）」，**不许**用故障红。
- 验收：四个工具各跑一次（或 mock 一份结果），截图证明共用同一套面板；阻断层不显示为失败。

## 交付格式

1. 改动文件清单 + 每文件一句话
2. 数据字段核对表：设计里用到的每个字段 ← 对应后端 `record` 的哪个成员（缺哪个直接标红）
3. 1440 / 768 截图（含过期态、失败态各一张）
4. 分组与排序的单测输出
5. `DESIGN.md §13` 验收清单逐条打勾，未通过项写明原因
6. 对 `healthState.js` 的改动 diff（应只有新增导出）

## 一句话判据

一个不熟悉这个系统的人，打开页面 3 秒内必须能说出：**现在有没有问题、几项、要不要我现在动手。**
做不到，就是没做成——标题写成「配置非证据」也算没做成。
