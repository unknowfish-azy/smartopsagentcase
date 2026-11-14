# 知识库 · 立体空间信息架构设计 v1

> 一句话：**把知识库从「一棵树 + 一篇文章」变成「一张能缩放的地图」——域是街区，条目是店面，连线是关系，缩放就是导航。**
> 依据：Expo Mode 的交互模型 + 本项目 737 条真实条目。技术路线不用 WebGL（见 [REVERSE.md](REVERSE.md) §5）。

| 项 | 值 |
| --- | --- |
| 落地位置 | `views/knowledge/KnowledgeView.vue` 增一个视图模式，或新增路由 `/knowledge/space` |
| 数据来源 | `views/knowledge/knowledgeCatalog.js`：`knowledgeDomains`（7 个）+ `knowledgeEntries`（**737 条**） |
| 检索能力 | 现有 `knowledgeReadApi`（`tree / node / path / search`）——**不改契约** |
| 渲染路线 | CSS 3D（`perspective` + `translate3d` + `scale`），卡片保持真实 DOM |
| 设计面 | 工具层（控制台）：零 WebGL、零 blur、半径 4-8px、1px 发丝线 |

---

## 1. 先看数据：为什么平铺列表在这里失效

实测（`node --input-type=module` 直接读 catalog）：

| 指标 | 数值 |
| --- | --- |
| 条目总数 | **737** |
| `domain` 取值 | **10 个** |
| `knowledgeDomains` 登记 | **7 个**（linux / cloud-operations / docker / mysql / nginx / ubuntu / centos） |
| 未登记的域 | `network` **195**、`web-lamp` **104**、`linux-services` **88** |
| 单域最大 | `linux` **225**（占总条目 30.5%） |
| `type` 分布 | ENGINEERING KNOWLEDGE 218 · INCIDENT 77 · WRONG_ANSWER 50 · QUESTION 49 · **undefined 31** · RUNBOOK 19 |
| `platform` 分布 | Linux 181 · Linux Web/LAMP 104 · Switching/VLAN 75 · IP Routing 75 · Cloud Native 48 |

三个结论直接决定设计：

1. **737 条不可能一次性全渲染**，必须做 LOD（分档）+ 虚拟化。
2. **`linux` 225 条独占三成**，面积必须按 `√n` 压缩，否则一个域吃掉半张地图。
3. **域清单与数据不一致**（10 vs 7），地图上会出现三块"无名区"——这是要先修数据、还是先在地图上显式标出来的选择题，见 §9 缺口 A。

---

## 2. 概念映射

| Expo Mode | 知识库 | 数据依据 |
| --- | --- | --- |
| 平台功能分区（商品/营销/履约…） | **知识域**（10 块展区） | `entry.domain` |
| 功能卡片 | **知识条目**（737 张卡） | `entry.id / title / summary` |
| 卡片内是真实界面 | 卡片内是**真实条目摘要**（可点开正文） | `title / summary / type` |
| 卡片间连线 = 功能关系 | **条目间关系**（同平台/同服务/互补类型） | `platform / service / type` |
| 俯瞰 → 钻进分区 → 读细节 | **三档相机**（全域 → 域内 → 卡片） | — |
| 缩放即导航 | 滚轮/捏合 = 相机推进，无面包屑 | — |
| 顶部检索 | 顶部检索（必需的兜底） | `knowledgeReadApi.search` |

---

## 3. 空间模型

### 3.1 三档 LOD（**必须**）

| 档 | 相机 scale | 屏幕上有什么 | DOM 挂载 |
| --- | --- | --- | --- |
| **L0 全域** | 0.20 – 0.32 | 只有 10 个域块：域标签 + 条目数 + 主要 type 分布；跨域连线 | 10 块 + 连线，**不挂卡片** |
| **L1 域内** | 0.50 – 0.85 | 当前域 + 相邻域的**摘要卡**：标题 + type chip | 只挂视口内的域（最多 3 个） |
| **L2 卡片** | 1.00 – 1.60 | 完整卡：标题 + 摘要两行 + 来源 | 只挂视口内 ± 一屏 |

**必须**：跨档切换不能让卡片"跳"——L1 的卡在 L2 展开时锚点（卡片左上角）保持不动，用 `scale` 与尺寸同步变化实现连续放大。

### 3.2 布局算法（纯函数，可单测）

