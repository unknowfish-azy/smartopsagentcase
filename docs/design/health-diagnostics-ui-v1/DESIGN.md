# 健康诊断模块 UI 设计 v1

> 一句话：**这个模块的职责是「告诉你现在有没有问题、问题在哪、下一步做什么」，不是「展示一堆检查项」。**
> 现状把三层信息压成了一层平铺列表：结论、证据、工具混在一起，用户看完仍然不知道要不要动手。

| 项 | 值 |
| --- | --- |
| 对应路由 | `frontend/src/router/index.js:68` → `/health` · `HealthCenter` · `SERVICE DIAGNOSTICS / 健康诊断` |
| 现有页面 | `views/diagnostics/HealthCenterView.vue`（8 行，巨标题「配置非证据」+ `HealthCheckList` + 3 个工具面板） |
| 现有组件 | `components/diagnostics/HealthCheckList.vue`、`healthState.js`、`NetworkDiagnosticTool.vue`、`ConfigDiffTool.vue` |
| 数据来源 | `GET /api/diagnostics/health`（user 范围）、`GET /api/diagnostics/admin/health`（admin 范围 + `policy`） |
| 后端实现 | `diagnostics/HealthDiagnosticService.java`，返回 `Summary{scope, checks[], policy?}` |
| 主动诊断 | 4 个独立 POST：`/api/diagnostics/host|database|kubernetes|network/diagnose`，另有 `/http`、`/certificate` |
| 设计面 | 工具层（控制台）：半径 4-8px、1px 发丝线、零 `backdrop-filter`、无 WebGL、状态色只用语义色 |

---

## 1. 现有实现的问题（逐条对应代码）

| # | 问题 | 证据 | 后果 |
| --- | --- | --- | --- |
| 1 | **首屏不回答「现在健康吗」** | `HealthCenterView.vue:1` 的 `<h1>` 是「配置非**证据**」，这是宣言不是模块名 | 用户第一眼看到的是口号，得自己数下面 7 行 |
| 2 | **7 个检查项平铺，没有优先级** | `HealthCheckList.vue:9` `v-for` 直接铺开 | 「1 项异常」和「6 项正常」占同样视觉权重 |
| 3 | **四种状态视觉权重相近** | `healthState.js:22-31` 里 `UNHEALTHY`/`UNCONFIGURED`/`NOT_CHECKED`/`FORBIDDEN` 并存，样式只有 `healthy/unhealthy/unconfigured/not_checked/forbidden` 五个近似 pill | 「没检查」被当成「有问题」，「已配置但未探测」和「没配置」混为一谈 |
| 4 | **证据硬度没有标注** | 后端 `Check.checkKind` 有 `LOCAL_CHECK / ACTIVE_PROBE / CONFIGURATION` 三档，前端只把它当小字元数据（`HealthCheckList.vue:10`） | 「请求活着」和「数据库真连上了」看起来一样硬 |
| 5 | **过期只有一行小字** | `HealthCheckList.vue:6` 文案 + `stale` 只作用于 pill 变警告色 | 5 分钟后的旧结果仍以正常配色展示，容易被当成实时 |
| 6 | **`policy` 被前端丢掉** | `HealthCheckList.vue:33` `emit('policy', …)`，`HealthCenterView.vue` 没有接 | 用户不知道并发 2、超时 3s/8s、响应上限 256KB，会误判「超时 = 服务挂了」 |
| 7 | **工具与检查结果脱节** | 检查项说「在工具中心选择目标执行检查」，页面上没有直达路径 | 从「发现问题」到「动手」中间断了一环 |
| 8 | **诊断失败 vs 服务不健康 不分** | `healthState.js:33-48` 已有 `errorCategory` 归一化，但没有 UI 位置 | 授权失败、超时、断言不匹配都被读成「服务坏了」 |
| 9 | **4 个主动诊断没有统一结果视图** | `HostDiagnosisResult` / `DatabaseDiagnosisResult` / `KubernetesDiagnosisResult` / `NetworkPathResult` 结构高度相似（scope + startedAt/endedAt/durationMs + checks/layers + 标志位），前端只有 `NetworkDiagnosticTool` 一个 | 加第 5 个工具就要再抄一遍 UI |

