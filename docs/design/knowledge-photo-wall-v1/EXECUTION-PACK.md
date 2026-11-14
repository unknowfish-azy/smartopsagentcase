# 知识库照片墙 · T23–T27 执行包（交实现模型）

日期：2026-11-14 22:00
状态：**方案已定稿，本文件为唯一执行指令；§10 交接提示词已就绪，当前可直接派发第 1 轮（T23+T24）**
依据：`docs/design/knowledge-photo-wall-v1/DESIGN.md` **v1.1**（唯一口径，先读它）
适用路由：`/knowledge/space`；目标：新增第 5 视图 `mosaic` 并设为默认
分工提醒：本执行包由「只出方案」的智能体编写，**未改任何代码、未跑构建/测试**；编码、构建、验证由实现模型完成

---

## 0. 裁决结论（用户 2026-11-14 已确认，不再讨论）

| 编号 | 议题 | **结论（执行时按此）** |
|---|---|---|
| D5 | 默认视图 | **是**，`viewMode` 默认 `'mosaic'`，场域保留为 pill |
| D6 | 悬浮窗可拖 / 多开 | **否**，单实例、不可拖、锚定格子 |
| D7 | 首页 Bento 同步换 | **否**，保持 D1 裁决，首页零改动 |
| D8 | 筛选紧凑重排开关 | **P1 才做**；P0 只做「降饱和 + 保留原位」 |
| D9 | 域排序 | **`knowledgeDomains` 登记顺序**（与 `knowledgeTree` 一致、测试写死），不做条数降序 |

---

## 1. 全局纪律（每包开工前复读）

**必须**
- 唯一取数入口：`import { searchKnowledgeEntries, knowledgeDomains } from '../../knowledgeCatalog.js'` → `searchKnowledgeEntries({})`（737 条、含 `directory`）。
- 所有颜色/字号/圆角/动效只用 `var(--ds-*)` 令牌（`variables.css` 深色 `:root` + 浅色 `[data-theme='light']` 双主题）。
- 所有新增选择器前缀 `.mw-*`，所有新增文件只在 `frontend/src/views/knowledge/space/mosaic/` 下。
- 文本全部屏幕空间 DOM；`data-size` 控制 4 档显隐；缩放只写单容器 transform。
- 字段缺失如实降级（`—` 或项目现有文案），**不造字段、不拿 `content` 冒充 `summary`、不把占位符当真实版本**。

**禁止（出现即打回）**
- 改 `knowledgeCatalog.js` / `catalogProjection` 白名单 / `useSpaceCamera.js` / 现有 4 个视图逻辑。
- 新增路由、后端接口、npm 依赖、位图素材、WebGL、Canvas、粒子、`backdrop-filter`、3D 变换（`perspective` / `rotate*` / `translateZ` / yaw / pitch）。
- 写死 hex 颜色、硬编码 `737` / `10` / `7`、硬编码域清单。
- 沿用场域的 480/180 预算截断（照片墙必须**全量 737 格同屏**）。
- 用 8 色 `TYPE_COLORS` 直接给 57 种 type 上色。
- 显示 `evidenceRefs`（全库不存在）、把 `reviewStatus: UNVERIFIED` 画成"已验证"、写「准确率 9X%」「AI 识别指令风险」。

**工作区状态**：当前约 16 个未提交文件（知识空间大改 + 侧栏半成品迁移）。**只新增 `mosaic/` 目录与下表的 8 处改动，不要覆盖他人改动、不要顺手格式化整份文件、不要提交不属于本任务的改动。**

**依赖顺序**：`T23 → T24 → (T25 ∥ T26) → T27`。T25/T26 可并行，但都依赖 T24 的 props 契约。

---

## 2. T23 · 数据与归一化纯函数

### 2.1 新建文件

| 文件 | 内容 |
|---|---|
| `frontend/src/views/knowledge/space/mosaic/mosaicType.js` | type 57→7 类、risk→6 档、占位符识别，纯函数 |
| `frontend/src/views/knowledge/space/mosaic/mosaicLayout.js` | 稳定排序、三级分段、网格坐标、`k→size`，纯函数 |
| `frontend/test/mosaic-type.test.mjs` | 归一化单测 |
| `frontend/test/mosaic-layout.test.mjs` | 布局单测 |

### 2.2 `mosaicType.js` 接口（可直接粘贴）