```
① 面积：area(domain) = √(n) / Σ√(n)          // √ 压缩，避免 linux 独占
② 切块：squarified treemap 把世界切成 10 个矩形
③ 街道：每块内缩 14px（L0 视觉留白），块间距 18px
④ 卡位：块内按 180×120 网格排布，列数 = clamp(2, 6, round(√(n*1.6)))
⑤ 排序：域内按 type 优先级（RUNBOOK > INCIDENT > ENGINEERING > QUESTION > WRONG_ANSWER）再按标题
```

世界尺寸固定 3200×2000（16:10），与容器比例解耦：容器变化只改相机，不改布局（布局抖动会让人失去空间记忆）。

**必须**：布局结果按域缓存，同一域在会话内坐标不变；只在新数据到达时重算。

### 3.3 关系连线（**必须**标注「推断」）

条目没有显式关系字段（缺口 B），连线只能由现有字段推断，规则按优先级：

| 关系 | 判定 | 视觉 |
| --- | --- | --- |
| 同平台 | `platform` 完全相同 | 实线 1px，域内 |
| 同服务 | `service` 完全相同且同域 | 实线 1px，更淡 |
| 类型互补 | 同域内 `INCIDENT ↔ RUNBOOK` | 虚线 1px |
| 跨域同主题 | `service` 相同但跨域（如 `container` 在 docker 与 cloud-operations） | 虚线 1px，最淡，只画 L0/L1 |

**必须**：图例里写明「连线由 platform/service/type 推断，不是人工确认的关系」。
**上限**：单域连线数 > 400 时，只画同平台与互补两类，避免变成一团毛线。

---

## 4. 相机模型

### 4.1 状态与变换

```js
// 只有三个数，全部作用于 #world
const camera = { k: 0.26, tx: 0, ty: 0 }        // k = scale
world.style.transform = `translate3d(${tx}px, ${ty}px, 0) scale(${k})`
```

**锚点缩放**（鼠标位置不跑）：

```js
const k2 = clamp(k * factor, K_MIN, K_MAX)
tx = mx - (mx - tx) * (k2 / k)
ty = my - (my - ty) * (k2 / k)
```

### 4.2 保持俯视，不要斜视（**关键决策**）

| 方案 | 取舍 |
| --- | --- |
| 俯视 `rotateX(0)` | 文字永远正向、点击命中精准、`Ctrl+F` 稳定 | ✅ **默认** |
| 斜视 15–25° | 空间感更强，但文字被压扁、命中偏移、窄屏文字不可读 | ❌ 不用 |

**空间感由这三样造，不靠倾斜**：区块留白（街道）、卡片阴影分层（`--ds-shadow-1..3` 按 hover 升级）、相机推进时的缩放速度差（近处元素 scale 变化更明显）。

### 4.3 缓动与档位吸附

- 滚轮缩放：连续、无吸附（`will-change: transform` 仅动画期间）
- 域跳转 / 搜索结果定位：`420ms` `--ds-ease-out`，目标 scale 落到该域的 L1 中值
- `Esc` 逐级回退：L2 → L1（域中值）→ L0
- `prefers-reduced-motion`：无动画，直接跳变

---

## 5. 交互

| 输入 | 行为 |
| --- | --- |
| 滚轮 / 双指捏合 | 以指针为锚点缩放 |
| 拖拽空白 | 平移（松手有极小惯性，≤120ms，可关） |
| 点域块 | 相机推进到该域（L1） |
| 点卡片 | 侧栏打开条目正文（不跳页，地图保持在原位） |
| `↑↓←→` | 在卡片间按**空间邻近**移动焦点（不是 DOM 顺序） |
| `Enter` | 打开当前焦点卡片的正文 |
| `Esc` | 逐级回退相机 |
| `/` 或 `Ctrl+K` | 聚焦检索框 |
| `0` | 回到 L0 |
| `Tab` | 按域 → 卡片的读屏顺序遍历（与视觉顺序一致） |

**必须**

- **检索永远可见**，并且是权威入口：搜索结果用 `knowledgeReadApi.search` 过滤，地图上把命中的卡片点亮、其余降到 25% 不透明度（不隐藏，保留空间记忆）。
- 右下角**迷你地图**（120×80）：画 10 个域块 + 当前视口矩形，点击可直接跳。
- 视图切换三态：**空间 / 网格 / 列表**。三态共享同一份数据与同一个 `aria` 语义，切换不丢选中项。
- 卡片 hover 时高亮它的关系连线（其余降到 10%），离开恢复。