---

## 2. 设计原则（四条，冲突时按顺序让位）

1. **结论先行。** 首屏第一行必须是「现在什么状态、要不要我动手」，不是标题、不是列表。
2. **无证据 ≠ 正常。** `NOT_CHECKED` / `UNCONFIGURED` 必须与 `HEALTHY` 在形状上就能分开（虚线 + 空心图标），不靠颜色区分。
3. **每条结论都标「有多硬」。** 每个检查项旁边写清它是本地检查、主动探测还是只读了配置。
4. **不能做就说原因。** 探测受限（并发/超时/权限/截断）时必须显式提示，不能把「没拿到证据」渲染成「一切正常」。

---

## 3. 三层信息架构

```
┌─ ① 结论带 ConclusionBar ───────────────────────────── 全宽 72px ─┐
│  ● 1 项需要处理   2 项缺证据   4 项通过   │  最近 2 分钟前 · 3 分钟后过期  [重新检查] │
└──────────────────────────────────────────────────────────────────┘
┌─ ② 检查层：按「要不要你动手」分组 ────── 8 栏 ─┐┌─ ③ 能力边界 ─ 4 栏 ─┐
│ ▾ 需要处理 (1)                                  ││ 探测限额 3 / 12 次   │
│   ✕ 关键业务表        主动探测 · 34ms           ││ 并发 2（全局 4）     │
│     部分关键表不可访问：knowledge_candidate…     ││ 超时 连接 3s / 读取 8s│
│     下一步：检查数据库迁移和表权限  [去处理 →]   ││ 响应上限 256 KB      │
│ ▾ 缺证据 (2)                                    ││──────────────────────│
│   ◌ Harbor 镜像仓库    配置读取 · 已配置未探测   ││ 工具                 │
│   ◌ 观测数据源         配置读取 · 未配置         ││ [主机][数据库][K8s][网络]│
│ ▸ 通过 (4)  ← 默认折叠                           ││ [HTTP][证书][配置差异] │
└─────────────────────────────────────────────────┘└──────────────────────┘
┌─ ④ 诊断结果面板（选中工具后出现，全宽） ──────────────────────────┐
│ K8s 诊断 · demo/web-7d9f · 2.4s · 结论：2 处发现  ⚠ 证据不完整(权限)│
│ ▾ DNS 解析     通过   3 项检查                                    │
│ ▾ TCP 连接     阻塞   被「缺少 NET_ADMIN」阻断（不是故障）          │
│ ▸ 发现 2 条：severity=high resource=Service/web-svc …             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. 状态语义（本设计最核心的一张表）

后端 `Check.status` 有 5 个值，前端还有 `stale` 与「诊断失败」两种派生状态。**必须**按下表区分为四个语义组，而不是五个同权重的 pill：

| 语义组 | 状态 | 颜色 | 形状 | 文案 | 是否催人 |
| --- | --- | --- | --- | --- | --- |
| **需处理** | `UNHEALTHY` | `--ds-semantic-danger` `#f85149` | 实心圆 + `✕` | 异常 | ✅ 排最前 |
| **需配置** | `UNCONFIGURED` | `--ds-semantic-warning` `#d29922` | 实心圆 + `!` | 未配置 | ✅ 排在需处理之后 |
| **缺证据** | `NOT_CHECKED` | `--ds-semantic-neutral` `#8b949e` | **虚线圆环 + 空心** | 未检查 / 已配置未探测 | ❌ 不催，但必须可见 |
| **通过** | `HEALTHY` | `--ds-semantic-success` `#3fb950` | 实心圆 + `✓` | 正常 | ❌ 默认折叠 |
| **无权** | `FORBIDDEN` | `--ds-semantic-neutral` 更暗 | 锁形 | 无权限查看 | ❌ 只说明，不催 |
| **过期** | `stale`（派生） | 整组降饱和 40% + 顶部条 | — | 结果可能已过期 | ⚠️ 提示重查 |
| **诊断失败** | `errorCategory`（派生） | 独立错误块，**不进检查列表** | — | 「检查未完成：授权失败/超时…」 | ✅ 提示重试 |

