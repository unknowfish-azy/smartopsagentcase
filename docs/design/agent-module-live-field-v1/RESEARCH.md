# 研究：把「构成场」从贴纸改成活的

> 结论：**贴纸的根因不在视觉，在数据流——`FableComposition` 只吃一个状态字符串，不吃任何数值。**
> 修法不是换更炫的库，而是把视觉参数改成 `f(后端字段)` 的连续函数；库只在需要时补位。

| 项 | 值 |
| --- | --- |
| 页面 | `/agent/module` → `views/agent/AgentModuleView.vue`（598 行）+ `components/agent/fable/{FableComposition,FableGaze,FatBlob}.vue` |
| 现在接了什么 | `getDecisionLoops()`、`getInspectorSummary()`、`useCompanionStore()` |
| 现在的问题 | 视觉参数是**硬编码常量表**；5 个状态里只有 2 个会被真实数据触发 |
| 本文范围 | 诊断 + GitHub 选型 + 许可核查；设计见 [DESIGN.md](DESIGN.md) |

---

## 1. 为什么它现在是贴纸（逐行证据）

| # | 证据 | 说明 |
| --- | --- | --- |
| 1 | `AgentModuleView.vue:290` `params: { aperture: '1.00', tilt: '−12°', volume: '1.00' }` | 五个状态的孔径/倾角/体积全是**字符串字面量**。它们不是算出来的，是写死的 |
| 2 | `:406-408` `profile = STATES.find(...)` | 视觉拿到的只有「哪一档」，没有任何连续量 |
| 3 | `:66` `<FableComposition :state="compositionState" />` | 组件 props 只有一个字符串 → 视觉与数据之间**没有函数关系** |
| 4 | `:404` `derivedState = warning ? 'decide' : 'idle'` | 5 个状态里，真实数据只能触发 **2 个**。`analyze / execute / reflect` 只有手点 `drillState` 才出现 |
| 5 | `:388-399` `health`、`alerts` | 已经算出来了，但**只喂给右侧小卡**，一个像素都没进构成场 |
| 6 | `:382` `runtimeLabel = warning ? 'WARNING' : 'IDLE'` | 运行态是二值，无法驱动形状 |

**判定**：这不是「动效不够炫」，是**视觉没有接数据**。换 Three.js、换 Rive、加发光描边，只要 props 还是一个状态字符串，它仍然是贴纸。

---

## 2. GitHub 选型（许可已实测，非记忆）

核查方式：直接抓各仓库 `raw.githubusercontent.com/<repo>/HEAD/LICENSE*` 原文匹配许可头（GitHub API 会限流，且拆分许可会报 `NOASSERTION`，见上一份 `agent-avatar-3d-v1/README.md` 的教训）。

