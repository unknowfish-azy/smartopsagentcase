# 空间知识场（Spatial Knowledge Field）设计方案 v1

日期：2026-11-14
状态：设计定稿 / 待实施（实施计划见 `.trae/documents/空间知识场-SP-01至SP-08实施计划.md`）
适用路由：`/knowledge/space`（`KnowledgeSpace`）、`/insights/*`（`NaturalLanguageInsightsView`）
约束基线：`design-system/MASTER.md`（2026-11-12 双 surface 契约 + 2026-11-19 scoped exception 先例）

---

## 0. 来源与证据（先说清楚哪些是看到的，哪些是我推的）

| 档位 | 内容 |
|---|---|
| **observed** | 小红书短链 `https://xhslink.cn/o/2DFrYt7fjNw` 可解析，302 到 `www.xiaohongshu.com/explore/6ae499880000000025013203?xsec_source=app_share`，随后被平台风控拦截：`error_code=300012`、`error_msg=IP at risk. Switch to a secure network and retry.`，最终渲染登录错误页。**原帖正文与视频均未取得。** |
| **observed** | 该错误页由 `fe-static.xhscdn.com/formula-static/fe-login` 提供，只有 APM 埋点与 `shield/webprofile` 风控请求，无正文数据接口。 |
| **derived** | 笔记 ID = `6ae499880000000025013203`；属移动端分享态，Web 端需登录且当前出口 IP 被判定为高风险，不做绕过。 |
| **inferred** | 标题后半句「把信息架构做成了立体的空间」是唯一可直接引用的设计命题。本方案据此逆向**交互原语**，不引用、不复制原帖任何具体实现、素材或文案。 |

**因此本方案的设计依据是「命题 + 交互原语」，不是「原帖像素级还原」。** 若需要像素级对齐，把原帖正文或录屏贴进会话，我按同一套观测/推断分档再做一轮 affordance 对齐，只改 §1 与 §5 的参数表，不动 §3/§4 的数据与坐标系。

---

## 1. 逆向结论：把「信息架构变成立体空间」拆成六条可实现的交互原语

一条命题能不能落地，取决于它是不是只买了「透视」。真正让空间承载信息架构的，是下面六条。缺任何一条，3D 就退化成「可缩放的一堆卡片」。

### P1 语义轴分配 — 每一根轴必须只承载一种含义
空间自由度是 3 个位置 + 3 个角度 + 缩放。轴一旦被装饰性使用（随机散布、随时间自转），用户就无法建立位置记忆，空间退化为动画。
**硬规则：三轴含义在 UI 上必须声明可见；禁止装饰性旋转与随机抖动。**

### P2 高度即抽象层级 — 竖直方向是「证据强度」梯度
同一高度上的对象才可比较。向下 = 更原始、更可核验；向上 = 更综合、更依赖推导。这条是最容易被做错的一条：大多数 3D 信息图把所有东西摊在同一水平面上，只是给了个斜视角——那不是立体，是斜着的平面。

### P3 语义缩放 — 缩放改变「对象类型」，不只是尺寸
远看是星团，中距是卡片，近看是正文。LOD 必须是**表示替换**而非**等比缩小**，否则远处永远是一片读不了的糊字。

### P4 聚焦与上下文 — 选择让对象靠近，不让世界离开
选中一个对象后，它前移、展开、详述；邻居**变暗但不消失**。任何"点进去就换页"的行为都在破坏空间的心智模型。

### P5 连线即论证链 — 每条线都是一个可追溯的主张
空间里的线不是装饰，是「我为什么这么说」的几何表达。线必须可 hover、可沿线下钻、可回答"这条结论用了哪几条知识、哪几条知识又有哪条证据"。

### P6 深度即版本/时序 — 前后方向承载时间
越靠前越新，越靠后越旧、越被取代。**知识过期不是一句灰字提示，是空间上的雾**。

### 反模式黑名单（实施时逐条自检）