**三条硬规则**：

1. `UNCONFIGURED` 与 `NOT_CHECKED` **不能同色**。「你还没配」需要人动作，「配了但没探测」只是缺证据。
2. `NOT_CHECKED` **永远不用绿色、也不用红色**。它是空的，不是好的也不是坏的。
3. `stale` 是**整块**属性，不能只改某一行 pill 的颜色——过期的是「这份报告」，不是某一条检查。

---

## 5. ① 结论带（ConclusionBar）

**必须**

- 高度 64–72px，一行放完；`role="status" aria-live="polite"`，只在结论变化时播报。
- 三个计数 + 一个新鲜度 + 一个动作：
  ```
  ● 1 项需要处理   2 项缺证据   4 项通过    │  最近 2 分钟前 · 3 分钟后过期  [重新检查]
  ```
- **计数为 0 时也显示**（`0 项需要处理` 比消失更可信），但降饱和到 `--ds-semantic-neutral`。
- 全部通过时结论文字变成「全部通过 · 7 项检查」，颜色转 success，**不要**弹庆祝动效（这是运维界面）。
- 一项都没查过时：`尚未检查 · 没有证据`，配中性色，动作按钮文案变成「开始检查」。

**应该**

- 新鲜度用 40px 环形进度（剩余时间/5 分钟），hover 显示 `最近获取 14:02:11 · 5 分钟内有效`（沿用 `FIVE_MINUTES_MS`）。
- 过期后环形变成静止的琥珀环，同时整页检查区加 40% 降饱和 + 顶部一行 `结果可能已过期，正在显示 14:02 的快照 [重新检查]`。
- 「重新检查」进行中：按钮变 `检查中… 3/7`，**不阻塞**已渲染内容（现有 `HealthCheckList.vue:4` 已经道歉式提示「旧结果仅作参考」，保留这个诚实做法）。

**可以**

- 结论带右侧放「导出快照」（JSON），便于贴进工单。

---

## 6. ② 检查层（分层列表）

### 6.1 分组与排序

**必须**

- 按固定顺序分组：`需处理 → 需配置 → 缺证据 → 通过`，每组标题带计数，`通过` 组默认折叠。
- 组内排序：先按 `checkKind` 硬度（`ACTIVE_PROBE` > `LOCAL_CHECK` > `CONFIGURATION`），再按 `durationMs` 降序——慢的检查更可能是问题源头。
- `FORBIDDEN` 不进任何组，单独一行灰字放在最后：`1 项无权查看（需要管理员权限）`。

### 6.2 单行结构

```
[状态标记] 关键业务表                              主动探测 · 34ms · 14:02:11
           部分关键表不可访问：knowledge_candidate、operation_run_record
           下一步：检查数据库迁移和表权限              [去处理 →]
```

| 位置 | 内容 | 数据字段 |
| --- | --- | --- |
| 左 | 状态标记（形状 + 颜色）+ `label` | `status`、`label` |
| 右上 | 证据硬度 + 耗时 + 时间戳 | `checkKind`、`durationMs`、`checkedAt` |
| 中 | 证据摘要（1–2 行截断，可展开） | `summary` |
| 下 | 下一步 + 跳转 | `nextAction` |

**必须**