```js
export const TYPE_CLASSES = ['RUNBOOK', 'INCIDENT', 'ENGINEERING', 'QUESTION', 'WRONG_ANSWER', 'RULE', 'REFERENCE']

const TYPE_RULES = [
  ['RUNBOOK',      ['RUNBOOK', 'STANDARD'], 'RB'],
  ['INCIDENT',     ['INCIDENT', 'PRODUCTION DIAGNOSIS'], 'INC'],
  ['ENGINEERING',  ['KNOWLEDGE', 'ENGINEERING', 'OPERATIONS', 'MODULE', 'AUTOMATION', 'SPECIFICATION', 'GUIDE', 'PATH', '工程知识卡'], 'ENG'],
  ['QUESTION',     ['QUESTION', 'BANK'], 'Q'],
  ['WRONG_ANSWER', ['WRONG_ANSWER', 'WRONG', 'ANTI-PATTERN'], 'WA'],
  ['RULE',         ['RULE', 'DECISION', 'POLICY', 'SAFETY'], 'RULE'],
]

export function normalizeKnowledgeType (raw) {
  const original = raw == null ? '' : String(raw)
  const upper = original.trim().toUpperCase()
  if (!upper) return { cls: 'REFERENCE', short: 'REF', original }
  for (const [cls, keys, short] of TYPE_RULES) {
    if (keys.some(key => upper.includes(key))) return { cls, short, original }
  }
  return { cls: 'REFERENCE', short: 'REF', original }
}

export function normalizeRisk (raw) {
  const r = String(raw ?? '').trim().toUpperCase()
  if (r === 'READ_ONLY')         return { key: 'READ_ONLY',         label: '只读',   short: 'RO' }
  if (r === 'REFERENCE')         return { key: 'REFERENCE',         label: '参考',   short: 'RF' }
  if (r === 'APPROVAL_REQUIRED') return { key: 'APPROVAL_REQUIRED', label: '需审批', short: 'AP' }
  if (r === 'HIGH')              return { key: 'HIGH',              label: '高风险', short: 'HI' }
  if (r === 'MEDIUM')            return { key: 'MEDIUM',            label: '中风险', short: 'MD' }
  return { key: 'OTHER', label: '其他', short: '—' }   // 29 条中文长句一律收这里，不显示长文
}

export function isPlaceholderVersion (v) {
  return !v || String(v).trim() === '未注明适用组件版本'
}
```

> `WRONG_ANSWER` 要在 `QUESTION` 之后但注意 `Wrong Answer Bank` 同时含 `BANK` → 会被 `QUESTION` 先命中。若实测出现误分类，把 `WRONG_ANSWER` 规则提到 `QUESTION` 之前并在单测里加一条断言；**规则顺序以单测为准，不要凭感觉改**。

### 2.3 `mosaicLayout.js` 接口（可直接粘贴骨架）

```js
export const BASE_TILE = 108
export const TILE_GAP = 1
export const SIZE_STEPS = [
  { id: 's0', k: 0.26, px: 28 },
  { id: 's1', k: 0.52, px: 56 },
  { id: 's2', k: 1.00, px: 108 },
  { id: 's3', k: 1.85, px: 200 },
]

export function sizeForK (k) {
  if (k < 0.39) return SIZE_STEPS[0]
  if (k < 0.76) return SIZE_STEPS[1]
  if (k < 1.42) return SIZE_STEPS[2]
  return SIZE_STEPS[3]
}

export function buildMosaic (entries, domains, stageWidth) {
  const order = new Map(domains.map((d, i) => [d.id, i]))
  const sorted = [...entries].sort((a, b) =>
    (order.get(a.directory.domainId) ?? 99) - (order.get(b.directory.domainId) ?? 99) ||
    String(a.directory.serviceId).localeCompare(String(b.directory.serviceId)) ||
    String(a.directory.sectionId).localeCompare(String(b.directory.sectionId)) ||
    String(a.id).localeCompare(String(b.id)))

  const cols = Math.max(1, Math.floor((stageWidth + TILE_GAP) / (BASE_TILE + TILE_GAP)))
  const rows = Math.ceil(sorted.length / cols)
  const tiles = sorted.map((entry, i) => {
    const col = i % cols, row = Math.floor(i / cols)
    return {
      id: String(entry.id), entry,
      col, row,
      x: col * (BASE_TILE + TILE_GAP),
      y: row * (BASE_TILE + TILE_GAP),
      cls: normalizeKnowledgeType(entry.type).cls,
      short: normalizeKnowledgeType(entry.type).short,
      risk: normalizeRisk(entry.risk),
      domainTag: null, serviceTag: null,   // 由分段逻辑回填
    }
  })
  // TODO(实现)：按 domain 连续段回填 domainTag；n<=2 的相邻段合并为「其他域 · n 条」标签，
  //             但 tiles 不合并、各自域色保留；同 serviceId 连续段 >=4 格才回填 serviceTag。
  return {
    tiles, cols, rows,
    worldW: cols * (BASE_TILE + TILE_GAP),
    worldH: rows * (BASE_TILE + TILE_GAP),
    segments: [], tags: [],
    total: tiles.length,
  }
}
```