| 反模式 | 后果 | 本方案的对抗手段 |
|---|---|---|
| 三轴全是装饰 | 无法形成位置记忆 | §3.1 轴语义表锁定 |
| 3D 里排文字（倾斜文本） | 不可读、不可选中、不可被读屏 | §7 文字永远在屏幕空间 |
| 无 LOD，全量绘制 | 过绘、掉帧、OOM | §6 预算表 + 视锥虚拟化 |
| 相机全 6 自由度 | 用户丢失方向感、找不回原视角 | §5 受限轨道 + 三个机位预设 + 一键复位 |
| 3D 是唯一入口 | 键盘/读屏/低配用户被排除 | §8 等价 2D 视图 + 全键盘操作 |
| 3D 替代导航 | 空间变成迷宫 | §5 空间只是"看关系"，路由仍是主结构 |

---

## 2. 落点判断：这个能力该长在项目的哪一层

现状实测（读码确认，非猜测）：

- `frontend/src/views/knowledge/space/KnowledgeSpaceView.vue`（864 行）已经是「伪 3D」：`world 3200×2000` 二维树图 + `translate3d(...) scale(k)` + `data-lod` 三级 + 迷你地图 + 键盘方向导航 + 侧栏详情 + 检索高亮。
- `useSpaceLayout.js`（148 行）是纯函数：√n 面积归一 → 递归二分切块 → 域内网格，确定性可单测。
- `useSpaceCamera.js`（98 行）只维护 `k/tx/ty` 三个数，无旋转。
- `NaturalLanguageInsightsView.vue`（314 行）的洞察对象是 `{ kind, badge, title, source, question, description, charts|items, note, updatedAt }`，四个固定 intent（alerts / servers / knowledge / health），**与知识库完全没有绑定关系**。

结论：**缺的不是"再加一个 3D 页面"，而是两件事**——
1. 把二维树图升级为真正有深度语义的三层空间（本文件 §3–§8）；
2. 把「知识条目」与「自然语言洞察」用一条垂直的、可追溯的关系绑起来（`KNOWLEDGE-INSIGHT-BINDING.md`）。

第 2 件才是这个功能真正的产品价值：**洞察不是知识的旁注，是知识的生成器。** 空间只是把这件事变得看得见。

---

## 3. 坐标系与图层（SmartOpsAgent 映射）

### 3.1 轴语义表（P1 / P2 / P6）

| 轴 | 含义 | 取值 | 为什么是它 |
|---|---|---|---|
| **X** | 领域轴 | 由 `knowledgeDomains` 顺序决定，`domainPitch = 720`，域内散布 `±260` | 项目已有 10 个域（linux / cloud-operations / docker / mysql / nginx / ubuntu / centos / network / web-lamp / linux-services），横向铺开符合现有心智，且域顺序稳定 → 位置可记忆 |
| **Y** | 抽象层级（altitude） | `0–140` 证据层；`240–420` 知识层；`520–660` 洞察层 | 这是全案的支点：**洞察在知识之上、证据在知识之下**，垂直距离 = 抽象跳跃幅度 |
| **Z** | 版本/时序轴 | `-1400 … +600`；当前 = 0，历史为负 | 项目已有 `version` / `applicableVersion` / `reviewStatus` 字段，知识过期必须在空间上有形态 |

世界单位取 px 等价（1 单位 ≈ 1 CSS px @ scale 1），世界尺度约 `7200 × 660 × 2000`。视口用真的透视投影（`perspective`），不做伪等距。

### 3.2 三层结构

```
        y=660 ┌──────────────────────────────────────────────┐
              │  L2  INSIGHT CANOPY  洞察层                   │
              │  悬浮字幕：自然语言结论 / 图表缩略 / 口径声明   │  ← 无实底，只有顶边 1px 规则线
              │        │            │            │            │
   y=420 ─────┼────────┼────────────┼────────────┼────────────┤
              │  L1  KNOWLEDGE SHELF  知识层                  │
              │  domain 分簇 · 知识原子平面（现有 10 域）       │  ← 1px 规则边框 + accent 顶边 2px
              │        │            │            │            │
   y=140 ─────┼────────┼────────────┼────────────┼────────────┤
              │  L0  EVIDENCE BED  证据层                     │
              │  日志/指标/巡检事件/告警 → 条带 + 点阵          │  ← Canvas2D 单例，opacity 0.10–0.22
        y=0   └──────────────────────────────────────────────┘
                    x: linux … linux-services      z: 历史 ← 0 → 未来
```