- `checkKind` 用中文而不是枚举值，并配一个极小的图标区分三档：
  - `LOCAL_CHECK` → `本地检查`（盾形）：证明请求链路活着，但**不证明下游服务健康**
  - `ACTIVE_PROBE` → `主动探测`（脉冲）：真的连了一次下游
  - `CONFIGURATION` → `配置读取`（文档）：只读了配置，没有连
- `checkedAt` 为空时显示 `—` 并标注 `无时间戳`，**不要**用 `Instant.now()` 兜底（后端 `HealthDiagnosticService.java:69` 在检查未完成时传 `null`，这是有意义的）。
- `nextAction` 是必填字段，永远显示；有可跳转目标时给 `[去处理 →]`，直接跳到对应工具并预填 `targetId`。

**应该**

- 点击行展开：完整 `summary`（不截断）+ `scope` + 原始 `id`（便于贴给 agent）+ 时间戳原文。
- 键盘：`↑↓` 在行间移动，`Enter` 展开，`R` 重新检查。

---

## 7. ③ 能力边界面板（PolicyPanel）

后端只在 admin 范围返回 `policy`（`HealthDiagnosticService.java:99`），**必须**展示，因为它回答了「为什么我不能一直点检查」和「为什么会有超时」。

| 字段 | 展示 | 为什么重要 |
| --- | --- | --- |
| `perUserConcurrency` / `globalConcurrency` | `并发 2（全局 4）` | 说明第 3 个并发探测会被拒，不是故障 |
| `connectTimeoutMs` / `readTimeoutMs` | `超时 连接 3s / 读取 8s` | 超时阈值以内的慢响应是正常的 |
| `maxResponseBytes` | `响应上限 256 KB` | 超过会被截断 → 对应结果的 `truncated` 标志 |
| `targetCount` | `授权目标 3 个` | 没有目标时所有探测都无从谈起 |
| `miniConfigured` / `observabilityConfigured` / `harborConfigured` | 三个布尔 → 图标 | 和检查项里的 `UNCONFIGURED` 互相印证 |

**必须**：非 admin 范围（`GET /health` 不带 policy）时整块隐藏，不显示「未知」。

---

## 8. ④ 工具区与诊断结果面板

### 8.1 工具区

现状把 `NetworkDiagnosticTool` 放了两遍（`certificate-mode`）再加 `ConfigDiffTool`，三个面板同权重一路排下去。改成：

- **工具条（chips）**：`主机` `数据库` `Kubernetes` `网络路径` `HTTP 探针` `证书` `配置差异`，一行放完，横向滚动优先于换行。
- 选中后**在下方原位展开**一个面板（不是弹窗、不是跳页），面板头部固定显示：工具名 · 目标 · 状态 · 耗时 · `[重新诊断]`。
- 默认不选中任何工具，避免首屏就压一块大面板；从检查项的 `[去处理 →]` 进入时自动选中并预填。

### 8.2 统一结果面板（4 个工具共用）

四个后端结果的字段高度一致，**必须**抽成一个 `DiagnosisResultPanel`：

| 区块 | 数据 | 渲染 |
| --- | --- | --- |
| 头部 | `scope` + `startedAt`/`endedAt` + `durationMs` + `overallStatus` | 一行：目标 · 耗时 · 结论 |
| **证据完整性横幅** | `unverified` / `truncated` / `permissionDenied` / `dataMissing` | 见 §8.3，**有任一项为 true 就必须出现**，压在头部下面 |
| 分层/分项 | `checks[]`（host/db）或 `layers[].checks[]`（network/k8s） | 可折叠列表，每项：名称 · 状态 · `command`（等宽）· `evidence`（可展开） |
| 发现 | `findings[]`（`type` / `severity` / `resourceKind` / `resourceName`） | 按 severity 排序，`high` 用 danger 左边框 |
| 阻断说明 | `layers[].blockedBy` | 单独一行「被 X 阻断（不是故障）」，**不能**渲染成红色失败 |

