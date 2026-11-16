# 引擎可观测 · 3D 引擎场 v1（ENGINE OBSERVABILITY 3D FIELD）

- 日期：2026-11-16
- 状态：**已执行**（2026-11-16 15:42 用户看页截图问「为什么没有动态动画，要 3D 的」；裁决：现有页内加一块 + 六引擎节点绑真实心跳）
- 小红书原文 WebFetch 成功，抓到的配图是评论表情包、界面主体未展开；技术栈由项目自身决定（three@0.186 已在依赖中）
- 上游口径：`docs/design/engine-observability-v1/DESIGN.md`（三条铁律全部继承，不改）
- 来源：小红书「AI量化引擎怎么全自动运行？Opus直接给你看」——只借"把引擎每时每刻在干嘛摊开"的功能内核，不碰量化交易/行情/收益。

---

## 0. 为什么现在没有动画（用户问的直接回答）

原方案刻意只做静态卡 + Canvas 2D 时间轴，原因写在三条铁律里：**无事件即静默、禁止用动画假装它在工作**。当时担心任意转动的 3D 会制造"引擎在忙"的假象，与"摸鱼检测"主题自相矛盾。

本次解法：**不是去掉约束，而是让动画本身成为真实数据的编码器**。节点只有在真实心跳新鲜时才亮/呼吸；无事件的节点就是暗的、完全静止的。转的从来不是"装饰"，是数据本身。

---

## 1. 视觉定义

在页头概览条与引擎卡片网格之间插入一块 3D 引擎场（高度约 240–280px，桌面；窄屏退化列表）。

**六个节点** = 六条真实引擎（sentinel-poll / sentinel-guardian / web-research / inspector / decision-loop / operation-run），按 id 固定角度排布于一个扁圆环（避免随机排布导致每次刷新位置不同）。

| 真实状态 | 3D 表现 | 数据来源 |
|---|---|---|
| RUNNING | 节点核心发光 + 缓慢呼吸（周期 2.4s），环上一条弧线随 `ageSec` 增长推进到 `expectedPeriodSec` 为止 | `eng.status` / `eng.ageSec` / `eng.expectedPeriodSec` |
| STALLED | 琥珀色、呼吸变慢且断续（周期随超时倍数变长），节点轻微下沉 | `ageSec / expectedPeriodSec` |
| ERROR | 红色尖峰闪一次后保持暗红稳态（不循环闪，避免假繁忙） | `eng.status === 'ERROR'` |
| NO_DATA | 灰色空心轮廓，完全静止 | `eventCount === 0` |
| NOT_RUN | 灰色虚线轮廓，完全静止，标签带「未运行」 | `status === 'NOT_RUN'` |

**中心**不是装饰球体，而是显示聚合状态：最后心跳时间 `generatedAt` 与 live 引擎数；无事件时中心只显示「静默」。

**不做**：服务器机房模型、区块链式连线流、随机的"数据流动"粒子——那些都会暗示不存在的活动。

---

## 2. 技术实现

- 新建 `src/components/sentinel/EngineField3D.vue`，用 three.js（项目已有 `three@0.186`）。
- 复用 `ParticleWhale.vue` 的成熟模式：`Scene` + `PerspectiveCamera` + `WebGLRenderer({alpha:true, antialias:false})`、像素比上限 1.5、`subscribe()` 共享 rAF、`observeCanvasTheme` 主题跟随、`onBeforeUnmount` 完整 dispose（geometry/material/renderer/observer/rAF）。
- props: `engines`（来自 `obs.engines.value`）、`selectedId`、`generatedAt`。**组件内不 fetch、不轮询**，完全由父级喂数据。
- 场景元素：6 个 `Mesh`（球体/八面体）+ 每节点一个呼吸光晕（`Sprite` 或半透明球）+ 扁平圆环轨道（`LineLoop`）+ 状态色 `CSS2D` 标签（用 HTML overlay 而非 three 的 CSS2DRenderer，省一个 addon）。
- 状态变化用 `watch` 驱动材质颜色/发光强度/呼吸速度，不做位置随机动画；节点位置只按固定角度布局。
- 点击节点 → emit `select(id)` → 父级 `obs.selectEngine(id)`，与现有卡片选中态联动。