**应该**

- 顶部一行状态：`737 条 · 10 个域 · 当前：linux（225）`，让人知道自己在地图哪一层。
- 卡片右下角标 `type` chip；`undefined` 的 31 条标成 `未分类`（中性色）。

---

## 6. 渲染与性能

### 6.1 虚拟化（**必须**）

737 张卡全挂 DOM 会直接卡死。策略是**域级虚拟化 + 卡级可见性**：

| 层 | 手段 |
| --- | --- |
| 域级 | L0 时只有域块（≤10 个节点），L1/L2 只挂当前域 + 相邻域 |
| 卡级 | `IntersectionObserver`（`root` = 视口容器）决定卡片是否展开为完整内容 |
| 卸载 | 离开域 500ms 后卸载该域的卡片 DOM，保留坐标（世界记忆不丢） |

### 6.2 预算（每条都要量）

| 指标 | 预算 | 测量方式 |
| --- | --- | --- |
| L0 首屏 | ≤ 300ms 可交互 | Performance 面板，`DOMContentLoaded` → 首帧 |
| 域跳转 | ≤ 480ms 完成且不掉帧 | `performance.now()` 打点 + 帧率 |
| 稳态帧时 | ≤ 8ms（60fps 目标） | Chrome Performance，缩放动画期间采样 3s |
| 同时挂载卡片 | ≤ 120 张 | `document.querySelectorAll('.space-card').length` |
| 布局计算 | ≤ 3ms / 域 | `console.time('layout')` |
| 内存 | ≤ 120MB（737 条元数据 + 120 张卡） | DevTools Memory |
| 布局抖动 | 0（会话内域坐标恒定） | 单测断言两次 layout 结果一致 |

**必须**：动画只用 `transform` / `opacity`；`will-change` 只在动画期间挂、结束摘掉；不用 `filter: blur`。

---

## 7. 视觉与令牌

| 元素 | 令牌 | 说明 |
| --- | --- | --- |
| 画布底 | `--ds-surface-base` `#0E1116` | 地图底 |
| 街道网格 | `rgba(159,190,207,.06)` 1px | 只画域边界，不画满格网格 |
| 域块 | `--ds-surface-raised` + 1px `--ds-color-border` | 圆角 12（`--ds-radius-lg`） |
| 域标签 | `--ds-font-mono` 11px + `.12em` 字距 + 域内条目数 | 与项目 editorial label 一致 |
| 卡片 | `--ds-surface-raised`，radius 8，`--ds-shadow-1` → hover `--ds-shadow-2` | 悬浮感靠阴影，不靠模糊 |
| 卡片标题 | `--ds-type-body-size` 14px / 500 | — |
| 卡片摘要 | `--ds-type-caption-size` 12px，`--ds-color-muted` | L2 才显示 |
| 域色（辅助识别） | `--ds-chart-1..5` + `--ds-semantic-neutral` | **只用于左侧 3px 竖条与迷你地图**，不作卡片底色 |
| 连线 | 同域 `rgba(159,190,207,.18)`；跨域 `.10` 虚线 | 线宽 `1/scale` 补偿，视觉恒定 1px |
| 焦点 | `--ds-focus-ring-color` 2px + 2px offset | — |

**禁止**：给 10 个域配 10 种颜色（违反「语义色收敛」）；用域色作卡片底色（会在缩放时变成噪点）；给卡片加 `backdrop-filter`。

---

## 8. 无障碍与降级

- **三态视图保底**：任何能力缺失都退到列表视图，信息不丢。
- 读屏顺序 = `域 → 卡片`，用 `role="region"` + `aria-label="linux 域，225 条"`。
- 卡片是 `<button>`/`<a>`，`aria-expanded` 表示侧栏开合。
- 空间移动（方向键）只在键盘用户主动进入地图时启用；`Tab` 仍走线性顺序。
- `prefers-reduced-motion`：无相机动画、无惯性，`Esc`/跳转直接跳变。
- 对比度：卡片标题 4.5:1 以上；`--ds-color-muted` 在 raised 上约 4.6:1，**不再降**。
- 只读用键盘也能完成：检索 → 结果列表 → 打开正文，不强制进入空间视图。

---

