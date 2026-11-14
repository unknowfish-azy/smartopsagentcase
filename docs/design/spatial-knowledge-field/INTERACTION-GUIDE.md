# 知识空间场 · 交互说明文档

日期：2026-11-14
适用路由：`/knowledge/space`（场域模式 `viewMode === 'field'`）
设计基线：[DESIGN.md](./DESIGN.md) §5（受限轨道 + 三机位预设）、§6（LOD 与预算）

---

## 1. 概述

知识空间场（Spatial Knowledge Field）以 3D 网状照片风格卡片承载 737 条知识条目，分布在 10 个领域中。交互体系围绕「**看关系 → 找条目 → 读详情**」三层目标设计，所有操作均不离开当前页面（P4：聚焦让对象靠近，不让世界离开）。

| 交互层 | 操作 | 目标 |
|---|---|---|
| 看关系 | 滚轮缩放 / 拖拽旋转 / 机位切换 | 浏览网状结构、发现关联 |
| 找条目 | Ctrl+K 搜索 / 域筛选 chip | 定位目标卡片 |
| 读详情 | 点击卡片 / Esc 回退 | 聚焦相机 + 打开详情抽屉 |

---

## 2. 鼠标滚轮缩放

### 2.1 行为定义

在场地任意位置滚动鼠标滚轮，相机沿视线方向推进/拉远，实现连续缩放。

| 操作 | 效果 |
|---|---|
| 滚轮向上（`deltaY < 0`） | 相机靠近（`dist` 减小），卡片放大 |
| 滚轮向下（`deltaY > 0`） | 相机拉远（`dist` 增大），卡片缩小 |

### 2.2 实现机制

事件绑定在 `FieldStage` 上（`@wheel.passive="onWheel"`），处理函数：

```js
// SpaceFieldView.vue
function onWheel (e) {
  e.preventDefault()
  cam.zoom(Math.exp(-e.deltaY * 0.0015))
}
```

缩放因子采用**指数映射**：`factor = exp(-deltaY × 0.0015)`，保证滚轮位移与缩放倍率呈对数线性关系（滚得越快缩得越多，但单步幅度平滑）。

`zoom()` 将 `dist` 乘以 factor 后钳制到合法范围：

```js
// useFieldCamera.js
function zoom (factor) {
  orbitTo({ dist: clampDist(dist.value * factor) })
}
```

### 2.3 参数边界

| 参数 | 值 | 说明 |
|---|---|---|
| `dist` 最小值 | 520px | 最近距离（focus 机位），再近会穿透卡片 |
| `dist` 最大值 | 2600px | 最远距离，再远卡片退化为色条不可读 |
| 缩放系数 | 0.0015 | 控制灵敏度，100px 滚轮位移 ≈ 16% 缩放 |

### 2.4 LOD 联动（P3 语义缩放）

缩放不仅改变尺寸，还切换卡片的**表示层级**：

| `dist` 范围 | LOD | 卡片显示内容 |
|---|---|---|
| `dist ≤ 900` | `near` | 完整卡片：头带 + 标题 + 摘要 + 标签 + 风险点 |
| `900 < dist ≤ 1500` | `mid` | 紧凑卡片：头带 + 标题 + 类型 chip |
| `dist > 1500` | `far` | 仅彩色色条（不可读，只表示位置与域色） |
| `focusPlaneId` 非空 | `focus` | 目标卡片完整显示并高亮，周围卡片降饱和 |

### 2.5 注意事项

- `e.preventDefault()` 阻止页面默认滚动，确保滚轮只作用于场域。
- `@wheel.passive` 修饰符由 Vue 编译为非 passive 监听器，保证 `preventDefault` 生效。
- 缩放不改变 `target`（相机注视点），因此缩放中心始终是当前画面中心，而非鼠标位置——这是受限轨道相机的设计取舍，避免用户在缩放中丢失全局方位。

---

## 3. 点击进模块（卡片下钻）

### 3.1 行为定义

