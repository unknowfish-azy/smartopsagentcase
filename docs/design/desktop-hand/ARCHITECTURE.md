# 桌面手（Desktop Hand）设计方案 v1

日期：2026-11-15
状态：设计定稿 / 待实施（计划见 `.trae/documents/桌面手-DH-01至DH-08实施计划.md`）
定位：给智维 Agent 一条 **UI 级兜底通道**——在没有 API 的老旧系统上"能看、能点、能打字"，且每一步都可证明。

---

## 0. 来源与证据（先划清哪些是看到的）

| 档位 | 内容 |
|---|---|
| **observed** | 视频标题：`【【开源】给 agent 一双真手：一个能看能点能打字的桌面 MCP】`；短链 `b23.tv/o1aLLle` 解析到 `bilibili.com/video/BV1hoWM6zEyB`。 |
| **observed** | 本项目 `agent/`、`ai-service/`、`tools/`、`scripts/` 全仓库检索：**不存在任何桌面控制实现**（无 pyautogui / pynput / pywinauto / mss / win32gui）。仅有 `scripts/e2e/ui_*.py` 三个 Playwright 脚本，是跑自己 Web UI 的端到端测试。 |
| **observed** | `agent/tools/` 已有统一 Tool 契约：`name` / `description` / `risk_level` / `requires_approval` / `execute()`（见 `agent/tools/server.py` 的 `ServerStatusTool`）。`agent/plugins/installed/robot/tools/fleet_submit.py` 证明插件式工具可挂载。 |
| **observed** | `ai-service/app/vision/` 已有 `grounding.py`（GroundingDINO 弱标注）、`screening.py`、`yolo26n.pt` 权重——**视觉定位能力已有，但只服务于离线标注，不在运行路径上**。 |
| **inferred** | 视频对应的仓库高度可能是 `pinzhuo0905-rgb/true-hands`：其描述 "An AI that really operates the computer — and can prove it. Built-in desktop driver, UI-only enforcement, project-scoped policy." 与标题「真手 true hands」+「能看能点能打字」完全对齐。**未证实**，需你确认或给我仓库链接。 |
| **unknown** | 视频内的具体实现、工具清单、演示场景。**浏览器抓取通道当前不可用**（Playwright provider 报 `execution_failure`，`raw.githubusercontent.com` 与 `api.github.com` 被 TLS 拦截），所以本文不冒充"逐帧还原"。 |

**因此本文的"精华蒸馏"来自：标题语义 + 同类开源项目的公开描述（true-hands / desktop-mcp / OmniParser / UI-TARS-desktop / desktop-hand / KiroCrew）+ 本项目现有架构。** 每一条精华我都标了它在真实仓库里的出处形态。

---

## 1. 蒸馏出的九条精华（每条都说明"为什么它值钱"）

| # | 精华 | 出处形态（公开描述级） | 为什么值钱 |
|---|---|---|---|
| 1 | **能看 = 截图转结构化元素树**，不是让模型看裸像素 | OmniParser 式"screen parsing"：解析出可交互元素 + 边框 + 语义标签 | 让模型输出**元素 id** 而不是坐标。坐标幻觉是纯像素方案的第一大死因 |
| 2 | **能点 = 点元素，不点坐标** | 元素 id → gateway 解析成真实坐标 | 模型不需要像素级精度，1.7B 也能胜任 |
| 3 | **能打字 = 先定位输入框 → 聚焦 → 键入 → 读回校验** | 输入类工具独立成组，默认关闭 | 打字是不可逆动作，必须可撤销/可验证 |
| 4 | **UI-only 强制** | true-hands 明确写 "UI-only enforcement" | 只能走 UI，不能绕过 UI 直连数据库/内部接口。**这是安全边界，也是审计边界** |
| 5 | **项目作用域策略** | "project-scoped policy" | 权限收敛到"某项目、某窗口、某进程"，不是"整台机器" |
| 6 | **可证明（can prove it）** | "and can prove it" | 每步 before/after 截图 + 元素 diff → 可回放的证据链。对应本项目「一本账」 |
| 7 | **薄壳 + 网关，不是把控制逻辑塞进 MCP** | KiroCrew 的 `mcp_computer.py` 自述 "a THIN SHIM over the gateway" | MCP 层只管协议，策略与执行在网关。这样才能换协议不换策略 |
| 8 | **工具分组按配置开关，输入类默认关** | desktop-mcp："Config-gated tool groups, input off by default" | 默认安全。装上不等于能用，要显式开 |
| 9 | **只有人才能恢复** | desktop-hand："只有人才能执行 `/desktop-hand resume`" | 急停之后 Agent 自己不能解除急停。这条是硬边界 |