**垂直线程（thread）= 论证链**：每条洞察向下连到它引用的知识原子（可多条），每个知识原子再向下连到它的证据锚点。
- 颜色：`insight canopy(--ds-accent-soft)` → `knowledge(--ds-accent)` → `evidence(--ds-text-secondary)`，纵向线性渐变，统一 1px。
- hover：该线程升到 2px 并浮出 relation 标签（`derived` / `corroborates` / `contradicts` / `operational`）。
- 孤立的洞察（`operational`，纯数据洞察，如"活跃告警分布"）不画向下线程，改画一条**短横线 + 空心端点**，明确表示"无知识依赖"。**不允许为了画面好看补一条假线。**

### 3.3 图层视觉配方（遵守 tool surface：无 backdrop-filter、无粒子装饰）

| 层 | 底 | 边 | 文本 | 动效 |
|---|---|---|---|---|
| L2 洞察 | 透明 | 顶边 1px `rgba(159,190,207,.18)` | 标题 `--ds-font-cn` 400 / 元信息 mono | 无永续动画；仅在数据真实刷新时 200ms 抬升 |
| L1 知识 | `--ds-surface #071018` | 1px 规则 + 顶 2px `--ds-accent` | 标题 + type chip | 仅在 hover/focus 时 160ms 边框提亮 |
| L0 证据 | 无 | 无 | 无 | 无。**证据层永远静止**，唯一例外是真实新事件到达时的 400ms 局部脉冲（一次性，不循环） |

层级区分靠**透明度与规则线**，不引入新色板（`design-system/MASTER.md` 明确 status/celebration 色不得挪用）。

---

## 4. 知识 ↔ 洞察绑定（摘要）

完整契约见 [`KNOWLEDGE-INSIGHT-BINDING.md`](./KNOWLEDGE-INSIGHT-BINDING.md)。这里只放结论。

1. **绑定是双向的**：`KnowledgeAtom.insightRefs` ↔ `Insight.binding.atoms`，两侧都可由 `bindingIndex.js` 纯函数重建，不落新服务。
2. **绑定必须带锚点**：`{ atomId, anchor: { chunkId?, span?: [start,end], field?: 'summary'|'content' }, weight }`，`anchor` 复用 `knowledge/evidence/models.py::Evidence` 的语义（`chunk_id / source / content / score / version`）。
3. **绑定必须带可信档位**：每条洞察标 `confidence: observed | derived | inferred`，与项目证据纪律一致。缺少锚点的洞察渲染为「**未绑定**」而不是「已关联」。
4. **绑定的闭环**：洞察 → 证据下钻 → 矛盾时进入现有 `KnowledgeCandidateReviewView` → 人工确认 → 知识版本 +1（旧版本沿 −Z 后退）或洞察固化为新知识（从 L2 下沉到 L1，线程由虚变实）。**不新建审批流。**

---

## 5. 相机与导航规范（P4）

### 5.1 受限轨道（禁止全 6 自由度）

| 参数 | 范围 | 理由 |
|---|---|---|
| yaw | `-35° … +35°` | 超过 35° 时带文字的平面开始不可读 |
| pitch | `8° … 52°` | 低于 8° 三层重叠成一坨；高于 52° 退化成正俯视 |
| distance | `520 … 2600` | 与 §6 LOD 阈值对齐 |

**焦点billboard规则**：进入 `focus` LOD 的平面，yaw 在 240ms 内缓动到 0（正面朝向相机），其他平面保持原角度。这是"3D 保结构、2D 保可读"的关键手法。

### 5.2 三个机位预设（给方向感兜底）

| 机位 | 相机 | 目标点 | 用途 | 快捷键 |
|---|---|---|---|---|
| `Overlook` | `(cx, 980, 1500)` | `(cx, 300, 0)` | 总览：看清域分布与三层厚度 | `1` |
| `Shelf` | `(cx, 330, 760)` | `(cx, 330, 0)` | 知识层平视：正常阅读卡片 | `2` |
| `Trace` | 选中洞察与其原子的中点上方 `+320`，`yaw=0` | 链条中点 | 沿一条论证链运镜 | `3` |

- `Esc` 三级回退：`focus 平面 → 所在域 → Overlook`（延续现有 `useSpaceCamera` 的回退语义）。
- 任何机位切换都是**补间**（`cubic-bezier(.22,.61,.36,1)`，480ms）；`prefers-reduced-motion` 下直接跳变、无补间。

