# 智能体构成场 · 活体设计 v1

> 目标：把 `/agent/module` 的「构成场」从 5 张状态贴纸，改成**一具会随真实遥测改变形体的身体**。
> 核心一句话：**视觉 = f(数据)。数据没变，画面不该动；数据变了，画面必须变。**

| 项 | 值 |
| --- | --- |
| 页面 | `views/agent/AgentModuleView.vue` |
| 视觉组件 | `components/agent/fable/FableComposition.vue`、`FableGaze.vue`、`FatBlob.vue` |
| 数据源（已核实存在） | `GET /api/agent/loops?limit=30`、`GET /api/agent/loops/stats`、`GET /api/inspector/summary`、`useCompanionStore()` |
| 渲染路线 | SVG + 手写 spring 插值（路线 A，零新依赖） |
| 动效预算 | 复用 `visual/motionScheduler.js`（30fps 默认、慢帧 15fps、离屏暂停） |

---

## 1. 不变量（三条，任何实现都必须满足）

1. **每个形变都能指回一个字段。** 说不出「这个形状为什么变」的参数，不许存在。
2. **读不到就冻结并标注，不补数。** 这是页面自己文案（「读不到时显示「—」，绝不补数」）的要求，视觉必须一样守。
3. **状态只决定引力中心，不直接决定终点。** 五个「构成状态」从「五张要贴的图」降级为「参数空间里的五个吸引子」，实际位置由真实数据算出。

---

## 2. 参数场：八个参数，八条来源

`FableComposition` 的 props 从 `state: String` 改成 `field: Object`。**每个参数必须能追到下面某一行**。

| # | 参数 | 类型/范围 | 公式（都做 0..1 归一后映射） | 来源字段 | 读不到时 |
| --- | --- | --- | --- | --- | --- |
| 1 | `aperture` 孔径 | 0.40 – 1.20 | `1.2 - 0.8 × norm(high + critical, 0..8)` | `GET /api/inspector/summary` → `high`、`critical`（现有 `alerts` 已算） | `—`，保持上一稳定值 |
| 2 | `tilt` 倾角 | −6° – −34° | 主导阶段相位：`Σ(stage权重 × 相位索引) / Σ权重` 映射到角度 | `GET /api/agent/loops/stats` → `byStage[{stage,count}]` | 保持 −12°（IDLE 位） |
| 3 | `volume` 体积 | 0.85 – 1.15 | `0.85 + 0.3 × log10(1 + total) / log10(1 + 100)` | `loops/stats` → `total` | 1.00 |
| 4 | `spin` 环速 | 0 – 1 | `norm(warning, 0..5)` | `inspector/summary` → `warning` | 0（停转） |
| 5 | `groove` 刻线数 | 8 – 48（离散） | `8 + 40 × norm(learnedCount, 0..200)` | `loops/stats` → `learnedCount` | 8 |
| 6 | `gaze` 瞳孔 | `{x,y} ∈ [-1,1]` | 焦点对象方向：选中 loop 的 stage / 最新 high 事件的严重度轴 | `loops[]`、`inspector/summary` | 回正 + 缓慢游移（唯一允许的无数据运动，见 §5.3） |
| 7 | `grain` 噪声 | 0 – 1 | `1 - resolveRate` | `loops/stats` → `resolveRate` | 0.5 中性 |
| 8 | `pulse` 心跳周期 | 2.4 – 6.0 s | 最近闭环时长滚动均值（`loops[]` 的 `endedAt - startedAt`） | `loops[]` | 停在 4.0s 且不呼吸 |

**必须**：所有参数集中在 `views/agent/fable/useCompositionField.js` 里算，组件只消费。**不许**在模板里写 `'1.00'` 这种字面量。

**待核对**：`agent_decision_loop.stage` 的取值集合（表默认 `'ANALYZE'`）。阶段 1 要用真实数据打印一次 `byStage`，确认是 `ANALYZE / DECIDE / EXECUTE / REFLECT` 还是有别的值；未知值一律归到 `ANALYZE` 并在 UI 里不显示该阶段名。

---

## 3. 五个吸引子（从「终值」降级为「引力中心」）

现有的五组数字不再直接渲染，而是作为**目标向量的参考点**。实际渲染值 = `当前值 + (吸引子向量 − 当前值) × 数据权重`，再由 spring 平滑。