---

## 2. 为什么要给智维 Agent 装这只手（以及它不该替代什么）

**要**：你的知识库里已经明确覆盖「无 API 的老旧系统」「现场拍屏」「CMDB 缺失」这类场景（`cli 与 legacy 系统`、视觉识别那几项）。这些场景下 `agent/tools/shell.py` 一点用没有——shell 到不了 GUI。

**不要替代**：这只手是**兜底**，不是主路。优先级永远是：

```
API / 工具调用（现有 tools/*）  >  CLI（tools/shell.py）  >  UI 操作（本方案）
```

理由：UI 操作最慢、最脆、最难审计。**能走 API 绝不走 UI。** 这条要写进 planner，不能靠自觉。

---

## 3. 架构

```
┌──────────────────────────────────────────────────────────────────┐
│ 决策层  agent/planner/react_agent.py（已有，不动）                │
└───────────────────────────┬──────────────────────────────────────┘
                            │ 工具调用：desktop.*
┌───────────────────────────▼──────────────────────────────────────┐
│ 工具面  agent/tools/desktop.py（新增，实现现有 Tool 契约）        │
│   感知：desktop.observe   打字：desktop.type   点击：desktop.click │
│   按键：desktop.key       窗口：desktop.focus_window              │
│   risk_level="HIGH"  requires_approval=True（输入类）             │
└───────────────────────────┬──────────────────────────────────────┘
                            │ 只传 element_id / window_id，不传坐标
┌───────────────────────────▼──────────────────────────────────────┐
│ 网关  agent/desktop/gateway.py（新增，唯一有策略的地方）           │
│   ① 窗口白名单 ② 禁入区 ③ 动作预算 ④ 限速 ⑤ 急停锁 ⑥ 审批闸       │
│   接既有：agent/safety/approval.py、agent/policies/permission.py  │
└───────────────────────────┬──────────────────────────────────────┘
                            │ 已授权的原生动作
┌───────────────────────────▼──────────────────────────────────────┐
│ 驱动  agent/desktop/driver.py（新增，唯一碰系统 API 的地方）       │
│   Windows: pywinauto / uiautomation（UIA 树）+ pyautogui 兜底      │
└───────────────────────────┬──────────────────────────────────────┘
                            │ 截图 + 元素树
┌───────────────────────────▼──────────────────────────────────────┐
│ 感知  ai-service 新增 /api/nn/desktop-perceive                    │
│   复用 ai-service/app/vision/grounding.py 的模型（本地，不出机器）│
│   输出：可交互元素列表 [{element_id, role, name, bbox, enabled}]  │
└───────────────────────────┬──────────────────────────────────────┘
                            │ UiActionReceipt
┌───────────────────────────▼──────────────────────────────────────┐
│ 证据  agent/recovery_contracts 的同规则 digest + 截图落盘         │
│   每步：before_shot_digest / after_shot_digest / element_diff     │
└──────────────────────────────────────────────────────────────────┘
```

