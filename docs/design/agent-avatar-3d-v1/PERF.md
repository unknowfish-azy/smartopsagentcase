# 智能体数字人 · 性能实测（阶段 5）

> 结论先行：**稳态帧时、内存、两条降级路径全部达标**；首帧、模型体积、draw call 三项**未达标，原因全部来自 CC0 占位模型本身**（15,074,328 B / VRM 0.x / 17 材质），已在 INTAKE §4 附条件放行。生产模型（KTX2 + Draco + 合并材质）必须在上线前把这三项补测到预算内。

## 1. 测量环境

| 项 | 值 |
| --- | --- |
| 设备 | Intel(R) UHD Graphics（ANGLE / D3D11），32 逻辑核，16 GB 内存 |
| 系统 / 浏览器 | Windows 10/11，Edge 157.0.4341.46（Chromium 157） |
| 视口 / 屏幕 | 1280 × 900，DPR 1 |
| 页面 | `/agent/persona`（Vite dev server，localhost） |
| 模型 | `avatar/sendagaya-shino/model.vrm`，15,074,328 B，SHA256 `1e177c1a…ca49b5` |
| 缓存 | 全新浏览器配置（冷缓存） |

> 局限：后端与前端都在本机，模型传输耗时 421 ms，**未模拟 PLAN 假设的 3 Mbps 弱网**；首帧里的网络部分只能作为下限参考。

## 2. 测量方法

- 首帧：`createVrmStage` 起算到第一帧真正 `renderer.render` 完成，取 `performance.now()`（相对 navigationStart）。
- 稳态帧时：渲染循环内 `performance.now()` 包住「姿态/表情/口型更新 + `vrm.update` + `render`」，环形缓冲保留最近 90 帧（30 fps ≈ 3 s），取 P50 / P90；偶发峰值单独记录、不计入稳态。
- 采样：首帧完成后预热 10 s，再每秒读一次遥测，共 6 次，确认数值稳定。
- 降级触发：CDP `Emulation.setCPUThrottlingRate = 10` 制造慢帧，读取降级标记。
- 上下文丢失：对舞台 canvas 调用 `WEBGL_lose_context.loseContext()`，1.5 s 后检查页面。
- 遥测来源：`/agent/persona` 的指标面板（每秒轮询 `readStats()`），数值与浏览器内一致。

## 3. 六项预算

| # | 预算 | 实测 | 结论 |
| --- | --- | --- | --- |
| 1 | 首帧可见 ≤ 1.2 s | **3140 ms**（其中 FCP 1596 ms、模型传输 421 ms） | 未达 · 占位模型例外 |
| 2 | 模型体积 ≤ 6 MB（KTX2） | **14.4 MB**（15,074,328 B，未压缩 VRM 0.x） | 未达 · 占位模型例外 |
| 3 | 稳态帧时 ≤ 8 ms（120 Hz）/ ≤ 14 ms（60 Hz） | **P50 1.2 ms / P90 1.4 ms** | 通过 |
| 4 | draw call ≤ 12 | **77**（几何 67 / 贴图 41） | 未达 · 占位模型例外 |
| 5 | 常驻内存 ≤ 180 MB | **JS 堆 57.6–62.1 MB**（整页含框架约 83 MB） | 通过 |
| 6 | 降级路径可用 | 帧时连续 2 s > 20 ms 自动降级；`webglcontextlost` 降静态替身 | 通过 |

### 3.1 三项未达标的归因与解除条件

| 项 | 归因 | 解除条件（生产模型） |
| --- | --- | --- |
| 首帧 3140 ms | 15 MB 未压缩 VRM 的下载 + 解析 + 贴图上传，占位模型远超 6 MB | 换成 KTX2 压缩贴图 + Draco/meshopt 的 ≤6 MB VRM 1.0，冷缓存首帧复测 ≤1.2 s |
| 模型 14.4 MB | CC0 占位模型是 VRoid 官方 2020 年示例，未做任何压缩 | 同上；入库门槛见 INTAKE §6 |
| draw call 77 | 17 个材质 → 77 次 draw call，占位模型不满足「合并材质」要求 | 生产模型合并到 ≤12 个材质/子网格后复测 |

> 这三项**不是代码侧可修**的问题：渲染器只画模型给的内容。占位模型的作用是跑通链路与验收状态/口型/降级，不承担预算验收。

## 4. 低端机复测（软件渲染 + DPR 2 代理）

没有第二台低端设备，用可复现的最坏情况代理：`--disable-gpu --enable-unsafe-swiftshader` 强制 SwiftShader 软件渲染，`deviceScaleFactor = 2`，1280×900 视口。GPU 自证：

```
ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)
```

| 指标 | 结果 |
| --- | --- |
| 首帧 | **1201 ms**（FCP 416 ms；同一环境三次采样为 908 / 1036 / 1201 ms，早期冷启动另有一次 3351 ms） |
| 稳态帧时 P50 / P90 | **1.5 / 2.0 ms**（降级前，DPR 2） |
| 降级触发耗时 | 页面进入渲染约 **3.7 s 后**自动触发 |
| 降级后像素比 | 2 → **1** |
| 降级前实际帧率 | **10.4 fps**（同一代理、同一代码路径的上一轮实测） |
| 降级后实际帧率 | **19.9 fps**（4 s 采样） |
| 降级后画面 | 模型完整、贴图无黑块（`lowend-after.png` 已核对） |
| console 报错 | 无 |

### 4.1 这轮复测改掉的一个判断缺陷

第一版看门狗只量「CPU 端提交耗时」，软件渲染下该值只有 1.5 ms，页面实际却只有 10 fps——**GPU/合成器端的慢完全没有被感知，降级永远不会触发**。

现在两条门槛并行，任一连续 2 s 成立即降级：