**降级（沿用 G5 四重）**：
- `prefers-reduced-motion` / `visualMode=lightweight|reduced-motion` / `isDegraded()` / WebGL 不可用 → 渲染静态 SVG 引擎场（同样六节点 + 状态色，无动画），DOM 结构与 3D overlay 一致，测试可断言。
- 窄屏 ≤760 → 不渲染 3D，改列表（页内已有卡片网格，3D 块隐藏）。

---

## 3. 红线（违反即不通过）

1. **任意时刻的动画强度必须能追到一个真实字段**：呼吸周期 ← `ageSec/expectedPeriodSec`，颜色 ← `status`，中心数字 ← `generatedAt`/live 数。做不到就让它静止。
2. **NO_DATA / NOT_RUN 节点禁止任何自动动画**。
3. 不新增后端接口、不改表、不改 poller；纯粹把 `/snapshot` 已有字段可视化。
4. 无金额、无收益、无准确率、无量化的 K 线与行情。
5. `training` 仍是 NOT_RUN 灰卡（3D 场里也是灰虚线静止节点）。

---

## 4. 验收门禁

- 单测：新增 `engineField3D.js` 纯函数（节点布局、状态→视觉参数映射、呼吸周期计算）独立测试。
- 浏览器：`engine-observability.browser.mjs` 扩展，mock live（含 STALLED/ERROR/NOT_RUN）+ 断言：6 节点存在、NOT_RUN/NO_DATA 节点静止（连续两帧像素一致）、STALLED 颜色为琥珀、点击节点联动选中卡片、reduced-motion 下走 SVG 静态分支、0 pageError、无横向溢出。
- 工程：`typecheck` 0、`lint` 0 error、双 build 通过；3D 组件按需 import，不进首屏主包。
- 真实性核查：逐项说明每个动效对应的真实字段。

---

## 5. 待裁决（默认执行）

- **D-3D1**：3D 与静态卡同时显示（默认：是，卡在下方保留全部数字）。
- **D-3D2**：节点标签用中文名还是 id（默认：中文名 + 小字 id）。
- **D-3D3**：3D 场默认展开还是折叠（默认：展开，但轻量模式下自动折叠为静态）。

---

## 6. 执行结果（2026-11-16 15:42–16:00）

**落地文件**
- `frontend/src/components/sentinel/engineField3D.js`（新增）：纯函数层——六节点固定角度布局、状态→视觉参数（呼吸周期由 age/period 推导）、中心聚合。
- `frontend/src/components/sentinel/EngineField3D.vue`（新增）：three.js 3D 场 + 静态 SVG 降级；6 节点、进度弧、中心数字、HTML 名字标签与点击命中区。
- `frontend/src/views/sentinel/EngineObservabilityView.vue`：概览条与卡片网格之间插入 3D 块，新增窄屏检测。
- `frontend/test/engine-field-3d.test.mjs`（新增）：6 条纯函数测试。

**真实浏览器实测**（dev 5173，带 6 引擎 mock，含 STALLED/ERROR/NO_DATA/NOT_RUN）
- 3D canvas = 1、六节点按钮 = 6、中心「2 运行中 / 6」、卡片 = 6。
- 点击第 4 个节点（无数据的纠察）→ 下方选中卡片联动正确。
- reduced-motion 页面：静态 SVG = 1、canvas = 0（降级生效）。
- `page errors: none`。
- 截图：`frontend/test-artifacts/eo3d-expanded.png`（gitignore）。

**门禁**：`npm test` **812/812**（+6 新测）、typecheck 0、lint 0 error（4 warning 均为并行改动文件）、`npm run build` 通过、a11y 0 seriousCritical / 0 overflow / 0 pageErrors / axe 无违规。

**关键坑（务必记住）**
1. **v-if / ref 死锁**：3D 容器若写 `v-if="webglReady && !staticMode"`，`host` ref 在 onMounted 时永远不存在 → WebGL 永不初始化 → 永远走降级。改成容器常驻 `v-show`，静态分支独立 `v-if="!webglReady || staticMode"`。
2. 呼吸只驱动 halo 的 opacity/scale；`engineVisualState` 对 NO_DATA/NOT_RUN 返回 `animated:false`，rAF 里 `continue` 跳过——这是「无事件静默」的代码级保证，不要改成统一动画。
3. 卡片状态色与 3D 节点色都从 `--ds-color-*` 令牌解析，避免两套色值漂移。

**未做**（红线）：无服务器机房模型、无随机数据流粒子、无收益/K 线；不新增后端接口、不改表、不改 poller。