### 2.4 单测断言清单

**`mosaic-type.test.mjs`**
1. 从 `searchKnowledgeEntries({})` 取全量，**57 种 `type` 全部有归类**，无抛错、无 `undefined`。
2. `normalizeKnowledgeType('DIAGNOSIS RUNBOOK')` → `RUNBOOK`，且 `original === 'DIAGNOSIS RUNBOOK'`（原始值不丢）。
3. `normalizeKnowledgeType('')` / `null` / `undefined` → `REFERENCE` / `REF`。
4. `normalizeKnowledgeType('工程知识卡')` → `ENGINEERING`。
5. `normalizeRisk` 对 `READ_ONLY / REFERENCE / APPROVAL_REQUIRED / HIGH / MEDIUM` 分别命中；中文长句 → `OTHER` 且 `short === '—'`。
6. `isPlaceholderVersion('未注明适用组件版本') === true`；`isPlaceholderVersion('1.0') === false`。

**`mosaic-layout.test.mjs`**
7. `buildMosaic(...).tiles.length === searchKnowledgeEntries({}).length`（运行时取，不写 737）。
8. `new Set(tiles.map(t => t.id)).size === tiles.length`（无重复）。
9. 排序稳定：同一输入连调两次坐标逐项相等；`domain` 顺序与 `knowledgeDomains` 一致。
10. `cols = floor((stageWidth + 1) / 109)`，1440 输入下 S0 档 `rows * 29 <= 900`（一屏放得下）。
11. `worldW/worldH` 与 `cols/rows` 自洽；`x,y` 全为非负、无重叠。
12. 小域折叠：`docker/ubuntu/centos` 合并为 1 枚标签，但 4 个 tile 仍在、`cls` 与域色各自独立。
13. **布局与 `k` 无关**：`sizeForK` 只返回档位，`buildMosaic` 结果不随缩放变化。

**完成判据**：两组单测全绿；`git diff` 中无 catalog / 现有视图文件。
**交接给 T24**：`buildMosaic()` 返回的 `tiles` 结构与 `SIZE_STEPS`。

---

## 3. T24 · 密铺骨架

### 3.1 新建文件与契约

| 文件 | props / 职责 |
|---|---|
| `MosaicWallView.vue` | 容器：`stageRef / worldRef`、HUD、事件；持有 `field = buildMosaic(...)`、`cam = useSpaceCamera(...)`、选中态 |
| `MosaicTile.vue` | `props: { entry: Object, tile: Object, size: String, hit: Boolean, selected: Boolean }`；`emits: ['open']`；**无内部响应式状态** |
| `MosaicDomainTag.vue` | `props: { label, count, kind }`；`emits: ['jump']`；屏幕空间，不随 `scale` 缩小 |
| `mosaic.css` | 全部 `.mw-*` 前缀 |

### 3.2 单格四层（真实字段，照此渲染）

```
.mw-tile  (width/height: var(--mw-tile) = 108px; contain: layout paint style size; content-visibility: auto)
├─ 域色底      background: color-mix(in srgb, var(--ds-chart-N) 30%, var(--ds-surface-base))
├─ 顶色条 3px  background: var(--ds-chart-N)  ← tile.cls (7 类映射 chart-1..5 + neutral)
├─ [s1+] 短码  tile.short   (--ds-font-mono, 11px)
├─ [s2+] 标题  entry.title  (2 行截断；完整值进 title 属性与 aria-label)
├─ [s2+] 标签  entry.tags[0]
├─ [s3+] 摘要  entry.summary || '当前资料暂未记录摘要。'   ← 188 条走后者
├─ [s3+] 原始 type chip：entry.type（不是归一化短码）
└─ 右下 risk 角标 tile.risk.short
```