点击任意知识卡片，触发**两级联动**：
1. **相机聚焦**：相机推到卡片正前方（`dist=520`），卡片移至画面中心并放大；
2. **详情抽屉**：右侧滑出抽屉，展示该条目的完整内容。

### 3.2 实现机制

```js
// SpaceFieldView.vue
function onPlaneClick (plane) {
  cam.focusOn(plane)          // ① 相机聚焦
  selectedPlane.value = plane // ② 打开抽屉
}
```

#### ① 相机聚焦（`focusOn`）

```js
// useFieldCamera.js
function focusOn (plane) {
  if (!plane) return
  focusPlaneId.value = plane.id          // 标记当前聚焦平面（LOD → focus）
  focusDomainId.value = plane.domainId    // 记录所在域（Esc 回退用）
  setPreset('focus', { cx: plane.x, cy: plane.y })
}
```

`focus` 机位参数：`yaw=0°, pitch=15°, dist=520, target=(plane.x, plane.y, 0)`。

聚焦后该卡片的 LOD 强制为 `focus`，应用高亮样式：`translateZ(30px) scale(1.06)` + 青色发光边框。

#### ② 详情抽屉（`FieldPlaneDrawer`）

抽屉通过 `selectedPlane` → `selectedEntry` 计算属性驱动，展示内容包括：

| 区块 | 数据来源 |
|---|---|
| 域渐变 banner | `entry.domain` → `DOMAIN_GRADIENTS` |
| 标题 | `entry.title` |
| 类型 chip | `entry.type` → 颜色映射 |
| 标签云 | `entry.tags[]` |
| 元信息 | ID / 证据数 / 版本号 |
| 风险指示 | `entry.risk` → 红/黄/绿色点 |
| 关联知识 | `entry.relatedIds[]` → 最多 8 条可点击跳转 |
| 正文 | `entry.content` 按 `\n\n` 分段 |

### 3.3 回退机制（Esc 三级回退）

按 `Esc` 键按层级回退，不破坏空间心智模型：

```
focus（聚焦单卡片 + 抽屉）
  │  Esc
  ▼
domain（相机拉回该域中心，抽屉关闭）
  │  Esc
  ▼
overlook（总览机位，dist=1500, pitch=28°）
```

实现：

```js
// SpaceFieldView.vue onKeyDown
if (e.key === 'Escape') {
  if (selectedPlane.value) { selectedPlane.value = null; return }  // 关抽屉
  const result = cam.back()                                          // 相机回退
  if (result === 'domain' && cam.focusDomainId.value) {
    const anchor = field.value.axes.domains.find(d => d.id === cam.focusDomainId.value)
    if (anchor) cam.orbitTo({ tx: anchor.x, ty: FIELD.knowledge.y0 + 80 })
  }
}
```

### 3.4 关联跳转

详情抽屉中的「关联知识」列表可点击，点击后复用 `focusEntry(entry)` 流程：定位该条目对应卡片 → `cam.focusOn` → 切换抽屉内容，实现条目间的无缝穿梭。

---

## 4. 其他辅助交互

### 4.1 拖拽旋转（轨道相机）

在场地空白处按住鼠标拖拽，可水平旋转（yaw）和俯仰（pitch）视角。

| 拖拽方向 | 效果 |
|---|---|
| 水平拖拽 | yaw 变化：右拖 → 世界向左转（`dx × 0.35°`） |
| 垂直拖拽 | pitch 变化：上拖 → 更俯视（`-dy × 0.25°`） |

约束：`yaw ∈ [-35°, 35°]`，`pitch ∈ [8°, 52°]`，防止用户翻到背面丢失方向感。

### 4.2 键盘快捷键

| 按键 | 功能 |
|---|---|
| `Ctrl + K` / `⌘ + K` | 打开搜索浮层（捕获阶段，优先于全局 CommandPalette） |
| `1` | 总览机位（overlook，dist=1500） |
| `2` | 平视机位（shelf，dist=760，默认） |
| `3` | 沿链机位（trace，预留） |
| `Esc` | 关闭抽屉 / 相机回退 / 关闭搜索 |
| `Enter`（卡片聚焦时） | 等同点击，打开详情 |

