# 悬浮桌宠 · 方案 v1（Persona Pet）

> 一句话：桌宠不是第五个生命体，是**第四生命体（数字人 / Agent 人格化身）的迷你形态**——把已打通的 VRM 管线缩进一个可拖拽浮窗，默认关闭、用户显式开启。
> 参考项目：[GML-MMGroup/GMTalker](https://github.com/GML-MMGroup/GMTalker)（深圳光明实验室，UE5 渲染交互数字人）。

| 项 | 值 |
| --- | --- |
| 宿主 | SmartOpsAgent 用户控制台（:5173，MainLayout 公共壳） |
| 形态 | fixed 浮窗（约 220×300），可拖拽、可收起成小球、可跳转 `/agent/persona` 全页模式 |
| 复用 | `useVrmModel` / `useLipSync` / `personaStates` / `frameBudget` 全部沿用，零新依赖 |
| 形象 | 继续 CC0 VRM；正式形象按「深海/生物发光」主题选型（见 §6） |
| 语音 | 浏览器 Web Speech（`speechSynthesis`），零依赖零许可风险 |

---

## 1. GMTalker 调研结论（2026-11-14，证据：仓库 README + License 原文）

| 项 | 内容 | 判定 |
| --- | --- | --- |
| 定位 | UE5 渲染的交互式数字人：FunASR（ASR）+ MeloTTS（TTS）+ LLM + 口型驱动，唤醒/打断/克隆 | 方法参考价值高 |
| 客户端 | UE 打包 exe / Android / **Web 串流**（服务端渲染，浏览器收视频流） | 渲染端不可嵌入本项目 |
| 形象 | 光墩墩（GuangDUNDUN），随 UE 工程发布 | 授权随工程，不可落地 |
| 许可 | **CC BY-NC 4.0**（非商业，需署名） | 按合规门属「有条件使用」→ **资产与代码均不进仓** |

**合规门判定**（沿 `design-system/MASTER.md` Open Source Intake）：

- ❌ 不引入光墩墩形象资产（CC BY-NC，非商业限制，与项目 MIT 主许可冲突）。
- ❌ 不引入 UE 渲染端 / 像素串流（运维重、违背本地轻量渲染路线）。
- ✅ 只做**方法级逆向**：口型驱动参数、微表情粒度、唤醒/打断交互、状态机节奏——参数化提取，不复制代码与资产（与 `PLAN.md` §5 逆向管线同路）。

## 2. 硬约束修订（本方案经用户裁决 2026-11-14）

| 约束 | 修订前 | 修订后 |
| --- | --- | --- |
| 数字人路由 | 仅允许出现在 `/agent/persona`，不得进入 MainLayout 公共壳与控制台 | 主形态仍在 `/agent/persona`；**悬浮桌宠为用户显式开启的迷你形态，允许进入公共壳** |
| 工具表面 WebGL（MASTER.md 2026-11-12 双表面契约「no particles, no WebGL」） | 工具表面零 WebGL | 桌宠作为**唯一例外**：默认关闭、单实例、用户显式开启（先例：Dashboard balanced 档位下的鲸） |
| 同屏 WebGL 主体 ≤ 1 | 数字人与鲸路由级互斥 | 保持不变：**桌宠展开时 ParticleWhale 暂停渲染（让位）**；进入 `/agent/persona` 时桌宠自动收起 |

## 3. 形态与交互

```
控制台任意页面 ──► 头部「桌宠」开关（记住选择，localStorage）
                    │ 开启
                    ▼
        PersonaPet 浮窗（右下角默认位，可拖拽，位置记忆）
        ├─ 展开态：220×300，AgentPersona compact（VRM + 状态 + 口型）
        ├─ 收起态：约 44px 发光小球（呼吸光斑，延续生物发光语言）
        └─ 快捷动作：说话（Web Speech）、跳转 /agent/persona、收起/关闭
```

- 拖拽：Pointer Events，边界钳制在视口内；位置写入 localStorage。
- 路由联动：`/agent/persona` 激活时桌宠强制收起（同屏一个 WebGL 主体）；离开后恢复用户上次展开/收起状态。
- 与鲸互斥：桌宠展开（WebGL 活跃）期间鲸暂停渲染，桌宠关闭/收起后恢复。收起小球是纯 DOM/CSS，不算 WebGL 主体。

## 4. 状态与口型

- **状态**：复用 `personaStates.js` 七状态枚举，状态源与鲸/控制台一致（全局 agent 状态，不新造）。
- **口型**：`speechSynthesis` 播报文本；`utterance.onboundary`（Chrome/Edge 支持字符边界回调）驱动 `useLipSync` 文字时间线跳钟——口型跟随真实播报进度，而非独立定时器漂移。UI 如实标注「近似口型，非音素级同步」。
- **静默**：不说话时口型归零，只留眨眼与呼吸（沿用既有规则，不让模型半张嘴）。

## 5. 性能与降级（桌宠专属预算）

| 指标 | 预算 | 手段 |
| --- | --- | --- |
| canvas | 220×300、DPR 1（不随屏放大） | 桌宠专用容器 |
| 帧率 | 共享 `motionScheduler` 30fps（慢帧 15fps） | 复用 |
| 看门狗 | `frameBudget` 双门槛沿用；持续慢帧 → 自动收起为静态小球并提示 | 复用 |
| 上下文丢失 | 静态替身（复用 AgentPersona 现有降级文案） | 复用 |
| reduced-motion / 移动端 | 不加载 3D，桌宠退化为 2D 状态徽章（文字 + 色彩） | 复用 `isLightweightVisualMode` |

## 6. 形象主题化（切合深海 / 生物发光体系）

占位模型 sendagaya-shino（CC0，已核验）仅用于打通形态。**正式形象选型标准**：

| 维度 | 标准 |
| --- | --- |
| 色调 | 青蓝/深海色系（accent `#2496ED` / accent soft `#7AD7F5` 方向的服装、发色或配件），与登录水母的粉紫做区分 |
| 风格 | 低调科技感、生物发光气质；拒绝浓艳妆造与无关二次元风格 |
| 许可 | 仅 CC0 / MIT / CC-BY（保留署名）；走 `sources.json` + `acquire.mjs` + SHA256 + 许可原文快照既有管线 |
| 候选源 | VRoid Hub CC0 区、VRM Consortium 官方示例、Booth CC0 区（逐个读原始许可原文，不信徽章） |

选型作为独立阶段执行（P4），不阻塞 P1–P3。

## 7. 分阶段执行

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| P1 形态骨架 | PersonaPet 浮窗（拖拽/收起/位置记忆）、AgentPersona compact 接入、与鲸互斥、约束文档落地 | 开关→浮窗→拖拽→收起→关闭全链路可用；展开时鲸暂停 |
| P2 状态与口型 | 全局 agent 状态接线、Web Speech + boundary 口型、演示控制 | 说话时口型有起伏且跟随播报进度，停止后闭嘴 |
| P3 性能与降级 | 桌宠预算、看门狗联动、2D 徽章降级、测试补齐 | 慢帧自动收起；reduced-motion 不加载 3D |
| P4 正式形象 | 深海风 CC0 VRM 选型 + 入库管线 | `sources.json` 全项 SPDX + SHA256 + 许可原文快照 |

## 8. 验收清单

- [ ] 桌宠默认关闭；开启后鲸自动让位，同屏 WebGL 主体 ≤ 1；关闭后鲸恢复
- [ ] 进 `/agent/persona` 桌宠自动收起；10 次路由切换 WebGL context 数不增长
- [ ] 拖拽位置与展开/收起状态跨会话记忆
- [ ] `speechSynthesis` 说话时口型起伏、跟随 boundary 进度、结束后闭嘴；UI 标注「近似」
- [ ] 七状态在桌宠小窗内仍可辨识（表情/姿态为主，色彩仅强化）
- [ ] reduced-motion 与移动端（pointer: coarse）不加载 3D，退化为 2D 状态徽章
- [ ] 仓库内无任何 GMTalker 代码/资产落地