- 档位显隐**只由 `#mw-world[data-size="s0|s1|s2|s3"]` 的 CSS 后代选择器控制**，不给每格加 `v-if`（737 个响应式判断会掉帧）。
- 间隙：`gap: 1px`（≤2px）；域间仅 1 条 `var(--ds-hairline)` 竖线；**不插空行**。
- `aria-label = \`${域} · ${tile.cls} · ${entry.title} · ${tile.risk.label}\``；`s0` 档 tile `aria-hidden="true"` + `tabindex="-1"`。
- Hover：`150ms` 边框提亮（`--ds-duration-micro` / `--ds-ease-out`），**不 scale、不发光、不 translateZ**。
- 域胶囊：`position: absolute` 在独立 overlay 层（**不是 world 子元素**，否则会跟着缩小）；`docker/ubuntu/centos` 合并一枚「其他域 · 4 条」。

### 3.3 完成判据

1. 1440 视口 S0 首屏可见 ≥400 格、间隙 ≤2px、域内无整格留白；放大到 S3 标题/摘要/原始 type 正确。
2. 深浅两套主题（` :root ` 与 `[data-theme='light']`）都过文字对比度 ≥4.5:1。
3. 浏览器检查：无 `perspective` / `rotate` / `translateZ` / `backdrop-filter` / 图片请求；控制台零报错。
4. 全量 737 格挂载，无"预算超限"warn。

---

## 4. T25 · 缩放与平移

### 4.1 复用而非新建（关键）

`useSpaceCamera.js` 已提供 `zoomAt(mx,my,factor,worldEl)` / `centerOn` / `fitOverview(worldEl,stageEl,{w,h})` / `apply`（`K_MIN=0.16`、`K_MAX=2.2`）。**直接 import，禁止新建 `useMosaicZoom.js`、禁止改该文件**。它的 `worldRect/stageRect` 两个参数当前实现未使用，传 `null, null` 或 computed 均可。

```js
import { useSpaceCamera } from '../useSpaceCamera.js'
import { sizeForK, buildMosaic } from './mosaicLayout.js'

const cam = useSpaceCamera(null, null)

function onWheel (e) {
  e.preventDefault()
  const st = stageRef.value.getBoundingClientRect()
  cam.zoomAt(e.clientX - st.left, e.clientY - st.top, Math.exp(-e.deltaY * 0.0015), worldRef.value)
  worldRef.value.dataset.size = sizeForK(cam.k.value).id
}
function resetOverview () {
  cam.fitOverview(worldRef.value, stageRef.value, { w: field.value.worldW, h: field.value.worldH })
  worldRef.value.dataset.size = sizeForK(cam.k.value).id
}
```

⚠️ `useSpaceCamera.apply()` 会顺带写 `dataset.lod`（3 档 L0/L1/L2）。**CSS 只认 `[data-size]`（4 档）**，两套属性并存即可；不要在 CSS 里用 `[data-lod]`，也不要覆盖 `lod`。

### 4.2 交互清单

- 滚轮：沿用项目灵敏度 `Math.exp(-deltaY * 0.0015)`（100px ≈ 16%）；以指针为锚点。
- 缩放条 `− 滑块 +`：直接 `cam.zoomAt(stageW/2, stageH/2, factor, worldRef.value)` 或按档位 `cam.apply(worldRef.value, { k: SIZE_STEPS[i].k })`。
- 「总览」：`fitOverview` 传**自定义** `{ w: worldW, h: worldH }`，不要用它默认的 3200×2000。
- 拖拽平移：空白区 pointerdown/move/up 只改 `tx/ty`（`cam.apply`），**禁旋转**。
- 375：双指捏合；默认 `k = 1.00`（S2，108px ≥44px 命中）；S0 档 tile 不可点，点击自动 `cam.apply(..., {k:1})`。
- `prefers-reduced-motion`：不做补间，档位切换直接生效。
- 缩放/筛选/开详情**都不重算 `buildMosaic`**（坐标缓存），只有 `entries` 变化才重算。