**四条分层铁律**（违反任何一条，这套东西就不能上生产）：
1. **只有 `driver.py` 允许 import 系统控制库。** 其他层一律通过它的抽象接口。
2. **只有 `gateway.py` 允许做策略判断。** 工具面不许自己判"这个能不能点"。
3. **LLM 只产出 `element_id`，永不产出坐标。** 坐标在 driver 内部解析。
4. **感知默认本地**。截图可能含敏感信息（工单号、IP、客户名），**默认不出机器**；要用云 VLM 必须显式配置且逐次记录。

### 3.5 部署形态与隧道（2026-11-19 决策）

**结论：driver 永远是「只监听 127.0.0.1 的 HTTP/JSON 小服务」，部署位置变、寻址方式变，driver 本身不变。**

这也是平台问题的解法：`agent/desktop/` 的契约层与门禁层（models / element_id / policy / gateway）**零系统依赖**，在阿里云 Linux 上照常导入；只有 driver 是 Windows 专属，跑在被控端。

```
模式一（agent 与本机同网）：agent ──TCP──> 局域网 Windows:9222/driver

模式二（agent 在阿里云）：
  Windows:9222 ──ssh -R 127.0.0.1:19222──> 阿里云 sshd
  阿里云 agent ──HTTP──> 127.0.0.1:19222（只绑 loopback，公网不可见）
```

| 项 | 决策 |
|---|---|
| 隧道类型 | **SSH 反向转发（`ssh -R`）**，非自建 WebSocket |
| 每机隧道数 | **每台被控端各建一条**，端口隔离，一台出事不影响其他机器 |
| 云端改动 | **零**。只需 sshd，不动 Spring Boot，不新建鉴权体系 |
| 端口规划 | `19200 + index`，必须维护 `machine_id → 端口` 注册表，禁止动态抢占 |
| 被控端服务化 | WinSW / NSSM 包成 Windows 服务，开机自启 + 断线重启 |
| 心跳参数 | `ServerAliveInterval=30 ServerAliveCountMax=3 ExitOnForwardFailure=yes`；云端在 `transport.is_active()` 之上加一层探测（逻辑同 `ssh_tunnel_tool/tunnel.py` 的 monitor loop） |

**上线前必须实测（不许靠默认值）**：
1. 阿里云 `sshd -T` 输出 `allowtcpforwarding yes` 且 `gatewayports no`；
2. 被控端出网 22 可达（只通 443 则本方案不成立，须改 WSS，届时另立设计）；
3. `ssh -R` 后被控端口在云上是 `127.0.0.1:19222` 而非 `0.0.0.0`。

**三条红线（与 §4 同级，不可配）**：
1. **禁止 `-D` 动态转发（SOCKS）**——等于把内网借给云，隧道只允许点对点；
2. driver **只绑 `127.0.0.1`**，不得监听 `0.0.0.0`；
3. 每个请求带**每机独立 token**，token 不进 driver 的日志。

**与铁律 3 的关系**：隧道上只跑 `window_id` / `element_id`，`element_id → bbox` 的解析始终发生在 driver 内部（被控机）。**坐标永不过网**，这是"远程"与"本地"两种形态共用同一套契约的原因。

**云端客户端（DH-09）**：`agent/desktop/driver_http.py::HttpDriver`。
- 构造即校验：`base_url` 非 loopback、非 `http`、缺端口、空 token 一律 `ValueError`；
- 配置走 `DESKTOP_HAND_DRIVER_URL` / `DESKTOP_HAND_DRIVER_TOKEN`（`SMARTOPS_` 前缀兜底），
  一台机器一个 index、一个 token，云端端口 = `19200 + index`（注册表 `docs/desktop_hand/machine_ports.csv`）；
- `driver_from_env()`：有远程地址即用 `HttpDriver`，否则回退本机 `WindowsDriver`，都没有返回 `None`；
- 被控端仍由 `driver_service.py` 提供 HTTP 入口，两侧协议由 `tests/desktop/test_driver_http.py` 做真两端回归。