### 5.3 键盘与指针分工

| 操作 | 指针 | 键盘 |
|---|---|---|
| 层内移动焦点 | 拖拽平移 / 点击 | `←↑→↓`（沿用现有 `findNeighborInZone` 的近邻算法，扩展一维：`↑↓` 同时可跨层） |
| 下钻一层 | 单击平面 | `Enter` |
| 上浮一层 | — | `Esc` |
| 切机位 | HUD 按钮 | `1 / 2 / 3` |
| 沿线程走 | hover 线程 | `Ctrl+↑ / Ctrl+↓`（洞察 ↔ 知识靠线程移动） |
| 检索 | 输入框 | `Ctrl+K` |

**空间不接管路由**：`/knowledge/space` 只是"看关系"的视图，条目详情仍走侧栏与既有路由；空间里的一切位置都能用 breadcrumb 复述（"知识层 · nginx · 502 诊断 Runbook"），保证可被读屏朗读、可被复制、可被链接。

---

## 6. LOD 与性能预算（P3 + 硬约束）

### 6.1 LOD 表（按相机到平面距离 `d`）

| LOD | 距离 | 可见对象 | 文本内容 | 平面 DOM |
|---|---|---|---|---|
| `far` | `d > 1200` | 域簇外框 + 洞察标题带 | 域 label、洞察标题（≤ 24 字截断） | 域框 1 个/域，洞察带 1 个/洞察 |
| `mid` | `620 < d ≤ 1200` | 知识平面（精简） | 标题 + type chip | ≤ 3 元素 |
| `near` | `240 < d ≤ 620` | 知识平面（完整） | 标题 + 摘要 + tags | ≤ 6 元素 |
| `focus` | `d ≤ 240` 或选中 | 完整平面 + 详情面板（DOM 屏幕空间） | 全正文（`knowledgeReadApi.node`） | 侧栏，2D |

### 6.2 预算（写进验收，不达标即视为未完成）

- 同帧挂载的世界平面 ≤ **480**；同帧可见 ≤ **180**；越界即触发视锥 + 距离裁剪。
- 世界平面用 `transform: translate3d(...) ` + `opacity`，**不写 `left/top/width`**；单次相机变更批量写一次，禁止在 rAF 里逐元素 `setState`。
- 渲染循环统一走 `frontend/src/visual/motionScheduler.js`（30fps 默认、慢帧自动降 15fps、离屏暂停、`prefers-reduced-motion` 单帧静态）。**禁止新开第二个 `requestAnimationFrame`。**
- `will-change: transform` 同时生效元素 ≤ 40，其余靠合成层提升。
- 首屏（`Overlook`）到可交互 ≤ 1.2s（本地基线，须在 `npm run perf:baseline` 里留 before/after 数字）。
- 内存：世界平面数据结构 ≤ 2 MB（纯 JS 对象，不含 DOM）。

### 6.3 与其他视图的关系

`space / grid / list` 三视图继续并存（P4 + §8 降级要求）。改造只动 `space`，`grid`/`list` 必须继续可用且**无需任何 3D 代码参与**——这是可访问性与低配设备的唯一保证。

---

## 7. 渲染技术决策：CSS 3D 为主，零 WebGL

这是本方案最重要的一条工程判断，先说结论再说理由。

### 结论
**Phase A 用 CSS 3D（`perspective` + `transform-style: preserve-3d` + DOM 平面）实现空间场；证据层用单个 Canvas2D 实例画点阵条带；不引入 WebGL。** WebGL / three.js 版本列为 Phase C，需要先改 `design-system/MASTER.md` 并给出可测量的收益证明。

### 对比

