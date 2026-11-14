# 智能体 3D 数字人形象 · 方案 v1

> 一句话：**不要扒别人的头像资产，要逆向别人的实现方法。**
> 形象用 CC0 自建（MPFB2 → VRM 1.0），渲染与驱动用 MIT 的 `@pixiv/three-vrm` 自己写，参考实现（ChatVRM）只读源码学做法。

| 项 | 值 |
| --- | --- |
| 宿主 | SmartOpsAgent（Vue 3 + `three ^0.186.0` 已在依赖里，`ParticleWhale.vue` 已用 three） |
| 范围 | ① 合规取得 3D 形象资产 ② 逆向参考实现拿到可复现规格 ③ 集成到本项目「生命体」体系 |
| 明确不做 | 提取/转存闭源或付费头像资产；绕过付费墙或授权；把带使用限制的模型再分发；抓取用户私人数据 |
| 交付物 | 本文件、`PROMPT.md`（交给执行模型）、`acquire.mjs` + `sources.json`（可审计抓取管线） |

---

## 1. 先说清楚「爬取」在这里指什么

「爬取 GitHub 上的智能体 3D 数字人」有两种完全不同的东西，混在一起会把项目做进版权坑：

| | 内容 | 许可状态 | 本方案 |
| --- | --- | --- | --- |
| **A. 模型资产** | `.vrm` / `.glb` / 贴图 / 骨骼动画 | 各仓库五花八门：CC0、有条件使用、保留所有权利 | **只取 CC0 或明确可再分发的**；其余一律不落地 |
| **B. 实现方法** | 加载管线、表情与口型驱动、相机/光照、性能策略 | 代码许可（MIT/Apache 居多） | **逆向读源码，自己重写**；不复制代码 |

结论：**A 走合规自建，B 走逆向学习**。这样既拿到同等效果，又不会因为一张脸让整个仓库有法律风险。

---

## 2. 形象选型（已经核查过许可，不用再猜）

### 2.1 推荐方案：Blender + MPFB2 自建 → 导出 VRM 1.0

