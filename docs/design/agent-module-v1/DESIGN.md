# 智能体模块 · 构成变换（Fable 5.2）v1

> 一句话：**智能体不是聊天框，是一具持续注视基础设施的身体。这个模块把"它在看、它在判断、它在等你批准"画成一张可读的版面，而不是再堆一屏指标卡。**

| 项 | 值 |
| --- | --- |
| 对应路由 | `frontend/src/router/index.js` → `/agent/module` · `AgentModule` · `AGENT MODULE / 智能体模块` |
| 页面实现 | `frontend/src/views/agent/AgentModuleView.vue` |
| 子组件 | `frontend/src/components/agent/fable/FableComposition.vue`、`FableGaze.vue`、`FatBlob.vue` |
| 视觉层 | `frontend/src/assets/styles/fable-agent.css`（全部选择器收在 `.fable-*` 下） |
| 导航 | `navigation/personalSystemNavigation.js` → AGENT 组第三项「智能体模块」；`pageFlow.js` → COMMAND CENTER → EXECUTION TRACE → AGENT MODULE |
| 数据来源 | `GET /api/inspector/summary`（健康/告警）、`GET /api/agent/loops?limit=8`（闭环记录）、`useCompanionStore().states.whale`（运行态） |
| 验收 | `frontend/test/agent-module.browser.mjs`（6 组断言，见 §10） |
| 设计面 | 工具层里的一张"版面"：模块内自带纸面色板，但半径仍用 `--ds-radius-sm`，零 `backdrop-filter`，零 WebGL，零粒子 |

## 0. 参考与取舍

需求给的参考是一条小红书分享链接（`xhslink.cn`）。该链接在浏览器外不可读，只能拿到描述性线索：

- **Fable 5.2 / 构成变换** —— 画面随状态重排的"构成主义"构图层；
- **祂在看** —— 一个持续注视的、带觉知感的视觉主体；
- **新肥波画风 / 舒适** —— 有体积、圆润、柔软、像搪胶或黏土，拒绝锐利与金属感。

所以本设计不是对某张图的复刻，而是把这三条线索翻译成一套可实现的规则：**几何负责结构，注视负责状态，体积负责情绪**。三条规则各自有独立的数据来源与动效预算，互不冒充。

## 1. 三层构成规则

| 层 | 内容 | 实现 | 动效 |
| --- | --- | --- | --- |
| 纸面 PAPER | 96px 测量网格、裁切角标、版号、竖排 `SCALE 1:1 · SVG · REV 5.2`、衬线级细规 | `.fable::before`、`.stage-meta`、`.crop--*` | 静态 |
| 构成 COMPOSITION | 方框（取景框）、弧规（右下四分之一圆，三层）、量规（竖向刻度尺）、斜规（两条对角线）、地尺（肥波脚下的黄油色量杆） | `FableComposition.vue` + CSS 变量 `--fab-*` | 900–1200ms 变换 |
| 肥波 FAT VOLUME | 智能体的"身体"：低阶谐波生成的团块，顶部高光、右下部体积阴影、接触投影 | `FatBlob.vue`（SVG + 定种子路径） | 7.4s 呼吸；体积随状态 0.90–1.05 |

**注视（祂在看）** 不属于构图也不属于身体，它是"状态器官"：一块被椭圆孔径裁切的暖色虹膜 + 深色瞳孔，孔径开合、刻线旋转、瞳孔缩放都由构成状态驱动。它不使用 WebGL，也不用 canvas，全部是 SVG + CSS 变量，随主题换色。

## 2. 五种构成状态

