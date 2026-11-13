# ExecutionTrace · 神经网络流水线动效说明

> 版本：v1.0 · 日期：2026-11-13 · 页面：`/agent/trace` · 文件：`ExecutionTraceView.vue`
> 源参考：抖音《基于 MLP+GRU 神经网络的引擎传感器时序预测项目》BV 1HZ9YBcEnY

---

## 1. 设计理念

ExecutionTrace 展示 **Agent 执行轨迹——4 步骤时序链**：Understand → Collect → Risk gate → Verification。

MLP+GRU 时序预测的核心视觉语言是**时间轴上的数据流 + 节点触发**——两者是同一个动效模型。本节将神经网络流水线的"接收→放大→发射"三级脉冲语义嫁接给 Agent 推理步骤。

**改动范围**：仅 ExecutionTraceView.vue 的 scoped CSS（+308/-21）。零 JS 改动，零 template 结构改动。

---

## 2. 五层动效全景

```
┌──────────────────────────────────────────────────────────────────┐
│  启佑背景层（已有，不动）                                          │
│  CanvasAmbientField 234颗星 + 130px 连线网络                       │
│  trace-aurora 双层极光 drift 16s + sweep 24s（**加速同频**）        │
│  MeteorShower 6颗流星                                             │
│  trace-mask 42% 暗度                                              │
├──────────────────────────────────────────────────────────────────┤
│  ExecutionTrace 专属（本节重点）                                    │
│                                                                  │
│  ① 数据流脉冲线  trace-pulse-flow  已完成步骤竖线光点从上往下流入    │
│  ② 节点三级脉冲  trace-neuron      接收→放大→发射光环扩散          │
│  ③ 指标网格脉冲  trace-digit-pulse 8格错峰 3.6s 模拟传感器读数      │
│  ④ 极光加速同频  drift 16s / sweep 24s（原 22s/32s）              │
│  ⑤ 推理摘要卡    trace-reason-flow 边框光流 6s + 文字呼吸 4s        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 五项动效详解

### 3.1 数据流脉冲线 · trace-pulse-flow

**视觉**：绿光点沿已完成步骤竖线**从上往下流入**，像神经元触发传导。

**实现原理**：利用 `.trace-connector::before`（2px 宽竖线）的 `inset box-shadow` 从底部扫到顶部，制造"光点沿竖线流动"的视觉错觉。

| 步骤状态 | 动画周期 | 颜色 | 说明 |
|---|---|---|---|
| `.trace-step.done` | **1.6s** | `rgba(63, 185, 80, .9)` 绿 | 快速传导，Agent 已完成 |
| `.trace-step.check` | **2.2s** | `rgba(63, 185, 80, .9)` 绿 | 稍慢，风险门控中 |
| `.trace-step.pending` | ❌ 无 | — | NOT RUN 无光点 |

```css
@keyframes trace-pulse-flow {
  0%, 100% { box-shadow: inset 0 -14px 14px rgba(63, 185, 80, .0); }
  50%      { box-shadow: inset 0  14px 14px rgba(63, 185, 80, .9); }
}
```

`inset 0 -14px 14px` → `inset 0 14px 14px` = 阴影从底部 → 顶部扫过竖线，等效光点向上流动（视觉上看起来是向下，因为竖线是从上往下排列的）。

### 3.2 节点三级脉冲 · trace-neuron

**视觉**：节点圆点像神经元一样**接收→放大→发射**。

**三阶段**：

```
时间轴：
0ms         300ms         600ms         2400ms（下一轮）
│           │             │             │
▼           ▼             ▼             ▼
┌────────────────────────────────────────────────────┐
│ 接收    → │ 放大    → │ 发射    → │ 静默等待下一轮  │
│          │           │           │                 │
│ 10px     │ 14px      │ 10px      │                 │
│ 6px 光晕 │ 18px 光晕 │ 10px 光晕 │                 │
│          │ 4px 光环  │ 20px 光环 │                 │
│          │           │ (opacity 0)│                │
└────────────────────────────────────────────────────┘
```

| 阶段 | 时间点 | 尺寸 | box-shadow | 语义 |
|---|---|---|---|---|
| 接收 | 0% | 10px | 6px 光晕 | 外部信号到达节点 |
| 放大 | 30% | **14px** | 18px 光晕 + **4px 光环** | 内部信号处理/放大 |
| 发射 | 60% | 10px | 10px 光晕 + **20px 扩散光环**（opacity 0） | 信号向下一个节点传递 |

```css
@keyframes trace-neuron {
  0%, 100% { width: 10px; height: 10px; box-shadow: 0 0 6px currentColor, 0 0 0 0 currentColor; }
  30%      { width: 14px; height: 14px; box-shadow: 0 0 18px currentColor, 0 0 0 4px rgba(63, 185, 80, .35); }
  60%      { width: 10px; height: 10px; box-shadow: 0 0 10px currentColor, 0 0 0 20px rgba(63, 185, 80, 0); }
}
```

`currentColor` 技巧：通过设置节点 `color` 为状态色（绿/黄），box-shadow 自动继承，无需写两套 keyframes。

### 3.3 指标网格实时脉冲 · trace-digit-pulse

**视觉**：8 格指标数字像**传感器读数**一样周期性刷新，暗示数据流持续更新。

**关键设计**：
- 8 格 **错峰 delay**（0s → .4s → .8s → 1.2s → 1.6s → 2.0s → 2.4s → 2.8s）
- 总周期 3.6s，视觉上产生"波浪"效果
- `font-variant-numeric: tabular-nums` 防止数字宽度变化导致卡片跳动

```css
@keyframes trace-digit-pulse {
  0%, 100% { transform: scale(1);    opacity: 1; }
  40%      { transform: scale(1.05); opacity: .85; }
  60%      { transform: scale(.97);  opacity: 1; }
}
```

`scale 1 → 1.05 → .97 → 1` = 微幅 overshoot 回弹，模拟物理传感器指针抖动。

### 3.4 极光加速与步骤同频

**问题**：原 drift 22s + sweep 32s 与步骤脉冲 2.4s 不同频，背景和内容各自为政。

**解**：
- drift 22s → **16s**
- sweep 32s → **24s**
- 16s / 2.4s ≈ 6.67（3 轮步骤脉冲 ≈ 1 轮极光 drift）
- 24s / 2.4s = 10（整数倍对齐）

**效果**：背景流动节奏暗示 Agent 正在持续工作。

### 3.5 推理摘要卡 · AI 输出感

**视觉**：边框有**青/绿光流扫过** + 文字**呼吸**暗示 AI 正在"思考"。

| 元素 | 动画 | 周期 | 效果 |
|---|---|---|---|
| `.reasoning-card::before` | `trace-reason-flow` | 6s linear | 120° 渐变光带从左到右扫过边框 |
| `.reasoning-card p` | `trace-reason-breathe` | 4s ease-in-out | opacity 1 → .78 → 1 微幅呼吸 |

```css
@keyframes trace-reason-flow {
  0%   { background-position: 0% 0%;   opacity: .7; }
  100% { background-position: 200% 0%; opacity: 1; }
}
@keyframes trace-reason-breathe {
  0%, 100% { opacity: 1; }
  50%      { opacity: .78; }
}
```

`::before` + `::after` 双层：`::before` 做大渐变扫光，`::after` 复制背景色盖在上面，只让边缘透出光带。

---

## 4. reduced-motion 完整关断

所有 5 项动效均加：

```css
@media (prefers-reduced-motion: reduce) {
  /* ① 数据流脉冲 */
  .trace-step.done .trace-connector::before,
  .trace-step.check .trace-connector::before { animation: none; }
  /* ② 节点三级脉冲 */
  .trace-step.done .trace-connector::after,
  .trace-step.check .trace-connector::after { animation: none; }
  /* ④ 极光 drift/sweep（启佑背景层已有） */
  /* ③⑤ 是 .grid strong 和 .reasoning-card p 的 animation，同上模式 */
}
```

---

## 5. 三主题适配

| 主题 | 背景 | 节点色 | 极光 | 推理卡边框 |
|---|---|---|---|---|
| `dark` | `#040B16` 深空 | `#3FB950` 绿 / `#E7C56D` 黄 | 青绿 drift + sweep | 青绿光流 |
| `light` | `#EAF3FA` 浅蓝星天 | 同 | 深青降饱和 | 深青光流 |
| 跟随系统 | 自动 | 自动 | 自动 | 自动 |

节点颜色通过 `color` CSS 属性注入，box-shadow 用 `currentColor` 自动继承——**零额外代码适配亮色**。

---

## 6. 改动统计

| 指标 | 数值 |
|---|---|
| 文件数 | 1（ExecutionTraceView.vue） |
| CSS 新增行 | +308 |
| CSS 删除行 | -21 |
| keyframes 新增 | 5（trace-pulse-flow / trace-neuron / trace-digit-pulse / trace-reason-flow / trace-reason-breathe） |
| JS 改动 | 0 |
| template 改动 | 0 |
| 回归 | typecheck 0 error / 503 tests 全绿 |

---

## 7. 后续可扩展

| 扩展 | 说明 | 复杂度 |
|---|---|---|
| 步骤触发时序 | 用 JS `setInterval` 逐步点亮 4 步骤（目前是全部常驻动画） | 中 |
| 数据流方向切换 | 支持 Agent 执行/回滚双向流动 | 低 |
| 节点接入真实 InspectorTrace | 后端返回 timing 数据，节点按真实时长触发 | 高 |
| 神经网络层可视化 | 在步骤间加感知层/隐藏层/输出层节点（纯 CSS 扩展） | 中 |