**完成判据**：鼠标锚点下的 tile id 缩放前后一致；4 档切换同一 tile 逻辑坐标误差 ≤1px；`resetOverview` 后回到 S0 且平移归零；慢帧下无逐帧 Vue 状态写入（Performance 面板核对）。

---

## 5. T26 · 悬浮详情窗

### 5.1 契约

```js
// MosaicDetailPopover.vue
defineProps({ entry: Object, tile: Object, anchor: Object })   // anchor = {x,y} 屏幕坐标
defineEmits(['close', 'navigate'])                            // navigate(id) 复用 FieldPlaneDrawer 语义
```

### 5.2 字段渲染（按真实字段，缺则如实降级）

| 区块 | 字段 | 降级 |
|---|---|---|
| 域 banner | `entry.directory.domainId` → `knowledgeDomains.label` | 中性色 + `id` |
| 标题 | `entry.title` | 必有 |
| 类型 chip | **原始 `entry.type`** | 空 → `—` |
| 平台 / 标签 | `entry.platform` / `entry.tags[]` | 必有 |
| 目录面包屑 | `entry.directory.pathKey` | 必有 |
| 来源 / 版本 | `entry.source` / `entry.version` | 必有 |
| 适用版本 | `isPlaceholderVersion(entry.applicableVersion)` | `true` → `—`（737 条全是占位符） |
| 摘要 | `entry.summary` | 缺 188 条 → `'当前资料暂未记录摘要。'` |
| 风险 | `normalizeRisk(entry.risk).label` + 原始 risk 文本 | 必有 |
| 核验状态 | 固定一行「未核验 · UNVERIFIED」 | **不做绿色已验证态** |
| 正文 | `entry.content` 按 `\n\n` 分段 | 必有 |
| 关联知识 | 仅当 `entry.relatedIds?.length` 时渲染（465 条有） | 其余不渲染该区块 |
| 证据数 | **不渲染**（`evidenceRefs` 全库不存在） | — |
| `level` / `verification` / `category` | **不渲染**（缺失 701 / 605 / 348） | — |

### 5.3 行为

- 形态：stage 内 `absolute` 浮层，宽 420–480px、最大高 70vh 内部滚动、≤768 转底部 sheet；**非全屏遮罩、非右侧抽屉**。
- 外观：`--ds-surface-overlay` + `--ds-hairline` + `--ds-elevation-2` + `--ds-radius-md`；零 `backdrop-filter`；150ms 淡入 + 8px 位移。
- 点击：世界 transform **不变**、路由不变、邻居一次性降饱和约 30%。
- 关闭：`Esc` / 点外部 / 关闭按钮；焦点陷阱，打开聚焦标题，关闭后**焦点回到原 tile**。
- `navigate(id)`：只换浮层内容 + 高亮目标格，**不重排、不移动世界**。
- 可拖 / 多开：**禁止**（D6）。

**完成判据**：随机抽 3 类条目（有 summary / 无 summary / 无 relatedIds）字段与 catalog 一致；详情窗不出现「证据数」；占位符版本显示 `—`；Esc 后焦点回到原格；浏览器断言 `.ks-side--alt` 不存在。

---

## 6. T27 · 集成与门禁（最容易踩坑的一包）

### 6.1 `KnowledgeSpaceView.vue` 精确改动表（**8 处，一处都不能漏**）

| # | 行 | 原文 | 新文 |
|---|---|---|---|
| 1 | 10 附近 | `import SpaceFieldView from './SpaceFieldView.vue'` | 其后追加 `import MosaicWallView from './mosaic/MosaicWallView.vue'` |
| 2 | 17 | `const viewMode = ref('field')` | `const viewMode = ref('mosaic')` |
| 3 | **516** | `function onKeyDown (e) {` | 函数体**首行**加 `if (viewMode.value === 'mosaic') return` —— 否则 Esc（546 行）会把视图切到 space，`/` 聚焦旧搜索框，`0` 调用旧相机 `fitOverview` + `renderHUD()` |
| 4 | 601 | `<label class="ks-search">` | `<label class="ks-search" v-if="viewMode !== 'mosaic'">`（照片墙用 `Ctrl+K` 的 `FieldSearch.vue`，避免两个搜索框） |
| 5 | 596–599 | `<div class="ks-stat">…L{{ stat.lod }} · {{ stat.scale }}% · {{ stat.mountedCards }} 卡…</div>` | 加 `v-if="viewMode !== 'mosaic'"`，并补一个 `v-else` 简化条：`{{ fieldTotal }} 格 · {{ domainCount }} 个域 · 照片墙`；**旧 stat 是 space 视图统计，在 mosaic 下会显示误导数字** |
| 6 | 607 前 | pill 区 | 最前插入 `<button class="ks-pill" type="button" :class="{ 'ks-pill--on': viewMode === 'mosaic' }" @click="onViewModeChange('mosaic')">照片墙</button>`；原 4 枚不动 |
| 7 | 741 前 | `<SpaceFieldView v-else-if="viewMode === 'field'" />` | 其前插入 `<MosaicWallView v-else-if="viewMode === 'mosaic'" />` |
| 8 | **780** | `v-if="selectedCard && viewMode !== 'space'"` | `v-if="selectedCard && viewMode !== 'space' && viewMode !== 'mosaic'"` —— 漏掉会**同时弹出右侧抽屉** |

