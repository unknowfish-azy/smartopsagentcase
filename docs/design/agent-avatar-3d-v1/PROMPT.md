# 执行提示词：给 SmartOpsAgent 加一个 3D 数字人形象

把下面整段发给 Trae（或任何能跑命令、能读写本仓库的模型）。它要求仓库里已有 `docs/design/agent-avatar-3d-v1/`。

---

## 你的任务

给 SmartOpsAgent 的 Agent 加一个 3D 数字人形象：**能加载、有表情、会说话、会跟随 Agent 状态变化**，视觉语言延续项目已有的深海 / 生物发光体系。

**先调研、再计划、后实现。** 第一步不要写代码，只输出：合规核查结论 + 选型结论 + 分阶段计划。等我确认后再动手。

## 开工前必读

| 文件 | 从中拿到 |
| --- | --- |
| `docs/design/agent-avatar-3d-v1/PLAN.md` | 全案：合规门、选型、爬取管线、逆向管线、集成规格、性能预算、验收清单 |
| `docs/design/agent-avatar-3d-v1/sources.json` | 已人工审核的抓取清单（含 `allow` 开关） |
| `docs/design/agent-avatar-3d-v1/acquire.mjs` | 可审计抓取脚本（拉元数据 + 许可原文 + SHA256） |
| `design-system/MASTER.md` | 生命体语义、单 canvas 约束（`Single canvas instance for protected SPA routes`）、性能与无障碍口径 |
| `frontend/src/layouts/MainLayout.vue` | 工具层视觉预算的真实口径：默认不加载 WebGL 装饰，仅 `Dashboard` + 用户显式选过 `balanced` 才启用增强层 |
| `frontend/src/components/common/ParticleWhale.vue` | 现有的 three.js 用法、`motionScheduler`、降级策略——**照它的风格写**，不要另起一套 |
| `frontend/src/visual/motionScheduler.js` | 共用的 rAF 调度器，30fps 默认、慢帧降 15fps、离屏暂停 |
| `frontend/src/assets/styles/variables.css` | `--smart-*` / `--ds-*` 令牌 |

## 红线（违反即不算完成）

1. **不许把「有条件使用」的模型放进仓库**。具体：`AvatarSample_A/B/C` 及任何「保留版权 + 使用条款」的资产一律不得落地。只允许 CC0 / MIT / Apache-2.0。
2. **不许复制参考实现（ChatVRM / three-vrm）的模型资产**。它们的示例形象有自己的条款。只学做法（参数、时序、算法思路），代码自己写。
3. **不许把数字人做成全局装饰**。只在专属路由（建议 `/agent/persona`）挂载，不得进 `MainLayout` 公共壳。工具层「默认不加载 WebGL 装饰」是现有口径（`MainLayout.vue` 的 P0/P3 注释），不要借这次放宽；但也不要把它写成「控制台绝对零 WebGL」——`Dashboard` + 显式 balanced 档位下鲸本来就会加载 WebGL。
4. **同屏只能有一个 WebGL 主体**。数字人与 `ParticleWhale` 路由级互斥，共用一个 canvas 容器。
5. **不许新增未登记依赖**。`three@^0.186.0` 已有；新增 `@pixiv/three-vrm` 前先查许可（MIT）并在 PR 里写 SPDX + 核查日期。
6. **不许用摄像头**。不做面部捕捉；如果坚持要做，先停下来问我。
7. **每个资产都要有出处**：`LICENSE.txt` + `SOURCE.txt`（URL、抓取时间、SHA256）。缺一个就当没做。
8. `prefers-reduced-motion` 或低端设备：**不加载 3D**，用静态立绘 + 文字状态。

## 分阶段执行（每阶段结束等我确认）

### 阶段 1：合规与选型（不写业务代码）