| # | key | 中文 | 英文 | 孔径 | 倾角 | 体积 | 风险 | 回路 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01 | idle | 静观 | IDLE / WATCHING | 1.00 | −12° | 1.00 | 1/5 | 感知 | 构成收拢成一条水平线，孔径最宽，什么都不抓 |
| 02 | analyze | 解析 | PARSING | 0.90 | −21° | 0.96 | 2/5 | 感知 | 环裂成弧、径向刻线展开，目光开始切片 |
| 03 | 决断 | DECIDING | 0.62 | −7° | 0.90 | 4/5 | 规划 | 楔形（弧规）收紧，孔径收窄，只剩两个选项 |
| 04 | execute | 执行 | EXECUTING | 0.78 | −32° | 1.05 | 5/5 | 执行 | 横杆加速、弧线沉入重力，动作被切成节拍 |
| 05 | reflect | 复盘 | REFLECTING | 0.94 | −16° | 0.98 | 2/5 | 核查 | 圆重新合拢，内侧长出螺旋，把这一轮折回自身 |

- `APERTURE / TILT / VOLUME` 三个数字写在标题下方，是**这张图本身的构成参数**（孔径系数、斜规角度、肥波缩放），不是运维指标；标签用等宽小字区分。
- 构成参数与 CSS 变量一一对应：`--aperture`、`--fab-diag-rot`、`--fab-volume`；改状态即改这三处，图形与数字不会各说各话。
- 运行时状态（`companion.states.whale`）只映射到两态：`DEGRADED → 决断`、其余 → `静观`。用户点选其它状态时进入**构成演练**，右下角出现「跟随运行时」按钮；再次点击当前状态即退出演练。

## 3. 版式

```
┌ PLATE 07 · AGENT MODULE · REV 5.2 ─────────────────────────────┐
│ 构成变换            COMPOSITION      ┌ COMPOSITION / 当前构成 ┐ │
│ 说明文案…            TRANSFORM       │ 静观  RUNTIME IDLE    │ │
└──────────────────────────────────────┴───────────────────────┘ │
┌ 舞台 α · COMPOSITION FIELD ───────────────────────────────────┐
│ 01/05 静观      测量网格 + 构成几何 + 注视 + 肥波              │
│ APERTURE TILT VOLUME                                          │
├ 01 静观 │ 02 解析 │ 03 决断 │ 04 执行 │ 05 复盘 ──────────────┤
└───────────────────────────────────────────────────────────────┘
┌ 构成权重 ┬ 回路 ┬ 人工门 ┬ 记忆尾迹 ┐
└──────────┴──────┴────────┴──────────┘
┌ 工具面（通栏，3×2） ─────────────────────────────────────────┐
└──────────────────────────────────────────────────────────────┘
```

- 舞台是**宽幅版面**（`min-height: clamp(520px, 56vh, 610px)`），字幕在左上、注视在右上、肥波在中下、弧规在右下，形成左上→右下的斜向构图；空白是构图的一部分，不再用卡片填满。
- 仪表带固定在舞台下方，四块面板等宽；工具面通栏收尾，让页面以一条"能力清单"结束而不是以空白结束。
- 断点：`1440` 四列仪表带；`1180` 两列（人工门、记忆尾迹、工具面通栏）；`1024` 版头单列、构成谱只留中文与序号；`767` 全部单列、构成谱两列、舞台从绝对定位切回文档流。
- 已核验 375 / 768 / 1024 / 1440 / 1920 无横向溢出（`test/agent-module.browser.mjs` 第 3 组）。

## 4. 数据契约（证据规则）

模块只有三种数据身份，界面上必须可分辨：

| 身份 | 表现 | 来源 |
| --- | --- | --- |
| LIVE | `LIVE` 标签 + 实数 | `GET /api/agent/loops`、`GET /api/inspector/summary`、`companion.states.whale` |
| SAMPLE | `SAMPLE` 标签 + 每条元信息写「SAMPLE · 记忆样例」 | 前端常量 `SAMPLE_MEMORIES`（4 条典型处置），仅在闭环接口不可用时出现 |
| REHEARSAL | `REHEARSAL` 标签 + 文案写明「仅本页构成演练」 | 人工门的「模拟批准 / 模拟驳回」 |

