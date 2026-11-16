# 远程连接中心实用性增强（对标 MobaXterm / FinalShell）v1

- 日期：2026-11-16
- 状态：**已执行**（用户指令：设计好方案然后执行）
- 唯一口径：本文档。

## 0. 背景与对标结论

用户给出 MobaXterm（开源 Home Edition）与 FinalShell（免费闭源）两个桌面远程工具作参照，要求把项目「连接中心」（`/operations/connections`，SmartOps Remote）的实用性补强。

现状盘点（全部为真实实现，非占位）：
- 后端：Apache MINA SSHD（`SshConnectionAdapter`），SSH 会话/跳板/SFTP/本地端口转发/主机钥匙管理/批量执行（审批制）/Agent 只读上下文。
- 前端：会话树、xterm.js 终端（WebSocket 桥）、远程文件、隧道面板、分屏、多会话 tab。

对标差距分析（按实用性排序）：

| 对手功能 | 本项目现状 | 决策 |
| --- | --- | --- |
| FinalShell 实时服务器监控（CPU/内存/网络/磁盘/负载） | 无 | ✅ W1+W2 采用：SSH runtime `execute()` 真采样 |
| MobaXterm 会话日志录制（log sessions） | 输出仅存 xterm 5000 行滚动缓冲，无法留档 | ✅ W3 采用：前端录制真实 OUTPUT 流导出 .log |
| MobaXterm macros / 命令片段 | 无 | ✅ W4 采用：片段库 + 一键回填/执行 |
| 隧道编辑交互 | `window.prompt/alert`，可用性差 | ✅ W5 升级：表单对话框 + 日志抽屉 |
| X11 / RDP / VNC / MOSH | `REQUIRES_NATIVE_BRIDGE` | ❌ 不做：Web 内无法诚实实现，禁伪造红线 |
| 凭据管理器（密钥库） | connect 时传 secret | ❌ 暂不做：涉密钥持久化安全边界，另行裁决 |
| 多重执行 / SFTP 文件管理 | 已有且质量更高（审批制） | 不重复造 |

## 1. 关键设计约束（红线）

- **监控数据全部来自真实采样**：单次 `execute()` 内完成（双采样 /proc/stat 算 CPU%，间隔 0.4s），解析失败/命令失败 → `supported:false + reason`，前端显示原因并停止轮询，**不编造数字**。
- **无事件静默**：面板只在 runtime 在线时轮询；断线/卸载即停；采样失败连续 3 次自动停并提示。
- **片段默认只回填不执行**：回填 = 把命令文本写入终端输入（不含换行），用户自己按回车；「直接执行」需 `window.confirm` 二次确认后才追加 `\r`。
- **录制是真实流**：录的是写进 xterm 的原始 OUTPUT（含 ANSI 转义原样落盘），文件名带会话名与时间戳。
- 监控端点走 `OperationRuntimeRegistry.requireOwned(runtimeId, userId)`，与文件端点同款鉴权。

## 2. 工作包

- **W1 后端**：`ServerMonitorSampleParser`（纯静态解析）+ `ServerMonitorService`（采样编排）+ `OperationMonitorController`（GET `/api/operations/runtimes/{runtimeId}/monitor`）+ JUnit。
- **W2 前端监控**：`getRuntimeMonitor` API + `serverMonitor.js` 纯函数（速率/历史封顶/字节格式化）+ `useServerMonitor` 轮询 composable + Inspector 监控区（条形 + Canvas 2D 迷你趋势，仅数据更新时重绘，reduced-motion 天然安全）。
- **W3 录制**：`OperationsTerminal` 头部加 录制/停止/导出 三态按钮 + 已录制字节计数。
- **W4 片段库**：`terminalInputBus.js`（runtimeId→send 注册表）+ `snippetStore.js`（localStorage 校验/封顶 50 条，纯函数可测）+ `SnippetsDialog.vue` + 工具栏入口（无 runtime 禁用）。
- **W5 隧道 UX**：composable 状态 `tunnelForm` / `logsFor`，TunnelWorkspace 内表单对话框 + 日志抽屉，删除 prompt/alert。
- **W6 门禁**：mvn test、npm test/typecheck/lint/build、浏览器实测（mock 采样）、a11y、本文档回填结果。

## 3. 采样命令（单次 execute，≈0.5s）

```sh
echo ===STAT1; head -1 /proc/stat; echo ===LOAD; cat /proc/loadavg; echo ===MEM; head -5 /proc/meminfo; echo ===DISK; df -kP / | tail -1; echo ===NET; cat /proc/net/dev; sleep 0.4; echo ===STAT2; head -1 /proc/stat
```