---

## 4. 六类风险与对应门禁（这是本方案的核心，不是附录）

桌面控制的危险程度 ≈ shell，但**更难审计**（shell 有命令行，UI 只有像素）。所以门禁必须比 shell 更严。

| 风险 | 具体形态 | 门禁 |
|---|---|---|
| **R1 代签授权** | Agent 点了「同意」「确认支付」「接受条款」 | **绝对禁止**：命中确认类文案（同意/确认/允许/授权/支付/签署）的元素，一律拒绝并上报。这条不给开关 |
| **R2 逃逸到 shell** | 通过点击"打开终端"、任务管理器、注册表编辑器获得更高权限 | **禁入区**：窗口标题/进程名命中 `cmd/powershell/terminal/regedit/taskmgr/mmc/控制面板` 一律拒绝 |
| **R3 越界窗口** | 操作了不该碰的窗口（别人的 IM、浏览器标签、生产后台） | **窗口白名单**：必须显式登记 `{进程名, 窗口标题正则, 允许的元素角色}` |
| **R4 无限动作** | 死循环点击把系统点坏 | **动作预算**（默认 50 步/会话）+ **限速**（默认 ≥300ms/动作）+ 连续 3 次同元素点击 → 强制停 |
| **R5 急停失效** | 出事后停不下来 | **全局热键**（默认 `Ctrl+Alt+Shift+F12`）→ 暂停并锁定；**只有人**能恢复（精华 9） |
| **R6 证据缺失** | 事后说不清做了什么 | 每步必产 `UiActionReceipt`；截图缺失 → 该步判为**未验证**，不得计入成功 |

**默认姿态**：安装后 `input` 组（click/type/key）**关闭**，只有 `observe`（只读截图+元素树）可用。要开输入组必须改配置 + 人工确认。这直接照搬 desktop-mcp 的 "input off by default"。

---

## 5. 数据契约

```python
# agent/tools/desktop.py 依赖的模型（放进 agent/desktop/models.py）

class UiElement(BaseModel):
    element_id: str            # 稳定 id：hash(window_id + role + name + bbox)
    role: str                  # button / edit / link / tabitem ...
    name: str                  # 可读名（UIA Name 或 OCR 文本）
    bbox: tuple[int, int, int, int]
    enabled: bool
    is_destructive: bool       # 由 gateway 按文案词典标注，不由模型判

class UiObservation(BaseModel):
    window_id: str
    window_title: str
    process_name: str
    shot_digest: str           # sha256:<64hex>
    captured_at: datetime
    elements: list[UiElement]
    truncated: bool            # 元素超上限时为 True，禁止在截断树上做危险动作

class UiActionReceipt(BaseModel):
    run_id: str
    step: int
    action: Literal["click","type","key","focus_window"]
    target: dict               # {window_id, element_id} —— 绝不含坐标
    before_shot_digest: str
    after_shot_digest: str | None
    element_diff: dict         # {appeared:[...], disappeared:[...], changed:[...]}
    verdict: Literal["VERIFIED","UNVERIFIED","REJECTED"]
    reject_reason: str | None  # R1..R6 之一
```

**三条硬规则**（沿用 recovery-contract 的纪律）：
1. `truncated=True` 时，`click/type` 一律拒绝（看不见全貌就别动手）。
2. `after_shot_digest` 缺失 → `verdict="UNVERIFIED"`，**不得**按成功计。
3. `digest` 用 `ai-service/app/core/canonical.py::canonical_digest`（DS-01 产出的同一实现），**不许另写一套**。

---

## 6. 开源 / 闭源 方案盘点

### 6.1 开源（许可证**逐项待核验**，按 MASTER.md 的 Open Source Intake 执行）