| 吸引子 | 孔径 | 倾角 | 体积 | 环速 | 刻线密度 | 何时最接近它（真实数据条件） |
| --- | --- | --- | --- | --- | --- | --- |
| 静观 IDLE | 1.00 | −12° | 1.00 | 0 | 低 | `high+critical = 0` 且 `requiresHuman = 0` |
| 解析 ANALYZE | 0.90 | −21° | 0.96 | 0.2 | 中 | `byStage` 主导 ANALYZE 且 有未决事件 |
| 决断 DECIDE | 0.62 | −7° | 0.90 | 0.45 | 中高 | 存在 `requires_human = TRUE` 的 loop |
| 执行 EXECUTE | 0.78 | −32° | 1.05 | 0.75 | 高 | `byStage` 主导 EXECUTE |
| 复盘 REFLECT | 0.94 | −16° | 0.98 | 0.3 | 最高 | `byStage` 主导 REFLECT 且 `learnedCount` 增长中 |

**必须**：`derivedState` 不再是 `warning ? 'decide' : 'idle'` 两分支，而是按上表条件判定（可多条件竞争时取权重最大者）。判定结果只作为「主导吸引子」提示，**视觉位置仍由 §2 的参数决定**。

### 3.1 演练模式（保留，但必须可见）

现有 `drillState` 手点切换保留，但要满足：

- 演练时角标变成 `REHEARSAL`（现有「人工门」卡已经有这个语义，复用同一措辞）；
- 视觉上有一个明确的「锁定」标记（磁场外一圈虚线 + 顶部 `DRILL` 小字）；
- 点击「跟随运行时 / FOLLOW RUNTIME」立即回到数据驱动。

理由：一个视觉如果可能来自手动演练，就不能让人误读成实时状态。

---

## 4. 渲染规格（SVG 结构 → 参数）

| 层 | 元素 | 受哪些参数影响 |
| --- | --- | --- |
| 外刻度环 | 3 圈刻线（8 / 16 / 32 等分） | `groove` 决定显示哪几圈、每圈多少条；`spin` 决定旋转速度 |
| 相位楔 | 3–5 个弧段 | `tilt` 决定整体旋转；主导阶段弧段高亮（不靠颜色，靠**弧长**） |
| 内螺旋 | 对数螺线 path | `grain` 决定螺线抖动幅度与透明度 |
| 虹膜 | 中心双弧 | `aperture` 直接控制开合角度 |
| 躯体线 | 横向贯穿线 | `volume` 控制长度与端点标记 |
| 瞳孔 | 中央圆 + 高光点 | `gaze` 控制位移与缩放 |

**只动这些属性**：`transform`、`opacity`、`stroke-dasharray`、`stroke-dashoffset`、`r`、`d`。
**禁止**：`filter: blur/drop-shadow`（工具层禁 blur）、`backdrop-filter`、任何 WebGL。

### 4.1 spring 插值（约 20 行，不引库）

```js
const tau = 0.28                       // 时间常数，秒
const k = 1 - Math.exp(-dt / tau)      // dt 由 motionScheduler 提供
cur.aperture += (target.aperture - cur.aperture) * k
```

**必须**：所有参数共用一个 `cur` 对象；每帧只算一次；`target` 只在数据到达时更新。

### 4.2 迟滞（防抖）

参数变化小于阈值（孔径 0.02 / 倾角 1.5° / 体积 0.01）时**不更新 target**，避免后端抖动让画面一直颤。这是「精密感」的一部分：稳定的东西看起来才像仪器。

---

## 5. 数据新鲜度

| 情况 | 行为 |
| --- | --- |
| 10s 轮询成功 | 更新 `target`、`fetchedAt` |
| ≥30s 未更新 | `stale = true`：整场降饱和度 40%、角标 `STALE`、**停止 pulse**、读数显示 `—` |
| 请求失败 | 保留上一帧形状 + `stale`，不显示「平衡态」假装正常（延续现有 `Promise.allSettled` 的容错风格） |
| 首次加载 | 只显示刻度环骨架 + `LOADING`，不要先画一个假的静观态 |

### 5.1 唯一允许的「无数据运动」

`pulse`（心跳）与 `gaze` 的轻微游移。而且：

- `pulse` 周期来自真实闭环时长；
- 数据 stale 时两者都停；
- `prefers-reduced-motion` 时两者都停。

除这两项外，**画面在数据不变时必须完全静止**。这是判断「这是仪器还是装饰」的分界线。

---

## 6. 组件与接口契约

```js
// FableComposition.vue —— 改造后
defineProps({
  field:     { type: Object, required: true },   // §2 的八个参数（已归一）
  attractor: { type: String, default: 'idle' },  // 仅用于高亮主导阶段，不决定形变
  stale:     { type: Boolean, default: false },
  reduced:   { type: Boolean, default: false }
})

// FableGaze.vue
defineProps({ gaze: { type: Object, required: true }, stale: Boolean, reduced: Boolean })
// gaze = { x, y }，单位向量；指针跟随仍然保留，但优先级低于数据焦点（数据焦点优先，见 §6.1）
```

