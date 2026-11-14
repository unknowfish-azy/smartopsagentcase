# 实现提示词：把「构成场」从贴纸改成活的

把下面整段发给 Trae（或任何能改本仓库的模型）。它要求仓库里已有 `docs/design/agent-module-live-field-v1/`。

---

## 你的任务

`/agent/module`（`views/agent/AgentModuleView.vue`）的构成场现在只吃一个状态字符串，视觉参数是硬编码常量，所以它是贴纸。把它改成**由真实遥测驱动的参数场**：八个参数各接一个后端字段，数据变了形状必须变，数据不变画面必须完全静止。

**先读、再核对字段、后实现。** 第一步只输出：字段核对表 + 参数公式确认 + 分阶段计划，等我确认后再动代码。

## 开工前必读

| 文件 | 从中拿到 |
| --- | --- |
| `docs/design/agent-module-live-field-v1/RESEARCH.md` | 贴纸根因（逐行证据）+ GitHub 选型（许可实测）+ 「科技感」的真来源 |
| `docs/design/agent-module-live-field-v1/DESIGN.md` | 八参数表、五吸引子、渲染规格、spring、迟滞、新鲜度、降级、验收清单 |
| `docs/design/agent-module-live-field-v1/field-lab.html` | 参数场实验台：拖滑杆看形状怎么变；`?demo=busy` 是同一份代码在另一组数据下的形状 |
| `views/agent/AgentModuleView.vue` | 现状：`:280-336` STATES 常量、`:404` 两分支 derivedState、`:388-399` 已算出但没用的 health/alerts |
| `components/agent/fable/{FableComposition,FableGaze,FatBlob}.vue` | 现有 SVG 结构；`FableComposition` 目前只收 `state: String` |
| `src/visual/motionScheduler.js`、`src/visual/visualMode.js` | 动效预算与降级开关，**必须复用，不要自建 rAF** |
| `src/api/decisionLoop.ts`、`src/api/inspector.ts` | `getDecisionLoops()`、`getDecisionLoopStats()`（**目前没用上**）、`getInspectorSummary()` |

## 硬约束

1. **不改后端、不加接口**。`GET /api/agent/loops/stats` 已经存在（返回 `total/reviewed/resolved/learnedCount/byStage/resolveRate`），直接用。
2. **参数只在 `useCompositionField.js` 里算**，组件只消费 `field`。模板里**不许出现** `'1.00'`、`'−12°'` 这类字面量。
3. **`FableComposition` 的 props 从 `state: String` 改成 `field: Object`**；`state` 可保留为 `attractor`，但**只用于高亮主导阶段，不得决定形变**。
4. **数据不变时画面完全静止**。唯一允许的无数据运动是 `pulse`（心跳）与 `gaze` 游移；`stale` 时两者都停。这条是判据，验收会截图对比。
5. **读不到就冻结 + STALE**，不许补数、不许画一个假的平衡态。
6. **演练必须可见**：手点状态切换时加 `REHEARSAL` 角标 + 虚线锁定环；点「跟随运行时」立刻回到数据驱动。
7. **零新依赖**（路线 A：手写 spring，约 20 行）。**不要**引入 Rive / Lottie / anime / Three / OGL / Pixi。
8. **禁止** `filter: blur`、`backdrop-filter`、WebGL；动画只碰 `transform / opacity / stroke-dasharray / stroke-dashoffset / r / d`。

## 分阶段执行（每阶段结束等我确认）

### 阶段 1：参数字段核对 + 纯函数

- 先打印一次真实数据：`GET /api/agent/loops/stats` 的 `byStage` 到底有哪些 `stage` 值（表默认 `'ANALYZE'`），以及 `inspector/summary` 的字段名（`total/pass/warning/high/critical` 是否都在）。
- 新建 `views/agent/fable/useCompositionField.js`：`(loops, stats, summary, companion) → field{aperture,tilt,volume,spin,groove,gaze,grain,pulse}`，**不 import Vue、不碰 DOM**。
- 每个参数写注释指向 DESIGN §2 的对应行。
- 单测：固定输入 → 确定输出；全 0 / 超大值不越界；`stage` 出现未知值时归到默认且不抛错。
- 验收：贴出 `byStage` 真实取值 + 单测输出。

### 阶段 2：组件改造（先把「数据→形状」打通）

- `FableComposition.vue` 改 props 为 `field/attractor/stale/reduced`，内部按 DESIGN §4 映射到 SVG 属性。
- spring 插值：`cur += (target - cur) * (1 - exp(-dt/tau))`，`tau = 0.28`，`dt` 从 `motionScheduler` 拿。
- 迟滞：孔径 <0.02、倾角 <1.5°、体积 <0.01 的变化不更新 target。
- 验收：改 `learnedCount` → 600ms 内刻线数变化；改 `high` → 孔径收窄。

### 阶段 3：新鲜度、STALE、演练

- 10s 轮询（可复用现有 load），`fetchedAt` + 30s 判 stale。
- stale：整场降饱和 40% + `STALE` 角标 + 停 pulse + 读数 `—`。
- 请求失败：保留上一帧形状 + stale，不显示假的静观态。
- 演练：`REHEARSAL` + 锁定环；`FOLLOW RUNTIME` 复位。
- 验收：停后端 30s 截图；演练态截图。

### 阶段 4：降级与性能

- `prefers-reduced-motion` / `visualMode = reduced-motion`：无插值、无 pulse、无游移，直接落位。
- 低端：刻线 8 条、去内螺旋与相位楔。
- 实测：稳态帧时、8 参数插值开销、离屏暂停是否生效（切标签页 30s 后回来不应补间）。
- 验收：贴测量数据（设备、分辨率、Chrome 版本）。

## 交付格式

1. 改动文件清单 + 每文件一句话
2. **字段核对表**：八个参数 ← 后端哪个字段 ← 哪个接口（缺的标红并说明降级）
3. 三张截图：常态 / `STALE` / `REHEARSAL`
4. 「数据不变」证据：静置 60s 前后两次截图（除时间戳应完全一致）
5. `DESIGN.md §10` 验收清单逐条打勾，未通过项写原因
6. 对 `FableComposition` props 的 diff（应只有 props + 内部映射，不改视觉语言）

## 一句话判据

**如果后端的数字全都没变，画面就不许动。** 动了就是装饰；不动、但数字一变立刻跟着变，才算仪器。