> #3 / #8 是本轮新发现的两个硬冲突（v1.1 文档只写了 #8）。#3 的 early return 让 `MosaicWallView` 自管 Esc / Ctrl+K / 方向键；现有 space/field/grid/list 四视图键盘行为**零变化**。
> `onMounted` 的 `if (viewMode.value === 'space') { init() }`（571 行）在 mosaic 默认下不执行是**正确行为**（field 模式同样跳过），不要改。

### 6.2 搜索与筛选接线

- `Ctrl+K` 复用 `FieldSearch.vue`（props `query`；emits `update:query / select / close`）。`select` 拿到条目后按 `id` 在 `field.tiles` 里查坐标 → `cam.centerOn(x, y, 1.00, worldEl, stageEl)` + 高亮命中格；**不重排**（D8）。
- 域筛选 chips：用 `searchKnowledgeEntries({ domain })` 得到命中 id 集合 → 非命中格降饱和；**不重排**。
- 顶栏 `/` 快捷键在 mosaic 下已被 #3 屏蔽，不要试图让它聚焦被隐藏的输入框。

### 6.3 演示与文档同步（不改代码，但必须做）

- `docs/competition/demo-script.md`、`演示讲解稿-4分钟-逐页.md`、`演示讲解稿-功能页-逐页口播.md` 中把 `/knowledge/space` 默认视图从「场域 / 3D 空间」改口播为「照片墙 / 737 格密铺」。
- 若口播里出现场域的「相机推进 / 三机位 / 480 平面」等说法，改成「四档缩放 / 域浮标签 / 悬浮详情窗」。
- **不得写未实测的性能数字**；性能结论一律带 before/after 与测量口径。

### 6.4 复跑命令（以 `frontend/package.json` 实际 scripts 为准）

```
typecheck        0 error
lint             0 error（warn 不新增）
build            用户端 + 管理端双端通过
test             全量（T11 基线 503 测试）0 失败；新增 mosaic 单测全绿
浏览器实测        /knowledge/space 在 375/768/1024/1440/1920 + 深浅双主题
Lighthouse       桌面 >= 92、移动 >= 95（不低于 T11 基线）
perf:baseline    已知 SSE 超时阻塞，标注「不计通过」，不要把它写成通过
```

### 6.5 浏览器实测必查项

1. 首屏默认就是照片墙，pill「照片墙」高亮；切到其余 4 个视图再切回来，行为正常。
2. 按 `Esc`（未开详情）、`/`、`0`、方向键：**不切视图、不报错、不调用旧相机**。
3. 点击任意格 → 悬浮窗出现、`.ks-side--alt` **不存在**、世界 transform 未变。
4. Ctrl+K 搜索命中 → 高亮 + 切 S2 + 居中，格子不重排。
5. 控制台零预算截断 warn；DOM 中 `.mw-tile` 数量 === `searchKnowledgeEntries({}).length`。
6. 无 `backdrop-filter` / WebGL / Canvas / 图片请求；`catalogProjection` 白名单 diff 为空。

---

## 7. 统一验收清单（12 条，缺一不算完成）