| 理由 | 证据 |
| --- | --- |
| 资产 CC0，输出无限制 | [MPFB2 LICENSE](https://github.com/makehumancommunity/mpfb2/blob/master/LICENSE.md)：代码 GPLv3，**assets 全部 CC0 1.0**，并明确「导出的 FBX/OBJ/模型文件属于你的数据，不作任何主张」 |
| 形象可控，贴合项目调性 | 项目已有「深海 / 生物发光」语言（Whale、Jellyfish），数字人应延续这条线而不是塞一个通用二次元角色 |
| VRM 1.0 自带驱动所需的 blend shape | 表情 `happy/angry/sad/relaxed/surprised`、口型 `aa/ih/ou/ee/oh`、眨眼 `blink/blinkLeft/blinkRight` |
| 离线工具，不进前端仓库 | GPLv3 只约束「再分发 addon 代码」，我们只在自己机器上用 Blender 生成资产，不分发 addon |

**执行链路**：Blender 4.x + MPFB2 生成基础形体 → 雕刻/贴图（自有创作）→ 绑骨、加表情与口型 blendshape → 导出 glTF → 用 VRM Add-on for Blender 转 VRM 1.0 → 落到 `frontend/public/avatar/`。

> **实测提醒**：GitHub API 对 MPFB2 报的是 `NOASSERTION`（因为它把许可拆成 `LICENSE.md` / `LICENSE.CODE.md` / `LICENSE.ASSETS.md` 三份）。首次跑 `acquire.mjs` 时脚本已把这条不一致写进 `manifest.generated.json` 的 `warnings`。
> 结论：**GitHub 的 license 徽章不能当授权依据**，必须读仓库里的许可原文（已快照到 `license-snapshots/mpfb2.LICENSE.txt`）。

### 2.2 备选 / 占位：CC0 的 VRM 示例模型

先把管线跑通再换皮，用 **CC0 那批**，**不要**用 `AvatarSample_A/B/C`：

| 模型 | 许可 | 能不能用 |
| --- | --- | --- |
| `AvatarSample_A/B/C` | 保留版权，**有条件使用**（须逐条遵守 VRoid 条款） | ❌ 不作为默认形象；如要用，条款原文必须落 `reports/` 并过评审 |
| VRoid 的 **CC0** 示例模型 | CC0 | ✅ 可作占位，可编辑可分发 |
| `madjin/vrm-samples` | 只是搬运/索引仓库，**许可跟着原模型走** | ⚠️ 只能当索引用，落资产前回到原始许可 |

来源：[VRoid 官方说明（有条件使用 / CC0 两类）](https://vroid.pixiv.help/hc/en-us/articles/4402614652569)、[vrm-samples README](https://raw.githubusercontent.com/madjin/vrm-samples/master/README.md)

### 2.3 不选的路（写清楚原因，免得后面反复讨论）

| 方案 | 为什么不选 |
| --- | --- |
| Ready Player Me / 商业数字人 SDK | 商业条款 + 依赖外部服务，形象与推理都不在自己手里 |
| `makehumancommunity/makehuman` 仓库直取 | 仓库许可 `NOASSERTION`（代码 AGPL 系），资产 CC0 但边界要靠 MPFB2 的 LICENSE 才清楚；用 MPFB2 更干净 |
| `microsoft/Microsoft-Rocketbox` | 仓库已归档（2022），MIT 主要覆盖脚本/工具，模型资产的授权需单独确认，不适合当基础形象 |
| 直接抓某商业产品的数字人 | 侵权，不做 |

### 2.4 逆向目标（只学方法）

| 仓库 | 许可 | 学什么 |
| --- | --- | --- |
| [`pixiv/three-vrm`](https://github.com/pixiv/three-vrm) | MIT | VRM 加载、表情/口型/视线 API、`three-vrm-animation` 的动画混合 |
| [`pixiv/ChatVRM`](https://github.com/pixiv/ChatVRM) | MIT（已归档 2025-05） | 一句话→语音→口型同步的完整链路、Web Audio 振幅驱动嘴型、相机与光照参数 |
| [`sh-akira/VirtualMotionCapture`](https://github.com/sh-akira/VirtualMotionCapture) | MIT | 可选：摄像头驱动面部（本项目默认不做，避免采集摄像头） |

---

## 3. 合规门（不通过不许落地）

沿用 `design-system/MASTER.md` 的 Open Source Intake 分级，增加一条资产专属规则：

| 级别 | 条件 | 处理 |
| --- | --- | --- |
| **A** | MIT / Apache-2.0 / CC0 / CC-BY（保留署名） | 可进仓库，记录 SPDX + 核查日期 + 原始 URL |
| **B** | GPL / AGPL / LGPL | 只作**离线工具**使用（如 MPFB2），不进前端运行时、不与前端代码链接 |
| **C** | 保留所有权利 / 无许可证 / 条款含糊 | **禁止落地**。可在方案里引用 URL，不下载资产 |

资产专属规则：

1. **一张表管所有资产**：`sources.json` 记录每个资产的来源、SPDX、核查日期、SHA256、是否再分发。
2. **许可原文必须留存**：抓取时把 LICENSE / 条款页正文落到 `docs/design/agent-avatar-3d-v1/license-snapshots/`，不留原文等于没有证据。
3. **模型文件带出处**：每个 `.vrm`/`.glb` 同目录放 `<name>.LICENSE.txt` + `<name>.SOURCE.txt`（URL + 抓取时间 + SHA256）。
4. **有条件使用的资产默认拒绝**：需要人工过评审，评审结论写进 `reports/`，不能只写在提交信息里。

---

## 4. 「爬取」管线（可审计、可复现）

```
sources.json  ──►  acquire.mjs  ──►  inbox/  ──►  verify  ──►  frontend/public/avatar/
（人工审核的清单）    （拉取+取证）      （原始落盘）  （哈希/许可/尺寸）   （归一化后的成品）
```

**每一步都留证**：

| 步骤 | 做什么 | 产物 |
| --- | --- | --- |
| 1. 清单 | 人工确认来源与许可，写进 `sources.json`，`allow: false` 的一律不抓 | `sources.json` |
| 2. 拉取 | `acquire.mjs` 走 GitHub API 取仓库元数据（license/commit）、下载资产、抓许可原文 | `inbox/<source>/…`、`license-snapshots/` |
| 3. 取证 | 计算 SHA256、文件大小、glTF 校验（`gltf-validator`）、记录实际 commit sha | `manifest.generated.json` |
| 4. 归一化 | 缩放尺度（1 单位 = 1 米）、朝向（+Z 前）、贴图压缩（KTX2/Basis）、meshopt 顶点压缩、去掉无用动画 | `frontend/public/avatar/<name>/` |
| 5. 入库 | 只把 A 级成品拷进仓库；B 级工具只在本地 | PR + `reports/` 里的入库记录 |

**可复现性要求**：manifest 里必须固定到 **commit sha**，不能只记分支名——否则三个月后无法解释「当时抓的是哪一版」。

---

## 5. 「逆向」管线（拿规格，不拿代码）

目标：用 REA 把参考实现拆到「能自己重写」的粒度，产出**参数化规格**（数值、时序、结构），而不是复制粘贴源码。

| 对象 | 手段 | 产出 |
| --- | --- | --- |
| ChatVRM / three-vrm 的页面实现 | `capture_browser_scenario` 起本地实例，`analyze_web_bundle` 静态拆包 | 模块清单、渲染管线调用顺序、每帧执行的事 |
| 口型同步链路 | `observe_web_execution` 精确覆盖率 + `trace_javascript_semantics` 数据流 | 「音频振幅 → 5 个元音权重 → blend shape」的具体映射与阈值 |
| 相机 / 光照 / 后处理 | 静态读参数 + 截图对比 | 视场角、相机高度、三点光强度与色温、是否有 bloom |
| 性能策略 | `inspect_web_page` 看资源、`capture_process_scenario` 量帧时间 | 每帧 draw call、贴图总量、是否 LOD、是否按需渲染 |
| 动作混合 | 读 `three-vrm-animation` 的 API 用法 | 状态切换的淡入淡出时长、优先级、互斥规则 |

**红线**：只提取参数与算法思路，代码自己写；模型资产一律不用参考实现自带的（ChatVRM 里那个示例形象有它自己的条款）。

---

## 6. 集成规格（贴本项目约束）

### 6.1 定位：这是「第四个生命体」，不是装饰

项目已有语义层级（`design-system/MASTER.md`）：

| 生命体 | 语义 | 技术 |
| --- | --- | --- |
| Docker Whale | 基础设施本体 | WebGL 粒子 18k |
| Kubernetes Spider | 集群拓扑 | 程序化 SVG |
| Living Jellyfish | Agent 觉察 | 程序化 SVG |
| **数字人（新增）** | **Agent 的人格化身**：能说话、有表情、有视线 | VRM + three-vrm |

关键约束（逐条引证现网代码与设计母本，不是新增约定）：

| 约束 | 出处 | 对数字人的含义 |
| --- | --- | --- |
| 受保护 SPA 路由只允许一个 canvas 实例 | `design-system/MASTER.md`「Particle Whale」节：`Single canvas instance for protected SPA routes` | 数字人与鲸路由级互斥，共用同一个 canvas 容器 |
| 工具层默认不加载 WebGL 装饰；只有用户显式选择过 `balanced` 档位、且当前路由为 `Dashboard` 时才启用增强层 | `frontend/src/layouts/MainLayout.vue` 的 P0/P3 视觉预算注释 + `showEnhancedHomeVisuals` 计算属性 | 数字人**不挂** `MainLayout` 公共壳，只在专属路由挂载；不能做成全局装饰 |

> 注意：控制台并非「绝对零 WebGL」——用户在 Dashboard 显式选过 balanced 时，鲸自身会加载 WebGL。因此本方案的可验收口径是「同屏 WebGL 主体 ≤ 1 + 数字人只在自己的路由」，而不是「控制台搜不到 WebGL」。

### 6.2 与粒子鲸的 GPU 互斥（硬规则）

| 规则 | 做法 |
| --- | --- |
| 同屏最多 1 个 WebGL 主体 | 路由级互斥：进数字人页时销毁 Whale 的 renderer 与 geometry，返回时重建 |
| 复用同一个 canvas 容器 | 用一个 `WebGLHost` 组件挂载/卸载，不在两个组件里各建 context |
| context 丢失要能恢复 | 监听 `webglcontextlost/restored`，丢上下文时降级为静态立绘 + 一行提示，不白屏 |
| 移动端不默认启用 | `matchMedia('(pointer: coarse)')` 或低端设备 → 默认静态立绘，用户可手动开启 |

### 6.3 状态映射（7 状态 → 表情/姿态/口型）

沿用 `ParticleWhale` 已有的状态枚举，不新造一套：

| 状态 | 表情 | 姿态/视线 | 附加 |
| --- | --- | --- | --- |
| `idle` | `relaxed` | 呼吸循环 + 缓慢眨眼 + 视线游移 | 发丝/衣摆微动 |
| `thinking` | `relaxed` + 眉微皱 | 视线偏离镜头、头微侧 | 呼吸变浅变快 |
| `executing` | `relaxed`（专注） | 正视镜头，点头节奏化 | 说话时口型同步 |
| `observing` | `neutral` | 视线跟随数据面板方向 | — |
| `warning` | `surprised` | 头微仰、身体后倾 | 琥珀色环境光微增 |
| `error` | `sad` | 低头、视线下垂 | 红色描边/环境光，**不使用**粒子爆炸 |
| `recovering` | `relaxed` → 复位 | 姿态缓慢回到 idle | 过渡 1.2s，不跳变 |

过渡规则：状态切换用 `crossFadeTo(0.35s)`；`error → recovering` 单独 1.2s；任何状态切换不得打断正在播放的口型。

### 6.4 口型与语音

- 有 TTS 音频时：`AnalyserNode` 取 RMS → 映射到 `aa/ih/ou/ee/oh` 权重（参考 ChatVRM 的做法，阈值与平滑系数自己标定）。
- 无音频、但 agent 正在「说」文字时：按字符推送的时间戳做**近似口型**（每字 60–120ms），明确标注为近似，不是真同步。
- 不说话时：口型权重归零，只保留眨眼与呼吸——**不要**让模型一直半张嘴。

### 6.5 性能预算（每条都要能量出来）

| 指标 | 预算 | 测量方式 |
| --- | --- | --- |
| 首帧可见 | ≤ 1.2s（3 Mbps 冷缓存） | Chrome Performance，`first-contentful-paint` → 模型首帧 |
| 模型体积 | ≤ 6 MB（含贴图），KTX2 压缩后 | `du` + 网络面板 |
| 稳态帧时 | ≤ 8ms（120Hz 设备）/ ≤ 14ms（60Hz） | `motionScheduler` 已有 30fps 默认、慢帧降 15fps，直接复用 |
| draw call | ≤ 12 | `renderer.info.render.calls` |
| 常驻内存 | ≤ 180 MB（模型 + 贴图解码后） | `performance.memory` / DevTools Memory |
| 降级路径 | 帧时连续 2s > 20ms → 关阴影、降贴图、停发丝物理 | 与 Whale 相同的降级策略 |

**所有数字必须写基线**（测量设备、分辨率、Chrome 版本），沿用项目「证据优先」的规矩。

### 6.6 无障碍

- `prefers-reduced-motion`：不渲染 3D，改静态立绘（PNG/WebP），状态仍由文字 + 角标表达。
- 数字人**不是**唯一信息通道：所有状态文字必须同时在 DOM 里。
- 提供「关闭形象」开关，记住选择。
- 不用摄像头（默认不做面部捕捉）；若未来要做，必须显式授权 + 本地处理 + 可随时关闭。

---

## 7. 目录与接口契约

```
frontend/public/avatar/<name>/
  model.vrm                  归一化后的形象（含 A/LICENSE.txt + A/SOURCE.txt）
  textures/*.ktx2
  poster.webp                静态降级图

frontend/src/components/persona/
  AgentPersona.vue           ← 对外唯一入口：props 收状态，内部管 WebGL 生命周期
  useVrmModel.js             ← 加载/释放/表情/口型（纯逻辑，可单测）
  useLipSync.js              ← 音频振幅 → 元音权重
  personaStates.js           ← 状态 → 表情/姿态映射表（纯数据，可单测）
  WebGLHost.vue              ← 与 Whale 共享的唯一 canvas 容器
```

```js
// AgentPersona.vue
props: {
  state: { type: String, default: 'idle' },   // idle|thinking|executing|observing|warning|error|recovering
  audioEl: { type: Object, default: null },   // 有 TTS 音频时传 <audio>
  speechText: { type: String, default: '' },  // 无音频时的近似口型
  quality: { type: String, default: 'auto' }  // auto|high|low|static
}
emits: ['ready', 'error', 'context-lost']
```

约束：`AgentPersona` **不自己取数据**、不发请求、不读 store；状态由父层传入。这样它可以在任何页面复用，也能单独做截图回归。

---

## 8. 验收清单

- [ ] `sources.json` 里每个资产都有 SPDX、核查日期、原始 URL、SHA256；`allow: false` 的一个都没落地
- [ ] 仓库里搜不到 `AvatarSample_A/B/C` 或任何「有条件使用」资产
- [ ] 模型目录里有 `LICENSE.txt` + `SOURCE.txt`，SHA256 与 manifest 一致
- [ ] 七个状态都能触发，且**不看颜色**也能从表情/姿态分辨
- [ ] `error → recovering` 平滑，无跳变
- [ ] 有音频时口型跟随，无音频时近似口型且不说话时闭嘴
- [ ] 数字人页与 Whale **不同屏**；切换路由无 WebGL context 泄漏（DevTools 里 context 数不增长）
- [ ] 丢上下文时降级为静态图 + 提示，不白屏
- [ ] `prefers-reduced-motion` 下不加载 3D
- [ ] 6 项性能预算逐条给出测量值与基线
- [ ] `.vrm` 请求只出现在 `/agent/persona`；离开该路由后 avatar 的 renderer / geometry / texture 全部 dispose，WebGL context 数回到基线
- [ ] 同屏 WebGL 主体数 ≤ 1（数字人与鲸互斥）；不要求控制台「零 WebGL」——Dashboard 在 balanced 档位下鲸自身会加载 WebGL

---

## 9. 风险与红线

| 风险 | 处置 |
| --- | --- |
| 形象丑/不可用，返工 | 先用 CC0 占位模型跑通全链路，形象单独迭代，**解耦** |
| 授权踩坑 | 合规门 + 许可快照；有条件使用的默认拒绝；分支上不许出现来路不明的 `.vrm` |
| 与 Whale 抢 GPU | 路由级互斥 + 单 canvas + 降级路径 |
| 3D 变成性能债 | 预算是硬指标，超了先降级再谈效果 |
| 被当成「扒站」 | 只抓公开仓库、只取 CC0/MIT、留证可追溯；不碰用户数据、不碰闭源资产 |
| 数字人抢走注意力 | 它是「人格化身」，默认在专属路由；控制台不出现 |

---

## 10. 与上次交付的关系

知识审核那套设计已经有人落地了（工作区里已有 `views/knowledge/reviewGraph/` 五个文件 + 测试）。本方案与那条线**互不影响**：一个改审核工作台，一个加形象层。唯一交叉点是「同屏只能有一个 WebGL 主体」这条规则，两边都要遵守。