### 8.3 证据完整性横幅（本设计的第二条核心）

后端已经有四个「证据不完整」标志位，前端一个都没展示。**必须**按下表翻译成人话，且样式统一用琥珀底、不参与「故障」配色：

| 标志 | 文案 | 用户该做什么 |
| --- | --- | --- |
| `permissionDenied` | `权限不足，部分检查没有执行` | 换授权账号或用管理员目标；**不要**当成服务故障 |
| `dataMissing` | `部分数据缺失，结论基于不完整的数据` | 补采集或放宽采集范围 |
| `unverified` | `未验证：结果只反映采集到的部分` | 看待结论时保留余地 |
| `truncated` | `输出被截断（超过 256 KB 上限）` | 缩小查询范围后重跑 |

多标志同时为真时**合并成一条**，列出全部原因，不要叠四个横幅。

### 8.4 「诊断失败」与「服务不健康」必须分开

`healthState.js:33-48` 已经把失败归类成 `CONFIGURATION / AUTHORIZATION / TIMEOUT / NETWORK / ASSERTION / NOT_CHECKED`。UI 上：

- 诊断工具响应失败 → 在**结果面板内部**显示错误块：`检查未完成：检查超时（8s）`，配 `[重试]`，并明确写 `这不代表目标服务不健康`。
- **不**把失败写进 §6 的检查列表——列表只放真正执行完成的检查结论。
- 失败后旧结果保留但立即置 `stale`（现有 `createDiagnosticState` 已这么做，UI 要跟上）。

---

## 9. 布局与响应式

| 宽度 | 形态 |
| --- | --- |
| ≥1440 | 结论带全宽；8/4 两栏（检查列表 / 能力边界+工具）；结果面板全宽 |
| 1024–1439 | 同上，右栏收窄到 300px，`policy` 项两列变一列 |
| 768–1023 | 单栏堆叠：结论带 → 检查列表 → 工具条 → 结果面板；能力边界折叠成一行可展开 |
| <768 | 结论带压成两行（计数一行、动作一行）；检查行变单列（状态+名称一行，摘要一行，下一步一行）；`[去处理]` 变整行按钮 |

适配断点严格用 `src/design/breakpoints.js` 的 375 / 768 / 1024 / 1440 / 1920。

---

## 10. 令牌映射

| 用途 | 令牌 | 值 |
| --- | --- | --- |
| 页面底 | `--ds-surface-base` | `#0E1116` |
| 卡片/面板 | `--ds-surface-raised` | `#151A21` |
| 展开行/工具面板 | `--ds-surface-overlay` | `#1B212A` |
| 结论带底 | `--ds-surface-raised` + 1px `--ds-hairline` | — |
| 正文 / 次要 / 三级 | `--ds-color-text` / `--ds-color-muted` / `--ds-semantic-neutral` | `#e8f2f7` / `#92a6b5` / `#8b949e` |
| 异常 / 待配 / 通过 / 缺证据 | `--ds-semantic-danger` / `--ds-semantic-warning` / `--ds-semantic-success` / `--ds-semantic-neutral` | `#f85149` / `#d29922` / `#3fb950` / `#8b949e` |
| 状态 pill 底 | `--ds-pill-danger-bg` / `--ds-pill-warning-bg` / `--ds-pill-success-bg` / `--ds-pill-neutral-bg` | 见 `variables.css:56-59` |
| 命令/证据代码块 | `rgba(0,0,0,.28)`（`--sunk`），等宽 `--ds-font-mono` | — |
| 半径 | 行 8（`--ds-radius-md`）、卡片 12（`--ds-radius-lg`）、pill 999 | — |
| 字体 | `--ds-font-cn` / `--ds-font-mono`；标签用 `--ds-type-overline-size` + `.12em` 字距 | — |
| 动效 | `--ds-duration-micro` 150ms + `--ds-ease-out` | — |
| 焦点 | `--ds-focus-ring-color` `#7ad7f5`，2px + 2px offset | — |