1. CPU 端单帧成本 > 20 ms；
2. 实际帧间隔 ≥ 60 ms（约低于 16 fps）。

第二条正是低端机的真实瓶颈。触发后像素比 2 → 1，帧率从 10.4 fps 提到 19.9 fps，是这次低端复测里唯一可量化的收益。

同一轮真机验收脚本的自测又暴露出第二个漏洞：`motionScheduler` 回调传入的是「相邻 rAF 的间隔」，而调度器会跳帧——GPU 瓶颈下 rAF 仍是 16 ms，实际只渲染 15 fps，第二门槛因此同样不会触发。现在 dt 与看门狗统一改用「两次真正渲染之间的间隔」；顺带修正了跳帧时动画会变慢的问题（此前 dt 也跟着 rAF 间隔走）。

## 5. 降级前后对比（硬件机 + 低端代理）

| 指标 | 硬件机（Intel UHD，DPR 1） | 低端代理（SwiftShader，DPR 2） |
| --- | --- | --- |
| 触发方式 | CPU 10× 节流 | 软渲染自然触发（3.7 s） |
| 帧时 P50 / P90 | 1.2 / 1.4 → 1.2 / 1.6 ms | 1.5 / 2.0 → 1.4 / 1.7 ms |
| 实际帧率 | 未测（稳定 30 fps 调度） | 10.4 → **19.9 fps** |
| 像素比 | 1 → 1（DPR 1 无可降空间） | 2 → **1** |
| draw call / 贴图 / 几何 | 77 / 41 / 67（不变） | 77 / 41 / 67（不变） |

**怎么读**：硬件机上 CPU 节流会同时拖慢 JS，数值只能证明链路被触发；低端代理下才是真实收益——渲染像素数减半带来约 2× 帧率。draw call 不变，因为降级不改模型几何，只改渲染成本。

另有一条全页约束要知道：`motionScheduler` 连续 3 帧超过 50 ms 后会把所有订阅者限到 15 fps，且不再恢复。真机脚本在这种状态下把「渲染帧率」记为 `EXEMPT`，避免把共享调度器的钳制误判成 GPU 能力。

降级具体动作（`useVrmModel.js` 的 `degrade()`）：

1. `renderer.shadowMap.enabled = false`（当前场景未开阴影，留作后续）；
2. `renderer.setPixelRatio(1)`，分辨率回 1x；
3. 全部贴图 `anisotropy = 1`、`minFilter = LinearFilter`（关多级渐远）；
4. `springBoneManager.update` 置空，停发丝/裙摆解算。

## 6. 上下文丢失验收

| 检查 | 结果 |
| --- | --- |
| 手动 `loseContext()` 是否可调用 | 是（`WEBGL_lose_context` 可用） |
| 1.5 s 后页面是否白屏 | **否**，正文非空 |
| WebGL canvas 数量 | 0（已销毁） |
| 静态替身是否出现 | 是，文案「WebGL 上下文丢失，已降级为静态替身」 |
| console 报错 | 无 |

## 7. 复现步骤

1. `npm run dev`（frontend，5173）。
2. 打开 `/agent/persona`，等指标面板出现「首帧」后预热 10 s。
3. 读数：面板里的 Draw call / 帧时 P50·P90 / 首帧 / 模型传输 / JS 堆 / 降级。
4. 触发降级：DevTools → Performance 面板开 6× 以上 CPU 节流，等 2 s 以上，看「降级」变为「已降级（慢帧持续 2s）」。
5. 复现低端：以 `--disable-gpu --enable-unsafe-swiftshader` 启动浏览器（DSF 2），约 4 s 后同上自动降级，像素比回落 1。
6. 触发上下文丢失：控制台执行
   `document.querySelector('.webgl-host__canvas').getContext('webgl2').getExtension('WEBGL_lose_context').loseContext()`。

### 7.1 真机验收脚本

`npm run persona:device`（在 `frontend/`）会起一个只加载验收页的 Vite 服务并打印局域网地址；真机与开发机处于同一网段，用手机浏览器打开即可，约 20–40 s 出结果。

| 文件 | 作用 |
| --- | --- |
| [persona-device-acceptance.mjs](file:///d:/SmartOpsAgent/frontend/test/persona-device-acceptance.mjs) | runner：起服务、接收回传、写 `.runtime/persona-device-<时间戳>/device-report.json`，硬性项失败退出码 1 |
| [persona-device-acceptance.html](file:///d:/SmartOpsAgent/frontend/test/persona-device-acceptance.html) | 手机上的验收页：进度、结论表、原始 JSON |
| [persona-device-harness.js](file:///d:/SmartOpsAgent/frontend/test/persona-device-harness.js) | 直接挂载生产同款 `createVrmStage`，采首帧 / 帧时 / 真实渲染帧率 / 降级 / 上下文丢失 |

三点边界：

- `AgentPersona` 对 `pointer: coarse` 默认退回静态替身（移动端设计如此），所以真机走的是本页的渲染链路验收，**不代表手机端的默认产品行为**。
- 真实渲染帧率取自 `stage.stats().frames` 的增量，不是 rAF 间隔；共享调度器已限到 15 fps 时该值会被钳制，脚本记 `EXEMPT` 而不判失败。
- 调试可加 `?warmup=1500&steady=2500&degrade=3000&after=1500` 缩短窗口，runner 会提示「不能作为正式验收结论」。

## 8. 与阶段 1–4 的关系

- 同屏 WebGL 主体仍为 1：丢失上下文后 `.webgl-host__canvas` 归零，2D 鲸不受影响。
- 口型/状态动画都在帧时 P90 1.4 ms 内完成，未突破预算。
- 遥测面板是验收工具，不是产品功能；后续接入真实编排时可按需下线。