| 仓库 | 许可（实测） | 是什么 | 对我们的价值 | 结论 |
| --- | --- | --- | --- | --- |
| [`rive-app/rive-wasm`](https://github.com/rive-app/rive-wasm) | **MIT** | Rive 官方 WASM 运行时；**状态机 + inputs**，输入可由 JS 实时设置 | 真正「状态驱动的动画」；设计师可控，绑定后端数值即可 | **可选增强（B）** |
| [`juliangarnier/anime`](https://github.com/juliangarnier/anime) | **MIT** | anime.js v4：spring、时间轴、可动画化任意数值 | 省掉手写 spring 的 30 行；可直接插值 SVG 属性 | **可选（A+）** |
| [`motiondivision/motion`](https://github.com/motiondivision/motion) | **MIT** | Motion（原 Framer Motion）vanilla 版；spring 数值驱动 | 同上，生态更大 | 可选 |
| [`airbnb/lottie-web`](https://github.com/airbnb/lottie-web) | **MIT** | Lottie 运行时（AE 导出 JSON） | 预烘焙动画，只能改速度/片段 | ❌ **本质仍是贴纸** |
| [`metafizzy/zdog`](https://github.com/metafizzy/zdog) | 待确认（LICENSE 存在但未匹配到标准头） | 伪 3D 图形引擎（canvas/SVG），扁平几何很好看 | 可做「构成变换」的体积块 | 待确认后可选 |
| [`oframe/ogl`](https://github.com/oframe/ogl) | 待确认 | 极简 WebGL | 自定义着色器 | ❌ 工具层禁 WebGL |
| [`pixijs/pixijs`](https://github.com/pixijs/pixijs) | **MIT** | 2D WebGL 渲染器 | 高性能粒子/波形 | ❌ 同上 |
| [`statelyai/xstate`](https://github.com/statelyai/xstate) | **MIT** | 状态机 | 把「感知→规划→执行→核查」建模成显式状态机 | 可选（仅当阶段变复杂） |
| [`theatre-js/theatre`](https://github.com/theatre-js/theatre) | **Apache-2.0** | 动效编辑器 + 运行时 | 可在浏览器里调参数 | ❌ 太重，工具层引入编辑器不合适 |
| [`vueuse/motion`](https://github.com/vueuse/motion) | **MIT** | Vue 声明式 spring | 简单 | 可选，但 SVG 属性动画支持不如 anime |
| [`patriciogonzalezvivo/lygia`](https://github.com/patriciogonzalezvivo/lygia) | **Apache-2.0** | GLSL 着色器库 | 生成式纹理 | ❌ 同上 |
| [`d3/d3-interpolate`](https://github.com/d3/d3-interpolate) | 待确认（d3 系通常 ISC） | 插值/缓动 | 手搓也能替代 | 不必要 |

### 三条候选路线

| 路线 | 组成 | 代价 | 适用 |
| --- | --- | --- | --- |
| **A · 参数场自研（推荐）** | SVG + 手写 spring（约 30 行）+ 现有 `motionScheduler` | 零新依赖；完全可控；天然可 a11y | 立刻落地 |
| **A+ · 自研 + anime.js** | 上面 + `anime@4`（MIT）插值 | +1 依赖（约 20KB） | 想少写代码 |
| **B · Rive 状态机** | Rive 编辑器做 artboard + inputs；`rive-wasm` 运行时 | 需要设计师与 Rive 编辑器；二进制资产；a11y 难；工具层新增 WASM | 视觉复杂度高、有设计资源时 |
| **C · 排除** | Lottie / Three / OGL / Pixi / Lygia | Lottie 无法真正接数据；其余违反「控制台零 WebGL」 | — |

**推荐：A 先落地，B 作为第二阶段可选。** 理由：这一页要解决的是「数据没接进视觉」，不是「画面不够炫」；换引擎解决不了 props 里只有字符串的问题。

---

## 3. 「科技感」到底从哪来（这条决定设计方向）

很多人以为科技感=发光/霓虹/粒子。在运维控制台里恰好相反——**科技感来自精度**：

| 真来源 | 假来源（要避免） |
| --- | --- |
| 刻度环、相位锁、示波器轨迹（可读数、可对齐） | 外发光、霓虹描边 |
| 参数读数与图形**同源**（改数就改形） | 装饰性粒子飘动 |
| 状态切换有物理感（spring、阻尼、留痕） | 循环播放的呼吸动画 |
| 数据陈旧时**冻结**并标 STALE | 永远在动，假装还活着 |
| 单色 + 一个强调色（项目已有 clay/gaze 体系） | 多色渐变滥用 |

所以设计的目标不是「更炫」，而是**让每个形变都能指回一个数字**。详见设计。

---

## 4. 与上一份逆向的关系

上一份（`knowledge-spatial-ia-v1`）的结论是「HTML-in-Canvas 的价值在于卡片是真 DOM」。这里同理：**这一页的价值在于图形是真数据**。两者是同一条原则的两个应用面——**不要用渲染技巧冒充信息**。

下一步：[DESIGN.md](DESIGN.md)（参数场设计 + 数据绑定表 + 动效规格 + 验收），以及 [PROMPT.md](PROMPT.md)（交给执行模型）。
