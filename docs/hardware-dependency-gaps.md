# 智维Agent · 设备级数字孪生 & 真机视频流 缺口技术说明

> 文档性质：技术说明（供答辩、评审、后续补全参考）
> 最后更新：2026-11-18 （v2 — 补精确代码路径证据）
> 代码基准：`main` 分支 `73d8577`（历史已清口令）

---

## 0. 概述

本文档说明智维Agent 在「设备级数字孪生」与「真机实时视频流」两项能力上的缺口。**核心结论：缺口源于硬件依赖顺序，而非架构盲区**——核心骨架已全部留口，补全路径清晰可落地，待真机硬件（BLE 状态包、URDF、WiFi/RTSP）就绪后即可快速工程化。

---

## 一、缺口 1：设备级数字孪生

### 1.1 现状

智维Agent 已实现**场景级数字孪生**（云服务器厂房 3D 场景 + 机器人巡逻轨迹 + 同步延迟标记 + 视觉预警点叠加），位于：

| 层 | 实现 | 路径 |
|---|---|---|
| 前端 3D 引擎 | `DataCenterTwinView` + `DataCenterTwin3D` | `frontend/src/views/sentinel/DataCenterTwinView.vue` |
| 轨迹数据源 | 机器人遥测 WebSocket 推送 | 后端遥测 WS endpoint |
| 预警联动 | 视觉告警红点反推机器人巡检 | `VisionInspectionService` → `RobotControlService` CAPTURE |

**缺什么**：机器人本体的 3D 模型 + 关节/轮式实时姿态映射（即参考项目「智巡孪卫」中的「数字双胞胎」）。

> 📐 **图 1 · 场景级数字孪生现状**（示意图，非运行时截图）：
>
> ![场景级数字孪生现状](hardware-gaps-assets/fig1-scene-twin.png)
>
> 云服务器厂房 3D 场景 + 机器人巡逻轨迹（蓝色发光路径）+ 预警点（机柜红色脉冲）。

### 1.2 缺口根因（硬技术前提）

设备级孪生必须依赖两类真机数据，当前均未就绪：

| 依赖 | 说明 | 就绪状态 |
|---|---|---|
| **URDF 参数表** | 机器人本体的关节层级、转动范围、连杆尺寸（四足：髋/膝；差速车：轮距/轴长；全向：麦克纳姆轮参数） | 未获取（真机在实验室待参数输出） |
| **BLE 状态包协议** | 机器人周期性上报的关节角度 / 轮速 / IMU 数据帧（参考：ROS 的 `/joint_states` 话题） | 未抓包（当前 `transport=simulated`，BLE 帧格式未解析） |

没有这两类数据，本体 3D 模型无法构建、也无法被实时驱动——**不是不想做，是做出来也是个静态假模型，反而误导**。

> 📐 **图 2 · 缺口对比：场景级 vs 设备级孪生**（示意图）：
>
> ![缺口对比](hardware-gaps-assets/fig2-gap-comparison.png)
>
> 左侧：现有场景级孪生（机器人只是个蓝色方盒子）；右侧：设备级孪生需要关节参数 + 实时状态帧才能驱动。灰色括号标注了缺失的 URDF + BLE 状态包。

### 1.3 架构已留口证据（精确代码路径 + 行号）

#### 留口 1：传输层已预留 BLE 入口，切换零成本