| 维度 | CSS 3D + DOM（选定） | WebGL / three.js（暂缓） |
|---|---|---|
| 文字可读性 | 原生 DOM 文本，屏幕空间清晰、可选中、可搜索 | 需 SDF/纹理，模糊或不可选 |
| 可访问性 | 语义化 DOM，读屏/焦点/Tab 顺序天然可用 | 需另建 a11y 影子层，工作量翻倍 |
| 与现有 864 行视图复用 | 直接复用 `mountedCards` / `hitIds` / 侧栏 / 键盘导航 | 几乎重写 |
| 设计系统合规 | 合规（无 WebGL、无粒子、无 `backdrop-filter`） | **违反 tool surface 的 "no WebGL"**，需先修 MASTER 并立 scoped exception |
| 480 平面规模 | 合成层可承（实测门槛在 ~600） | 轻松，但收益要到 2000+ 才显现 |
| 打包体积 | 0 新增依赖（`three` 已在依赖里但本方案不引入路径） | 引入 `three` 运行时路径与 shader 维护成本 |
| 证据层点阵密度 | Canvas2D 够用（L0 是背景信息，不是主角） | 过剩 |

`three@0.186.0` 确实已在 `frontend/package.json` 中，但**"依赖存在"不是"应该使用"的理由**。本项目是证据优先的运维控制台，文字可读性与 a11y 的权重高于渲染上限；480 个平面的规模远未到需要 GPU 管线的地步。

### 若未来要开 WebGL 的准入条件（写死，避免临时起意）
1. `motionScheduler` 基线显示 CSS 方案在目标机型上稳定低于 24fps；
2. 世界平面规模 ≥ 1500（即知识条目数翻三倍）；
3. 在 `design-system/MASTER.md` 新增一节 `Revision — Spatial Field plate (scoped exception)`，明确：只在该路由、单 canvas、无粒子、无 `backdrop-filter`、reduced motion 静态帧；
4. 有 before/after 帧时间与内存实测。

---

## 8. 可访问性与降级（P4 的底线）

- **等价 2D**：`grid` 与 `list` 视图是空间的等价表达，任何信息在 2D 中都可达。空间独有的只有"关系看得见"，不承载独占信息。
- **焦点管理**：`focus` 平面才可 Tab 聚焦；`far`/`mid` 平面 `aria-hidden="true"`、不参与 Tab 序（覆盖现有的 `ks-card--offscreen` 语义）。
- **朗读**：每个平面 `aria-label` 复述位置与身份，例如 `知识层 · nginx · 502 Bad Gateway Diagnosis Runbook，DIAGNOSIS RUNBOOK`；洞察朗读包含 `confidence` 与绑定条数（"引用 2 条知识，其中 1 条已过期"）。
- **对比度**：所有文本 ≥ 4.5:1；层级差异靠规则线与透明度，不靠低对比文字。
- **命中区**：触控布局平面命中区 ≥ 44px。
- **断点**：严格 375 / 768 / 1024 / 1440 / 1920（`frontend/src/design/breakpoints.js`），不新增临时断点。375 宽度下默认落 `Space` 的 `Overlook` 且禁用自由轨道，只保留机位切换。

---

## 9. 与现有代码的落位（文件级）

```
frontend/src/views/knowledge/space/
  KnowledgeSpaceView.vue      # 改造：world 从 2D 树图 → 三层空间场；保留 grid/list/侧栏/检索
  useSpaceLayout.js           # 保留（2D 树图算法仍被 grid/list 使用）
  useSpaceCamera.js           # 保留（k/tx/ty 继续服务 2D 画面）
  useFieldLayout.js           # 新增：纯函数，entries + domains + insights → 三层世界坐标（确定性、可单测）
  useFieldCamera.js           # 新增：受限轨道 + 三机位 + focus billboard + reduced motion
  FieldStage.vue              # 新增：stage / world / perspective 容器 + LOD 分发
  FieldPlane.vue              # 新增：单个世界平面（DOM），按 LOD 切换内部结构
  InsightCanopy.vue           # 新增：L2 洞察带 + confidence 标记 + 未绑定态
  ThreadLayer.vue             # 新增：P5 论证链（SVG，屏幕空间叠加，与世界坐标同步）
  EvidenceBed.vue             # 新增：L0 证据层（Canvas2D 单例，motionScheduler 驱动）
  bindingIndex.js             # 新增：知识 ↔ 洞察双向索引 + 可解释匹配（纯函数）

frontend/src/views/knowledge/
  knowledgeCatalog.js         # 扩展：knowledgeEntries 允许可空 evidenceRefs / insightRefs
  knowledgeModel.js           # 复用：rankKnowledgeEntries 的 matchReason 风格用于绑定解释

frontend/src/views/insights/
  NaturalLanguageInsightsView.vue   # 扩展：洞察对象增加 id / binding / confidence；保持 4 个 intent 可解释规则
  insightBinding.js                 # 新增：intent 结果 → binding 的映射（规则化，不猜）

design-system/MASTER.md       # 新增 Revision 节：Spatial Field plate（明确 CSS 3D 允许、WebGL 仍禁止）
```