### 6.1 指针 vs 数据焦点

现有 `gazeFollow`（指针跟随）**降级为次要输入**：

| 优先级 | 输入 | 生效条件 |
| --- | --- | --- |
| 1（最高） | 选中 loop / 最新 high 事件 | 有焦点对象时 |
| 2 | 指针位置 | 上一级为空，且 `gazeFollow = true` |
| 3 | 缓慢游移 | 以上都为空，且非 stale、非 reduced |

原来的 `GAZE` 按钮文案改成 `指针跟随`，并在 tooltip 写明「有焦点对象时以焦点为准」。

---

## 7. 文件与职责

```
views/agent/
  AgentModuleView.vue          ← 只做编排：取数、轮询、stale 判定、把 field 传给组件
  fable/
    useCompositionField.js     ← ★新增：字段 → 八参数（纯函数，可单测）
    useCompositionClock.js     ← 轮询 + stale + 曲线平滑（复用 motionScheduler）
components/agent/fable/
  FableComposition.vue         ← props 改 field；内部只做插值与绘制
  FableGaze.vue                ← props 改 gaze
  FatBlob.vue                  ← 加 volume prop（breathe 由 pulse 驱动）
```

**必须**：`useCompositionField.js` 不 import Vue、不碰 DOM，`(loops, stats, summary, companion) → field`，可用 Node 直接跑单测。

---

## 8. 性能与降级

| 场景 | 行为 |
| --- | --- |
| 正常 | 30fps（`motionScheduler`），参数插值 8 个标量 ≈ 可忽略 |
| 慢帧（连续 2s > 20ms） | 降到 15fps；刻线只画最密一圈 |
| 离屏 / 标签页隐藏 | 暂停 rAF，恢复时按当前 `target` 直接落位（不做补间） |
| `prefers-reduced-motion` | 无插值、无 pulse、无游移，直接落位；读数照常 |
| 低端（`visualMode === 'reduced-motion'` 或 `pointer: coarse`） | 刻线 8 条、无内螺旋、无相位楔，只保留虹膜 + 躯体线 + 瞳孔 |

---

## 9. 「科技感」检查表（实现时逐条对照）

- [ ] 刻度环至少三档密度，且密度由 `learnedCount` 决定（不是写死）
- [ ] 读数标签与图形同一帧渲染（同一个 `field` 对象）
- [ ] 参数变化有迟滞，静止时画面完全不动
- [ ] 相位切换有「过零」动作（先收拢再过零），不是淡入淡出
- [ ] stale 时降饱和 + 停 pulse + 读数变 `—`
- [ ] 演练模式有 `REHEARSAL` 角标 + 锁定虚线环
- [ ] 全页找不到 `filter: blur` / `backdrop-filter` / WebGL

---

## 10. 验收清单

- [ ] 改 `learnedCount`（DB 里造一条 loop）→ 600ms 内刻线数变化，且能在 UI 上指回该字段
- [ ] 把 `high + critical` 从 0 改成 3 → 孔径收窄，收敛过程无抖动
- [ ] `requires_human = TRUE` 的 loop 存在时，主导吸引子变 DECIDE，且倾角向 −7° 移动
- [ ] 停掉后端 30s → `STALE` + 降饱和 + pulse 停
- [ ] 请求失败 → 保留形状 + `STALE`，不出现假的「静观」
- [ ] 手点演练 → `REHEARSAL` + 锁定环；点 FOLLOW RUNTIME 立刻回到数据驱动
- [ ] `prefers-reduced-motion` 下无任何动画，读数与形状仍正确
- [ ] 数据不变时静置 60s，截图两次**完全一致**（除时间戳）——这是「不是装饰」的硬证据
- [ ] 8 个参数逐条给出「字段来源」注释，无字面量
- [ ] 单测：`useCompositionField` 给定固定输入 → 输出确定；边界（全 0 / 超大值）不越界

---

## 11. 参考

| 文件 | 说明 |
| --- | --- |
| [RESEARCH.md](RESEARCH.md) | 贴纸根因的逐行证据 + GitHub 选型（许可已实测）+ 科技感来源 |
| [PROMPT.md](PROMPT.md) | 交给执行模型的实现提示词 |
| `field-lab.html` | 参数场实验台：拖滑杆改八个参数，直接看形状怎么变（这一份的"原型"，因为静态图证明不了「数据一变画面就变」） |