- 接口 503 / 断网 / 未登录：健康、告警、闭环一律显示 `—`，**不补数、不估算**；`健康分 = null` 而非 0。
- 健康分口径与顶栏一致：`round((pass + warning × 0.5) / total × 100)`，`total ≤ 0` 视为不可用。
- 人工门只在页面内改本地状态，`gate-result` 用 `aria-live="polite"` 播报结果，不写任何运行时、不发任何请求。
- 页面底部固定一行证据声明，避免截图外传后被当成真实运维画面。

## 5. 交互契约

| 交互 | 行为 | 可访问名 |
| --- | --- | --- |
| 构成谱五个按钮 | 切换状态；`aria-pressed="true"` 表示当前；再点当前项退出演练 | `01 静观 / IDLE / WATCHING` |
| 跟随运行时 | 演练时出现在印章里，点击回到运行时构成 | `跟随运行时 / FOLLOW RUNTIME` |
| 注视指针开关 | 默认开启；指针在舞台内移动时瞳孔按 30fps 平滑跟随（共享 rAF 调度器） | `aria-pressed` + 文案「注视指针 / GAZE」 |
| 指针离开 | 目标归零，收敛后自动退订 rAF，不常驻 | — |
| 模拟批准 / 模拟驳回 | 本地演练，结果文案明确「不写入运行时」 | 按钮内文字 |
| 记忆尾迹条目 | 只读文本，长标题自动换行 | — |

- 舞台状态变化会通过 `.fable-sr` 的 `aria-live` 区域播报「当前构成：静观。运行时状态 IDLE。」。
- 减少动效（系统偏好或页面「减少动效」档位）：呼吸停止、注视默认关闭、变换过渡压缩为 1ms；版式与信息不变。

## 6. 动效预算

| 动效 | 时长 | 实现 | 降级 |
| --- | --- | --- | --- |
| 构成变换（位置/旋转/缩放） | 900–1200ms，`cubic-bezier(.22,1,.36,1)` | CSS transition + CSS 变量 | `prefers-reduced-motion` → 1ms |
| 孔径开合（遮罩 + 描边同步） | 900ms | 同一 `.aperture-shape` 组的 `scaleY()`，同时供 `mask` 与描边使用 | 同上 |
| 虹膜/瞳孔注视 | 620–700ms | CSS transition，位移由 `--look-x/y` 驱动 | 同上 |
| 肥波呼吸 | 7.4s，`ease-in-out`，幅度 ≤1.6% | 单一 transform 关键帧 | 减少动效或 `data-reduced="true"` → `none` |
| 执行态轨道点 | 16s 线性旋转 | 仅 `execute` 状态 `animation-play-state: running` | 同上 |

- 页面内没有独立 `requestAnimationFrame` 循环：注视跟随走 `src/visual/motionScheduler.js`，`fps: 30`，指针离开后自动退订。
- 没有 canvas、WebGL、`backdrop-filter`、位图；最大绘制层是 SVG + CSS 渐变。
- 该路由在 `MainLayout.vue` 里隐藏了环境鲸与水母（`isCompositionPlate`），避免粒子穿过版面正文；桌宠保留，用户可自行收起。

## 7. 可访问性

- 构成谱是 `role="group"` + 原生 `<button>` + `aria-pressed`，键盘 Tab / Space / Enter 可用，焦点环 2px `--fab-gaze`。
- 舞台/图表对所有装饰层 `aria-hidden="true"`，语义由标题、字幕、参数表承担（`dl` 带 `aria-label="构成参数"`）。
- 面板标题用 `<h3>` + `aria-labelledby` 关联；运行时数值用 `b`，标签用 `span`，不使用表格冒充。
- 触控目标：构成谱 58–68px 高、按钮 36px 高、开关 30px 高（均为 44px 行高容器内）。
- 深色/浅色两套纸面色板都通过 4.5:1 正文对比度校验（验收脚本第 5 组，实测选择器：`.stage-caption h2`、`.cap-desc`、`.fable-panel-head h3`、`.weights .w-label`）。
- 浅色模式下模块**不做**白卡：面板底色 `#fbf7ee`，与全局 `.panel` 规则隔离（所有类名带 `fable-` 前缀，验收脚本断言不会变成 `rgb(255,255,255)`）。