**新增文件 9 个，改造文件 4 个，新增依赖 0 个。** 无后端改动（Phase A）；Phase B 才动 `knowledge/evidence/`（见绑定文档 §7）。

---

## 10. 验收标准

| 编号 | 判据 | 验证方式 |
|---|---|---|
| A1 | `useFieldLayout` 同输入同输出（逐字段 deepEqual） | `cd frontend; node --test test/field-layout.test.mjs` |
| A2 | 三轴语义在 UI 可见（轴标/图例），无装饰性旋转 | 目视 + `test/spatial-field.browser.mjs` 断言轴标存在 |
| A3 | 三层（L0/L1/L2）在同一机位下同时可见且互不遮挡主体 | 三个机位各截一图存档 |
| A4 | LOD 四档在跨越阈值时发生**表示替换**（元素数变化），非等比缩放 | browser test 断言 `data-lod` 切换后子元素数不同 |
| A5 | 绑定：每条洞察要么有 ≥1 条锚点，要么显式渲染「未绑定」 | `test/binding-index.test.mjs` + 目视 |
| A6 | 线程 hover 可读出 relation 与两端身份 | browser test |
| A7 | 键盘可完成：机位切换 / 层内移动 / 下钻 / 上浮 / 线程移动 | `npm run test:a11y` + 手工脚本 |
| A8 | `prefers-reduced-motion` 下无补间、无循环动画、单帧静态 | `test:a11y` |
| A9 | 平面挂载 ≤ 480、可见 ≤ 180、帧率 30fps、无新增 rAF | `npm run perf:baseline` before/after 记录 |
| A10 | `grid` / `list` 视图功能与改造前等价 | 现有用例全绿 |
| A11 | 断点 375/768/1024/1440/1920 无横向滚动、无遮挡 | `npm run test:visual` |
| A12 | 文字全部为屏幕空间 DOM，可选中、可被读屏、可搜索 | 手工：选中一段洞察正文并复制 |

---

## 11. 未决问题（明确标注，不假装解决）

1. **原帖具体实现未知**：本方案基于命题与交互原语，`§1` 的原语清单是推断而非原帖还原。拿到正文/录屏后可做 affordance 对齐，仅调 `§3.1` 与 `§5` 参数。
2. **证据层数据源**：Phase A 的 L0 用现有 `/api/inspector/events`、`/api/sentinel/alerts`、`/api/servers` 的已授权字段；指标时序密度（真正的"点阵"）需要后端提供聚合接口，Phase B 再议。
3. **知识条目的证据锚点缺失**：当前 `knowledgeEntries` 没有 `evidenceRefs`，Phase A 大量条目会渲染为「未绑定 / 无证据锚点」。**这是真实状态，不允许补占位数据冒充有证据。**
4. **`contradicts` 的判定**：Phase A 只做**结构判定**（同一 `service`+`version` 下洞察与知识结论词项互斥），不做语义推理；语义判定列为 Phase C。
5. **性能数字**：A9 的 1.2s 首屏是假设目标，须以 `npm run perf:baseline` 实测后回填，不回填视为未验收。

---

## 12. 为什么这个设计值得做

原来的 `KnowledgeSpaceView` 解决了「10 个域、几百条知识怎么一屏看全」——它是**检索的放大器**。
本方案要解决的是下一层问题：**我怎么知道一条结论凭什么成立，以及它什么时候会失效**。

而这件事只有在空间里才成立：因为「凭什么成立」是一个**纵向的、多跳的、带方向的关系**，列表能表达层级、图能表达邻接，只有空间能同时表达**层级 + 邻接 + 时效**。

一句话概括这套设计：
> **证据沉在下面，知识摆在中间，洞察飘在上面；每条洞察都有一根线垂到自己凭的那几条知识上——线断了，就说明这条结论没人背书。**

这就是把「可信」做成看得见的东西。也是这个项目相对普通运维面板唯一不可替代的地方。