- CPU% = STAT1→STAT2 各列 delta（除 idle/iowait 外为 busy），越界钳制 0–100。
- 网络：`/proc/net/dev` 各接口字节求和（排除 lo），速率由前端相邻两次采样 diff 得出。
- 磁盘：`df -kP /`（POSIX 兼容输出）取根分区。
- 负载：loadavg 前 3 列。

## 4. 风险与边界

- `execute()` 走 exec 通道，命令经远端 shell 解析，`;`/管道可用；个别受限 shell（rbash）可能失败 → 诚实报 `supported:false`。
- Windows 目标无 /proc → 同上，不降级伪造。
- 轮询默认 3s、可切 5/10s；每轮 1 次 execute，开销与 FinalShell 同级。
- 历史封顶 60 点，Canvas 重绘仅在采样到达时发生。

## 5. 执行记录（2026-11-16 W6 已收口）

**新增文件**
- 后端：`operations/ServerMonitorSample.java`（含 `toView()`）、`operations/ServerMonitorSampleParser.java`（纯静态解析）、`operations/ServerMonitorService.java`（采样编排）、`controller/OperationMonitorController.java`（GET `/api/operations/runtimes/{runtimeId}/monitor`）、`test/.../ServerMonitorSampleParserTest.java`（5 条）。
- 前端：`operations/serverMonitor.js`（速率/历史/格式化/Canvas 迷你趋势）、`composables/useServerMonitor.js`（轮询：3/5/10s 可调、在线才轮询、连续 3 次失败自动停并诚实报错）、`operations/terminalInputBus.js`（终端输入注册表）、`operations/snippetStore.js`（localStorage 片段库，封顶 50）、`operations/SnippetsDialog.vue`、`test/server-monitor.test.mjs`+`snippet-store.test.mjs`+`terminal-input-bus.test.mjs`（10 条）。

**改动文件**
- `ConnectionInspector.vue`：新增「实时监控」区（五项条形 + 迷你趋势 + 档位切换；仅采样到达时重绘，reduced-motion 天然安全；Windows/受限 shell 目标诚实显示"不支持采样：原因"）。
- `OperationsTerminal.vue`：头部加 录制/停止/导出（真实 OUTPUT 流原样落盘，含 ANSI），显示已录制大小；注册终端输入总线。
- `ConnectionTerminalWorkspace.vue`：工具栏加「命令片段」入口（无在线终端禁用）；隧道面板接入表单/日志抽屉 props。
- `TunnelWorkspace.vue`：`window.prompt/alert` 全部替换为表单对话框（创建/编辑）+ 日志抽屉。
- `useConnectionsWorkspace.js`：`tunnelForm`/`logsFor` 状态机替代 prompt/alert 流。
- `api/operations.ts`：`getRuntimeMonitor`。

**门禁实测**
- 后端：`mvn test` **869/0 失败/1 跳过**（含解析器 5 条：真实 /proc 输出、CPU 双采样钳制与回绕拒绝、分区缺失仍部分支持、畸形网卡计数跳过）。
- 前端：typecheck 0、lint 0 error、build 通过；新增纯函数测试 10/10 + 既有相关 20/20。
- 浏览器实测（专用 dev server，mock REST + 假 WS 走真实 INPUT 通道）：
  - 监控面板：五项条形 + 数值 + 趋势线 + 档位切换渲染正确；
  - 录制：录制→OUTPUT→停止→导出 `.log`（文件名 `web-01-<时间戳>.log`）；
  - 片段：添加→回填**不带换行**→执行（confirm 后）**带 `\r`**，经真实 INPUT 通道；
  - 隧道：表单创建→表格出现→LOG 抽屉显示；
  - 0 page error。截图 `test-artifacts/ops-monitor-panel.png`。

**实现坑（3 个）**
1. Playwright `waitForFunction(fn, {timeout})` 的第二参是 **arg 不是 options**——超时全部变成默认 30s，误导排障半小时。
2. mock 路由 glob 必须兼容 query 串：`'**/api/operations/sessions/7/connect'` 匹配不到带 `?decision=NONE` 的真实请求 → 落到真后端 401 → 触发全局 `smartops:unauthorized` 被踢到登录页。尾通配 `connect*` 解决。
3. 录制中「导出」按钮按设计禁用（`|| recording`），脚本必须先停止再导出，否则 click 卡在等按钮可用。

**并行协作记录**：TRAE 于 17:48 进一步整合导航（insights 并入新顶级组「智能仓库」，注释确认沿用 `?view=milestones` 方案），波及 5 条导航测试；其中我方战报断言已适配"两组均不单列"的更强语义，其余 4 条为 TRAE 自身 WIP 测试与数据的进行中状态，未代改。

**遗留（未做，按 DESIGN 第 0 节决策）**：X11/RDP/VNC/MOSH（Web 内无法诚实实现）、凭据管理器（涉密钥持久化安全边界，另行裁决）。