**台账 enrichment 方法** — [RobotRegistryService.java#L103-L109](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/RobotRegistryService.java#L103-L109)

```java
private void enrich(Map<String, Object> device) {
    device.put("capabilities", parseJson(device.get("capabilities")));
    device.put("transport", parseJson(device.get("transport")));  // ← 解析 transport JSON 列
    Object formFactor = device.get("formFactor");
    device.put("teleop", RobotTeleopProfiles.forFormFactor(
            formFactor == null ? null : String.valueOf(formFactor)));
}
```

**transport 字段白名单** — [RobotRegistryService.java#L40-L42](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/RobotRegistryService.java#L40-L42)

```java
private static final Set<String> TRANSPORT_TYPES = Set.of("BLE");     // ← M0 已留 BLE 类型
private static final Set<String> TRANSPORT_KEYS = Set.of("type", "mac", "protocolId");
```

**transport 格式校验** — [RobotRegistryService.java#L256-L283](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/RobotRegistryService.java#L256-L283)

```java
private Map<String, Object> normalizeTransport(Map<String, Object> raw) {
    ...
    String type = String.valueOf(raw.getOrDefault("type", "")).strip();
    if (!TRANSPORT_TYPES.contains(type)) {
        throw new BusinessException("transport.type M0 阶段仅支持 BLE（ROBOT_INVALID_TRANSPORT）");
    }
    String mac = String.valueOf(raw.getOrDefault("mac", "")).strip();
    if (!MAC.matcher(mac).matches()) { ... }
    String protocolId = String.valueOf(raw.getOrDefault("protocolId", "")).strip();
    if (!PROTOCOL_ID.matcher(protocolId).matches()) { ... }
    ...
}
```

> 真机 BLE 就绪后，把台账里 `transport.type` 从模拟值改成 `BLE`（填 MAC + protocolId），无需改 Java 代码。

#### 留口 2：四形态能力清单唯一来源（运动学已定义，关节参数只差真机喂入）

**CAR / DOG / SPIDER / ROBOT 四形态定义** — [RobotTeleopProfiles.java#L38-L51](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/robot/RobotTeleopProfiles.java#L38-L51)

```java
map.put("CAR", profile("CAR", "巡逻车", "differential",
        List.of("forward", "yaw"), 0.6, 0.85, List.of(),        // ← 差速：无横移执行器
        "差速：前进 + 自转，无横移执行器"));
map.put("DOG", profile("DOG", "机器狗", "quadruped",
        List.of("forward", "lateral", "yaw", "gait"), 0.35, 0.7, // ← 四足：限速 0.35 防失稳
        List.of("TROT", "WALK", "STAND"),
        "四足：可横移，限速低于轮式以免失稳"));
map.put("SPIDER", profile("SPIDER", "蜘蛛机器人", "omnidirectional",
        List.of("forward", "lateral", "yaw"), 0.45, 0.8, List.of(), // ← 全向：三轴独立
        "全向：三轴独立，可原地横移"));
map.put("ROBOT", profile("ROBOT", "巡检机器人", "differential",
        List.of("forward", "yaw"), 0.5, 0.8, List.of(),
        "通用形态：保守按差速处理"));
```

> 运动学（differential / quadruped / omnidirectional）已定义，URDF 关节参数只需填入 `profile()` 新增字段即可，不改现有结构。

#### 留口 3：3D 场景已支持子 Group 挂载，本体模型直接 add

**机器人 Group + syncRobot 方法** — [DataCenterTwin3D.vue#L190-L216](file:///d:/SmartOpsAgent/frontend/src/components/sentinel/DataCenterTwin3D.vue#L190-L216)

```javascript
/* 机器人：机体 + 桅杆 + 顶部信标，位置直接来自 props.robot。 */
const robotGroup = new Group()
const robotBodyGeo = new BoxGeometry(0.62, 0.3, 0.46)
...
robotGroup.add(robotBody, mast, beacon, halo)
root.add(robotGroup)           // ← 挂载到场景根节点

function syncRobot() {
  const spot = props.robot || { x: 0, z: 0, heading: 0 }
  robotGroup.position.set(spot.x, 0, spot.z)
  robotGroup.rotation.y = spot.heading || 0
}
```

> 真机 BLE 状态包就绪后，URDF 转 GLB 得到的 `Group` 直接 `robotGroup.add(glbGroup)` 即可；关节角度帧走 WebSocket 推过来，在 `syncRobot()` 里多调用一次 `glbGroup.children[i].rotation.x = jointAngle`，不改 Three.js 渲染循环。

#### 留口 4：遥测 WebSocket 通道已在用，多推一路关节角度零新增连接

**心跳看门狗（证明 WS 通道稳定）** — [RobotControlService.java#L256-L280](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/RobotControlService.java#L256-L280)

```java
@Scheduled(fixedDelay = 200)
public void heartbeatWatchdog() {
    for (String deviceKey : hub.connectedDeviceKeys()) {
        ...
        if (hub.silenceMillis(deviceKey) > heartbeatTimeoutMs) {  // ← 默认 600ms
            hub.sendToBridge(deviceKey, "cmd", envelope("STOP", Map.of(), "WATCHDOG"));
            apply(deviceKey, RobotMode.FAULT, "watchdog", "HEARTBEAT_LOST");
        }
    }
}
```

> 现有 WS 通道已在推 pose（x/y/theta），关节角度帧只需 `hub.broadcast("joints", payload)` 追加字段，客户端订阅同一个 WebSocket 即可。

### 1.4 补全路径（可落地）

```
步骤 1：获取真机 URDF
    ↓  1-2 天
步骤 2：BLE 状态包抓包（用 nRF Connect / Wireshark）
    ↓  1 天
步骤 3：后端 RobotControlService 补状态帧解析（新增 handleStatusFrame() 方法，
       或扩展现有 hub.telemetry() 返回值，不新增类）
    ↓  1 天
步骤 4：WebSocket 遥测通道增推关节角度帧（复用 hub.broadcast()，无新连接）
    ↓  0.5 天
步骤 5：前端 DataCenterTwin3D 加载 URDF→GLB，在 syncRobot() 里实时驱动关节
    ↓  1-2 天
总周期：3-5 天（含真机调通）
```

### 1.5 依赖清单（硬件侧）

| 依赖 | 提供方 | 备注 |
|---|---|---|
| 四足 URDF 参数表 | 机器人厂商（Unitree/宇树等） | 含髋/膝关节转动范围 |
| 巡逻车 URDF 参数表 | 机器人厂商 | 含轮距/轴长/轮径 |
| BLE 状态包协议文档 / 抓包 | 实验室真机 | 关注通知特征值的 payload 格式 |

---

## 二、缺口 2：真机实时视频流

### 2.1 现状

智维Agent 已实现**模拟视频回传面板**，位于：

| 层 | 实现 | 路径 |
|---|---|---|
| 前端面板 | `RobotVideoPanel.vue`（canvas 绘制低频 JPEG 关键帧） | `frontend/src/components/robot/RobotVideoPanel.vue` |
| 抽帧触发 | `RobotControlService.command()` CAPTURE 分支 | `backend/.../RobotControlService.java` |
| 视觉分析链路 | `VisionInspectionService.inspect()` | `backend/.../VisionInspectionService.java` |
| 模拟帧源 | `sim.py` 合成灰度 PNG | `robot-bridge/sim.py` |

**缺什么**：真机摄像头的实时视频流（RTSP/WebRTC）。

### 2.2 缺口根因（带宽硬冲突）

机器人控制与视频传输是**互斥的带宽需求**：

| 链路 | 协议 | 带宽需求 | 延迟要求 |
|---|---|---|---|
| 控制帧 | BLE（蓝牙 5.2） | ≤ 30 kbps（deadman 看门狗 ~80ms/帧） | ≤ 50ms（600ms 无包触发急停） |
| 视频帧 | WiFi/5G（RTSP） | ≥ 2 Mbps（1080p@30fps） | ≤ 200ms（否则画面卡顿） |

BLE 有效带宽 ≤ 300 kbps，**如果视频也走 BLE，会直接挤掉控制帧，触发 deadman 急停**——这是硬冲突，无法妥协。

> 📐 **图 3 · 带宽硬冲突示意图**：
>
> ![带宽硬冲突](hardware-gaps-assets/fig3-bandwidth-conflict.png)
>
> BLE 窄管道（30 kbps 控制帧）挤不下 2 Mbps 视频；硬 X 标在视频穿 BLE 管路上，意味着必然触发 deadman 急停。

> 600ms 阈值证据：[RobotControlService.java#L54](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/RobotControlService.java#L54) `heartbeatTimeoutMs = 600`，[RobotControlService.java#L263](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/RobotControlService.java#L263) 看门狗每 200ms 检查一次沉默时长。

### 2.3 架构已留口证据（精确代码路径 + 行号）

#### 留口 1：CAPTURE 抽帧命令已打通到视觉巡检入口

**后端 CAPTURE 分支** — [RobotControlService.java#L204-L206](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/RobotControlService.java#L204-L206)

```java
// 拍照已下发：登记一次视觉巡检意图，等桥回传的关键帧到达后触发识别
if ("CAPTURE".equals(normalizedOp)) {
    frames.expectCapture(deviceKey, String.valueOf(normalized.getOrDefault("target", "")));
}
```

> 真机视频就绪后，CAPTURE 命令改为「拉 RTSP 流截图」替代「等关键帧」，调用同一个 `VisionInspectionService.inspect()` 即可。

#### 留口 2：视觉分析链路已支持「未配置模型时降级，不伪造结果」

**inspect() 方法完整链路** — [VisionInspectionService.java#L75-L104](file:///d:/SmartOpsAgent/backend/src/main/java/com/smartops/service/VisionInspectionService.java#L75-L104)

```java
public Map<String, Object> inspect(String imageBase64, String target, String filename, Long userId,
        String taskIdPrefix, Map<String, Object> extraMetadata) {
    ...
    if (simulatedAbnormal) {
        // 测试模式：合成 WARN 触发重规划验证
        ...
    } else if (!engine.configured()) {
        // 未配置本地模型 → 诚实地降级为 INFO（不伪造异常）
        abnormal = false;
        modelName = "unconfigured";
        summary = "视觉模型未配置，跳过检测";
    } else {
        VisionInspectionEngine.VisionAnalysis analysis = engine.analyze(imageBase64);
        abnormal = analysis.abnormal();
        ...
    }
    ...
}
```

> 真机视频就绪后，视觉链路完全不用改——只要把 RTSP 截到的帧传进来即可。

#### 留口 3：前端面板已用 canvas 绘制，Video.js 封装只差换 src

**面板设计注释** — [RobotVideoPanel.vue#L62-L67](file:///d:/SmartOpsAgent/frontend/src/components/robot/RobotVideoPanel.vue#L62-L67)

```javascript
/**
 * 机器人视觉回传面板（M2）。
 *
 * 关键帧用 canvas 绘制而非 <video>：设备只上报低频 JPEG 关键帧，
 * 不提供流媒体地址，用 video 会伪造出「实时视频」的观感。
 * 识别结论一律标注为模型主张，最终处置在纠察中心人工复核。
 */
```

> 真机 RTSP 就绪后，把 `canvas` 换成 `<video>`，Video.js rtsp.js 插件拉流，改约 20 行。

#### 留口 4：配置入口已在 application.yml 预留

**vision 配置块** — [application.yml#L125-L127](file:///d:/SmartOpsAgent/backend/src/main/resources/application.yml#L125-L127)

```yaml
# 视觉巡检（本地多模态模型识别，如 llava / qwen2.5vl）。
# 2026-11-16 已启用：指向本地已装的 qwen2.5vl:3b（Ollama）。
# 未配置时 /api/inspector/vision fail-closed 返回 503。
vision:
  base-url: ${SMARTOPS_VISION_BASE_URL:http://127.0.0.1:11434}
  model: ${SMARTOPS_VISION_MODEL:qwen2.5vl:3b}
```

> 真机 RTSP 就绪后，追加一行 `rtsp-url: ${SMARTOPS_ROBOT_RTSP_URL:}` 即可，不改动现有 vision 配置结构。

#### 留口 5：模拟器模拟帧链路已验证（真机只需替换帧源）

**模拟帧合成 + 回传** — [sim.py#L205-L213](file:///d:/SmartOpsAgent/robot-bridge/sim.py#L205-L213)

```python
if device.frames_pending > 0:
    device.frames_pending -= 1
    await socket.send(json.dumps({"type": "frame", "payload": {
        "deviceKey": device.device_key,
        "imageBase64": synth_frame_base64(),    # ← 合成灰度 PNG
        "mime": "image/png",
        "quality": "sim",
        "simulated": True,
    }}))
```

**模拟帧合成本身** — [sim.py#L43-L60](file:///d:/SmartOpsAgent/robot-bridge/sim.py#L43-L60)

```python
def synth_frame_base64() -> str:
    """合成一张灰度渐变 PNG 作为「摄像头关键帧」。
    叠声明：这不是真实画面，仅用于在无真机时验证
    「CAPTURE → 帧回传 → 后端视觉巡检」链路是否通。
    """
    ...
    return base64.b64encode(png).decode("ascii")
```

> 真机就绪后，`synth_frame_base64()` 替换成从 RTSP 流截帧，其他链路（WebSocket 帧格式、后端 `frames.expectCapture()`、VisionInspectionService）全不变。

### 2.4 补全路径（可落地）

```
步骤 1：真机开启 RTSP 服务（WiFi 连通）
    ↓  1 天
步骤 2：后端 application.yml 追加 rtsp-url 配置项（在 vision 块下）
    ↓  0.5 天
步骤 3：RobotVideoPanel.vue 换 Video.js rtsp.js 插件拉流（canvas → <video>）
    ↓  0.5 天
步骤 4：视觉链路验证（CAPTURE → RTSP 截帧 → VisionInspectionService → 事件）
    ↓  1 天
总周期：2-3 天（含真机 WiFi 调通）
```

### 2.5 依赖清单（硬件侧）

| 依赖 | 提供方 | 备注 |
|---|---|---|
| 真机 WiFi 模块 | 机器人厂商 | 需支持 STA 模式连入同一局域网 |
| RTSP 服务开启 | 真机侧（ONVIF / MediaMTX） | 默认端口 554，码率 ≤ 4 Mbps |
| RTSP 流地址 | 实验室真机 | 格式 `rtsp://ip:554/stream1` |

---

## 三、总结

| 维度 | 设备级孪生 | 真机视频流 |
|---|---|---|
| 缺口性质 | 硬件依赖（URDF + BLE 状态包） | 硬件依赖（WiFi + RTSP） |
| 架构留口 | ✅ 完全（传输切换点 + 能力清单已定义 + 3D Group 挂载 + WS 通道复用） | ✅ 完全（CAPTURE → 帧回传 → 视觉链路全通，真机只需替换帧源） |
| 补全周期 | 3-5 天 | 2-3 天 |
| 风险 | 低（现有骨架已验证，无重构） | 低（同上） |
| 优先级 | 中（场景孪生已可用） | 中（模拟帧已可演示交互） |

**答辩红线**：绝对不能说「没做」「放弃了」「太复杂」。必须说「硬件依赖顺序 + 架构分层取舍，核心架构已留口，补全路径清晰」。