| # | 门禁 |
|---|---|
| 1 | tile 数 === `searchKnowledgeEntries({}).length`；id 唯一；10 域按登记顺序；小域折叠 1 枚标签 |
| 2 | 57 种 type 全部归 7 类；详情显原始 type；31 条空 type 走灰条 `REF`；risk 6 档覆盖 100% |
| 3 | 不出现 `evidenceRefs` 相关 UI；占位符版本显示 `—`；`summary` 缺 188 条走项目文案；无 `level/verification/category` 区块 |
| 4 | S0 首屏 ≥400 格、间隙 ≤2px；4 档缩放锚点不跑位、坐标误差 ≤1px；总览复位 |
| 5 | 悬浮窗字段与 catalog 一致；Esc 回焦；关联跳转不重排；右侧抽屉不出现 |
| 6 | typecheck / lint / 双端构建 / 全量测试 0 失败；Lighthouse 不低于 92 / 95 |
| 7 | 零 blur / WebGL / Canvas / bitmap / 新增依赖 / 新增接口；白名单 diff 为空；现有 4 视图测试全绿 |
| 8 | 深浅双主题对比度 ≥4.5:1；375 可点格 ≥44px；五断点无溢出 |
| 9 | 全键盘可达（Tab / 方向键 / Enter / Esc / Ctrl+K）；S0 档不进 Tab 序；reduced-motion 无补间 |
| 10 | 性能结论带 before/after + 测量口径，无实测数字视为未验收 |
| 11 | 无「准确率 9X%」「AI 识别指令风险」；UNVERIFIED 不画成已验证；无虚构证据/风险/版本 |
| 12 | `git diff` 仅含 `mosaic/` 新增文件 + `KnowledgeSpaceView.vue` 8 处 + 新增测试 + 演示口播；无他人改动被覆盖 |

---

## 8. 回滚与交接

- 回滚：删除 `mosaic/` 目录、还原 `KnowledgeSpaceView.vue` 的 8 处改动、移除 2 个新增测试文件；**不触碰任何其他文件**（工作区有他人未提交改动）。
- 若 T27 出现无法解决的全局键盘冲突，退路是把 `viewMode` 默认改回 `'field'`（D5 降级），其余 7 处保留，照片墙仍可通过 pill 进入 —— 但需先向用户报备，不要自行改裁决。
- 完成后交接：改动文件清单、单测与浏览器实测输出、Lighthouse 与 perf 的 before/after 数字、双主题截图（各 1 张 1440 视口）、遗留问题列表。

---

## 9. 索引

- 方案唯一口径：`docs/design/knowledge-photo-wall-v1/DESIGN.md`（v1.1）
- 本执行包：`docs/design/knowledge-photo-wall-v1/EXECUTION-PACK.md`
- 规范基线：`design-system/MASTER.md`、`frontend/src/assets/styles/variables.css`
- 数据真相：`frontend/src/views/knowledge/knowledgeCatalog.js`
- 复用组件：`useSpaceCamera.js`、`FieldSearch.vue`、`FieldPlaneDrawer.vue`（仅参考字段）、`src/visual/motionScheduler.js`

---

## 10. 交接启动提示词（用户已确认，可直接复制给实现模型）

> 下面整段是自包含的，接收方看不到本对话，直接粘贴即可。**建议先只派 T23+T24**（省赛 11-18 截止，P0 最小闭环优先），回执合格后再派 T25/T26/T27。