## 9. 数据缺口（先决策再实现）

### 缺口 A：域清单与数据不一致（**必须先解决**）

`knowledgeDomains` 只登记 7 个域，但 `entry.domain` 有 10 个取值，多出 `network`(195)、`web-lamp`(104)、`linux-services`(88)——合起来 **387 条（52%）**。

| 方案 | 做法 | 地图上的表现 |
| --- | --- | --- |
| A1（推荐先做） | 把三个域补进 `knowledgeDomains`，给中文名与 detail | 10 块都有名字，地图完整 |
| A2 | 在 UI 里把它们并进父域（network→linux-services? 需人工确认归属） | 7 块，但会掩盖真实结构 |
| A3 | 地图上显示为「未登记域」灰色块 | 诚实但难看，只能过渡 |

### 缺口 B：没有显式关系字段

`entry` 没有 `relations[]` / `relatedIds`。连线只能推断（§3.3），**必须在图例标注「推断」**。建议后续在 catalog 里加 `related: string[]`，地图就能画真实关系。

### 缺口 C：31 条 `type` 缺失

地图与卡片都没有 type chip。建议数据层补 `type`，或统一标 `未分类`（本设计采用后者，中性色，不催）。

### 缺口 D：737 条 vs `search` 契约

`knowledgeReadApi.search` 现支持按 filters 检索，但返回值是否包含空间布局所需的 `domain/service/platform` 需确认；缺字段就先用 `knowledgeEntries` 全量本地过滤（737 条在内存里过滤 < 2ms，可接受）。

---

## 10. 组件拆分

```
views/knowledge/space/
  KnowledgeSpaceView.vue     ← 编排：数据、视图模式（空间/网格/列表）、侧栏
  useSpaceLayout.js          ← domain → 区域矩形 + 卡片坐标（纯函数，可单测）
  useSpaceCamera.js          ← k/tx/ty、锚点缩放、缓动、键盘空间导航、LOD 判定
  SpaceZone.vue              ← 域块（标签、计数、type 分布、边界）
  SpaceCard.vue              ← 卡片（三档渲染：L0 不挂 / L1 摘要 / L2 完整）
  SpaceLinks.vue             ← 关系连线（单个 SVG，线宽按 1/scale 补偿）
  SpaceMinimap.vue           ← 迷你地图 + 视口矩形
  SpaceSearchBar.vue         ← 检索 + 命中高亮（复用 knowledgeReadApi.search）
  space.css                  ← 只新增
```

**必须**：`useSpaceLayout.js` 不 import Vue、不碰 DOM，纯 `(entries, domains) → layout`，可用 Node 直接跑单测。

---

## 11. 验收清单

- [ ] 737 条数据下，L0 首屏 ≤300ms，同时挂载卡片 ≤120 张
- [ ] 缩放跨 LOD 档位时，卡片锚点不跳、文字不糊
- [ ] 域坐标在会话内恒定（两次 layout 结果一致，单测断言）
- [ ] 滚轮缩放以指针为锚点（指针下的卡片位置不动）
- [ ] `Esc` 三级回退正确；`0` 回总览；`/` 聚焦检索
- [ ] 检索命中卡片点亮、其余 25% 不透明，且不丢空间位置
- [ ] 连线图例明确写「推断关系」
- [ ] 迷你地图视口矩形与主视图同步（误差 ≤2px）
- [ ] 网格/列表视图与空间视图数据一致，切换不丢选中项
- [ ] `prefers-reduced-motion` 下无动画、无惯性
- [ ] 只用键盘能完成：检索 → 打开正文
- [ ] 代码里搜不到 `three`、`WebGL`、`backdrop-filter`、`filter: blur`
- [ ] 10 个域都有名字（缺口 A 已落地）
- [ ] 性能 6 项预算逐条给出测量值与设备基线

---

## 12. 参考素材

| 文件 | 说明 |
| --- | --- |
| [REVERSE.md](REVERSE.md) | 逆向报告：Expo Mode 的模型 + HTML-in-Canvas 真实 API 与支持现状 |
| `index.html` | 参考原型：CSS 3D 实现，10 域 + 真实条目标题，缩放/拖拽/迷你地图/列表切换/侧栏 |
| `PROMPT.md` | 交给执行模型的实现提示词 |
| `preview-1440.png` / `preview-768.png` | 两宽度实际渲染截图 |