- 跑 `node docs/design/agent-avatar-3d-v1/acquire.mjs --dry-run`，核对 `sources.json` 里每条来源的许可。
- 产出 `docs/design/agent-avatar-3d-v1/INTAKE.md`：每个候选源的 SPDX、核查日期、能不能用、备选取舍理由。
- 结论必须明确回答：**用 CC0 占位模型先跑通，还是直接做自建形象？**（推荐前者）
- 验收：`INTAKE.md` 里没有任何「未确认许可」的资产被标为可用。

### 阶段 2：打通加载（一条最小链路）

- 新增 `components/persona/AgentPersona.vue` + `useVrmModel.js` + `WebGLHost.vue`。
- 用一个 CC0 占位 `.vrm` 跑通：加载 → 站立 → 呼吸 + 眨眼 → 释放（`dispose` 干净，无纹理泄漏）。
- 接到一个**专属路由**（建议 `/agent/persona`），不碰控制台。
- 验收：进出该路由 10 次，DevTools 里 WebGL context 数量不增长；`renderer.info` 显示几何与纹理都被释放。

### 阶段 3：状态与表情

- 写 `personaStates.js`：七个状态（`idle/thinking/executing/observing/warning/error/recovering`）→ 表情 + 姿态 + 视线 + 附加效果，纯数据表。
- 状态切换 `crossFadeTo(0.35s)`；`error → recovering` 用 1.2s。
- 验收：七个状态逐个截图；把截图转灰度后仍能分辨状态（说明不是靠颜色）。

### 阶段 4：口型与语音

- `useLipSync.js`：有 `<audio>` 时用 `AnalyserNode` 振幅 → `aa/ih/ou/ee/oh` 权重，自己做平滑（建议 60–120ms 时间常数，实测调）。
- 无音频只有文字时：按字推送时间戳做近似口型，**UI 上不要暗示这是真同步**。
- 不说话时口型归零。
- 验收：给一段 10 秒音频，录屏确认嘴型有起伏且停下后闭嘴。

### 阶段 5：性能与降级

- 逐条测 PLAN §6.5 的 6 项预算，写进 `docs/design/agent-avatar-3d-v1/PERF.md`：**测量设备、分辨率、Chrome 版本、前后对比**。
- 实现两条降级：① 帧时连续 2s > 20ms → 关阴影、降贴图；② `webglcontextlost` → 静态立绘 + 提示。
- 验收：手动触发 `WEBGL_lose_context` 扩展，页面不白屏。

## 逆向部分怎么做（阶段 2 之前可并行）

参考实现是 MIT 的 `pixiv/ChatVRM`（已归档）与 `pixiv/three-vrm`。用 REA 拿规格而不是抄代码：

1. 本地起 ChatVRM（`npm i && npm run dev`），`list_browser_targets` → `analyze_web_bundle` 看它怎么组织 VRM 加载与口型。
2. `observe_web_execution` 在「说一句话」的窗口里看哪些函数真的跑了（别信名字，信覆盖率）。
3. `trace_javascript_semantics` 从音频节点追到 blend shape 写入，拿到映射与阈值。
4. `capture_web_screenshot` 截图量相机/光照观感，反推 FOV、相机高度、主光方向。
5. 把结论写进 `docs/design/agent-avatar-3d-v1/REVERSE.md`：**参数表 + 时序图**，不贴对方源码。

## 交付格式

1. 改动文件清单 + 每个文件一句话作用
2. `INTAKE.md`（合规结论）、`REVERSE.md`（逆向参数）、`PERF.md`（性能实测）
3. 七状态截图 + 灰度版对照
4. 口型录屏（或 3 张关键帧）
5. 自检：PLAN §8 验收清单逐条打勾，未通过的写明原因
6. 风险与已知限制（例如移动端默认关闭、近似口型的精度边界）

## 一句话判据

如果明天有人问「这个数字人的脸是哪来的、能不能商用」，你应该能在 30 秒内翻到 `sources.json` 里那一行 + 许可快照 + SHA256。做不到，就是没做完。