## 8. 与设计系统的关系

- 遵守 `design-system/MASTER.md` 的「工具层」约束：半径 `--ds-radius-sm`（4px）、1px 发丝线、零玻璃、零 WebGL、状态色只用于状态。
- 例外只在**色板与图形语言**：模块内自带一套纸面/墨色/陶土色板（`--fab-*`），不影响全局 token；这是"表现型版面"在工具层内的一次受限例外，已写入 MASTER.md 的 Revision 2026-11-19 小节。
- 断点固定使用 375 / 768 / 1024 / 1440 / 1920（`src/design/breakpoints.js`），未引入新断点。

## 9. 文件与改动面

| 文件 | 改动 |
| --- | --- |
| `src/views/agent/AgentModuleView.vue` | 新增页面（版面、状态机、数据接线、演练门） |
| `src/components/agent/fable/FableComposition.vue` | 新增：方框/弧规/量规/斜规/地尺 |
| `src/components/agent/fable/FableGaze.vue` | 新增：孔径遮罩、虹膜放射纹理、瞳孔注视、复盘螺旋 |
| `src/components/agent/fable/FatBlob.vue` | 新增：定种子团块 + 体积渐变 + 呼吸 |
| `src/assets/styles/fable-agent.css` | 新增：全套 `.fable-*` 视觉层与断点 |
| `src/router/index.js` | 新增 `/agent/module` 路由（懒加载） |
| `src/navigation/personalSystemNavigation.js` | AGENT 组新增「智能体模块」 |
| `src/navigation/routeMetadata.js` | `AgentModule` → `personalGroup: agent` |
| `src/navigation/pageFlow.js` | Agent 流程追加第三站 |
| `src/layouts/MainLayout.vue` | 该路由隐藏环境鲸/水母（`isCompositionPlate`） |
| `test/agent-module.browser.mjs` | 新增浏览器验收 |

## 10. 验收

```bash
# 前置：dev server 已在 5173（脚本自行 mock 会话与接口）
cd frontend && node test/agent-module.browser.mjs
```

六组断言：

1. 五种状态可切换，`data-state` / `--aperture` / 孔径遮罩 transform / 参数表三值同步；再点当前状态回到运行时（`.seal-reset` 消失）。
2. 运行时 LIVE 标签与健康分格式；人工门演练文案；离线时三行显示 `—`、尾迹变 `SAMPLE`。
3. 375 / 768 / 1440 无横向溢出；窄屏构成谱两列。
4. 减少动效：`data-reduced="true"`、注视默认关闭、肥波不再呼吸。
5. 浅色纸面不被全局 `.panel` 染白，且四处文字对比度 ≥ 4.5。
6. 注视开关 `aria-pressed` 往返，指针悬停后瞳孔矩阵含位移。

预览图：`preview-1440.png`、`preview-768.png`、`preview-375.png`（深色）；`preview-light-1440.png`（浅色纸面）。

## 11. 已知取舍

- **构成权重是结构性的**：五条权重（指标/日志/知识/工具/审批）随状态变化，表达的是"这个状态下注意力分布长什么样"，不来自运行时采样；面板右上角标 `STRUCTURAL`，不写百分比，避免被读成监控数据。
- **孔径开合是视觉隐喻**：`APERTURE` 不是相机参数，也不代表模型温度或置信度，只是构图层面的开合；文档与标签都避免暗示。
- **复盘螺旋是唯一"非几何"的构成元素**：只在复盘态出现，用来标记"这一轮折回自身"；若后续接入真实复盘数据，应改为按复盘条目数生成环数，而不是继续静态装饰。
- **尚未接入的**：真实闭环的逐条时间线、审批流的后端写回、语音播报。当前人工门与记忆尾迹分别停在 REHEARSAL / SAMPLE 边界上，等接口就绪再升级。