**禁止**：为状态发明新色相；用绿色表示「未检查」；用红色表示「缺证据」；`backdrop-filter`；状态指示只靠颜色。

---

## 11. 组件拆分

```
views/diagnostics/
  HealthCenterView.vue          ← 只做编排：取数 + 分组 + 事件分发（现在 8 行，之后约 60 行）
components/diagnostics/
  ConclusionBar.vue             ← ① 结论带（含新鲜度环、重新检查）
  CheckGroupList.vue            ← ② 分组列表（容器：分组、排序、折叠）
  CheckRow.vue                  ← 单行 + 展开
  PolicyPanel.vue               ← ③ 能力边界
  ToolBar.vue                   ← 工具 chips
  DiagnosisResultPanel.vue      ← ④ 统一结果面板（host/db/k8s/network 共用）
  EvidenceBanner.vue            ← 证据完整性横幅（§8.3）
  healthState.js                ← 复用并扩展：加 groupOf(status)、severityRank(check)
```

约束：`HealthCheckList.vue` 保留为 `CheckGroupList` + `ConclusionBar` 的组合壳，避免路由返工；`healthState.js` 只**加**导出，不改现有函数签名（有测试与其它调用方）。

---

## 12. 无障碍

- 状态不能只靠颜色：每个状态都有**形状**（实心/虚线/锁/空心）+ **文字**（异常/未配置/未检查/正常）。
- `ConclusionBar` 用 `role="status"` + `aria-live="polite"`；检查行不用 live，避免重查时刷屏朗读。
- 展开行 `aria-expanded` + `aria-controls`；折叠组同。
- 焦点环 2px `#7ad7f5`，不被 `overflow:hidden` 裁掉。
- 热区 ≥44px（检查行 56px、按钮 40px 起）。
- `prefers-reduced-motion`：进度环不转、展开无高度动画。
- 对比度：正文 ≥4.5:1；`#8b949e` 在 `#151A21` 上约 4.6:1，可用但**不要**再降。

---

## 13. 验收清单

- [ ] 首屏 3 秒内能回答三个问题：有没有问题 / 几项 / 我该做什么
- [ ] `UNCONFIGURED` 与 `NOT_CHECKED` 在不看颜色时也能区分（形状不同）
- [ ] `NOT_CHECKED` 在任何主题下都不出现绿/红
- [ ] `checkKind` 三档都有中文标签 + 图标，`LOCAL_CHECK` 旁有「不证明下游健康」的说明
- [ ] `checkedAt = null` 显示 `—`，不显示时间
- [ ] 过期后整块降饱和 + 顶部提示，且能一键重查
- [ ] `policy` 六项全展示（admin 侧），非 admin 侧整块隐藏
- [ ] 四个诊断工具共用 `DiagnosisResultPanel`，没有第二套结果 UI
- [ ] `permissionDenied / dataMissing / unverified / truncated` 四标志各有中文文案且合并成一条横幅
- [ ] 诊断失败只在结果面板内报错，且明确写「不代表目标服务不健康」
- [ ] `[去处理 →]` 能跳到对应工具并预填目标
- [ ] 键盘 `↑↓ Enter R` 可用；`aria-expanded` 正确
- [ ] `prefers-reduced-motion` 下无动画
- [ ] 375 / 768 / 1024 / 1440 四宽度无横向滚动
- [ ] 现有测试通过（`healthState.js` 的函数签名未变）

---

## 14. 参考素材

| 文件 | 说明 |
| --- | --- |
| `index.html` | 单文件参考原型（播种真实字段），含结论带、分组、能力边界、证据横幅、诊断结果面板 |
| `PROMPT.md` | 交给执行模型的实现提示词（分阶段 + 自检 + 交付格式） |
| `preview-1440.png` / `preview-768.png` | 两宽度实际渲染截图 |