| 项目 | 形态 | 值得偷的点 |
|---|---|---|
| [pinzhuo0905-rgb/true-hands](https://github.com/pinzhuo0905-rgb/true-hands) | 桌面驱动 + UI-only 强制 + 项目作用域策略 | **最贴近视频主题**；"UI-only enforcement" 与"can prove it" 两条直接采用 |
| [jaimenbell/desktop-mcp](https://github.com/jaimenbell/desktop-mcp) | Windows 桌面控制 MCP：截图/窗口/键鼠/录屏，工具分组可配置 | **工具分组 + input 默认关** 的设计照搬 |
| [microsoft/OmniParser](https://github.com/microsoft/OmniParser) | 屏幕解析：纯视觉 GUI Agent 的元素识别 | **感知层的参考实现**；你已有 `grounding.py` 可对接 |
| [bytedance/UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop) | VLM 驱动的 GUI Agent 应用 | 端到端交互组织方式；注意它是 VLM 重方案，你 1.7B 尺度不适合抄推理 |
| [Zero20230619/desktop-hand](https://github.com/Zero20230619/desktop-hand) | 「桌面操控手」 | **只有人才能 `/resume`** 的急停模型照搬 |
| [mikamikasuki/KiroCrew](https://github.com/mikamikasuki/KiroCrew)（`src/kiro_crew/mcp_computer.py`） | 自述 "a THIN SHIM over the gateway" | **薄壳 + 网关**的分层方式照搬 |
| [polease/agent-tars](https://github.com/polease/agent-tars) | 基于 UI-TARS 的 GUI Agent | 任务编排层参考 |
| `realhands` / computer-use-mcp（PyPI） | MCP 形态的 computer-use 工具集 | 工具命名与参数形态参考 |
| Playwright MCP / Browser Use | **浏览器域**的同类能力 | 你已有 Playwright，Web 侧别重复造 |

### 6.2 闭源（只做对照，不引入）

| 产品 | 形态 | 借鉴点 |
|---|---|---|
| Anthropic Computer Use | 截图→动作循环的行业范式 | 工具三件套 `screenshot / click / type` 的最小集 |
| OpenAI Operator / CUA | 云端托管 GUI 操作 | 强隔离执行环境（你在本地则对应沙箱） |
| Google Project Mariner | 浏览器域自动化 | 作用域与用户确认交互 |
| Microsoft Copilot Studio computer use | 企业内托管 | 与企业权限体系对齐的方式 |
| UiPath / Automation Anywhere | 传统 RPA | **元素选择器 + 重试 + 可回放录制**，这三样 RPA 已经做了二十年，比多数新项目扎实 |

**结论**：不要把闭源方案当依赖（数据出机器、审计断链），但**RPA 的元素选择器与录制回放思想必须吸收**——这正是「can prove it」的成熟解法。

---

## 7. 与既有体系的接线（不新建任何体系）

| 既有机制 | 怎么接 |
|---|---|
| `agent/tools/` Tool 契约 | `desktop.*` 直接实现 `name/risk_level/requires_approval/execute`，进 `tool_registry` |
| `agent/security_baseline/redlines.py` | 禁入区（R2）与代签禁止（R1）注册为红线规则 |
| `agent/safety/approval.py` | 输入类动作走人工审批；`risk_level="HIGH"` |
| `agent/policies/permission.py` | 窗口白名单即 permission scope 的一种 |
| `agent/recovery_contracts/` | `UiActionReceipt` 与 `VerificationReceipt` 共用 digest 规则与存储 |
| `ai-service/app/vision/grounding.py` | 感知层复用其模型；新增 runtime 端点而非改离线脚本 |
| `agent/planner/react_agent.py` | 加一条路由优先级：API > CLI > UI（§2） |

---

## 8. 验收

| 编号 | 判据 | 验证方式 | 结论（2026-11-19） |
|---|---|---|---|
| H1 | 输入组默认关闭；未开启时 `desktop.click` 返回明确拒绝而非静默失败 | 单测 | 通过：`test_gateway.py`（拒绝码 `INPUT_GROUP_DISABLED`） |
| H2 | R1 代签：构造"确认支付"按钮的观测，`click` 必须被拒且记 `reject_reason="R1"` | 单测（仿真 UIA 树） | 通过：`test_gateway.py` |
| H3 | R2 禁入区：`cmd.exe` / `regedit` 窗口一律拒绝 | 单测 | 通过：`test_gateway.py` |
| H4 | R3 窗口白名单：非登记窗口的操作被拒 | 单测 | 通过：`test_gateway.py` |
| H5 | R4 预算/限速：第 51 步被拒；同元素连续 3 次点击触发停 | 单测 | 通过：`test_gateway.py` |
| H6 | R5 急停：热键后所有动作拒绝，且 Agent 无法自行恢复 | 手工 + 单测（模拟恢复调用被拒） | 部分：单测通过（R5 锁定、恢复需一次性 token）；真机热键尚未按手册实测 |
| H7 | R6 证据：每步产 receipt；缺 after 截图 → `UNVERIFIED` | 单测 | 通过：`test_receipts.py` |
| H8 | 元素 id 稳定性：同窗口同元素两次观测 id 相同；元素消失后 id 不复用 | 单测 | 通过：`test_models.py`（同属性 id 稳定；换窗 / 位置 / 角色 id 必变） |
| H9 | `truncated=True` 时 click/type 全拒 | 单测 | 通过：`test_gateway.py` |
| H10 | digest 与 `canonical_digest` 一致（同一输入跨模块相同） | 单测 | 通过：`test_receipts.py::test_digest_与_ai_service_canonical_一致` |
| H11 | 真机冒烟：在**记事本**上完成"打开→输入一行字→读回校验"，全程有 receipt | 手工，仅记事本，不碰生产 | 通过：四步全绿（observe 40 个元素、type VERIFIED 且 UIA 回读通过、Ctrl+S 落盘校验通过、Ctrl+W 关闭）；3 个输入回执均 VERIFIED，证据在 `agent/desktop/shots/smoke-notepad`（运行态不入库） |
| H12 | UI 失败不污染主链路：桌面手异常时 planner 能回落到 API/CLI 路径 | 集成测试 | 通过（单测）：`test_planner_tool_priority.py` 证明 planner 不自动降级，desktop 报错作为 Observation 喂回；真实 API 联调未跑 |

---

## 9. 明确不做（避免做成四不像）

1. ❌ **不做纯坐标点击**（`click(x, y)`）。只接受 `element_id`。
2. ❌ **不做全屏自由操作**。必须窗口白名单。
3. ❌ **不做"自动同意/自动确认"**。这条没有配置开关。
4. ❌ **不做云 VLM 默认路径**。截图默认不出机器。
5. ❌ **不做无人值守长跑**。默认需要人盯，急停必须物理可达。
6. ⚠️ **多机纳管做，远程桌面不做**（2026-11-19 修订）。多台 Windows 被控端按 §3.5 各建一条 SSH 反向隧道纳管；但 **RDP/VNC/X11 的桌面画面共享仍不做**——那是人看屏幕，不是 Agent 操作控件，且已被 `remote-connections-enhance-v1` 定为 `REQUIRES_NATIVE_BRIDGE`。两者别混。
7. ❌ **不碰生产环境**。首个落地目标只能是**老旧内部系统 / 测试环境 / 演示环境**。

---

## 10. 实施进度（2026-11-19 DH-01→DH-08 交付）

### 已决（DH 系列全部落地）

| 编号 | 内容 | 交付 | 实测结论 |
| --- | --- | --- | --- |
| DH-01 | 契约层 | `agent/desktop/models.py` + `element_id.py` | AST 分层自检在 pytest 里绿 |
| DH-02 | 门禁层 | `policy.py` + `gateway.py` | R1~R6 六道门禁固定顺序，112 passed |
| DH-03 | 驱动 | `driver.py` + `driver_windows.py` + `driver_service.py` + `requirements-driver.txt` | WindowsDriver.available/probe/list_windows 实测可用；UIA 枚举在 pytest 进程里会阻塞，已改成 available 只查 import、probe 才查实时 |
| DH-04 | 感知端点 | `ai-service/app/services/desktop_perceive.py` + `api/desktop_perceive.py` + `/api/nn/desktop-perceive` | 13 个端点测试过；GroundingDINO 懒加载，缺依赖时返回 `available=false` 而非 500；elapsed_ms 必填 |
| DH-05 | 工具面 | `agent/tools/desktop.py`（6 工具） + `registry.register_desktop_tools` | 17 个工具测试过；schema 无坐标；输入组默认关 |
| DH-06 | 证据链 | `receipts.py` + `ShotStore` + `DesktopReceiptLog` + 账本自校验 | 12 个证据测试过；digest 算法与 DS-01 共享；REJECTED receipt 允许 before=None（总开关未启用） |
| DH-07 | 路由优先级 | `agent/tools/priority.py` + `react_planner._build_catalog` 按 API>CLI>UI 分组 + SYSTEM_PROMPT 明确写优先级 | 12 个路由测试过；**planner 不做自动降级**——API 调用报错不会自动切 desktop，报错 Observation 喂回让 LLM 自己决定 |
| DH-08 | 默认关 + 冒烟 | `DesktopPolicy.from_env` + `desktop_hand_enabled()` + `DesktopGateway(enabled=False)` + `.env.example` 三变量 + `smoke_notepad.py` | 默认 `DESKTOP_HAND_ENABLED=false`、`INPUT_GROUP=false`；单测全绿；真机冒烟四步全绿（见 §8 H11） |
| DH-09 | 远程 driver 客户端 | `driver_http.py`（`HttpDriver` + `driver_from_env`） + `desktop_hand_tunnel.ps1` + `docs/desktop_hand/machine_ports.csv` | 19 个真两端测试（loopback/token/坐标/协议往返）；非 loopback 地址构造即拒；隧道脚本 `probe/start/status/stop` 就绪 |
| DH-10 | UIA 枚举硬化 | `driver_windows.py`：`list_windows` 改 Win32 `EnumWindows`（13 个窗口 0.5s），UIA 只在 `_window` 里按句柄直连；`set_focus` 改 Win32 `SetForegroundWindow` | 解决了 DH-08 冒烟的全局阻塞：桌面里任一 UIA provider 卡死会让 `Desktop.windows()` 挂起 >30s；改造后冒烟四步全绿 |

### 未决（保留）

1. **true-hands 仓库未证实**（视频 `BV1hoWM6zEyB` 对应的仓库）。若你给我链接，我可以把它的工具清单与本文 §3 逐项对齐。
2. ~~**真机冒烟完整通过**~~：已通过（2026-11-19，H11 见 §8）。四步均在记事本上完成，无需再补。
3. **SSH 反向转发实测**：脚本与云端客户端已就绪（DH-09），仍需在阿里云真机核 §3.5 的三项：`sshd -T`、被控端出网 22、云端只绑 `127.0.0.1:192XX`。
4. **性能预算**：一次 observe（截图+UIA 枚举）延迟实测目标 <800ms。grounding.py 视觉感知额外延迟取决于模型加载，首次 700MB 权重下载不计。远程形态还应加上隧道 RTT（同机房实测量级 1–3ms，跨公网另计）。

---

## 11. 一句话总结

这只手真正的价值不是"能点"，而是**「做了什么都留得下证据，且它只能看见你允许它看见的那一个窗口」**。

能给 Agent 一双真手的项目很多；能让运维敢把生产环境交出去的，靠的是 §4 那六道门禁和 §5 那份 receipt。
**没有门禁的桌面控制在运维场景里不是能力，是事故源。**