### 4.3 搜索（Ctrl+K）

浮层内输入关键词，实时过滤条目（匹配标题 / 域名 / 正文），最多显示 20 条结果。点击结果 → `focusEntry(entry)` → 相机聚焦 + 打开抽屉 + 关闭搜索。

### 4.4 域筛选

顶部域名 chip（10 个域）点击切换，多选叠加。激活后 `mountedPlanes` 只渲染选中域的卡片，HUD 出现「清除筛选」按钮。

---

## 5. 交互状态机

```
                    ┌──────────┐
          1/2/3 键  │ overlook │  dist=1500, LOD=mid
        ┌──────────┤ (总览)    │
        │          └────┬─────┘
        │               │ 滚轮/拖拽
        │               ▼
        │          ┌──────────┐
        │          │  shelf   │  dist=760, LOD=near（默认）
        │          │ (平视)   │
        │          └────┬─────┘
        │               │ 点击卡片
        │               ▼
        │          ┌──────────┐
        │          │  focus   │  dist=520, LOD=focus + 抽屉
        │          │ (聚焦)   │
        │          └────┬─────┘
        │               │ Esc
        │               ▼
        │          ┌──────────┐
        └──────────│  domain  │  域中心，dist=760
                   └────┬─────┘
                        │ Esc
                        ▼
                   回到 overlook
```

---

## 6. 代码位置索引

| 交互 | 文件 | 关键符号 |
|---|---|---|
| 滚轮缩放 | `frontend/src/views/knowledge/space/SpaceFieldView.vue` | `onWheel()` |
| 缩放实现 | `frontend/src/views/knowledge/space/useFieldCamera.js` | `zoom()`, `ORBIT.distMin/distMax` |
| 点击进模块 | `frontend/src/views/knowledge/space/SpaceFieldView.vue` | `onPlaneClick()`, `selectedPlane` |
| 相机聚焦 | `frontend/src/views/knowledge/space/useFieldCamera.js` | `focusOn()`, `setPreset('focus')` |
| 详情抽屉 | `frontend/src/views/knowledge/space/FieldPlaneDrawer.vue` | `FieldPlaneDrawer` 组件 |
| 拖拽旋转 | `frontend/src/views/knowledge/space/SpaceFieldView.vue` | `onPointerDown/Move/Up()` |
| 键盘快捷键 | `frontend/src/views/knowledge/space/SpaceFieldView.vue` | `onKeyDown()` |
| LOD 判定 | `frontend/src/views/knowledge/space/SpaceFieldView.vue` | `computeLod()`, `currentLod` |
| 域筛选 | `frontend/src/views/knowledge/space/SpaceFieldView.vue` | `toggleDomain()`, `mountedPlanes` |

---

## 7. 参数速查表

| 参数 | 值 | 位置 |
|---|---|---|
| 卡片尺寸 | 168 × 96 px | `FIELD.planeW / planeH` |
| 每域列数 | 6 | `FIELD.maxCols` |
| 域间距 | 1160 px | `FIELD.domainPitch` |
| Z 轴行间距 | 30 px | `layoutKnowledgePlanes.rowDepthStep` |
| 透视值 | `dist × 5` | `FieldStage.perspective` |
| `dist` 范围 | 520 – 2600 px | `ORBIT.distMin / distMax` |
| yaw 范围 | -35° – 35° | `ORBIT.yawMin / yawMax` |
| pitch 范围 | 8° – 52° | `ORBIT.pitchMin / pitchMax` |
| 缩放灵敏度 | 0.0015 | `onWheel` 中 `Math.exp(-e.deltaY * 0.0015)` |
| 拖拽灵敏度 | 0.35°/px（水平）, 0.25°/px（垂直） | `onPointerMove` |
| LOD near 阈值 | `dist ≤ 900` | `computeLod` |
| LOD mid 阈值 | `dist ≤ 1500` | `computeLod` |
| 最大挂载卡片 | 480 | `MAX_MOUNT` |