```
任务：在 D:/SmartOpsAgent 落地「知识库照片墙」第 5 视图，本轮只做 T23 + T24。

先读这三份（按顺序，不要跳）：
1. docs/design/knowledge-photo-wall-v1/DESIGN.md            （方案唯一口径 v1.1）
2. docs/design/knowledge-photo-wall-v1/EXECUTION-PACK.md   （执行唯一指令，本轮按 §2 T23、§3 T24）
3. frontend/src/views/knowledge/knowledgeCatalog.js        （数据真相，只读不改）

本轮交付：
- 新建 frontend/src/views/knowledge/space/mosaic/mosaicType.js + mosaicLayout.js，接口按执行包 §2.2/§2.3 直接粘贴后补全 TODO（域分段、serviceTag、小域折叠）。
- 新建 frontend/test/mosaic-type.test.mjs + mosaic-layout.test.mjs，断言按执行包 §2.4 的 13 条。
- 新建 frontend/src/views/knowledge/space/mosaic/ 下 MosaicWallView.vue / MosaicTile.vue / MosaicDomainTag.vue / mosaic.css，规格按执行包 §3（四层配方、data-size 四档、.mw-* 前缀、全量 737 格）。
- 跑通这两组单测，并给出输出。

硬性红线（违反即打回）：
- 唯一取数入口 import { searchKnowledgeEntries, knowledgeDomains } from '../../knowledgeCatalog.js'，用 searchKnowledgeEntries({})；不要碰 knowledgeCatalog.js、catalogProjection 白名单、useSpaceCamera.js、现有 4 个视图。
- 不要 import searchableKnowledgeEntries（未导出）；不要用 knowledgeEntries（无 normalize/directory）。
- 不硬编码 737 / 10 / 7，条目数与域数一律运行时取；域顺序按 knowledgeDomains 登记顺序。
- 颜色/字号/圆角/动效只用 var(--ds-*) 令牌（项目有深色 :root 与浅色 [data-theme='light'] 双主题），禁止写死 hex。
- 格子内容只用真实字段：域色=directory.domainId，色条=type 归一 7 类（详情窗仍显示原始 type），短码/标题=title，右下角标=risk；不显示 evidenceRefs（全库不存在）、不把 applicableVersion 占位符当版本、不用 content 冒充 summary（缺 188 条用「当前资料暂未记录摘要。」）。
- 全量挂载所有格子，禁止套用场域的 480/180 预算截断；零 WebGL/Canvas/位图/backdrop-filter/3D 变换；不新增依赖、路由或后端接口。
- 工作区有约 16 个他人未提交改动：只新增 mosaic/ 目录与 2 个测试文件，不要覆盖、不要顺手格式化别的文件、不要提交不属于本任务的内容。

不要做（留给后续包）：缩放接线(T25)、悬浮详情窗(T26)、KnowledgeSpaceView.vue 集成改动(T27，共 8 处，见执行包 §6.1)。
不要自行改裁决：D5 默认 mosaic / D6 单实例 / D7 首页不动 / D8 不重排 / D9 登记顺序 已由用户确认。

完成后按 §11 回执模板汇报，附改动文件清单、单测输出、1440 视口截图（深色+浅色各一张）。性能/效果结论必须带测量口径与 before/after，无实测数字不要写「通过」。
```

### 10.1 后续派包顺序

| 轮次 | 派发内容 | 前置条件 |
|---|---|---|
| 第 1 轮 | T23 + T24 | 无（现在即可派） |
| 第 2 轮 | T25 + T26（可并行给两个模型） | T24 的 `MosaicTile` props 契约已定 |
| 第 3 轮 | T27 集成 + 全量门禁复跑 | T25/T26 回执合格 |
| 收尾 | 演示口播同步 + 双主题截图 + 回滚预案核对 | T27 通过 |

---

## 11. 实现模型回执模板（要求对方按此格式回复）

```
【包号】T23 / T24 / T25 / T26 / T27（逐项）
【改动文件】新增：…  修改：…  （必须只有 mosaic/ + 指定测试 + KnowledgeSpaceView.vue 8 处）
【单测】命令 / 通过数 / 失败数 / 关键断言结果（tile 数 === 运行时 length、57 种 type 覆盖、坐标确定性）
【浏览器实测】断点 375/768/1024/1440/1920、深浅双主题、Esc//(/0/Ctrl+K 按键、抽屉不出现、控制台零报错
【基线复跑】typecheck / lint / 双端构建 / 全量测试 / Lighthouse（桌面·移动）/ perf:baseline（标注不计通过）
【证据】性能与效果的 before/after + 测量口径；截图路径
【遗留问题】未达标项与原因，不得把未验收项写成通过
【回滚】本包改动如何单独撤销
```

### 11.1 我方验收对照（收到回执后逐条打勾）

- [ ] `git diff` 只有约定范围，没有覆盖他人未提交改动
- [ ] DOM 中 `.mw-tile` 数量 === `searchKnowledgeEntries({}).length`，无预算截断 warn
- [ ] 详情窗无「证据数」、占位符显示 `—`、缺摘要走项目文案、原始 type 未被短码替换
- [ ] 默认视图是照片墙；按 Esc / `/` / `0` / 方向键不切视图、不报错
- [ ] 点击格子时 `.ks-side--alt` 不存在，世界 transform 未变
- [ ] 深色与浅色两套主题对比度 ≥4.5:1
- [ ] 12 条统一门禁（执行包 §7）全绿，性能结论带实测口径
- [ ] 演示讲解稿中 `/knowledge/space` 口播已改为「照片墙」
